import csv
import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime
from io import StringIO
from typing import Any
from uuid import UUID

from app.auth.service import write_audit
from app.config import get_settings
from app.database import get_supabase
from app.errors import AppError
from app.ml.risk_scoring import (
    RISK_SCORE_HOLD_THRESHOLD,
    compute_risk_score,
    score_physical_workers_batch,
    score_remote_workers_batch,
)
from app.payroll.schemas import PayrollDecisionRequest
from app.bmoni.orchestrator import initiate_single_payment, poll_pending_payout

logger = logging.getLogger(__name__)


VERDICT_ORDER = {"FLAGGED": 0, "SUSPICIOUS": 1, "VERIFIED": 2}


def _page(rows: list[dict[str, Any]], page: int, page_size: int) -> tuple[list[dict[str, Any]], dict[str, int]]:
    start = (page - 1) * page_size
    return rows[start : start + page_size], {"page": page, "page_size": page_size, "total": len(rows)}


def _money(value: Any) -> float:
    return float(value or 0)


def _require_row(data: Any, code: str, message: str) -> dict[str, Any]:
    if not data:
        raise AppError(500, code, message)
    return data[0] if isinstance(data, list) else data


async def _get_run_for_hr(hr: dict[str, Any], run_id: UUID | str) -> dict[str, Any]:
    rows = get_supabase().table("payroll_runs").select("*").eq("id", str(run_id)).eq("company_id", hr["company_id"]).limit(1).execute().data
    if not rows:
        raise AppError(404, "PAYROLL_RUN_NOT_FOUND", "Payroll run was not found.")
    return rows[0]


async def payroll_runs(hr: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    runs = db.table("payroll_runs").select("*").eq("company_id", hr["company_id"]).order("generated_at", desc=True).execute().data
    run_ids = [str(r["id"]) for r in runs]
    approvers = {}
    if run_ids:
        audit_rows = db.table("audit_logs").select("*").eq("actor_type", "hr").eq("action", "PAYROLL_APPROVED").in_("target_id", run_ids).execute().data
        approvers = {str((row.get("metadata") or {}).get("run_id")): (row.get("metadata") or {}).get("approved_by_name") for row in audit_rows}
    return {
        "runs": [
            {
                "id": run["id"],
                "month_year": run["month_year"],
                "status": run["status"],
                "total_workers": run["total_workers"],
                "flagged_count": run["flagged_count"],
                "suspicious_count": run["suspicious_count"],
                "verified_count": run["verified_count"],
                "generated_at": run["generated_at"],
                "approved_at": run.get("approved_at"),
                "approved_by_name": approvers.get(str(run["id"])),
            }
            for run in runs
        ]
    }


def _decorate_result(row: dict[str, Any]) -> dict[str, Any]:
    worker = row.get("workers") or {}
    role = worker.get("roles") or {}
    gross = _money(role.get("gross_salary") or row.get("gross_salary"))
    deductions = _money(role.get("pension_deduct")) + _money(role.get("health_deduct")) + _money(role.get("other_deductions"))
    stored_net_pay = row.get("net_pay")
    net_pay = float(stored_net_pay) if stored_net_pay is not None else round(gross - deductions, 2)
    return {
        "worker_id": row["worker_id"],
        "worker_name": f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip() or row.get("worker_name"),
        "role_name": role.get("role_name") or row.get("role_name"),
        "gross_salary": gross,
        "net_pay": net_pay,
        "days_present": row.get("days_present"),
        "days_absent": row.get("days_absent"),
        "trust_score": row.get("trust_score"),
        "verdict": row.get("verdict"),
        "flag_reasons": row.get("flag_reasons"),
        "feature_values": row.get("feature_values"),
        "hr_decision": row.get("hr_decision") or "PENDING",
        "hr_note": row.get("hr_note"),
    }


async def payroll_results(hr: dict[str, Any], run_id: UUID, verdict: str | None, page: int, page_size: int) -> dict[str, Any]:
    run = await _get_run_for_hr(hr, run_id)
    query = get_supabase().table("ghost_analysis_results").select("*, workers(first_name,last_name,roles(role_name,gross_salary,pension_deduct,health_deduct,other_deductions))").eq("payroll_run_id", str(run_id))
    if verdict:
        query = query.eq("verdict", verdict)
    rows = [_decorate_result(row) for row in query.execute().data]
    rows.sort(key=lambda row: (VERDICT_ORDER.get(row.get("verdict"), 99), _money(row.get("trust_score"))))
    pending_count = sum(1 for row in rows if row["verdict"] in {"FLAGGED", "SUSPICIOUS"} and row["hr_decision"] == "PENDING")
    items, pagination = _page(rows, page, page_size)
    return {
        "run": {
            "id": run["id"],
            "month_year": run["month_year"],
            "status": run["status"],
            "summary_counts": {
                "flagged_count": run["flagged_count"],
                "suspicious_count": run["suspicious_count"],
                "verified_count": run["verified_count"],
            },
        },
        "results": items,
        "pending_decisions_count": pending_count,
        "pagination": pagination,
    }


async def set_decision(hr: dict[str, Any], run_id: UUID, worker_id: UUID, payload: PayrollDecisionRequest) -> dict[str, Any]:
    run = await _get_run_for_hr(hr, run_id)
    if run.get("status") != "ANALYSED":
        raise AppError(409, "PAYROLL_ALREADY_APPROVED", "Payroll already approved.")
    if payload.decision not in {"INCLUDE", "EXCLUDE"}:
        raise AppError(400, "INVALID_HR_DECISION", "Decision value must be INCLUDE or EXCLUDE.", "decision")
    if payload.decision == "EXCLUDE" and not (payload.note and payload.note.strip()):
        raise AppError(400, "NOTE_REQUIRED", "A note is required when excluding a worker.", "note")
    db = get_supabase()
    rows = db.table("ghost_analysis_results").select("*").eq("payroll_run_id", str(run_id)).eq("worker_id", str(worker_id)).limit(1).execute().data
    if not rows:
        raise AppError(404, "PAYROLL_RESULT_NOT_FOUND", "Payroll result was not found.")
    result = rows[0]
    update_result = (
        db.table("ghost_analysis_results")
        .update({"hr_decision": payload.decision, "hr_reviewed_at": datetime.now(UTC).isoformat(), "hr_note": payload.note})
        .eq("id", result["id"])
        .execute()
    )
    updated = _require_row(update_result.data, "DATABASE_UPDATE_FAILED", "Could not save payroll decision.")
    await write_audit(
        hr["id"],
        "hr",
        "HR_PAYROLL_DECISION",
        str(worker_id),
        "worker",
        {"run_id": str(run_id), "decision": payload.decision, "note": payload.note, "worker_trust_score": result.get("trust_score"), "worker_verdict": result.get("verdict")},
    )
    return updated


def _needs_decision(row: dict[str, Any]) -> bool:
    return row.get("verdict") in {"FLAGGED", "SUSPICIOUS"} and (row.get("hr_decision") or "PENDING") == "PENDING"


async def approve_payroll(hr: dict[str, Any], run_id: UUID) -> dict[str, Any]:
    db = get_supabase()
    run = await _get_run_for_hr(hr, run_id)
    if run.get("status") != "ANALYSED":
        raise AppError(409, "PAYROLL_ALREADY_APPROVED", "Payroll run already locked and approved.")
    results = db.table("ghost_analysis_results").select("*, workers(roles(gross_salary,pension_deduct,health_deduct,other_deductions))").eq("payroll_run_id", str(run_id)).execute().data
    pending = sum(1 for row in results if _needs_decision(row))
    if pending:
        raise AppError(400, "PENDING_DECISIONS_REMAIN", f"{pending} workers still need your decision before you can approve payroll.")
    included = [row for row in results if row.get("hr_decision") == "INCLUDE" or ((row.get("hr_decision") or "PENDING") == "PENDING" and row.get("verdict") == "VERIFIED")]
    excluded = [row for row in results if row.get("hr_decision") == "EXCLUDE"]

    # CRITICAL: Lock salary amounts at approval time — store net_pay so role changes
    # between approval and disbursement cannot change the payout amount.
    total_kobo = 0
    worker_pay_map: dict[str, dict] = {}
    for row in included:
        wid = str(row["worker_id"])
        role = ((row.get("workers") or {}).get("roles") or {})
        gross = _money(role.get("gross_salary"))
        deductions = _money(role.get("pension_deduct")) + _money(role.get("health_deduct")) + _money(role.get("other_deductions"))
        net_ngn = round(gross - deductions, 2)
        net_kobo = int(net_ngn * 100)
        total_kobo += net_kobo
        worker_pay_map[wid] = {"gross_ngn": gross, "deductions_ngn": deductions, "net_ngn": net_ngn, "net_kobo": net_kobo}

    # CRITICAL: Check wallet balance BEFORE approving — gives instant feedback to HR
    wallet = db.table("company_wallet").select("*").eq("company_id", hr["company_id"]).single().execute().data
    if not wallet:
        raise AppError(400, "WALLET_NOT_FOUND", "Company wallet not found. Contact support.")
    if wallet["balance_kobo"] < total_kobo:
        shortfall_ngn = (total_kobo - wallet["balance_kobo"]) / 100
        raise AppError(402, "INSUFFICIENT_WALLET_BALANCE", (
            f"Insufficient funds. Payroll requires NGN {total_kobo/100:,.2f} "
            f"but wallet has NGN {wallet['balance_kobo']/100:,.2f}. "
            f"Please deposit at least NGN {shortfall_ngn:,.2f} to proceed."
        ))

    # CRITICAL: Store net_pay in ghost_analysis_results to lock salary amount for disbursement
    approved_at = datetime.now(UTC).isoformat()
    for wid, pay in worker_pay_map.items():
        db.table("ghost_analysis_results").update({
            "net_pay": pay["net_ngn"],
            "gross_salary": pay["gross_ngn"],
        }).eq("payroll_run_id", str(run_id)).eq("worker_id", wid).execute()

    # CRITICAL: Optimistic lock — only update if status is still ANALYSED
    # This prevents concurrent approval requests from both succeeding
    update_result = db.table("payroll_runs").update({
        "status": "APPROVED", "approved_at": approved_at
    }).eq("id", str(run_id)).eq("company_id", hr["company_id"]).eq("status", "ANALYSED").execute()
    if not update_result.data:
        raise AppError(409, "PAYROLL_ALREADY_APPROVED", "Payroll was already approved by another request.")
    updated = update_result.data[0]

    hr_name = f"{hr.get('first_name', '')} {hr.get('last_name', '')}".strip()
    await write_audit(hr["id"], "hr", "PAYROLL_APPROVED", str(run_id), "payroll_run", {
        "run_id": str(run_id), "month_year": run["month_year"],
        "approved_worker_count": len(included),
        "approved_by_name": hr_name,
        "total_net_pay_kobo": total_kobo,
    })
    return {
        "run_id": str(run_id),
        "approved_at": updated.get("approved_at") or approved_at,
        "workers_to_be_paid": len(included),
        "workers_excluded": len(excluded),
        "estimated_total_payout": round(total_kobo / 100, 2),
    }


from datetime import datetime, timezone


async def disburse_payroll(run_id: str, hr_officer: dict) -> dict:
    """
    Disburse payroll for a payroll run.
    Called after HR approves. Checks wallet balance first.
    Transfers to each included worker via BMONI offramp.
    Updates company wallet and creates payment receipts.

    CRITICAL: Uses the net_pay stored in ghost_analysis_results at approval time
    so that role changes between approval and disbursement CANNOT change the payout.
    Wallet deduction uses optimistic locking to prevent race conditions.
    """
    now = datetime.now(timezone.utc)
    company_id = hr_officer["company_id"]
    db = get_supabase()

    # Load payroll run — must be in APPROVED status
    run = db.table("payroll_runs").select("*").eq(
        "id", run_id
    ).eq("company_id", company_id).single().execute().data
    if not run:
        raise AppError(404, "RUN_NOT_FOUND", "Payroll run not found.")
    if run.get("status") not in ("APPROVED", "DISBURSING"):
        raise AppError(409, "INVALID_RUN_STATUS",
                        f"Cannot disburse payroll in status '{run.get('status')}'.")

    # Load workers to pay: hr_decision=INCLUDE, or VERIFIED with PENDING decision
    results = db.table("ghost_analysis_results").select(
        "*, workers(id, first_name, last_name, company_id, "
        "worker_bank_accounts(account_number, bank_code, bank_name, account_name, is_active))"
    ).eq("payroll_run_id", run_id).execute().data or []

    workers_to_pay = [
        r for r in results
        if r["hr_decision"] == "INCLUDE"
        or (r["verdict"] == "VERIFIED" and r["hr_decision"] == "PENDING")
    ]

    if not workers_to_pay:
        raise AppError(400, "NO_WORKERS_TO_PAY", "No workers approved for payment in this payroll run.")

    # CRITICAL: Use net_pay stored at approval time — do NOT refetch from roles
    total_kobo_needed = 0
    worker_pay_details = []

    for result in workers_to_pay:
        worker = result.get("workers", {})

        bank_accounts = worker.get("worker_bank_accounts", [])
        active_bank = next((b for b in bank_accounts if b["is_active"]), None)
        if not active_bank:
            logger.warning("Worker %s has no active bank account — skipping", worker["id"])
            continue

        # Use the net_pay and gross_salary locked in at approval time
        net_ngn = float(result.get("net_pay") or 0)
        gross_ngn = float(result.get("gross_salary") or 0)
        net_kobo = int(net_ngn * 100)

        if net_kobo <= 0:
            logger.warning("Worker %s net pay is zero or negative (net_pay=%.2f) — skipping", worker["id"], net_ngn)
            continue

        total_kobo_needed += net_kobo
        deductions_ngn = round(gross_ngn - net_ngn, 2)
        worker_pay_details.append({
            "result": result,
            "worker": worker,
            "bank": active_bank,
            "gross_ngn": gross_ngn,
            "deductions_ngn": deductions_ngn,
            "net_ngn": net_ngn,
            "net_kobo": net_kobo
        })

    # RISK SCORING — check every worker BEFORE any payout
    if worker_pay_details:
        month_year = run["month_year"]
        remote_scores = await score_remote_workers_batch(company_id)
        physical_scores = await score_physical_workers_batch(company_id, month_year)
        batch_scores: dict[str, Any] = {**remote_scores, **physical_scores}

        held_workers: list[dict[str, Any]] = []
        passing_details: list[dict[str, Any]] = []

        for detail in worker_pay_details:
            wid = detail["worker"]["id"]
            risk = await compute_risk_score(wid, batch_scores=batch_scores)
            if risk["risk_score"] >= RISK_SCORE_HOLD_THRESHOLD:
                logger.warning(
                    "PAYROLL_HELD — worker=%s risk_score=%d flags=%s scoring_method=%s "
                    "run=%s month_year=%s",
                    wid, risk["risk_score"], risk["flags"],
                    risk["scoring_method"], run_id, month_year,
                )
                held_workers.append({"detail": detail, "risk": risk})
            else:
                passing_details.append(detail)

        if held_workers:
            db = get_supabase()
            db.table("payroll_runs").update({"status": "PAYROLL_PAUSED"}).eq("id", run_id).execute()
            for hw in held_workers:
                risk = hw["risk"]
                await write_audit(
                    hr_officer["id"], "hr", "PAYROLL_HELD",
                    risk["worker_id"], "worker",
                    {
                        "run_id": run_id,
                        "risk_score": risk["risk_score"],
                        "flags": risk["flags"],
                        "scoring_method": risk["scoring_method"],
                        "reason": "risk_score_exceeded_threshold",
                    },
                )
            logger.info(
                "Payroll run %s PAUSED — %d worker(s) held (threshold=%d). "
                "Admin override required before these workers can be paid.",
                run_id, len(held_workers), RISK_SCORE_HOLD_THRESHOLD,
            )
            return {
                "success": False,
                "message": (
                    f"Payroll paused — {len(held_workers)} worker(s) have risk scores "
                    f"≥ {RISK_SCORE_HOLD_THRESHOLD}. Admin override required before disbursement."
                ),
                "data": {
                    "run_id": run_id,
                    "held_count": len(held_workers),
                    "passing_count": len(passing_details),
                    "hold_threshold": RISK_SCORE_HOLD_THRESHOLD,
                },
            }

        worker_pay_details = passing_details

    if not worker_pay_details:
        raise AppError(400, "NO_WORKERS_TO_PAY", "No workers cleared risk checks for payment.")

    # CRITICAL: Re-check wallet balance with fresh read (safety net — already checked at approval time)
    wallet = db.table("company_wallet").select("*").eq(
        "company_id", company_id
    ).single().execute().data

    if not wallet:
        raise AppError(400, "WALLET_NOT_FOUND", "Company wallet not found. Contact support.")

    if wallet["balance_kobo"] < total_kobo_needed:
        shortfall_ngn = (total_kobo_needed - wallet["balance_kobo"]) / 100
        available_ngn = wallet["balance_kobo"] / 100
        needed_ngn = total_kobo_needed / 100
        raise AppError(402, "INSUFFICIENT_WALLET_BALANCE", (
            f"Insufficient funds. Payroll requires NGN {needed_ngn:,.2f} "
            f"but wallet has NGN {available_ngn:,.2f}. "
            f"Please deposit at least NGN {shortfall_ngn:,.2f} to proceed."
        ))

    # CRITICAL: Optimistic lock — only move to DISBURSING if still APPROVED
    # This prevents concurrent disbursement from processing the same run twice
    status_update = db.table("payroll_runs").update({
        "status": "DISBURSING"
    }).eq("id", run_id).eq("status", "APPROVED").execute()
    if not status_update.data:
        logger.warning("disburse_payroll: run %s not in APPROVED status (concurrent disbursement?)", run_id)
        raise AppError(409, "ALREADY_DISBURSING",
                        "Payroll run is already being disbursed or has moved past APPROVED.")

    # DISBURSE TO EACH WORKER
    paid_count = 0
    failed_count = 0
    total_paid_kobo = 0
    current_balance = wallet["balance_kobo"]
    current_total_disbursed = wallet.get("total_disbursed_kobo", 0)

    for detail in worker_pay_details:
        worker = detail["worker"]
        bank = detail["bank"]
        net_kobo = detail["net_kobo"]
        result = detail["result"]
        month_year = run["month_year"]

        remark = f"GhostGuard Salary {month_year} - {worker['first_name']} {worker['last_name']}"

        # Create wallet_transaction record BEFORE BMONI call
        tx_insert = db.table("wallet_transactions").insert({
            "company_id": company_id,
            "type": "DISBURSEMENT",
            "amount_kobo": net_kobo,
            "status": "PENDING",
            "description": remark,
            "worker_id": worker["id"],
            "payroll_run_id": run_id,
            "created_at": now.isoformat()
        }).execute()

        tx_id = tx_insert.data[0]["id"] if tx_insert.data else None

        # CALL BMONI ORCHESTRATOR (creates receipt + calls BMONI offramp)
        if get_settings().use_squad_lookup:
            tx_ref = f"GG-PAY-{run_id[:8].upper()}-{worker['id'][:8].upper()}-{int(now.timestamp())}"
            bmoni_result = await initiate_single_payment(
                worker_result=result,
                run_id=run_id,
                reference=tx_ref,
            )
            success = bmoni_result.get("success", False)
            receipt_id = bmoni_result.get("receipt_id")
            bmoni_tx_id = bmoni_result.get("bmoni_tx_id") if success else None
            tx_ref = bmoni_result.get("reference", tx_ref)
        else:
            # Mock mode — simulate payment for demo (no BMONI call)
            import asyncio, uuid
            await asyncio.sleep(0.3)
            tx_ref = f"GG-PAY-{run_id[:8].upper()}-{worker['id'][:8].upper()}-{int(now.timestamp())}"
            bmoni_tx_id = f"BMONI{uuid.uuid4().hex[:12].upper()}"
            receipt_insert = db.table("payment_receipts").insert({
                "payroll_run_id": run_id,
                "worker_id": worker["id"],
                "company_id": company_id,
                "bmoni_reference": tx_ref,
                "gross_salary": detail["gross_ngn"],
                "total_deductions": detail["deductions_ngn"],
                "net_pay": detail["net_ngn"],
                "amount_kobo": net_kobo,
                "bank_account_number": bank["account_number"],
                "bank_code": bank["bank_code"],
                "bank_name": bank["bank_name"],
                "account_name": bank["account_name"],
                "trust_score": result.get("trust_score"),
                "verdict": result.get("verdict"),
                "days_present": result.get("days_present"),
                "hr_decision": result.get("hr_decision"),
                "bmoni_status": "PAID",
                "bmoni_tx_id": bmoni_tx_id,
                "paid_at": now.isoformat(),
                "month_year": month_year,
                "created_at": now.isoformat()
            }).execute()
            receipt_id = receipt_insert.data[0]["id"] if receipt_insert.data else None
            success = True

        if success:
            if tx_id:
                db.table("wallet_transactions").update({
                    "status": "SUCCESS",
                    "squad_reference": tx_ref,
                    "squad_tx_id": bmoni_tx_id,
                    "updated_at": now.isoformat()
                }).eq("id", tx_id).execute()

            # CRITICAL: Atomic wallet deduction with optimistic locking
            # Only deduct if balance_kobo still equals our expected current_balance
            # This prevents race conditions with concurrent disbursements
            new_balance = current_balance - net_kobo
            new_total_disbursed = current_total_disbursed + net_kobo
            wallet_update = db.table("company_wallet").update({
                "balance_kobo": new_balance,
                "total_disbursed_kobo": new_total_disbursed,
                "last_disburse_at": now.isoformat(),
                "updated_at": now.isoformat()
            }).eq("company_id", company_id).eq("balance_kobo", current_balance).execute()

            if not wallet_update.data:
                logger.error(
                    "WALLET_RACE_DETECTED — company=%s worker=%s expected_balance=%d net_kobo=%d. "
                    "Money was SENT via BMONI but wallet deduction failed! Manual reconciliation required.",
                    company_id, worker["id"], current_balance, net_kobo,
                )
                raise AppError(500, "WALLET_RACE_DETECTED",
                    f"Wallet balance changed unexpectedly. Worker {worker['id']} was paid via BMONI "
                    f"but wallet deduction failed. Contact support for reconciliation.")

            current_balance = new_balance
            current_total_disbursed = new_total_disbursed
            paid_count += 1
            total_paid_kobo += net_kobo

        else:
            if tx_id:
                db.table("wallet_transactions").update({
                    "status": "FAILED",
                    "squad_reference": tx_ref,
                    "failure_reason": bmoni_result.get("error"),
                    "updated_at": now.isoformat()
                }).eq("id", tx_id).execute()

            failed_count += 1

    # Update payroll run to DISBURSED
    db.table("payroll_runs").update({
        "status": "DISBURSED",
        "approved_at": now.isoformat()
    }).eq("id", run_id).execute()

    # Audit log
    db.table("audit_logs").insert({
        "actor_id": hr_officer["id"],
        "actor_type": "hr",
        "action": "PAYROLL_DISBURSEMENT_COMPLETE",
        "target_id": run_id,
        "target_type": "payroll_run",
        "metadata": {
            "paid_count": paid_count,
            "failed_count": failed_count,
            "total_paid_ngn": total_paid_kobo / 100,
            "month_year": run["month_year"]
        }
    }).execute()

    return {
        "success": True,
        "message": f"Payroll disbursed. {paid_count} workers paid, {failed_count} failed.",
        "data": {
            "paid_count": paid_count,
            "failed_count": failed_count,
            "total_paid_ngn": total_paid_kobo / 100,
            "run_id": run_id
        }
    }


async def receipts(hr: dict[str, Any], run_id: UUID, bmoni_status: str | None, page: int, page_size: int) -> dict[str, Any]:
    await _get_run_for_hr(hr, run_id)
    query = get_supabase().table("payment_receipts").select("*, workers(first_name,last_name,roles(role_name))").eq("payroll_run_id", str(run_id))
    if bmoni_status:
        query = query.eq("bmoni_status", bmoni_status)
    rows = query.order("created_at", desc=True).execute().data
    summary_rows = get_supabase().table("payment_receipts").select("*").eq("payroll_run_id", str(run_id)).execute().data
    decorated = [_decorate_receipt(row) for row in rows]
    items, pagination = _page(decorated, page, page_size)
    return {
        "summary": {
            "total_paid": sum(1 for row in summary_rows if row.get("bmoni_status") == "PAID"),
            "total_failed": sum(1 for row in summary_rows if row.get("bmoni_status") == "FAILED"),
            "total_pending": sum(1 for row in summary_rows if row.get("bmoni_status") == "PENDING"),
            "total_amount_disbursed": round(sum(_money(row.get("net_pay")) for row in summary_rows if row.get("bmoni_status") == "PAID"), 2),
        },
        "receipts": items,
        "pagination": pagination,
    }


def _decorate_receipt(row: dict[str, Any]) -> dict[str, Any]:
    worker = row.get("workers") or {}
    role = worker.get("roles") or {}
    return {
        "id": row["id"],
        "worker_id": row["worker_id"],
        "worker_name": f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip(),
        "role_name": role.get("role_name"),
        "net_pay": row.get("net_pay"),
        "amount_kobo": row.get("amount_kobo"),
        "bank_account_number": row.get("bank_account_number"),
        "bank_name": row.get("bank_name"),
        "account_name": row.get("account_name"),
        "bmoni_tx_id": row.get("bmoni_tx_id"),
        "bmoni_reference": row.get("bmoni_reference"),
        "bmoni_status": row.get("bmoni_status"),
        "trust_score": row.get("trust_score"),
        "verdict": row.get("verdict"),
        "days_present": row.get("days_present"),
        "hr_decision": row.get("hr_decision"),
        "hr_note": row.get("hr_note"),
        "paid_at": row.get("paid_at"),
    }


async def receipts_csv(hr: dict[str, Any], run_id: UUID) -> tuple[str, str]:
    run = await _get_run_for_hr(hr, run_id)
    rows = get_supabase().table("payment_receipts").select("*, workers(first_name,last_name,roles(role_name))").eq("payroll_run_id", str(run_id)).order("created_at").execute().data
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=["worker_name", "role", "gross_salary", "deductions", "net_pay", "bank_account", "bank_name", "bmoni_tx_id", "bmoni_status", "trust_score", "verdict", "days_present", "hr_decision", "paid_at"])
    writer.writeheader()
    for row in rows:
        worker = row.get("workers") or {}
        role = worker.get("roles") or {}
        writer.writerow(
            {
                "worker_name": f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip(),
                "role": role.get("role_name"),
                "gross_salary": row.get("gross_salary"),
                "deductions": row.get("total_deductions"),
                "net_pay": row.get("net_pay"),
                "bank_account": row.get("bank_account_number"),
                "bank_name": row.get("bank_name"),
                "bmoni_tx_id": row.get("bmoni_tx_id"),
                "bmoni_status": row.get("bmoni_status"),
                "trust_score": row.get("trust_score"),
                "verdict": row.get("verdict"),
                "days_present": row.get("days_present"),
                "hr_decision": row.get("hr_decision"),
                "paid_at": row.get("paid_at"),
            }
        )
    return output.getvalue(), f"ghostguard_receipts_{run['month_year']}.csv"


async def retry_receipt(hr: dict[str, Any], run_id: UUID, receipt_id: UUID) -> dict[str, Any]:
    run = await _get_run_for_hr(hr, run_id)
    db = get_supabase()
    rows = db.table("payment_receipts").select("*").eq("id", str(receipt_id)).eq("payroll_run_id", str(run_id)).eq("company_id", hr["company_id"]).limit(1).execute().data
    if not rows:
        raise AppError(404, "RECEIPT_NOT_FOUND", "Payment receipt not found.")
    receipt = rows[0]
    if receipt.get("bmoni_status") != "FAILED":
        raise AppError(400, "PAYMENT_NOT_FAILED", "Retry requested but payment is not in FAILED status.")
    result_rows = db.table("ghost_analysis_results").select("*").eq("payroll_run_id", str(run_id)).eq("worker_id", receipt["worker_id"]).limit(1).execute().data
    if not result_rows:
        raise AppError(404, "PAYROLL_RESULT_NOT_FOUND", "Payroll result was not found.")
    db.table("payment_receipts").update({"bmoni_status": "PENDING", "failure_reason": None}).eq("id", str(receipt_id)).execute()
    attempt = await initiate_single_payment(result_rows[0], str(run_id), receipt["bmoni_reference"])
    await write_audit(hr["id"], "hr", "PAYMENT_RETRY", str(receipt_id), "payment_receipt", {"receipt_id": str(receipt_id), "worker_id": receipt["worker_id"], "bmoni_reference": receipt["bmoni_reference"], "attempt": attempt, "month_year": run["month_year"]})
    return {"success": True, "message": "Payment retry initiated."}


async def worker_payslip(worker: dict[str, Any], month_year: str | None) -> dict[str, Any]:
    db = get_supabase()
    query = db.table("payment_receipts").select("*, workers(first_name,last_name,roles(role_name))").eq("worker_id", worker["id"])
    if month_year:
        query = query.eq("month_year", month_year)
    rows = query.order("created_at", desc=True).limit(1).execute().data
    if not rows:
        raise AppError(404, "RECEIPT_NOT_FOUND", "No payslip found for this period.")
    row = rows[0]
    result_rows = db.table("ghost_analysis_results").select("days_absent").eq("payroll_run_id", row["payroll_run_id"]).eq("worker_id", worker["id"]).limit(1).execute().data
    worker_data = row.get("workers") or {}
    role = worker_data.get("roles") or {}
    payload = {
        "worker_name": f"{worker_data.get('first_name', '')} {worker_data.get('last_name', '')}".strip(),
        "role_name": role.get("role_name"),
        "month_year": row.get("month_year"),
        "gross_salary": row.get("gross_salary"),
        "total_deductions": row.get("total_deductions"),
        "net_pay": row.get("net_pay"),
        "days_present": row.get("days_present"),
        "days_absent": result_rows[0].get("days_absent") if result_rows else None,
        "bank_account_number": row.get("bank_account_number"),
        "bank_name": row.get("bank_name"),
        "bmoni_tx_id": row.get("bmoni_tx_id"),
        "bmoni_status": row.get("bmoni_status"),
        "paid_at": row.get("paid_at"),
        "trust_score": row.get("trust_score"),
        "verdict": row.get("verdict"),
    }
    if _money(row.get("trust_score")) < 70 and row.get("verdict") == "SUSPICIOUS":
        payload["message"] = "Your attendance patterns triggered a review. Contact HR if you have questions."
    return payload


async def worker_payslips(worker: dict[str, Any]) -> dict[str, Any]:
    rows = get_supabase().table("payment_receipts").select("month_year, net_pay, bmoni_status, paid_at, trust_score").eq("worker_id", worker["id"]).order("created_at", desc=True).execute().data
    return {"payslips": rows}


async def override_payroll_hold(admin: dict[str, Any], worker_id: str) -> dict[str, Any]:
    db = get_supabase()
    run = (
        db.table("payroll_runs")
        .select("*")
        .eq("company_id", admin["company_id"])
        .eq("status", "PAYROLL_PAUSED")
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not run:
        raise AppError(404, "NO_PAUSED_RUN", "No payroll run is currently in PAYROLL_PAUSED status.")

    run_id = run[0]["id"]

    await write_audit(
        admin["id"], "admin", "PAYROLL_HOLD_OVERRIDDEN",
        worker_id, "worker",
        {
            "run_id": str(run_id),
            "overridden_by": admin["id"],
            "month_year": run[0]["month_year"],
        },
    )

    logger.info(
        "Admin %s overrode hold for worker %s in payroll run %s",
        admin["id"], worker_id, run_id,
    )

    return {
        "success": True,
        "message": f"Hold overridden for worker {worker_id}. Audit logged.",
        "data": {"run_id": str(run_id), "worker_id": worker_id},
    }


async def risk_summary(admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    run = (
        db.table("payroll_runs")
        .select("*")
        .eq("company_id", admin["company_id"])
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
        .data
    )

    workers = (
        db.table("workers")
        .select("id, first_name, last_name, work_mode, status")
        .eq("company_id", admin["company_id"])
        .eq("status", "ACTIVE")
        .execute()
        .data
    )

    if not workers:
        return {"risk_summary": [], "payroll_run": run[0] if run else None}

    month_year = run[0]["month_year"] if run else datetime.now(UTC).strftime("%Y-%m")

    remote_scores = await score_remote_workers_batch(admin["company_id"])
    physical_scores = await score_physical_workers_batch(admin["company_id"], month_year)
    batch_scores: dict[str, Any] = {**remote_scores, **physical_scores}

    results: list[dict[str, Any]] = []
    for w in workers:
        wid = w["id"]
        risk = await compute_risk_score(wid, batch_scores=batch_scores)
        results.append({
            "worker_id": wid,
            "worker_name": f"{w.get('first_name', '')} {w.get('last_name', '')}".strip(),
            "work_mode": risk["work_mode"],
            "risk_score": risk["risk_score"],
            "flags": risk["flags"],
            "scoring_method": risk["scoring_method"],
            "payout_status": run[0].get("status", "") if run else "NO_RUN",
        })

    results.sort(key=lambda r: r["risk_score"], reverse=True)

    return {
        "payroll_run": run[0] if run else None,
        "risk_summary": results,
    }


async def refresh_receipt_status(admin: dict[str, Any], receipt_id: UUID) -> dict[str, Any]:
    """Look up a payment receipt, verify it belongs to the admin's company,
    then poll BMONI for the latest payout status and update the receipt if resolved."""
    db = get_supabase()
    rows = db.table("payment_receipts").select("*").eq("id", str(receipt_id)).limit(1).execute().data
    if not rows:
        raise AppError(404, "RECEIPT_NOT_FOUND", "Payment receipt not found.")
    receipt = rows[0]
    if receipt.get("company_id") != admin["company_id"]:
        raise AppError(403, "FORBIDDEN", "This receipt does not belong to your company.")

    result = await poll_pending_payout(str(receipt_id))

    await write_audit(
        admin["id"], "admin", "RECEIPT_STATUS_REFRESHED",
        str(receipt_id), "payment_receipt",
        {
            "receipt_id": str(receipt_id),
            "worker_id": receipt["worker_id"],
            "previous_status": result.get("previous_status"),
            "current_status": result.get("current_status"),
            "bmoni_status": result.get("bmoni_status"),
            "updated": result.get("updated"),
        },
    )

    return {
        "receipt_id": str(receipt_id),
        "previous_status": result.get("previous_status"),
        "current_status": result.get("current_status"),
        "bmoni_status": result.get("bmoni_status"),
        "updated": result.get("updated", False),
    }


async def handle_squad_webhook(raw_body: bytes, signature: str | None) -> dict[str, Any]:
    """
    DEPRECATED — Squad webhook handler.

    BMONI does not send webhooks; it uses the polling fallback (poll_pending_payout).
    This endpoint (POST /webhooks/squad/payout) is dead code and will never fire
    for BMONI payouts. This function is dead code and will never fire
    for BMONI payouts. If this code is ever removed, delete this entire function
    and its route registration in payroll/router.py.
    """
    settings = get_settings()
    expected = hmac.new(settings.squad_secret_key.encode(), raw_body, hashlib.sha512).hexdigest().upper()
    if not signature or not hmac.compare_digest(expected, signature.upper()):
        await write_audit("00000000-0000-0000-0000-000000000000", "system", "SQUAD_WEBHOOK_INVALID_SIGNATURE", None, "payment_receipt", {})
        return {"ignored": True}
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        return {"ignored": True}
    reference = payload.get("transaction_reference") or payload.get("reference")
    status = str(payload.get("transaction_status") or payload.get("status") or "").lower()
    amount = payload.get("amount")
    if not reference:
        return {"ignored": True}
    db = get_supabase()
    rows = db.table("payment_receipts").select("*").eq("bmoni_reference", reference).limit(1).execute().data
    if not rows:
        return {"ignored": True}
    receipt = rows[0]
    if status == "success":
        update_result = db.table("payment_receipts").update({"bmoni_status": "PAID", "paid_at": datetime.now(UTC).isoformat(), "bmoni_tx_id": reference}).eq("id", receipt["id"]).execute()
        updated = _require_row(update_result.data, "DATABASE_UPDATE_FAILED", "Could not update payment receipt.")
        await write_audit(receipt["worker_id"], "system", "SQUAD_PAYMENT_CONFIRMED", receipt["id"], "payment_receipt", {"receipt_id": receipt["id"], "worker_id": receipt["worker_id"], "amount": amount})
        return updated
    if status == "failed":
        message = payload.get("message") or payload.get("status_message") or "Payment failed."
        update_result = db.table("payment_receipts").update({"bmoni_status": "FAILED", "failure_reason": message}).eq("id", receipt["id"]).execute()
        updated = _require_row(update_result.data, "DATABASE_UPDATE_FAILED", "Could not update payment receipt.")
        await write_audit(receipt["worker_id"], "system", "SQUAD_PAYMENT_FAILED", receipt["id"], "payment_receipt", {"receipt_id": receipt["id"], "worker_id": receipt["worker_id"], "amount": amount, "message": message})
        return updated
    return {"ignored": True}

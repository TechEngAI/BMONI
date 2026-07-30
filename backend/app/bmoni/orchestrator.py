from decimal import Decimal
from typing import Any

import httpx

from app.bmoni.client import BMONI_TIMEOUT, _headers
from app.bmoni.payout import offramp_nigeria, BmoniPayoutError
from app.config import get_settings
from app.database import get_supabase


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _first_row(data: Any) -> dict[str, Any] | None:
    if not data:
        return None
    return data[0] if isinstance(data, list) else data


async def initiate_single_payment(worker_result: dict[str, Any], run_id: str, reference: str | None = None) -> dict[str, Any]:
    """Create a receipt, then initiate one BMONI offramp for one worker.
    
    This follows the same pattern as the Squad implementation but uses BMONI's smart wallet offramp.
    
    The flow is:
    1. Create a payment_receipt row with status PENDING and a generated idempotency_key
    2. Call offramp_nigeria() with that idempotency_key
    3. On success, update the receipt to PAID with the transaction ID
    4. On failure, update the receipt to FAILED with the error reason
    
    CRITICAL: Uses the net_pay and gross_salary from worker_result (ghost_analysis_results)
    which were locked in at approval time. Does NOT refetch from roles to prevent
    salary changes between approval and disbursement from affecting the payout.
    
    Args:
        worker_result: Dict containing worker_id, net_pay, gross_salary, trust_score, verdict, days_present, hr_decision, hr_note
        run_id: Payroll run ID
        reference: Optional reference/idempotency key (generated if not provided)
    
    Returns:
        Dict with success status, transaction details, and receipt_id
    """
    db = get_supabase()
    settings = get_settings()
    worker_id = str(worker_result["worker_id"])
    
    # Look up payroll run
    runs = db.table("payroll_runs").select("*").eq("id", run_id).limit(1).execute().data
    if not runs:
        return {"success": False, "error": "Payroll run not found"}
    run = runs[0]
    
    # CRITICAL: Use stored values from ghost_analysis_results (locked at approval time)
    # Do NOT refetch from roles — that would allow salary changes to affect payout
    net_pay = _money(worker_result.get("net_pay"))
    gross = _money(worker_result.get("gross_salary"))
    
    # Fallback for legacy rows where net_pay was not stored at approval time
    if net_pay <= 0 and gross > 0:
        workers = db.table("workers").select("*, roles(*)").eq("id", worker_id).limit(1).execute().data
        if workers:
            role = workers[0].get("roles") or {}
            gross_from_role = _money(role.get("gross_salary"))
            deductions_from_role = _money(role.get("pension_deduct")) + _money(role.get("health_deduct")) + _money(role.get("other_deductions"))
            net_pay = gross_from_role - deductions_from_role
            gross = gross_from_role
    
    if net_pay <= 0:
        return {"success": False, "error": "Net pay is zero or negative", "code": "ZERO_NET_PAY"}
    
    amount_ngn = float(net_pay)
    deductions = float(gross - net_pay) if gross >= net_pay else 0.0
    
    # Look up active bank account
    bank_rows = db.table("worker_bank_accounts").select("*").eq("worker_id", worker_id).eq("is_active", True).limit(1).execute().data
    if not bank_rows:
        return {"success": False, "error": "No active bank account", "code": "NO_ACTIVE_BANK_ACCOUNT"}
    bank = bank_rows[0]
    
    # Generate reference/idempotency key if not provided
    if not reference:
        import time
        reference = f"GG-PAY-{run_id[:8].upper()}-{worker_id[:8].upper()}-{int(time.time())}"
    
    # Check for existing receipt with this reference (idempotency)
    existing = db.table("payment_receipts").select("*").eq("bmoni_reference", reference).limit(1).execute().data
    if existing:
        receipt = existing[0]
    else:
        # Create receipt with PENDING status BEFORE calling BMONI
        receipt_result = (
            db.table("payment_receipts")
            .insert(
                {
                    "payroll_run_id": run_id,
                    "worker_id": worker_id,
                    "company_id": run["company_id"],
                    "bmoni_reference": reference,
                    "gross_salary": float(gross),
                    "total_deductions": float(deductions),
                    "net_pay": float(net_pay),
                    "amount_kobo": int(net_pay * 100),  # Still stored in kobo for backward compatibility
                    "bank_account_number": bank["account_number"],
                    "bank_code": bank["bank_code"],
                    "bank_name": bank["bank_name"],
                    "account_name": bank["account_name"],
                    "trust_score": worker_result.get("trust_score"),
                    "verdict": worker_result.get("verdict"),
                    "days_present": worker_result.get("days_present"),
                    "hr_decision": worker_result.get("hr_decision"),
                    "hr_note": worker_result.get("hr_note"),
                    "bmoni_status": "PENDING",
                    "month_year": run["month_year"],
                }
            )
            .execute()
        )
        receipt = _first_row(receipt_result.data)
        if not receipt:
            return {"success": False, "error": "Could not create payment receipt", "code": "RECEIPT_CREATE_FAILED"}
    
    # Get BMONI withdrawal account ID for this worker
    # This should have been previously registered via register_withdrawal_account
    withdrawal_account_id = bank.get("bmoni_withdrawal_account_id")
    if not withdrawal_account_id:
        error_msg = "No BMONI withdrawal account ID found for worker. Please register the bank account first."
        db.table("payment_receipts").update({"bmoni_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
        return {"success": False, "error": error_msg, "code": "NO_WITHDRAWAL_ACCOUNT", "receipt_id": receipt["id"]}
    
    # Call BMONI offramp
    try:
        smart_wallet_id = settings.bmoni_smart_wallet_id
        result = await offramp_nigeria(
            smart_wallet_id=smart_wallet_id,
            withdrawal_account_id=withdrawal_account_id,
            amount=amount_ngn,
            idempotency_key=reference
        )
    except BmoniPayoutError as exc:
        # Update receipt to FAILED with error details
        error_msg = f"{exc.code}: {exc.message}"
        db.table("payment_receipts").update({"bmoni_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
        return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}
    except ValueError as exc:
        error_msg = f"Invalid input: {exc}"
        db.table("payment_receipts").update({"bmoni_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
        return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}
    
    # Handle success
    if result["status"] == "SUCCESS":
        transaction_id = result.get("transaction_id")
        db.table("payment_receipts").update({
            "bmoni_tx_id": transaction_id,
            "bmoni_status": "PAID",
            "failure_reason": None
        }).eq("id", receipt["id"]).execute()
        return {
            "success": True,
            "bmoni_tx_id": transaction_id,
            "reference": reference,
            "receipt_id": receipt["id"],
            "amount_ngn": amount_ngn
        }
    
    # Handle failure from BMONI (shouldn't normally reach here since BmoniPayoutError is raised)
    error_msg = "Payout failed with unknown error"
    db.table("payment_receipts").update({"bmoni_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
    return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}


async def poll_pending_payout(receipt_id: str) -> dict[str, Any]:
    """Poll BMONI for the current status of a payout transaction.

    Calls GET /v1/users/{userId}/smart-wallets/{smartWalletId}/transactions/{transactionId}
    on BMONI to check the latest status. Updates the receipt if a terminal state
    (PAID/FAILED) is now reported.

    Args:
        receipt_id: The payment_receipts row ID (UUID as string)

    Returns:
        Dict with success, receipt_id, previous_status, current_status,
        bmoni_tx_id, bmoni_status, and whether the receipt was updated.
    """
    db = get_supabase()
    settings = get_settings()

    rows = db.table("payment_receipts").select("*").eq("id", receipt_id).limit(1).execute().data
    if not rows:
        return {"success": False, "error": "Receipt not found"}
    receipt = rows[0]

    bmoni_tx_id = receipt.get("bmoni_tx_id")
    if not bmoni_tx_id:
        return {"success": False, "error": "No BMONI transaction ID (bmoni_tx_id) on this receipt"}

    previous_status = receipt.get("bmoni_status", "PENDING")
    user_id = settings.bmoni_user_id
    smart_wallet_id = settings.bmoni_smart_wallet_id

    url = (
        f"{settings.bmoni_base_url.rstrip('/')}"
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/transactions/{bmoni_tx_id}"
    )

    async with httpx.AsyncClient(timeout=BMONI_TIMEOUT) as client:
        try:
            response = await client.get(url, headers=_headers())
        except httpx.TimeoutException:
            return {"success": False, "error": "BMONI status check timed out", "bmoni_tx_id": bmoni_tx_id}
        except httpx.RequestError as exc:
            return {"success": False, "error": f"BMONI request failed: {exc}", "bmoni_tx_id": bmoni_tx_id}

    if response.status_code >= 400:
        return {"success": False, "error": f"BMONI returned status {response.status_code}", "bmoni_tx_id": bmoni_tx_id}

    data = response.json()
    bmoni_status = (data.get("status") or "").upper()

    STATUS_MAP = {
        "SUCCESS": "PAID",
        "COMPLETED": "PAID",
        "FAILED": "FAILED",
        "REVERSED": "FAILED",
        "CANCELLED": "FAILED",
    }
    our_status = STATUS_MAP.get(bmoni_status)

    updated = False
    if our_status and our_status != previous_status:
        update: dict[str, Any] = {"bmoni_status": our_status}
        if our_status == "PAID":
            from datetime import datetime, timezone
            update["paid_at"] = datetime.now(timezone.utc).isoformat()
        db.table("payment_receipts").update(update).eq("id", receipt_id).execute()
        updated = True

    return {
        "success": True,
        "receipt_id": receipt_id,
        "previous_status": previous_status,
        "current_status": our_status or previous_status,
        "bmoni_tx_id": bmoni_tx_id,
        "bmoni_status": bmoni_status,
        "updated": updated,
    }

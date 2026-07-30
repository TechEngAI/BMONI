from collections import Counter, defaultdict
from datetime import UTC, datetime
from typing import Any

from app.database import get_supabase


def _money(value: Any) -> float:
    return float(value or 0)


def _worker_name(worker: dict[str, Any] | None) -> str:
    worker = worker or {}
    return f"{worker.get('first_name', '')} {worker.get('last_name', '')}".strip()


async def summary(admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    company_id = admin["company_id"]
    workers = db.table("workers").select("id").eq("company_id", company_id).eq("status", "ACTIVE").execute().data
    runs = db.table("payroll_runs").select("id").eq("company_id", company_id).execute().data
    results = db.table("ghost_analysis_results").select("*, workers(roles(gross_salary))").eq("company_id", company_id).execute().data
    receipts = db.table("payment_receipts").select("net_pay, bmoni_status").eq("company_id", company_id).execute().data
    signals = db.table("fraud_signals").select("signal_type").eq("company_id", company_id).execute().data
    signal_counts = Counter(row.get("signal_type") for row in signals if row.get("signal_type"))
    most_common = None
    if signal_counts:
        signal_type, count = signal_counts.most_common(1)[0]
        most_common = {"signal_type": signal_type, "count": count}
    excluded = [row for row in results if row.get("hr_decision") == "EXCLUDE"]
    return {
        "total_workers": len(workers),
        "total_payroll_runs": len(runs),
        "total_ghosts_detected": sum(1 for row in results if row.get("verdict") == "FLAGGED"),
        "total_excluded_workers": len(excluded),
        "total_salary_saved": round(sum(_money(((row.get("workers") or {}).get("roles") or {}).get("gross_salary") or row.get("gross_salary")) for row in excluded), 2),
                "total_disbursed": round(sum(_money(row.get("net_pay")) for row in receipts if row.get("bmoni_status") == "PAID"), 2),
        "fraud_signal_count": len(signals),
        "most_common_signal": most_common,
    }


async def payroll_history(admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    runs = db.table("payroll_runs").select("*").eq("company_id", admin["company_id"]).order("year", desc=True).order("month", desc=True).execute().data
    history = []
    for run in runs:
        results = db.table("ghost_analysis_results").select("*, workers(roles(gross_salary))").eq("payroll_run_id", run["id"]).execute().data
        receipts = db.table("payment_receipts").select("net_pay, bmoni_status").eq("payroll_run_id", run["id"]).execute().data
        excluded = [row for row in results if row.get("hr_decision") == "EXCLUDE"]
        history.append(
            {
                "month_year": run["month_year"],
                "status": run["status"],
                "total_workers": run["total_workers"],
                "flagged_count": sum(1 for row in results if row.get("verdict") == "FLAGGED") or run.get("flagged_count"),
                "suspicious_count": sum(1 for row in results if row.get("verdict") == "SUSPICIOUS") or run.get("suspicious_count"),
                "verified_count": sum(1 for row in results if row.get("verdict") == "VERIFIED") or run.get("verified_count"),
                "excluded_count": len(excluded),
        "total_disbursed": round(sum(_money(row.get("net_pay")) for row in receipts if row.get("bmoni_status") == "PAID"), 2),
                "salary_saved": round(sum(_money(((row.get("workers") or {}).get("roles") or {}).get("gross_salary") or row.get("gross_salary")) for row in excluded), 2),
            }
        )
    return {"history": history}


async def fraud_breakdown(admin: dict[str, Any]) -> dict[str, Any]:
    rows = get_supabase().table("fraud_signals").select("*, workers(first_name,last_name)").eq("company_id", admin["company_id"]).execute().data
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    worker_counts: dict[str, dict[str, Any]] = {}
    for row in rows:
        grouped[row["signal_type"]].append(row)
        worker_id = row.get("worker_id")
        if worker_id:
            current = worker_counts.setdefault(worker_id, {"worker_id": worker_id, "worker_name": _worker_name(row.get("workers")), "signal_count": 0})
            current["signal_count"] += 1
    breakdown = []
    for signal_type, items in grouped.items():
        breakdown.append(
            {
                "signal_type": signal_type,
                "count": len(items),
                "critical_count": sum(1 for row in items if row.get("severity") == "CRITICAL"),
                "high_count": sum(1 for row in items if row.get("severity") == "HIGH"),
                "reviewed_count": sum(1 for row in items if row.get("is_reviewed") is True),
                "unreviewed_count": sum(1 for row in items if row.get("is_reviewed") is not True),
            }
        )
    breakdown.sort(key=lambda row: row["count"], reverse=True)
    top_workers = sorted(worker_counts.values(), key=lambda row: row["signal_count"], reverse=True)[:5]
    return {"breakdown": breakdown, "top_workers": top_workers}


async def top_risk_workers(admin: dict[str, Any], limit: int) -> dict[str, Any]:
    rows = get_supabase().table("ghost_analysis_results").select("*, workers(first_name,last_name,roles(role_name))").eq("company_id", admin["company_id"]).execute().data
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["worker_id"]].append(row)
    output = []
    for worker_id, items in grouped.items():
        latest = sorted(items, key=lambda row: row.get("created_at") or "", reverse=True)[0]
        worker = latest.get("workers") or {}
        role = worker.get("roles") or {}
        output.append(
            {
                "worker_id": worker_id,
                "worker_name": _worker_name(worker),
                "role_name": role.get("role_name"),
                "avg_trust_score": round(sum(_money(row.get("trust_score")) for row in items) / len(items), 2),
                "appearances_as_flagged": sum(1 for row in items if row.get("verdict") == "FLAGGED"),
                "appearances_as_suspicious": sum(1 for row in items if row.get("verdict") == "SUSPICIOUS"),
                "total_payroll_runs_appeared": len(items),
                "latest_verdict": latest.get("verdict"),
            }
        )
    output.sort(key=lambda row: row["avg_trust_score"])
    return {"workers": output[: max(1, min(limit, 100))]}


async def attendance_overview(admin: dict[str, Any], month_year: str | None) -> dict[str, Any]:
    month = month_year or datetime.now(UTC).strftime("%Y-%m")
    rows = get_supabase().table("attendance_records").select("*, workers(roles(work_type))").eq("company_id", admin["company_id"]).eq("month_year", month).execute().data
    closed_hours = [_money(row.get("hours_worked")) for row in rows if row.get("hours_worked") is not None]
    remote = 0
    onsite = 0
    for row in rows:
        role = ((row.get("workers") or {}).get("roles") or {})
        if role.get("work_type") == "REMOTE":
            remote += 1
        if role.get("work_type") == "ONSITE":
            onsite += 1
    return {
        "month_year": month,
        "total_check_ins": len(rows),
        "unique_workers_attended": len({row["worker_id"] for row in rows if row.get("worker_id")}),
        "average_hours_worked": round(sum(closed_hours) / len(closed_hours), 2) if closed_hours else 0,
        "late_check_ins": sum(1 for row in rows if row.get("is_late") is True),
        "manual_edits": sum(1 for row in rows if row.get("is_manual_edit") is True),
        "remote_check_ins": remote,
        "onsite_check_ins": onsite,
    }

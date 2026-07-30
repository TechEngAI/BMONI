from decimal import Decimal
from typing import Any

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
    
    Args:
        worker_result: Dict containing worker_id, trust_score, verdict, days_present, hr_decision, hr_note
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
    
    # Look up worker
    workers = db.table("workers").select("*, roles(*)").eq("id", worker_id).limit(1).execute().data
    if not workers:
        return {"success": False, "error": "Worker not found"}
    worker = workers[0]
    
    # Look up active bank account
    bank_rows = db.table("worker_bank_accounts").select("*").eq("worker_id", worker_id).eq("is_active", True).limit(1).execute().data
    if not bank_rows:
        return {"success": False, "error": "No active bank account", "code": "NO_ACTIVE_BANK_ACCOUNT"}
    bank = bank_rows[0]
    
    # Calculate salary
    role = worker.get("roles") or {}
    gross = _money(role.get("gross_salary"))
    deductions = _money(role.get("pension_deduct")) + _money(role.get("health_deduct")) + _money(role.get("other_deductions"))
    net_pay = gross - deductions
    
    if net_pay <= 0:
        return {"success": False, "error": "Net pay is zero or negative", "code": "ZERO_NET_PAY"}
    
    amount_ngn = float(net_pay)
    
    # Generate reference/idempotency key if not provided
    if not reference:
        import time
        reference = f"GG-PAY-{run_id[:8].upper()}-{worker_id[:8].upper()}-{int(time.time())}"
    
    # Check for existing receipt with this reference (idempotency)
    existing = db.table("payment_receipts").select("*").eq("squad_reference", reference).limit(1).execute().data
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
                    "squad_reference": reference,
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
                    "squad_status": "PENDING",
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
        db.table("payment_receipts").update({"squad_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
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
        db.table("payment_receipts").update({"squad_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
        return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}
    except ValueError as exc:
        error_msg = f"Invalid input: {exc}"
        db.table("payment_receipts").update({"squad_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
        return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}
    
    # Handle success
    if result["status"] == "SUCCESS":
        transaction_id = result.get("transaction_id")
        db.table("payment_receipts").update({
            "squad_tx_id": transaction_id,
            "squad_status": "PAID",
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
    db.table("payment_receipts").update({"squad_status": "FAILED", "failure_reason": error_msg}).eq("id", receipt["id"]).execute()
    return {"success": False, "error": error_msg, "receipt_id": receipt["id"], "amount_ngn": amount_ngn}

from datetime import UTC, datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from fuzzywuzzy import fuzz

from app.admin.service import notify_admins
from app.auth.service import write_audit
from app.database import get_supabase
from app.errors import AppError
from app.profile import calculate_completeness, missing_profile_fields
from app.bmoni.client import verify_nigerian_account
from app.worker.schemas import BankChangeRequest, BankLookupRequest, BankSubmitRequest, WorkerProfileUpdate


def _public_worker(worker: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in worker.items() if not key.startswith("_")}


def _require_row(data: Any, code: str, message: str) -> dict[str, Any]:
    if not data:
        raise AppError(500, code, message)
    return data[0] if isinstance(data, list) else data


async def get_profile(worker: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated worker's profile."""

    db = get_supabase()
    result = (
        db.table("workers")
        .select("*, roles(role_name, department), worker_bank_accounts(*)")
        .eq("id", worker["id"])
        .limit(1)
        .execute()
    )
    rows = result.data if result is not None else None
    profile = rows[0] if rows else worker
    public_profile = _public_worker(profile)
    public_profile["missing_optional_fields"] = missing_profile_fields(profile)
    return public_profile


async def update_profile(worker: dict[str, Any], payload: WorkerProfileUpdate) -> dict[str, Any]:
    """Update optional worker profile fields and recalculate completeness."""

    db = get_supabase()
    before = worker.copy()
    update_data = payload.model_dump(exclude_unset=True)
    merged = {**worker, **jsonable_encoder(update_data)}
    update_data["completeness_score"] = calculate_completeness(merged)
    update_result = db.table("workers").update(jsonable_encoder(update_data)).eq("id", worker["id"]).execute()
    updated = _require_row(update_result.data, "DATABASE_UPDATE_FAILED", "Could not update profile. Please try again.")
    await write_audit(worker["id"], "worker", "WORKER_PROFILE_UPDATED", worker["id"], "worker", {"before": _public_worker(before), "after": _public_worker(updated)})
    return _public_worker(updated)


async def bank_lookup(payload: BankLookupRequest) -> dict[str, Any]:
    """Look up account details through BMONI without saving them."""

    result = await verify_nigerian_account(payload.account_number, payload.bank_code)
    return {"account_name": result["account_name"], "bank_name": result.get("bank_name")}


def _name_match_score(account_name: str, worker: dict[str, Any]) -> int:
    middle_name = worker.get("middle_name") or ""
    forward = f"{worker['first_name']} {middle_name} {worker['last_name']}".strip()
    reverse = f"{worker['last_name']} {worker['first_name']} {middle_name}".strip()
    return max(fuzz.token_sort_ratio(account_name.upper(), forward.upper()), fuzz.token_sort_ratio(account_name.upper(), reverse.upper()))


async def submit_bank(worker: dict[str, Any], payload: BankSubmitRequest) -> dict[str, Any]:
    """Save a bank account and classify the fuzzy name match result."""

    db = get_supabase()
    lookup = await verify_nigerian_account(payload.account_number, payload.bank_code)
    squad_account_name = lookup["account_name"]
    if payload.confirmed_account_name.strip().upper() != squad_account_name.strip().upper():
        raise AppError(422, "BANK_LOOKUP_FAILED", "Confirmed account name does not match latest bank verification.", "confirmed_account_name")
    score = _name_match_score(squad_account_name, worker)
    if score >= 85:
        match_status = "AUTO_VERIFIED"
        bank_verified = True
        worker_status = "ACTIVE"
    elif score >= 60:
        match_status = "MANUAL_REVIEW"
        bank_verified = False
        worker_status = "PENDING_BANK"
    else:
        match_status = "REJECTED"
        bank_verified = False
        worker_status = "PENDING_BANK"

    existing = db.table("worker_bank_accounts").select("*").eq("worker_id", worker["id"]).eq("is_active", True).execute().data
    if existing:
        db.table("worker_bank_accounts").update({"is_active": False}).eq("worker_id", worker["id"]).execute()

    bank_result = db.table("worker_bank_accounts").insert(
        {
            "worker_id": worker["id"],
            "bank_name": payload.bank_name,
            "bank_code": payload.bank_code,
            "account_number": payload.account_number,
            "account_name": squad_account_name,
            "match_score": score,
            "match_status": match_status,
            "is_active": True,
            "verified_at": datetime.now(UTC).isoformat() if bank_verified else None,
        }
    ).execute()
    bank_account = _require_row(bank_result.data, "DATABASE_INSERT_FAILED", "Could not save bank account. Please try again.")
    worker_update = db.table("workers").update({"bank_verified": bank_verified, "status": worker_status}).eq("id", worker["id"]).execute()
    updated_worker = _require_row(worker_update.data, "DATABASE_UPDATE_FAILED", "Could not update bank verification status.")

    if existing:
        db.table("bank_account_history").insert(
            {
                "worker_id": worker["id"],
                "old_account": existing[0]["account_number"],
                "new_account": payload.account_number,
                "old_bank_code": existing[0]["bank_code"],
                "new_bank_code": payload.bank_code,
                "reason": "Worker submitted replacement bank account",
            }
        ).execute()

    await write_audit(worker["id"], "worker", "BANK_ACCOUNT_ADDED", worker["id"], "worker", {"bank_account": bank_account, "match_score": score})
    if match_status == "MANUAL_REVIEW":
        await notify_admins(
            worker["company_id"],
            "Worker bank account requires review",
            f"<p>{worker['first_name']} {worker['last_name']} submitted a bank account with match score {score}.</p>",
        )
    if match_status == "REJECTED":
        raise AppError(400, "BANK_NAME_MISMATCH", "Bank account name does not match your registered name.", "account_name")
    return {"bank_account": bank_account, "worker": _public_worker(updated_worker), "match_score": score}


async def current_bank(worker: dict[str, Any]) -> dict[str, Any]:
    """Return the worker's active bank account and verification status."""

    rows = get_supabase().table("worker_bank_accounts").select("*").eq("worker_id", worker["id"]).eq("is_active", True).limit(1).execute().data
    return {"bank_account": rows[0] if rows else None, "bank_verified": worker["bank_verified"], "status": worker["status"]}


async def request_bank_change(worker: dict[str, Any], payload: BankChangeRequest) -> dict[str, Any]:
    """Record a bank change request for admin review."""

    lookup = await verify_nigerian_account(payload.new_account_number, payload.new_bank_code)
    current = get_supabase().table("worker_bank_accounts").select("*").eq("worker_id", worker["id"]).eq("is_active", True).limit(1).execute().data
    metadata = {
        "requested_account": {**payload.model_dump(), "account_name": lookup["account_name"]},
        "current_account": current[0] if current else None,
        "reason": payload.reason,
    }
    get_supabase().table("bank_account_history").insert(
        {
            "worker_id": worker["id"],
            "old_account": current[0]["account_number"] if current else None,
            "new_account": payload.new_account_number,
            "old_bank_code": current[0]["bank_code"] if current else None,
            "new_bank_code": payload.new_bank_code,
            "reason": payload.reason,
        }
    ).execute()
    await write_audit(worker["id"], "worker", "BANK_CHANGE_REQUEST", worker["id"], "worker", metadata)
    await notify_admins(worker["company_id"], "Worker requested bank account change", f"<p>{worker['first_name']} {worker['last_name']} requested a bank account change.</p>")
    return {"requested": True, "message": "Bank account change request submitted. Your administrator will review it."}

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fastapi.encoders import jsonable_encoder

from app.auth.schemas import RefreshRequest
from app.auth.service import write_audit
from app.config import get_settings
from app.database import get_supabase, get_supabase_admin_client, get_supabase_auth_client
from app.errors import AppError
from app.hr.schemas import (
    HRCreateRequest,
    HRForgotPasswordRequest,
    HRLoginRequest,
    HRResetPasswordRequest,
)
from app.squad.client import requery_transfer


def _public_hr(hr: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in hr.items() if not key.startswith("_")}


def _auth_user_id(response: Any) -> str:
    user = getattr(response, "user", None)
    if not user:
        raise AppError(502, "AUTH_PROVIDER_ERROR", "Supabase Auth did not return a user.")
    return str(user.id)


def _session(response: Any) -> Any:
    session = getattr(response, "session", None)
    if not session:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.")
    return session


def _require_row(data: Any, code: str, message: str) -> dict[str, Any]:
    if not data:
        raise AppError(500, code, message)
    return data[0] if isinstance(data, list) else data


def _email_in_use(email: str) -> bool:
    db = get_supabase()
    for table in ("admins", "workers", "hr_officers"):
        result = db.table(table).select("id").eq("email", email).execute()
        if result.data and len(result.data) > 0:
            return True
    return False


def _is_email_not_verified_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "email not confirmed" in text or "email_not_confirmed" in text or "email not verified" in text


async def create_hr_officer(admin: dict[str, Any], payload: HRCreateRequest) -> dict[str, Any]:
    db = get_supabase()
    settings = get_settings()
    email = str(payload.email).lower()
    if _email_in_use(email):
        raise AppError(409, "HR_ALREADY_EXISTS", "This email is already in use.", "email")
    try:
        invite = get_supabase_admin_client().auth.admin.invite_user_by_email(
            email,
            options={
                "data": {"user_type": "hr", "company_id": admin["company_id"]},
                "redirect_to": f"{settings.frontend_url}/auth/confirm",
            },
        )
    except TypeError:
        invite = get_supabase_admin_client().auth.admin.invite_user_by_email(
            email,
            {
                "data": {"user_type": "hr", "company_id": admin["company_id"]},
                "email_redirect_to": f"{settings.frontend_url}/hr/verify?email={email}",
            },
        )
    except Exception as exc:
        raise AppError(400, "AUTH_INVITE_FAILED", "Unable to send HR invitation.") from exc

    hr_result = (
        db.table("hr_officers")
        .insert(
            jsonable_encoder(
                {
                    "auth_user_id": _auth_user_id(invite),
                    "company_id": admin["company_id"],
                    "first_name": payload.first_name,
                    "last_name": payload.last_name,
                    "email": email,
                    "phone_number": payload.phone_number,
                    "created_by": admin["id"],
                }
            )
        )
        .execute()
    )
    hr = _require_row(hr_result.data, "DATABASE_INSERT_FAILED", "Could not create HR profile. Please try again.")
    await write_audit(admin["id"], "admin", "HR_OFFICER_CREATED", hr["id"], "hr_officer", {"email": email})
    return {"hr_officer": hr}


async def list_hr_officers(admin: dict[str, Any]) -> dict[str, Any]:
    result = (
        get_supabase()
        .table("hr_officers")
        .select("id, first_name, last_name, email, status, last_login, created_at")
        .eq("company_id", admin["company_id"])
        .order("created_at", desc=True)
        .execute()
    )
    rows = getattr(result, "data", None) or []
    return {"hr_officers": rows}


async def get_company_hr(admin: dict[str, Any], hr_id: UUID) -> dict[str, Any]:
    result = get_supabase().table("hr_officers").select("*").eq("id", str(hr_id)).eq("company_id", admin["company_id"]).limit(1).execute()
    rows = getattr(result, "data", None) or []
    if not rows:
        raise AppError(404, "HR_NOT_FOUND", "HR officer does not exist for this company.")
    return rows[0]


async def suspend_hr(admin: dict[str, Any], hr_id: UUID) -> dict[str, Any]:
    db = get_supabase()
    hr = await get_company_hr(admin, hr_id)
    try:
        get_supabase_admin_client().auth.admin.update_user_by_id(hr["auth_user_id"], {"ban_duration": "876600h"})
    except Exception as exc:
        raise AppError(400, "AUTH_UPDATE_FAILED", "Unable to suspend HR auth account.") from exc
    updated_result = db.table("hr_officers").update({"status": "SUSPENDED"}).eq("id", str(hr_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not suspend HR officer.")
    await write_audit(admin["id"], "admin", "HR_OFFICER_SUSPENDED", str(hr_id), "hr_officer", {"email": hr["email"]})
    return updated


async def reactivate_hr(admin: dict[str, Any], hr_id: UUID) -> dict[str, Any]:
    db = get_supabase()
    hr = await get_company_hr(admin, hr_id)
    try:
        get_supabase_admin_client().auth.admin.update_user_by_id(hr["auth_user_id"], {"ban_duration": "none"})
    except Exception as exc:
        raise AppError(400, "AUTH_UPDATE_FAILED", "Unable to reactivate HR auth account.") from exc
    updated_result = db.table("hr_officers").update({"status": "ACTIVE"}).eq("id", str(hr_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not reactivate HR officer.")
    await write_audit(admin["id"], "admin", "HR_OFFICER_REACTIVATED", str(hr_id), "hr_officer", {"email": hr["email"]})
    return updated


async def delete_hr(admin: dict[str, Any], hr_id: UUID) -> dict[str, Any]:
    db = get_supabase()
    hr = await get_company_hr(admin, hr_id)
    try:
        get_supabase_admin_client().auth.admin.delete_user(hr["auth_user_id"])
    except Exception as exc:
        raise AppError(400, "AUTH_DELETE_FAILED", "Unable to delete HR auth account.") from exc
    db.table("hr_officers").delete().eq("id", str(hr_id)).execute()
    await write_audit(admin["id"], "admin", "HR_OFFICER_DELETED", str(hr_id), "hr_officer", {"email": hr["email"]})
    return {"deleted": True}


async def login(payload: HRLoginRequest) -> dict[str, Any]:
    db = get_supabase()
    try:
        response = get_supabase_auth_client().auth.sign_in_with_password({"email": str(payload.email).strip().lower(), "password": payload.password})
    except Exception as exc:
        print(f"HR login error for {payload.email}: {exc}")
        if _is_email_not_verified_error(exc):
            raise AppError(403, "EMAIL_NOT_VERIFIED", "Please verify your email before logging in.") from exc
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.") from exc
    user = getattr(response, "user", None)
    session = _session(response)
    if not user:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.")
    profile_result = db.table("hr_officers").select("*").eq("auth_user_id", user.id).maybe_single().execute()
    if not profile_result.data:
        raise AppError(403, "UNAUTHORIZED", "This account does not have HR access.")
    hr = profile_result.data
    if hr.get("status") != "ACTIVE":
        raise AppError(403, "ACCOUNT_SUSPENDED", "Account suspended.")
    update_result = db.table("hr_officers").update({"last_login": datetime.now(UTC).isoformat()}).eq("id", hr["id"]).execute()
    hr = _require_row(update_result.data, "DATABASE_UPDATE_FAILED", "Could not update last login.")
    await write_audit(hr["id"], "hr", "LOGIN", hr["id"], "hr_officer", {})
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user_type": "hr",
        "hr_profile": {
            "id": hr["id"],
            "first_name": hr["first_name"],
            "last_name": hr["last_name"],
            "email": hr["email"],
            "company_id": hr["company_id"],
        },
    }


async def logout(hr: dict[str, Any]) -> dict[str, Any]:
    try:
        get_supabase_admin_client().auth.admin.sign_out(hr["_access_token"])
    except Exception:
        try:
            get_supabase_auth_client().auth.sign_out()
        except Exception as exc:
            raise AppError(400, "LOGOUT_FAILED", "Unable to sign out the current session.") from exc
    return {"logged_out": True}


async def refresh_access_token(payload: RefreshRequest) -> dict[str, Any]:
    try:
        response = get_supabase_auth_client().auth.refresh_session(payload.refresh_token)
    except TypeError:
        response = get_supabase_auth_client().auth.refresh_session({"refresh_token": payload.refresh_token})
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Refresh token is invalid or expired.") from exc
    session = _session(response)
    return {"access_token": session.access_token, "refresh_token": session.refresh_token, "token_type": "bearer"}


async def forgot_password(payload: HRForgotPasswordRequest) -> dict[str, Any]:
    try:
        get_supabase_auth_client().auth.reset_password_for_email(str(payload.email).lower())
    except Exception as exc:
        raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to send password reset email.") from exc
    return {"sent": True}


async def reset_password(payload: HRResetPasswordRequest) -> dict[str, Any]:
    try:
        user_response = get_supabase_auth_client().auth.get_user(payload.access_token)
        user = getattr(user_response, "user", None)
        if not user:
            raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to reset password with the provided token.")
        get_supabase_admin_client().auth.admin.update_user_by_id(str(user.id), {"password": payload.new_password})
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to reset password with the provided token.") from exc
    return {"updated": True}


async def list_payment_receipts(hr: dict[str, Any], page: int = 1, per_page: int = 20) -> dict[str, Any]:
    """List payment receipts for the HR's company."""
    db = get_supabase()
    offset = (page - 1) * per_page
    result = (
        db.table("payment_receipts")
        .select(
            "id, payroll_run_id, worker_id, squad_reference, squad_tx_id, squad_status, gross_salary, total_deductions, net_pay, amount_kobo, bank_account_number, bank_code, bank_name, account_name, trust_score, verdict, days_present, hr_decision, hr_note, paid_at, failure_reason, month_year, created_at"
        )
        .eq("company_id", hr["company_id"])
        .order("created_at", desc=True)
        .range(offset, offset + per_page - 1)
        .execute()
    )
    receipts = result.data or []
    # Get total count
    count_result = db.table("payment_receipts").select("id", count="exact").eq("company_id", hr["company_id"]).execute()
    total = count_result.count or 0
    return {"receipts": receipts, "total": total, "page": page, "per_page": per_page}


async def get_payment_receipt(hr: dict[str, Any], receipt_id: UUID) -> dict[str, Any]:
    """Get a specific payment receipt."""
    db = get_supabase()
    result = db.table("payment_receipts").select("*").eq("id", str(receipt_id)).eq("company_id", hr["company_id"]).execute()
    if not result.data:
        raise AppError(404, "RECEIPT_NOT_FOUND", "Payment receipt not found.")
    return result.data[0]


async def update_receipt_decision(hr: dict[str, Any], receipt_id: UUID, decision: str, note: str | None = None) -> dict[str, Any]:
    """Update HR decision on a payment receipt."""
    if decision not in ["APPROVED", "REJECTED", "PENDING"]:
        raise AppError(400, "INVALID_DECISION", "Decision must be APPROVED, REJECTED, or PENDING.")
    db = get_supabase()
    receipt = await get_payment_receipt(hr, receipt_id)
    update_data = {"hr_decision": decision}
    if note is not None:
        update_data["hr_note"] = note
    updated_result = db.table("payment_receipts").update(update_data).eq("id", str(receipt_id)).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not update receipt decision.")
    await write_audit(hr["id"], "hr", "RECEIPT_DECISION_UPDATED", str(receipt_id), "payment_receipt", {"decision": decision, "note": note})
    return updated


async def requery_receipt_status(hr: dict[str, Any], receipt_id: UUID) -> dict[str, Any]:
    """Re-query the status of a payment receipt from Squad."""
    db = get_supabase()
    receipt = await get_payment_receipt(hr, receipt_id)
    if not receipt.get("squad_reference"):
        raise AppError(400, "NO_REFERENCE", "Receipt has no Squad reference to requery.")
    try:
        squad_data = await requery_transfer(receipt["squad_reference"])
    except AppError as exc:
        raise AppError(exc.status_code, exc.code, f"Requery failed: {exc.message}") from exc
    # Map Squad status to our status
    squad_status = squad_data.get("transaction_status", "").upper()
    if squad_status == "SUCCESS":
        our_status = "SUCCESS"
    elif squad_status in ["FAILED", "REVERSED"]:
        our_status = "FAILED"
    else:
        our_status = "PENDING"
    # Update the receipt
    update_data = {"squad_status": our_status}
    if squad_data.get("nip_transaction_reference"):
        update_data["squad_tx_id"] = squad_data["nip_transaction_reference"]
    if our_status == "SUCCESS" and not receipt.get("paid_at"):
        from datetime import UTC, datetime
        update_data["paid_at"] = datetime.now(UTC).isoformat()
    elif our_status == "FAILED":
        update_data["failure_reason"] = squad_data.get("response_description") or "Failed via requery"
    updated_result = db.table("payment_receipts").update(update_data).eq("id", str(receipt_id)).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not update receipt status.")
    await write_audit(hr["id"], "hr", "RECEIPT_STATUS_REQUERIED", str(receipt_id), "payment_receipt", {"squad_status": squad_status, "our_status": our_status})
    return {"receipt": updated, "squad_data": squad_data}

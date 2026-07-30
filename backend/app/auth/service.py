from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi.encoders import jsonable_encoder

from app.auth.schemas import (
    AdminRegisterRequest,
    ForgotPasswordRequest,
    LoginRequest,
    OtpVerifyRequest,
    RefreshRequest,
    ResendOtpRequest,
    ResetPasswordRequest,
    WorkerRegisterRequest,
)
from app.config import get_settings
from app.database import get_supabase, get_supabase_admin_client, get_supabase_auth_client
from app.errors import AppError
from app.profile import calculate_completeness

UserType = Literal["admin", "worker"]


def _require_db_result(result: Any, message: str = "Database operation returned no response.") -> Any:
    if result is None:
        raise AppError(500, "DATABASE_NO_RESPONSE", message)
    return result


def _safe_db_result(result: Any, context: str) -> Any:
    if result is None:
        print(f"Supabase database returned no response during {context}.")
        return None
    return result


def _auth_client():
    return get_supabase_auth_client().auth


def _admin_auth_client():
    return get_supabase_admin_client().auth.admin


def _is_email_not_verified_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "email not confirmed" in text or "email_not_confirmed" in text or "email not verified" in text


def _ensure_email_channel(verif_channel: str | None) -> None:
    if verif_channel and verif_channel != "email":
        raise AppError(400, "PHONE_VERIFICATION_NOT_CONFIGURED", "Phone verification is not configured. Use email verification.")


async def sign_in_with_otp(email: str, user_type: UserType, should_create_user: bool = True) -> dict[str, Any]:
    """Send a passwordless Supabase email OTP using the anon key client."""

    normalized_email = email.lower()
    settings = get_settings()
    try:
        _auth_client().sign_in_with_otp(
            {
                "email": normalized_email,
                "options": {
                    "should_create_user": should_create_user,
                    "email_redirect_to": f"{settings.frontend_url}/{user_type}/verify?email={normalized_email}",
                },
            }
        )
    except TypeError:
        _auth_client().sign_in_with_otp({"email": normalized_email})
    except Exception as exc:
        raise AppError(400, "OTP_SEND_FAILED", "Unable to send verification code.") from exc
    return {"sent": True}


def _resend_signup_otp(email: str, user_type: UserType) -> None:
    """Resend a signup confirmation OTP for a user created with sign_up()."""

    settings = get_settings()
    redirect_to = f"{settings.frontend_url}/{user_type}/verify?email={email}"
    try:
        _auth_client().resend(
            {
                "type": "signup",
                "email": email,
                "options": {"email_redirect_to": redirect_to},
            }
        )
    except TypeError:
        _auth_client().resend({"type": "signup", "email": email})


def _auth_user_id(auth_response: Any) -> str:
    user = getattr(auth_response, "user", None)
    if not user:
        raise AppError(502, "AUTH_PROVIDER_ERROR", "Supabase Auth did not return a user.")
    return str(user.id)


def _auth_session(auth_response: Any) -> Any:
    session = getattr(auth_response, "session", None)
    if not session:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.")
    return session


def _signup_options(user_type: UserType, first_name: str, last_name: str, email: str) -> dict[str, Any]:
    settings = get_settings()
    return {
        "data": {
            "user_type": user_type,
            "first_name": first_name,
            "last_name": last_name,
        },
        "email_redirect_to": f"{settings.frontend_url}/{user_type}/verify?email={email}",
    }


def _table_for(user_type: UserType) -> str:
    return "admins" if user_type == "admin" else "workers"


def _public_profile(profile: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in profile.items() if not key.startswith("_")}


def _user_email(user: Any, fallback: str | None = None) -> str | None:
    email = getattr(user, "email", None) or fallback
    return str(email).lower() if email else None


def _email_exists(table: str, email: str) -> bool:
    try:
        result = get_supabase().table(table).select("id").eq("email", email.lower()).execute()
    except Exception as exc:
        print(f"Email existence check failed for {table}: {exc}")
        return False
    if result is None:
        print(f"Email existence check returned no response for {table}; continuing signup.")
        return False
    return bool(result.data and len(result.data) > 0)


def _phone_exists(table: str, phone_number: str | None) -> bool:
    if not phone_number:
        return False
    try:
        result = get_supabase().table(table).select("id").eq("phone_number", phone_number).execute()
    except Exception as exc:
        print(f"Phone existence check failed for {table}: {exc}")
        return False
    if result is None:
        print(f"Phone existence check returned no response for {table}; continuing signup.")
        return False
    return bool(result.data and len(result.data) > 0)


def _require_inserted(row: Any, code: str, message: str) -> Any:
    if not row:
        raise AppError(500, code, message)
    return row[0] if isinstance(row, list) else row


def _delete_auth_user_quietly(auth_user_id: str | None) -> None:
    if not auth_user_id:
        return
    try:
        _admin_auth_client().delete_user(auth_user_id)
    except Exception as exc:
        print(f"Failed to roll back Supabase auth user {auth_user_id}: {exc}")


async def register_admin(payload: AdminRegisterRequest) -> dict[str, Any]:
    """Register an admin with Supabase Auth and create the linked company profile."""

    db = get_supabase()
    email = str(payload.email).lower()
    if _email_exists("admins", email):
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "An admin with this email already exists.", "email")
    if _phone_exists("admins", payload.phone_number):
        raise AppError(409, "PHONE_ALREADY_EXISTS", "An admin with this phone number already exists.", "phone_number")
    _ensure_email_channel(payload.verif_channel)

    auth_user_id: str | None = None
    try:
        auth_response = _auth_client().sign_up(
            {
                "email": email,
                "password": payload.password,
                "options": _signup_options("admin", payload.first_name, payload.last_name, email),
            }
        )
        auth_user_id = _auth_user_id(auth_response)
    except Exception as exc:
        print(f"Admin sign_up failed for {email}: {exc}")
        raise AppError(400, "AUTH_SIGNUP_FAILED", "Unable to create Supabase Auth user.") from exc

    try:
        company_result = db.table("companies").insert({"name": payload.company_name, "size": payload.company_size, "industry": payload.industry}).execute()
        _require_db_result(company_result)
        company = _require_inserted(company_result.data, "DATABASE_INSERT_FAILED", "Could not create company. Please try again.")
        admin_payload = {
            "auth_user_id": auth_user_id,
            "company_id": company["id"],
            "first_name": payload.first_name,
            "last_name": payload.last_name,
            "middle_name": payload.middle_name,
            "email": email,
            "phone_number": payload.phone_number,
            "gender": payload.gender,
            "date_of_birth": payload.date_of_birth,
            "status": "ACTIVE",
            "verif_channel": payload.verif_channel,
        }
        admin_result = db.table("admins").insert(jsonable_encoder(admin_payload)).execute()
        _require_db_result(admin_result)
        admin = _require_inserted(admin_result.data, "DATABASE_INSERT_FAILED", "Could not create admin profile. Please try again.")
        try:
            _resend_signup_otp(email, "admin")
        except Exception as otp_err:
            print(f"Admin signup OTP resend failed for {email}: {otp_err}")
        await write_audit(admin["id"], "admin", "CREATE_COMPANY", company["id"], "company", {"after": company})
        return {"admin": _public_profile(admin), "company": company}
    except AppError:
        _delete_auth_user_quietly(auth_user_id)
        raise
    except Exception as exc:
        _delete_auth_user_quietly(auth_user_id)
        print(f"Registration error for admin {email}: {exc}")
        raise AppError(500, "REGISTRATION_FAILED", "Registration failed. Please try again.") from exc


async def register_worker(payload: WorkerRegisterRequest) -> dict[str, Any]:
    """Register a worker with Supabase Auth using a valid role invite code."""

    db = get_supabase()
    email = str(payload.email).lower()
    try:
        role_result = db.table("roles").select("*").eq("invite_code", payload.invite_code).eq("code_active", True).execute()
    except Exception as exc:
        print(f"Invite code lookup failed: {exc}")
        raise AppError(400, "INVALID_INVITE_CODE", "Invalid or expired invite code.", "invite_code") from exc
    if role_result is None or not role_result.data:
        raise AppError(400, "INVALID_INVITE_CODE", "Invalid or expired invite code.", "invite_code")
    role = role_result.data[0]
    if int(role["headcount_filled"]) >= int(role["headcount_max"]):
        raise AppError(400, "ROLE_FULL", "This role has no available headcount slots.")
    if _email_exists("workers", email):
        raise AppError(409, "EMAIL_ALREADY_EXISTS", "A worker with this email already exists.", "email")
    if _phone_exists("workers", payload.phone_number):
        raise AppError(409, "PHONE_ALREADY_EXISTS", "A worker with this phone number already exists.", "phone_number")
    _ensure_email_channel(payload.verif_channel)

    auth_user_id: str | None = None
    try:
        auth_response = _auth_client().sign_up(
            {
                "email": email,
                "password": payload.password,
                "options": _signup_options("worker", payload.first_name, payload.last_name, email),
            }
        )
        auth_user_id = _auth_user_id(auth_response)
    except Exception as exc:
        raise AppError(400, "AUTH_SIGNUP_FAILED", "Unable to create Supabase Auth user.") from exc

    try:
        worker_payload = payload.model_dump(exclude={"password", "confirm_password", "invite_code"})
        worker_payload["auth_user_id"] = auth_user_id
        worker_payload["email"] = email
        worker_payload["company_id"] = role["company_id"]
        worker_payload["role_id"] = role["id"]
        worker_payload["status"] = "PENDING_BANK"
        worker_payload["completeness_score"] = calculate_completeness(worker_payload)
        worker_result = db.table("workers").insert(jsonable_encoder(worker_payload)).execute()
        if worker_result is None:
            print(f"Worker insert returned no response for {email}; checking whether the profile was created.")
            lookup_result = db.table("workers").select("*").eq("auth_user_id", auth_user_id).execute()
            worker = lookup_result.data[0] if lookup_result is not None and lookup_result.data else None
            if not worker:
                lookup_result = db.table("workers").select("*").eq("email", email).execute()
                worker = lookup_result.data[0] if lookup_result is not None and lookup_result.data else None
            if not worker:
                raise AppError(500, "DATABASE_INSERT_FAILED", "Could not create worker profile. Please try again.")
        else:
            worker = _require_inserted(worker_result.data, "DATABASE_INSERT_FAILED", "Could not create worker profile. Please try again.")
        role_update = db.table("roles").update({"headcount_filled": int(role["headcount_filled"]) + 1}).eq("id", role["id"]).execute()
        if role_update is None:
            print(f"Role headcount update returned no response for role {role['id']}; worker signup will continue.")
        elif not role_update.data:
            print(f"Role headcount update returned no data for role {role['id']}; worker signup will continue.")
        try:
            _resend_signup_otp(email, "worker")
        except Exception as otp_err:
            print(f"Worker signup OTP resend failed for {email}: {otp_err}")
        await write_audit(worker["id"], "worker", "REGISTER_WORKER", worker["id"], "worker", {"role_id": role["id"]})
        return {"worker": _public_profile(worker), "role": role}
    except AppError:
        _delete_auth_user_quietly(auth_user_id)
        raise
    except Exception as exc:
        _delete_auth_user_quietly(auth_user_id)
        print(f"Registration error for worker {email}: {exc}")
        raise AppError(500, "REGISTRATION_FAILED", "Registration failed. Please try again.") from exc


async def login_user(user_type: UserType, payload: LoginRequest) -> dict[str, Any]:
    """Authenticate with Supabase Auth and return the linked GhostGuard profile."""

    db = get_supabase()
    try:
        auth_response = _auth_client().sign_in_with_password({"email": str(payload.email).strip().lower(), "password": payload.password})
    except Exception as exc:
        print(f"Login error for {payload.email}: {exc}")
        if _is_email_not_verified_error(exc):
            raise AppError(403, "EMAIL_NOT_VERIFIED", "Please verify your email before logging in.") from exc
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.") from exc

    user = getattr(auth_response, "user", None)
    session = _auth_session(auth_response)
    if not user:
        raise AppError(401, "INVALID_CREDENTIALS", "Invalid credentials.")
    if getattr(user, "email_confirmed_at", None) is None:
        raise AppError(403, "EMAIL_NOT_VERIFIED", "Please verify your email first.")

    profile_result = db.table(_table_for(user_type)).select("*").eq("auth_user_id", user.id).maybe_single().execute()
    _require_db_result(profile_result)
    if not profile_result.data:
        raise AppError(404, "PROFILE_NOT_FOUND", "Account setup incomplete. Contact support.")
    profile = profile_result.data
    if user_type == "admin" and profile.get("status") != "ACTIVE":
        raise AppError(403, "ACCOUNT_SUSPENDED", "Account suspended.")
    if user_type == "worker" and profile.get("status") == "SUSPENDED":
        raise AppError(403, "ACCOUNT_SUSPENDED", "Account suspended.")
    if user_type == "worker" and profile.get("status") == "DELETED":
        raise AppError(403, "ACCOUNT_DELETED", "Account deleted.")

    update_data: dict[str, Any] = {"last_login": datetime.now(UTC).isoformat()}
    if user_type == "worker" and payload.device_id:
        update_data["device_id"] = payload.device_id
    update_result = db.table(_table_for(user_type)).update(update_data).eq("id", profile["id"]).execute()
    _require_db_result(update_result)
    profile = _require_inserted(update_result.data, "DATABASE_UPDATE_FAILED", "Could not update last login.")
    await write_audit(profile["id"], user_type, "LOGIN", profile["id"], user_type, {})
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user_type": user_type,
        "profile": _public_profile(profile),
    }


async def refresh_access_token(payload: RefreshRequest) -> dict[str, Any]:
    """Refresh a Supabase Auth session."""

    try:
        response = _auth_client().refresh_session(payload.refresh_token)
    except TypeError:
        response = _auth_client().refresh_session({"refresh_token": payload.refresh_token})
    except Exception as exc:
        raise AppError(401, "UNAUTHORIZED", "Refresh token is invalid or expired.") from exc
    session = _auth_session(response)
    return {"access_token": session.access_token, "refresh_token": session.refresh_token, "token_type": "bearer"}


async def logout_user(access_token: str) -> dict[str, Any]:
    """Sign out the current Supabase Auth session."""

    try:
        _admin_auth_client().sign_out(access_token)
    except Exception:
        try:
            _auth_client().sign_out()
        except Exception as exc:
            raise AppError(400, "LOGOUT_FAILED", "Unable to sign out the current session.") from exc
    return {"logged_out": True}


async def forgot_password(payload: ForgotPasswordRequest) -> dict[str, Any]:
    """Ask Supabase Auth to send a password reset email."""

    try:
        settings = get_settings()
        try:
            _auth_client().reset_password_for_email(str(payload.email).lower(), {"redirect_to": f"{settings.frontend_url}/reset-password"})
        except TypeError:
            _auth_client().reset_password_for_email(str(payload.email).lower())
    except Exception as exc:
        raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to send password reset email.") from exc
    return {"sent": True}


async def verify_otp(user_type: UserType, payload: OtpVerifyRequest) -> dict[str, Any]:
    """Verify a Supabase signup OTP and return a session.

    Keep this path independent of profile-table reads. The worker/admin profile is
    fetched by protected routes after the token is stored, so a transient DB read
    must not make a valid email code look like a failed verification.
    """

    email = str(payload.email).lower() if payload.email else None
    try:
        if payload.token_hash:
            response = _auth_client().verify_otp({"token_hash": payload.token_hash, "type": payload.type or "signup"})
        else:
            response = _auth_client().verify_otp({"email": email, "token": payload.otp, "type": payload.type or "signup"})
    except Exception as exc:
        raise AppError(400, "INVALID_OTP", "Invalid or expired verification code.") from exc
    session = _auth_session(response)
    user = getattr(response, "user", None)
    if not user:
        raise AppError(400, "INVALID_OTP", "Invalid or expired verification code.")
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "token_type": "bearer",
        "user_type": user_type,
        "profile": {},
        "profile_pending": True,
    }


async def resend_otp(user_type: UserType, payload: ResendOtpRequest) -> dict[str, Any]:
    """Ask Supabase Auth to resend the signup OTP email."""

    email = str(payload.email).lower()
    db = get_supabase()
    table = _table_for(user_type)
    profile_result = db.table(table).select("id, last_otp_sent").eq("email", email).maybe_single().execute()
    profile_result = _safe_db_result(profile_result, f"{user_type} resend OTP profile lookup")
    if profile_result and profile_result.data and profile_result.data.get("last_otp_sent"):
        last_sent = datetime.fromisoformat(str(profile_result.data["last_otp_sent"]).replace("Z", "+00:00"))
        if datetime.now(UTC) - last_sent < timedelta(seconds=60):
            raise AppError(429, "RESEND_TOO_SOON", "Please wait 60 seconds before requesting a new code.")
    try:
        _resend_signup_otp(email, user_type)
        if profile_result and profile_result.data:
            update_result = db.table(table).update({"last_otp_sent": datetime.now(UTC).isoformat()}).eq("id", profile_result.data["id"]).execute()
            _safe_db_result(update_result, f"{user_type} resend OTP timestamp update")
    except Exception as exc:
        raise AppError(400, "OTP_RESEND_FAILED", "Unable to resend verification email.") from exc
    return {"sent": True}


async def reset_password(payload: ResetPasswordRequest) -> dict[str, Any]:
    """Update a user's password using the reset access token from Supabase."""

    try:
        user_response = _auth_client().get_user(payload.access_token)
        user = getattr(user_response, "user", None)
        if not user:
            raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to reset password with the provided token.")
        _admin_auth_client().update_user_by_id(str(user.id), {"password": payload.new_password})
    except Exception as exc:
        if isinstance(exc, AppError):
            raise
        raise AppError(400, "PASSWORD_RESET_FAILED", "Unable to reset password with the provided token.") from exc
    return {"updated": True}


async def write_audit(
    actor_id: str,
    actor_type: str,
    action: str,
    target_id: str | None,
    target_type: str | None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
) -> None:
    """Persist an audit log entry."""

    try:
        result = get_supabase().table("audit_logs").insert(
            {
                "actor_id": actor_id,
                "actor_type": actor_type,
                "action": action,
                "target_id": target_id,
                "target_type": target_type,
                "metadata": metadata or {},
                "ip_address": ip_address,
            }
        ).execute()
        if result is None:
            print(f"Audit log skipped because database returned no response for action {action}.")
    except Exception as exc:
        print(f"Audit log failed for action {action}: {exc}")

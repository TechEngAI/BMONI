from typing import Any
from uuid import UUID
from datetime import datetime, timezone
import random
import string

from fastapi.encoders import jsonable_encoder

from app.admin.schemas import BankReviewRequest, CompanyUpdate, CreateRoleSchema, UpdateRoleSchema, WorkerReassignRequest, WorkerSuspendRequest
from app.auth.service import write_audit
from app.database import get_supabase
from app.errors import AppError


def _generate_code(company_name: str, role_name: str) -> str:
    """Generate a GhostGuard invite code."""

    co = "".join(c for c in company_name.upper() if c.isalnum())[:4].ljust(4, "X")
    ro = "".join(c for c in role_name.upper() if c.isalnum())[:3].ljust(3, "X")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"GG-{co}-{ro}-{suffix}"


def _require_row(data: Any, code: str, message: str) -> dict[str, Any]:
    if not data:
        raise AppError(500, code, message)
    return data[0] if isinstance(data, list) else data


def _require_response(response: Any, code: str, message: str) -> Any:
    if response is None:
        raise AppError(500, code, message)
    error = getattr(response, "error", None)
    if error:
        raise AppError(500, code, f"{message} {error}")
    return response


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None) if response is not None else None


def _unique_invite_code(db: Any, company_name: str, role_name: str, current_code: str | None = None) -> str:
    if not company_name or not role_name:
        raise AppError(400, "INVALID_INPUT", "Company name and role name are required.")
    
    max_attempts = 10
    for attempt in range(max_attempts):
        code = _generate_code(company_name, role_name)
        try:
            existing = _require_response(
                db.table("roles").select("id").eq("invite_code", code).execute(),
                "DATABASE_QUERY_FAILED",
                "Could not verify invite code uniqueness."
            )
            existing_data = _response_data(existing) or []
            if len(existing_data) == 0 and code != current_code:
                return code
        except AppError:
            raise
        except Exception as e:
            raise AppError(500, "DATABASE_QUERY_FAILED", f"Failed to check invite code uniqueness: {str(e)}")
        if attempt == max_attempts - 1:
            raise AppError(500, "CODE_GENERATION_FAILED", "Could not generate unique code. Try again.")
    raise AppError(500, "CODE_GENERATION_FAILED", "Could not generate unique code. Try again.")


def _admin_company_id(current_admin: dict[str, Any]) -> str:
    company_id = current_admin.get("company_id") or current_admin.get("company", {}).get("id")
    if not company_id:
        raise AppError(400, "COMPANY_NOT_FOUND", "Admin has no associated company. Complete company setup first.")
    return company_id


async def get_company(admin: dict[str, Any]) -> dict[str, Any]:
    """Return the authenticated admin's company profile."""

    result = _require_response(
        get_supabase().table("companies").select("*").eq("id", admin["company_id"]).maybe_single().execute(),
        "DATABASE_QUERY_FAILED",
        "Could not fetch company profile. Please try again."
    )
    if result.data is None:
        raise AppError(404, "COMPANY_NOT_FOUND", "Company profile was not found.")
    return result.data


async def update_company(admin: dict[str, Any], payload: CompanyUpdate) -> dict[str, Any]:
    """Update company settings and audit before/after changes."""

    db = get_supabase()
    before = await get_company(admin)
    update_data = payload.model_dump(exclude_unset=True)
    if not update_data:
        return before
    after_result = db.table("companies").update(jsonable_encoder(update_data)).eq("id", admin["company_id"]).execute()
    after = _require_row(after_result.data, "DATABASE_UPDATE_FAILED", "Could not update company. Please try again.")
    await write_audit(admin["id"], "admin", "UPDATE_COMPANY", admin["company_id"], "company", {"before": before, "after": after})
    return after


async def create_role(data: CreateRoleSchema, current_admin: dict[str, Any]) -> dict[str, Any]:
    """Create a new role for the admin's company."""

    db = get_supabase()
    company_id = _admin_company_id(current_admin)

    try:
        company_result = db.table("companies").select("name").eq("id", company_id).single().execute()
        company_name = company_result.data["name"] if company_result.data else "COMP"
    except Exception:
        company_name = "COMP"

    now_iso = datetime.now(timezone.utc).isoformat()
    base_insert_payload = {
        "company_id": company_id,
        "role_name": data.role_name.strip(),
        "department": data.department,
        "grade_level": data.grade_level,
        "headcount_max": data.headcount_max,
        "headcount_filled": 0,
        "gross_salary": float(data.gross_salary),
        "pension_deduct": float(data.pension_deduct or 0),
        "health_deduct": float(data.health_deduct or 0),
        "other_deductions": float(data.other_deductions or 0),
        "work_type": data.work_type or "ONSITE",
        "code_active": True,
        "created_at": now_iso,
        "updated_at": now_iso,
    }

    result = None
    invite_code = ""
    for attempt in range(3):
        invite_code = _unique_invite_code(db, company_name, data.role_name)
        try:
            result = db.table("roles").insert({**base_insert_payload, "invite_code": invite_code}).execute()
            break
        except Exception as e:
            error_str = str(e).lower()
            if "unique" in error_str and "invite_code" in error_str and attempt < 2:
                continue
            print(f"Role insert error: {e}")
            raise AppError(500, "ROLE_CREATE_FAILED", "Failed to create role. Please try again.")

    if not result or not result.data:
        raise AppError(500, "ROLE_CREATE_FAILED", "Role creation returned no data. Check Supabase RLS policies.")

    new_role = result.data[0]

    try:
        db.table("audit_logs").insert({
            "actor_id": current_admin["id"],
            "actor_type": "admin",
            "action": "CREATE_ROLE",
            "target_id": new_role["id"],
            "target_type": "role",
            "metadata": {
                "role_name": data.role_name,
                "headcount_max": data.headcount_max,
                "gross_salary": float(data.gross_salary),
                "invite_code": invite_code,
            },
            "created_at": now_iso,
        }).execute()
    except Exception as audit_err:
        print(f"Audit log failed for role creation: {audit_err}")

    return {
        "success": True,
        "message": f"Role '{data.role_name}' created successfully.",
        "data": new_role,
    }


async def list_roles(admin: dict[str, Any]) -> list[dict[str, Any]]:
    """List roles belonging to the admin's company."""

    company_id = _admin_company_id(admin)
    return get_supabase().table("roles").select("*").eq("company_id", company_id).order("created_at", desc=True).execute().data


async def get_role(admin: dict[str, Any], role_id: UUID) -> dict[str, Any]:
    """Return a single company role."""

    result = get_supabase().table("roles").select("*").eq("id", str(role_id)).eq("company_id", admin["company_id"]).maybe_single().execute()
    if not result.data:
        raise AppError(404, "ROLE_NOT_FOUND", "Role was not found.")
    return result.data


async def update_role(role_id: str | UUID, data: UpdateRoleSchema, current_admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    company_id = _admin_company_id(current_admin)

    existing = db.table("roles").select("*").eq("id", str(role_id)).eq("company_id", company_id).execute()

    if not existing.data:
        raise AppError(404, "ROLE_NOT_FOUND", "Role not found or does not belong to your company.")

    existing_role = existing.data[0]

    update_payload: dict[str, Any] = {}
    if data.role_name is not None:
        update_payload["role_name"] = data.role_name.strip()
    if data.department is not None:
        update_payload["department"] = data.department
    if data.grade_level is not None:
        update_payload["grade_level"] = data.grade_level
    if data.headcount_max is not None:
        if data.headcount_max < existing_role["headcount_filled"]:
            raise AppError(400, "HEADCOUNT_TOO_LOW", f"Cannot set max headcount below current filled count ({existing_role['headcount_filled']}).")
        update_payload["headcount_max"] = data.headcount_max
    if data.gross_salary is not None:
        update_payload["gross_salary"] = float(data.gross_salary)
    if data.pension_deduct is not None:
        update_payload["pension_deduct"] = float(data.pension_deduct)
    if data.health_deduct is not None:
        update_payload["health_deduct"] = float(data.health_deduct)
    if data.other_deductions is not None:
        update_payload["other_deductions"] = float(data.other_deductions)
    if data.work_type is not None:
        update_payload["work_type"] = data.work_type

    if not update_payload:
        return {"success": True, "message": "No changes made.", "data": existing_role}

    update_payload["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = db.table("roles").update(update_payload).eq("id", str(role_id)).execute()

    if not result.data:
        raise AppError(500, "UPDATE_FAILED", "Role update failed.")

    try:
        db.table("audit_logs").insert({
            "actor_id": current_admin["id"],
            "actor_type": "admin",
            "action": "UPDATE_ROLE",
            "target_id": str(role_id),
            "target_type": "role",
            "metadata": {"before": existing_role, "after": update_payload},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as audit_err:
        print(f"Audit log failed for role update: {audit_err}")

    return {"success": True, "message": "Role updated.", "data": result.data[0]}


async def delete_role(role_id: str | UUID, current_admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    company_id = _admin_company_id(current_admin)

    existing = db.table("roles").select("*").eq("id", str(role_id)).eq("company_id", company_id).execute()

    if not existing.data:
        raise AppError(404, "ROLE_NOT_FOUND", "Role not found.")

    existing_role = existing.data[0]

    if existing_role["headcount_filled"] > 0:
        raise AppError(400, "ROLE_HAS_WORKERS", f"Cannot delete a role with {existing_role['headcount_filled']} active worker(s). Reassign them first.")

    db.table("roles").delete().eq("id", str(role_id)).execute()

    try:
        db.table("audit_logs").insert({
            "actor_id": current_admin["id"],
            "actor_type": "admin",
            "action": "DELETE_ROLE",
            "target_id": str(role_id),
            "target_type": "role",
            "metadata": {"role_name": existing_role["role_name"]},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as audit_err:
        print(f"Audit log failed for role deletion: {audit_err}")

    return {"success": True, "message": f"Role '{existing_role['role_name']}' deleted."}


async def regenerate_invite_code(role_id: str | UUID, current_admin: dict[str, Any]) -> dict[str, Any]:
    db = get_supabase()
    company_id = _admin_company_id(current_admin)

    existing = _require_response(
        db.table("roles").select("*").eq("id", str(role_id)).eq("company_id", company_id).execute(),
        "DATABASE_QUERY_FAILED",
        "Could not fetch role. Please try again."
    )

    existing_role_data = _response_data(existing) or []
    if len(existing_role_data) == 0:
        raise AppError(404, "ROLE_NOT_FOUND", "Role not found.")
    existing_role = existing_role_data[0]

    company_result = _require_response(
        db.table("companies").select("name").eq("id", company_id).single().execute(),
        "DATABASE_QUERY_FAILED",
        "Could not fetch company. Please try again."
    )
    company = _response_data(company_result)
    company_name = company["name"] if company else "COMP"

    new_code = _unique_invite_code(db, company_name, existing_role["role_name"], existing_role["invite_code"])

    now_iso = datetime.now(timezone.utc).isoformat()
    result = _require_response(db.table("roles").update({
        "invite_code": new_code,
        "updated_at": now_iso,
    }).eq("id", str(role_id)).eq("company_id", company_id).execute(),
        "DATABASE_UPDATE_FAILED",
        "Could not update invite code. Please try again."
    )
    updated_role = _require_row(_response_data(result), "DATABASE_UPDATE_FAILED", "Invite code update returned no data.")

    try:
        db.table("audit_logs").insert({
            "actor_id": current_admin["id"],
            "actor_type": "admin",
            "action": "REGENERATE_ROLE_CODE",
            "target_id": str(role_id),
            "target_type": "role",
            "metadata": {"old_code": existing_role["invite_code"], "new_code": new_code},
            "created_at": now_iso,
        }).execute()
    except Exception as audit_err:
        print(f"Audit log failed for code regeneration: {audit_err}")

    return {
        "success": True,
        "message": "New invite code generated. Old code is now invalid.",
        "data": {"invite_code": updated_role["invite_code"]},
    }


async def regenerate_role_code(admin: dict[str, Any], role_id: UUID) -> dict[str, Any]:
    return await regenerate_invite_code(role_id, admin)


async def list_workers(
    admin: dict[str, Any],
    role_id: UUID | None,
    status: str | None,
    bank_verified: bool | None,
    search: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    """List company workers with optional filters."""

    query = get_supabase().table("workers").select("*, roles(role_name), worker_bank_accounts(*)").eq("company_id", admin["company_id"])
    if role_id:
        query = query.eq("role_id", str(role_id))
    if status:
        query = query.eq("status", status)
    if bank_verified is not None:
        query = query.eq("bank_verified", bank_verified)
    workers = query.order("created_at", desc=True).execute().data
    if search:
        needle = search.lower()
        workers = [
            worker
            for worker in workers
            if needle in f"{worker.get('first_name', '')} {worker.get('last_name', '')} {worker.get('email', '')}".lower()
        ]
    total = len(workers)
    start = (page - 1) * page_size
    end = start + page_size
    return {"items": workers[start:end], "total": total, "page": page, "page_size": page_size}


async def get_worker(admin: dict[str, Any], worker_id: UUID) -> dict[str, Any]:
    """Return a worker profile with role and bank account details."""

    rows = (
        get_supabase()
        .table("workers")
        .select("*, roles(*), worker_bank_accounts(*), bank_account_history(count)")
        .eq("id", str(worker_id))
        .eq("company_id", admin["company_id"])
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        raise AppError(404, "WORKER_NOT_FOUND", "Worker was not found.")
    return rows[0]


async def review_worker_bank(admin: dict[str, Any], worker_id: UUID, payload: BankReviewRequest) -> dict[str, Any]:
    """Manually approve or reject a worker's bank match."""

    db = get_supabase()
    worker = await get_worker(admin, worker_id)
    approved = payload.action == "approve"
    status = "ACTIVE" if approved else "PENDING_BANK"
    updated_result = db.table("workers").update({"bank_verified": approved, "status": status}).eq("id", str(worker_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not update worker bank status.")
    db.table("worker_bank_accounts").update({"match_status": "MANUALLY_APPROVED" if approved else "REJECTED"}).eq("worker_id", str(worker_id)).eq("is_active", True).execute()
    await write_audit(admin["id"], "admin", "MANUAL_BANK_VERIFY", str(worker_id), "worker", {"before": worker, "after": updated, "note": payload.note})
    return updated


async def suspend_worker(admin: dict[str, Any], worker_id: UUID, payload: WorkerSuspendRequest) -> dict[str, Any]:
    """Suspend a company worker."""

    worker = await get_worker(admin, worker_id)
    updated_result = get_supabase().table("workers").update({"status": "SUSPENDED"}).eq("id", str(worker_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not suspend worker.")
    await write_audit(admin["id"], "admin", "SUSPEND_WORKER", str(worker_id), "worker", {"before": worker, "after": updated, "reason": payload.reason})
    return updated


async def reactivate_worker(admin: dict[str, Any], worker_id: UUID) -> dict[str, Any]:
    """Reactivate a suspended worker."""

    worker = await get_worker(admin, worker_id)
    if worker.get("bank_verified") is not True:
        raise AppError(400, "BANK_NAME_MISMATCH", "Worker bank account must be verified before reactivation.")
    updated_result = get_supabase().table("workers").update({"status": "ACTIVE"}).eq("id", str(worker_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not reactivate worker.")
    await write_audit(admin["id"], "admin", "REACTIVATE_WORKER", str(worker_id), "worker", {"before": worker, "after": updated})
    return updated


async def reassign_worker(admin: dict[str, Any], worker_id: UUID, payload: WorkerReassignRequest) -> dict[str, Any]:
    """Move a worker to a different role while preserving headcount constraints."""

    db = get_supabase()
    worker = await get_worker(admin, worker_id)
    new_role = await get_role(admin, payload.new_role_id)
    if int(new_role["headcount_filled"]) >= int(new_role["headcount_max"]):
        raise AppError(400, "ROLE_FULL", "Target role has no available headcount slots.")
    old_role = await get_role(admin, UUID(worker["role_id"]))
    db.table("roles").update({"headcount_filled": max(0, int(old_role["headcount_filled"]) - 1)}).eq("id", old_role["id"]).execute()
    db.table("roles").update({"headcount_filled": int(new_role["headcount_filled"]) + 1}).eq("id", new_role["id"]).execute()
    updated_result = db.table("workers").update({"role_id": str(payload.new_role_id)}).eq("id", str(worker_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not reassign worker.")
    await write_audit(admin["id"], "admin", "REASSIGN_WORKER", str(worker_id), "worker", {"old_role_id": old_role["id"], "new_role_id": new_role["id"], "before": worker, "after": updated})
    return updated


async def soft_delete_worker(admin: dict[str, Any], worker_id: UUID) -> dict[str, Any]:
    """Soft delete a worker and release the role headcount slot."""

    db = get_supabase()
    worker = await get_worker(admin, worker_id)
    if worker.get("status") != "DELETED":
        role = await get_role(admin, UUID(worker["role_id"]))
        db.table("roles").update({"headcount_filled": max(0, int(role["headcount_filled"]) - 1)}).eq("id", role["id"]).execute()
    updated_result = db.table("workers").update({"status": "DELETED"}).eq("id", str(worker_id)).eq("company_id", admin["company_id"]).execute()
    updated = _require_row(updated_result.data, "DATABASE_UPDATE_FAILED", "Could not delete worker.")
    await write_audit(admin["id"], "admin", "DELETE_WORKER", str(worker_id), "worker", {"before": worker, "after": updated})
    return updated


async def notify_admins(company_id: str, subject: str, html: str) -> None:
    """Store an admin notification audit event for dashboard review."""

    admins = get_supabase().table("admins").select("id").eq("company_id", company_id).eq("status", "ACTIVE").execute().data
    for admin in admins:
        await write_audit(admin["id"], "admin", "ADMIN_NOTIFICATION", None, "notification", {"subject": subject, "html": html})

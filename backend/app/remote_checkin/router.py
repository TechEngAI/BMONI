from typing import Any

from fastapi import APIRouter, Depends, Request

from app.dependencies import get_current_worker
from app.errors import success_response
from app.remote_checkin import service
from app.remote_checkin.schemas import RemoteCheckInRequest

router = APIRouter(tags=["remote_checkin"])


@router.post("/worker/remote/checkin")
async def remote_check_in(
    payload: RemoteCheckInRequest,
    request: Request,
    worker: dict[str, Any] = Depends(get_current_worker),
):
    ip_address = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
    if not ip_address:
        ip_address = request.client.host if request.client else "unknown"
    return success_response(
        await service.check_in(worker, payload.device_fingerprint, ip_address),
        "Remote check-in recorded successfully",
    )

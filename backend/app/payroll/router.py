from io import BytesIO
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import StreamingResponse

from app.dependencies import get_current_hr, get_current_worker
from app.errors import success_response
from app.payroll import service
from app.payroll.schemas import PayrollDecisionRequest
from app.wallet.service import get_wallet_balance

router = APIRouter(tags=["hr-payroll"])


@router.get("/hr/payroll/runs")
async def runs(hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await service.payroll_runs(hr), "Payroll runs retrieved.")


@router.get("/hr/payroll/{run_id}/results")
async def results(run_id: UUID, verdict: str | None = None, page: int = 1, page_size: int = 50, hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await service.payroll_results(hr, run_id, verdict, max(page, 1), min(max(page_size, 1), 100)), "Payroll results retrieved.")


@router.patch("/hr/payroll/{run_id}/worker/{worker_id}/decision")
async def decision(run_id: UUID, worker_id: UUID, payload: PayrollDecisionRequest, hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await service.set_decision(hr, run_id, worker_id, payload), "Payroll decision saved.")


@router.post("/hr/payroll/{run_id}/approve")
async def approve(run_id: UUID, background_tasks: BackgroundTasks, hr: dict[str, Any] = Depends(get_current_hr)):
    data = await service.approve_payroll(hr, run_id)
    background_tasks.add_task(service.disburse_payroll, str(run_id), hr)
    return success_response(data, "Payroll approved. Salary disbursement has started.")


@router.get("/hr/payroll/{run_id}/receipts")
async def receipts(run_id: UUID, bmoni_status: str | None = None, page: int = 1, page_size: int = 50, hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await service.receipts(hr, run_id, bmoni_status, max(page, 1), min(max(page_size, 1), 100)), "Payment receipts retrieved.")


@router.get("/hr/payroll/{run_id}/receipts/download")
async def download_receipts(run_id: UUID, hr: dict[str, Any] = Depends(get_current_hr)):
    csv_text, filename = await service.receipts_csv(hr, run_id)
    return StreamingResponse(BytesIO(csv_text.encode("utf-8")), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.patch("/hr/payroll/{run_id}/receipt/{receipt_id}/retry")
async def retry(run_id: UUID, receipt_id: UUID, hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await service.retry_receipt(hr, run_id, receipt_id), "Payment retry initiated.")


@router.get("/hr/payroll/wallet-balance")
async def hr_wallet_balance(hr: dict[str, Any] = Depends(get_current_hr)):
    return success_response(await get_wallet_balance(hr["company_id"]), "Wallet balance retrieved.")


@router.get("/worker/payslip")
async def payslip(month_year: str | None = None, worker: dict[str, Any] = Depends(get_current_worker)):
    return success_response(await service.worker_payslip(worker, month_year), "Payslip retrieved.")


@router.get("/worker/payslips")
async def payslips(worker: dict[str, Any] = Depends(get_current_worker)):
    return success_response(await service.worker_payslips(worker), "Payslips retrieved.")


@router.post("/webhooks/squad/payout")
async def squad_payout_webhook(request: Request):
    raw_body = await request.body()
    signature = request.headers.get("X-Squad-Encrypted-Body")
    await service.handle_squad_webhook(raw_body, signature)
    return {"success": True}

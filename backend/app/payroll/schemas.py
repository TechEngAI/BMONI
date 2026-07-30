from pydantic import BaseModel


class PayrollDecisionRequest(BaseModel):
    decision: str
    note: str | None = None


class ReceiptRetryResponse(BaseModel):
    success: bool = True
    message: str = "Payment retry initiated."


class SquadWebhookEvent(BaseModel):
    transaction_reference: str | None = None
    transaction_status: str | None = None
    amount: int | float | None = None
    message: str | None = None


class OverrideHoldRequest(BaseModel):
    worker_id: str
    note: str | None = None

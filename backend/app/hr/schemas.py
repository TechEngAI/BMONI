from pydantic import BaseModel, EmailStr, Field


class HRCreateRequest(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    phone_number: str | None = None


class HRRegisterWithCodeRequest(BaseModel):
    invite_code: str = Field(..., min_length=1)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    phone_number: str | None = None


class HRLoginRequest(BaseModel):
    email: EmailStr
    password: str


class HRForgotPasswordRequest(BaseModel):
    email: EmailStr


class HRResetPasswordRequest(BaseModel):
    access_token: str
    new_password: str = Field(..., min_length=8)


class UpdateReceiptDecisionRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(APPROVED|REJECTED|PENDING)$")
    note: str | None = None

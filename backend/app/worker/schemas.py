from datetime import date
from pydantic import BaseModel, Field, field_validator


class WorkerProfileUpdate(BaseModel):
    middle_name: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    home_address: str | None = None
    state_of_origin: str | None = None
    next_of_kin_name: str | None = None
    next_of_kin_phone: str | None = None
    emergency_contact_name: str | None = None
    emergency_contact_phone: str | None = None
    nin: str | None = None
    has_company_device: bool | None = None


class BankLookupRequest(BaseModel):
    account_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    bank_code: str = Field(..., min_length=3, max_length=3, pattern=r"^\d{3}$")

    @field_validator("bank_code", mode="before")
    @classmethod
    def coerce_bank_code(cls, v: any) -> str:
        """Convert integer bank_code to string; ensure numeric pattern."""
        if isinstance(v, int):
            v = str(v)
        if not isinstance(v, str):
            raise ValueError("bank_code must be a string or integer")
        if not v.isdigit():
            raise ValueError("bank_code must contain only digits")
        return v


class BankSubmitRequest(BaseModel):
    account_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    bank_code: str = Field(..., min_length=3, max_length=3, pattern=r"^\d{3}$")
    bank_name: str
    confirmed_account_name: str

    @field_validator("bank_code", mode="before")
    @classmethod
    def coerce_bank_code(cls, v: any) -> str:
        """Convert integer bank_code to string; ensure numeric pattern."""
        if isinstance(v, int):
            v = str(v)
        if not isinstance(v, str):
            raise ValueError("bank_code must be a string or integer")
        if not v.isdigit():
            raise ValueError("bank_code must contain only digits")
        return v


class BankChangeRequest(BaseModel):
    new_account_number: str = Field(..., min_length=10, max_length=10, pattern=r"^\d{10}$")
    new_bank_code: str = Field(..., min_length=3, max_length=3, pattern=r"^\d{3}$")
    reason: str

    @field_validator("new_bank_code", mode="before")
    @classmethod
    def coerce_new_bank_code(cls, v: any) -> str:
        """Convert integer new_bank_code to string; ensure numeric pattern."""
        if isinstance(v, int):
            v = str(v)
        if not isinstance(v, str):
            raise ValueError("new_bank_code must be a string or integer")
        if not v.isdigit():
            raise ValueError("new_bank_code must contain only digits")
        return v

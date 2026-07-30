from pydantic import BaseModel, Field


class RemoteCheckInRequest(BaseModel):
    device_fingerprint: str = Field(..., min_length=1, description="Browser-generated device fingerprint hash")

    class Config:
        extra = "ignore"

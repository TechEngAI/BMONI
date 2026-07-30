import logging

import httpx

from app.config import get_settings
from app.errors import AppError

logger = logging.getLogger(__name__)

BMONI_TIMEOUT = 10.0


def _headers() -> dict[str, str]:
    settings = get_settings()
    return {
        "Content-Type": "application/json",
        "x-api-key": settings.bmoni_api_key,
    }


async def verify_nigerian_account(account_number: str, bank_code: str) -> dict:
    """Verify a Nigerian bank account name via BMONI.

    Calls POST /bank-accounts/verify-nigerian-account.
    Returns a dict with keys: account_number, account_name, bank_name, bank_code.

    Raises ValueError for invalid input, AppError for API failures.
    """

    if not account_number or not account_number.isdigit() or len(account_number) != 10:
        raise ValueError("account_number must be exactly 10 digits.")
    if not bank_code or not bank_code.strip():
        raise ValueError("bank_code must be a non-empty string.")

    settings = get_settings()
    url = f"{settings.bmoni_base_url.rstrip('/')}/bank-accounts/verify-nigerian-account"
    payload = {"accountNumber": account_number.strip(), "bankCode": bank_code.strip()}

    async with httpx.AsyncClient(timeout=BMONI_TIMEOUT) as client:
        try:
            response = await client.post(url, json=payload, headers=_headers())
        except httpx.TimeoutException:
            logger.error("BMONI bank verification timed out for bank %s", bank_code)
            raise AppError(422, "BANK_VERIFY_TIMEOUT", "Bank verification timed out. Try again.")
        except httpx.RequestError as exc:
            logger.error("BMONI request failed for bank verification: %s", exc)
            raise AppError(422, "BANK_VERIFY_UNAVAILABLE", "Could not reach bank verification service.")

    if response.status_code >= 400:
        message = "Bank verification failed."
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or message
        except ValueError:
            message = response.text or message
        logger.error("BMONI bank verify failed: status=%s, message=%s", response.status_code, message)
        raise AppError(422, "BANK_VERIFY_FAILED", message)

    data = response.json()
    account_name = data.get("accountName") or data.get("account_name")
    if not account_name:
        logger.error("BMONI bank verify returned no account_name: %s", data)
        raise AppError(422, "BANK_VERIFY_FAILED", "Bank verification returned no account name.")

    return {
        "account_number": data.get("accountNumber") or data.get("account_number") or account_number,
        "account_name": account_name,
        "bank_name": data.get("bankName") or data.get("bank_name"),
        "bank_code": data.get("bankCode") or data.get("bank_code") or bank_code,
    }

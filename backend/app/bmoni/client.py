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


async def get_smart_wallet_balances() -> list[dict]:
    """Fetch all smart wallet balances for the configured BMONI user.

    Calls GET /v1/users/{userId}/smart-wallets/account/balances.

    Returns a list of wallet balance objects (each typically has
    smartWalletId, currency, availableBalance, ledgerBalance, etc.).

    Raises AppError on failure.
    """
    from app.errors import AppError

    settings = get_settings()
    user_id = settings.bmoni_user_id
    url = f"{settings.bmoni_base_url.rstrip('/')}/v1/users/{user_id}/smart-wallets/account/balances"

    logger.info("BMONI balance request: GET %s", url)

    async with httpx.AsyncClient(timeout=BMONI_TIMEOUT) as client:
        try:
            response = await client.get(url, headers=_headers())
            logger.info("BMONI balance response status: %s", response.status_code)
        except httpx.TimeoutException:
            logger.error("BMONI smart wallet balances timed out for url %s", url)
            raise AppError(502, "BALANCE_TIMEOUT", "Could not fetch wallet balance (timeout).")
        except httpx.RequestError as exc:
            logger.error("BMONI balances request failed for url %s: %s", url, exc)
            raise AppError(502, "BALANCE_UNAVAILABLE", "Could not reach balance service.")

    if response.status_code >= 400:
        message = "Failed to fetch wallet balance."
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or message
        except ValueError:
            message = response.text or message
        logger.error("BMONI balances failed: status=%s, message=%s", response.status_code, message)
        raise AppError(502, "BALANCE_FAILED", message)

    data = response.json()
    logger.info("BMONI balance raw JSON response: %s", data)

    # The API may return a list directly or wrapped in a key
    if isinstance(data, list):
        logger.info("BMONI balances: list of %d entries", len(data))
        return data
    # Some APIs wrap in { "data": [...] } or { "balances": [...] }
    result = data.get("data") or data.get("balances") or data.get("wallets") or []
    logger.info("BMONI balances: extracted %d entries from wrapped response", len(result))
    return result


async def verify_nigerian_account(account_number: str, bank_code: str) -> dict:
    """Verify a Nigerian bank account name via BMONI.

    Calls POST /v1/users/{userId}/bank-accounts/verify-nigerian-account.
    The userId is read from settings.bmoni_user_id.
    Returns a dict with keys: account_number, account_name, bank_name, bank_code.

    Raises ValueError for invalid input, AppError for API failures.
    """

    if not account_number or not account_number.isdigit() or len(account_number) != 10:
        raise ValueError("account_number must be exactly 10 digits.")
    if not bank_code or not bank_code.strip():
        raise ValueError("bank_code must be a non-empty string.")

    settings = get_settings()
    user_id = settings.bmoni_user_id
    url = f"{settings.bmoni_base_url.rstrip('/')}/v1/users/{user_id}/bank-accounts/verify-nigerian-account"
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

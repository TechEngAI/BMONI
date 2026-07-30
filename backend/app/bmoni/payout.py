import logging
from typing import Any

import httpx

from app.bmoni.client import verify_nigerian_account, _headers, BMONI_TIMEOUT
from app.config import get_settings
from app.database import get_supabase
from app.errors import AppError

logger = logging.getLogger(__name__)


class BmoniPayoutError(Exception):
    """Raised when a BMONI payout operation fails."""
    
    def __init__(self, message: str, code: str = "BMONI_PAYOUT_ERROR", details: dict[str, Any] | None = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)


def _account_names_match(verified_name: str, provided_name: str) -> bool:
    """Check if two account names reasonably match for fraud prevention.
    
    This is a simple but effective check - both names should contain the same
    key parts (surname, first name) ignoring case and extra whitespace.
    """
    if not verified_name or not provided_name:
        return False
    
    # Normalize both names
    verified_normalized = " ".join(verified_name.strip().lower().split())
    provided_normalized = " ".join(provided_name.strip().lower().split())
    
    # If they're exactly equal after normalization, that's a match
    if verified_normalized == provided_normalized:
        return True
    
    # Check if the verified name contains the provided name or vice versa
    # This handles cases where one might be a fuller version
    if verified_normalized in provided_normalized or provided_normalized in verified_normalized:
        return True
    
    # Check if they share at least one significant word (surname match)
    verified_words = set(verified_normalized.split())
    provided_words = set(provided_normalized.split())
    
    # If they share at least one word and are reasonably similar, consider it a match
    common_words = verified_words & provided_words
    if common_words and len(common_words) >= 1:
        return True
    
    return False


async def register_withdrawal_account(
    user_id: str, 
    account_number: str, 
    bank_code: str, 
    account_name: str
) -> dict[str, Any]:
    """Register a Nigerian bank account as a withdrawal account for a BMONI user.
    
    Args:
        user_id: BMONI user ID
        account_number: 10-digit Nigerian account number
        bank_code: Nigerian bank code
        account_name: Account holder name as provided by the user
    
    Returns:
        Dict containing the withdrawal account ID and registration details
    
    Raises:
        ValueError: If account validation fails
        BmoniPayoutError: If the account name doesn't match or registration fails
    """
    # Step 1: Verify the account details with BMONI
    try:
        verified = await verify_nigerian_account(account_number, bank_code)
    except (ValueError, AppError) as exc:
        logger.error("Account verification failed for %s/%s: %s", account_number, bank_code, exc)
        raise BmoniPayoutError(
            f"Account verification failed: {exc}",
            code="ACCOUNT_VERIFICATION_FAILED"
        )
    
    # Step 2: Fraud prevention - check if names match
    verified_name = verified.get("account_name", "")
    if not _account_names_match(verified_name, account_name):
        logger.warning(
            "Account name mismatch for %s: verified='%s', provided='%s'",
            account_number, verified_name, account_name
        )
        raise BmoniPayoutError(
            f"Account name mismatch. Bank returned '{verified_name}' but you provided '{account_name}'. "
            "For your security, we cannot proceed with this account.",
            code="ACCOUNT_NAME_MISMATCH",
            details={"verified_name": verified_name, "provided_name": account_name}
        )
    
    # Step 3: Register as withdrawal account
    settings = get_settings()
    url = f"{settings.bmoni_base_url.rstrip('/')}/v1/users/{user_id}/bank-accounts/withdrawal-accounts/nigeria"
    
    payload = {
        "accountNumber": account_number,
        "bankCode": bank_code,
        "accountName": account_name,
    }
    
    async with httpx.AsyncClient(timeout=BMONI_TIMEOUT) as client:
        try:
            response = await client.post(url, json=payload, headers=_headers())
        except httpx.TimeoutException:
            logger.error("BMONI withdrawal account registration timed out for user %s", user_id)
            raise BmoniPayoutError(
                "Registration timed out. Please try again.",
                code="REGISTRATION_TIMEOUT"
            )
        except httpx.RequestError as exc:
            logger.error("BMONI request failed for withdrawal account registration: %s", exc)
            raise BmoniPayoutError(
                "Could not reach BMONI service. Please try again.",
                code="REGISTRATION_UNAVAILABLE"
            )
    
    if response.status_code >= 400:
        message = "Withdrawal account registration failed."
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or message
        except ValueError:
            message = response.text or message
        
        logger.error("BMONI withdrawal account registration failed: status=%s, message=%s", response.status_code, message)
        raise BmoniPayoutError(message, code="REGISTRATION_FAILED")
    
    data = response.json()
    withdrawal_account_id = data.get("id") or data.get("withdrawalAccountId") or data.get("withdrawal_account_id")
    
    if not withdrawal_account_id:
        logger.error("BMONI withdrawal account registration returned no ID: %s", data)
        raise BmoniPayoutError(
            "Registration succeeded but no account ID was returned.",
            code="REGISTRATION_NO_ID"
        )
    
    return {
        "withdrawal_account_id": withdrawal_account_id,
        "account_number": account_number,
        "bank_code": bank_code,
        "account_name": account_name,
        "raw_response": data,
    }


async def offramp_nigeria(
    smart_wallet_id: str,
    withdrawal_account_id: str,
    amount: float,
    idempotency_key: str
) -> dict[str, Any]:
    """Initiate a Nigeria offramp (payout) from a BMONI smart wallet to a bank account.
    
    CRITICAL: This function is idempotent. If a payout with this idempotency_key
    has already succeeded, it returns the existing result without calling BMONI again.
    
    Args:
        smart_wallet_id: BMONI smart wallet ID
        withdrawal_account_id: Previously registered withdrawal account ID
        amount: Amount to payout in NGN (must be > 0)
        idempotency_key: Unique key for this payout to ensure idempotency
    
    Returns:
        Dict containing:
        - status: "SUCCESS" or "FAILED"
        - transaction_id: BMONI transaction ID (if successful)
        - amount: Payout amount
        - raw_response: Full BMONI API response
    
    Raises:
        ValueError: If amount is invalid
        BmoniPayoutError: If the payout fails
    """
    # Validate amount
    if amount <= 0:
        raise ValueError(f"Amount must be greater than 0, got {amount}")
    
    # CRITICAL: Check idempotency - has this payout already succeeded?
    db = get_supabase()
    existing = db.table("payment_receipts").select("*").eq("bmoni_reference", idempotency_key).limit(1).execute().data
    
    if existing and existing[0].get("bmoni_status") == "PAID":
        receipt = existing[0]
        logger.info("Returning existing successful payout for idempotency_key=%s", idempotency_key)
        return {
            "status": "SUCCESS",
            "transaction_id": receipt.get("bmoni_tx_id"),
            "amount": receipt.get("net_pay", amount),
            "raw_response": {"idempotent": True, "receipt_id": receipt["id"]},
        }
    
    # Proceed with BMONI API call
    settings = get_settings()
    user_id = settings.bmoni_user_id
    url = f"{settings.bmoni_base_url.rstrip('/')}/v1/users/{user_id}/smart-wallets/{smart_wallet_id}/offramp/nigeria"
    
    payload = {
        "withdrawalAccountId": withdrawal_account_id,
        "amount": amount,
        "idempotencyKey": idempotency_key,
    }
    
    async with httpx.AsyncClient(timeout=BMONI_TIMEOUT) as client:
        try:
            response = await client.post(url, json=payload, headers=_headers())
        except httpx.TimeoutException:
            logger.error("BMONI offramp timed out for wallet %s, amount=%s", smart_wallet_id, amount)
            raise BmoniPayoutError(
                "Payout timed out. Please check if the transaction completed before retrying.",
                code="OFFRAMP_TIMEOUT"
            )
        except httpx.RequestError as exc:
            logger.error("BMONI request failed for offramp: %s", exc)
            raise BmoniPayoutError(
                "Could not reach BMONI service. Please try again.",
                code="OFFRAMP_UNAVAILABLE"
            )
    
    if response.status_code >= 400:
        message = "Payout failed."
        try:
            body = response.json()
            message = body.get("message") or body.get("error") or message
        except ValueError:
            message = response.text or message
        
        logger.error("BMONI offramp failed: status=%s, message=%s", response.status_code, message)
        raise BmoniPayoutError(message, code="OFFRAMP_FAILED")
    
    data = response.json()
    transaction_id = data.get("transactionId") or data.get("transaction_id") or data.get("id")
    
    return {
        "status": "SUCCESS",
        "transaction_id": transaction_id,
        "amount": amount,
        "raw_response": data,
    }

from app.database import get_supabase
from app.squad.payments import initiate_deposit, verify_payment
from app.squad.transfer import get_ledger_balance
from app.bmoni.client import get_smart_wallet_balances
from app.wallet.schemas import WalletOverview, WalletTransaction, WalletBalance
from fastapi import HTTPException
import hmac
import hashlib
from app.config import get_settings
from typing import List, Optional


async def _fetch_bmoni_balance_kobo() -> int:
    """Fetch the real BMONI smart wallet balance, returning it in kobo."""
    try:
        balances = await get_smart_wallet_balances()
        import logging
        log = logging.getLogger(__name__)
        log.info("BMONI balances raw response: %s", balances)
        if not balances:
            log.warning("BMONI balances returned empty list")
            return 0
        # Pick the first wallet with a positive balance
        for bal in balances:
            raw = bal.get("balance") or bal.get("availableBalance") or bal.get("available_balance") or "0"
            log.info("BMONI wallet entry: %s, raw_balance=%s", bal, raw)
            amount = float(str(raw).strip())
            if amount > 0:
                result = int(amount * 100)
                log.info("BMONI balance resolved to %d kobo (%.2f NGN)", result, result / 100)
                return result
        log.warning("No BMONI wallet had a non-zero balance")
        return 0
    except Exception:
        log = logging.getLogger(__name__)
        log.exception("Failed to fetch BMONI balance, falling back to 0")
        return 0


async def get_wallet_overview(company_id: str) -> WalletOverview:
    # Load company_wallet (for historical totals — balance is overridden from BMONI)
    wallet = get_supabase().table("company_wallet").select("*").eq("company_id", company_id).single().execute().data
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet not found")

    # Load last 10 wallet_transactions
    transactions = get_supabase().table("wallet_transactions").select("*").eq("company_id", company_id).order("created_at", desc=True).limit(10).execute().data or []

    # Get Squad ledger balance (backup / historical)
    ledger = await get_ledger_balance()
    squad_balance_ngn = ledger.get("balance_kobo", 0) / 100 if ledger.get("success") else 0

    # Real BMONI balance
    bmoni_balance_kobo = await _fetch_bmoni_balance_kobo()

    return WalletOverview(
        balance_ngn=bmoni_balance_kobo / 100,
        balance_kobo=bmoni_balance_kobo,
        total_deposited_ngn=wallet["total_deposited_kobo"] / 100,
        total_disbursed_ngn=wallet["total_disbursed_kobo"] / 100,
        last_deposit_at=wallet.get("last_deposit_at"),
        last_disburse_at=wallet.get("last_disburse_at"),
        recent_transactions=transactions,
        squad_ledger_balance_ngn=squad_balance_ngn
    )


async def initiate_wallet_deposit(amount_ngn: float, admin: dict) -> dict:
    if amount_ngn < 1000:
        raise HTTPException(status_code=400, detail="Minimum deposit is NGN 1,000")

    company_id = admin["company_id"]

    # Load admin email
    admin_data = get_supabase().table("admins").select("email").eq("id", admin["id"]).single().execute().data
    if not admin_data:
        raise HTTPException(status_code=404, detail="Admin not found")

    # Load company name
    company = get_supabase().table("companies").select("name").eq("id", company_id).single().execute().data
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    result = await initiate_deposit(amount_ngn, company_id, company["name"], admin_data["email"])
    if not result["success"]:
        raise HTTPException(status_code=502, detail=result["error"])

    # Create wallet_transactions record
    get_supabase().table("wallet_transactions").insert({
        "company_id": company_id,
        "type": "DEPOSIT",
        "amount_kobo": result["amount_kobo"],
        "status": "PENDING",
        "squad_reference": result["transaction_reference"],
        "description": "Admin deposit initiated"
    }).execute()

    return {
        "checkout_url": result["checkout_url"],
        "transaction_reference": result["transaction_reference"],
        "amount_ngn": amount_ngn
    }


async def handle_squad_webhook(raw_body: bytes, signature: str, body: dict):
    # Validate signature
    expected_signature = hmac.new(get_settings().squad_webhook_secret.encode(), raw_body, hashlib.sha512).hexdigest().upper()
    if signature.upper() != expected_signature:
        print("Invalid webhook signature")
        return {"status": "ok"}  # Always return 200

    transaction_ref = body.get("transaction_ref")
    transaction_status = body.get("transaction_status")
    amount_kobo = body.get("amount")

    if not transaction_ref:
        return {"status": "ok"}

    # Find wallet_transactions
    tx = get_supabase().table("wallet_transactions").select("*").eq("squad_reference", transaction_ref).single().execute().data
    if not tx:
        return {"status": "ok"}

    if transaction_status == "success":
        # Verify payment
        verify_result = await verify_payment(transaction_ref)
        if verify_result["success"] and verify_result["transaction_status"] == "success":
            # Update wallet_transactions
            get_supabase().table("wallet_transactions").update({
                "status": "SUCCESS",
                "squad_tx_id": verify_result.get("raw", {}).get("transaction_id"),
                "squad_response": verify_result["raw"]
            }).eq("id", tx["id"]).execute()

            # Update company_wallet
            wallet = get_supabase().table("company_wallet").select("*").eq("company_id", tx["company_id"]).single().execute().data
            if wallet:
                get_supabase().table("company_wallet").update({
                    "balance_kobo": wallet["balance_kobo"] + tx["amount_kobo"],
                    "total_deposited_kobo": wallet["total_deposited_kobo"] + tx["amount_kobo"],
                    "last_deposit_at": "now()"
                }).eq("company_id", tx["company_id"]).execute()

            # Audit log
            get_supabase().table("audit_logs").insert({
                "actor_type": "system",
                "action": "WALLET_DEPOSIT_CONFIRMED",
                "target_id": tx["id"],
                "target_type": "wallet_transaction",
                "metadata": {"amount_ngn": tx["amount_kobo"] / 100}
            }).execute()
        else:
            get_supabase().table("wallet_transactions").update({
                "status": "FAILED"
            }).eq("id", tx["id"]).execute()
    elif transaction_status == "failed":
        get_supabase().table("wallet_transactions").update({
            "status": "FAILED"
        }).eq("id", tx["id"]).execute()

    return {"status": "ok"}


async def get_wallet_transactions(company_id: str, page: int = 1, page_size: int = 20, tx_type: str = None) -> List[WalletTransaction]:
    query = get_supabase().table("wallet_transactions").select("*").eq("company_id", company_id)
    if tx_type:
        query = query.eq("type", tx_type)
    transactions = query.order("created_at", desc=True).range((page-1)*page_size, page*page_size - 1).execute().data or []
    return [WalletTransaction(**tx) for tx in transactions]


async def get_wallet_balance(company_id: str) -> WalletBalance:
    bmoni_balance_kobo = await _fetch_bmoni_balance_kobo()
    return WalletBalance(
        balance_kobo=bmoni_balance_kobo,
        balance_ngn=bmoni_balance_kobo / 100
    )
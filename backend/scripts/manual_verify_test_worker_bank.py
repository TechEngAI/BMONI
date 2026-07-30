"""
TEST-ONLY: Manually insert a verified bank account for a single test worker.

THIS IS NOT A REAL VERIFICATION FLOW.  It bypasses the broken BMONI sandbox
verify-nigerian-account endpoint (confirmed non-functional by BMONI staff as of
July 2026) so that end-to-end payout testing can proceed.

Usage:
    python -m scripts.manual_verify_test_worker_bank

Requires:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY in the environment or backend/.env
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("manual_verify_bank")


# ---------------------------------------------------------------------------
# Banner – impossible to miss
# ---------------------------------------------------------------------------

BANNER = """
###############################################################################
#                                                                             #
#   THIS IS A TEST-ONLY BYPASS OF BANK VERIFICATION DUE TO A CONFIRMED       #
#   BMONI SANDBOX ISSUE.  DO NOT USE THIS FOR REAL WORKERS IN PRODUCTION.     #
#                                                                             #
#   THIS DOES NOT REPLACE THE REAL VERIFICATION FLOW.                         #
#                                                                             #
#   You are directly inserting a bank-verified record into the database       #
#   without calling verify_nigerian_account() or register_withdrawal_account().
#                                                                             #
#   This record is explicitly flagged so it can be identified later.          #
#                                                                             #
###############################################################################
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _from_dotenv(key: str) -> str | None:
    """Read a value from backend/.env (key=value lines)."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.exists():
        return None
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            if k.strip() == key:
                return v.strip().strip("\"'")
    return None


def _connect():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.database import get_supabase
    return get_supabase()


def _prompt(prompt_text: str, required: bool = True) -> str:
    while True:
        val = input(prompt_text).strip()
        if val or not required:
            return val
        print("  This field is required.")


def _confirm(prompt_text: str) -> bool:
    return input(f"{prompt_text} [y/N] ").strip().lower() in ("y", "yes")


def _ensure_bmoni_withdrawal_column(db) -> None:
    """Add the bmoni_withdrawal_account_id column if it does not exist.

    This column is referenced by bmoni/orchestrator.py but was never added to
    the migration.  We add it here so the orchestrator can find it during
    test payouts.
    """
    try:
        db.rpc(
            "add_bmoni_withdrawal_column", {}
        ).execute()
    except Exception:
        pass
    try:
        db.table("worker_bank_accounts").select("bmoni_withdrawal_account_id").limit(0).execute()
        logger.info("Column bmoni_withdrawal_account_id already exists.")
        return
    except Exception:
        pass

    logger.info("Adding missing column bmoni_withdrawal_account_id to worker_bank_accounts …")
    try:
        raw = db.table("worker_bank_accounts").select("id").limit(1).execute()
    except Exception as exc:
        logger.warning("Cannot probe table state: %s", exc)

    sql = """
    ALTER TABLE worker_bank_accounts
    ADD COLUMN IF NOT EXISTS bmoni_withdrawal_account_id VARCHAR(255);
    """
    try:
        db.rpc("exec_sql", {"query": sql}).execute()
        logger.info("Column added via RPC.")
    except Exception:
        try:
            import httpx
            from app.config import get_settings
            settings = get_settings()
            resp = httpx.post(
                f"{settings.supabase_url.rstrip('/')}/rest/v1/rpc/exec_sql",
                json={"query": sql},
                headers={
                    "apikey": settings.supabase_service_key,
                    "Authorization": f"Bearer {settings.supabase_service_key}",
                    "Content-Type": "application/json",
                },
            )
            if resp.is_success:
                logger.info("Column added via direct RPC call.")
            else:
                logger.warning(
                    "Could not add column via RPC (status=%s).  "
                    "You may need to run the SQL manually:\n%s",
                    resp.status_code, sql,
                )
        except Exception as exc:
            logger.warning(
                "Could not add column automatically.  "
                "If you need the BMONI payout path, run this SQL manually:\n%s\n"
                "Error: %s",
                sql, exc,
            )


def main() -> None:
    print(BANNER)

    if not _confirm("Do you acknowledge this is a TEST-ONLY bypass and proceed?"):
        print("Aborted.")
        sys.exit(0)

    db = _connect()
    logger.info("Connected to Supabase (service role).")

    # ------------------------------------------------------------------
    # Step 1: find the worker
    # ------------------------------------------------------------------
    worker_id_or_email = _prompt("Worker ID or email: ")
    if "@" in worker_id_or_email:
        rows = db.table("workers").select("*").eq("email", worker_id_or_email).limit(1).execute().data
    else:
        rows = db.table("workers").select("*").eq("id", worker_id_or_email).limit(1).execute().data

    if not rows:
        logger.error("Worker not found.")
        sys.exit(1)

    worker = rows[0]
    worker_id = worker["id"]
    logger.info(
        "Found worker: %s %s (%s)  company=%s  status=%s  bank_verified=%s",
        worker.get("first_name", ""),
        worker.get("last_name", ""),
        worker.get("email", ""),
        worker.get("company_id", ""),
        worker.get("status", ""),
        worker.get("bank_verified", False),
    )

    # ------------------------------------------------------------------
    # Step 2: prompt for bank details (operator manually confirms)
    # ------------------------------------------------------------------
    print("\n--- Bank account details (operator must confirm these are correct) ---")

    account_number = _prompt("Account number (10 digits): ")
    bank_code = _prompt("Bank code (3-digit CBN code, e.g. 011 for First Bank): ")
    bank_name = _prompt("Bank name (for display, e.g. First Bank of Nigeria): ")
    account_name = _prompt("Account holder name (as it appears on the account): ")

    bmoni_wd_id = input(
        "BMONI withdrawal account ID (optional – leave blank if not yet registered): "
    ).strip()

    # ------------------------------------------------------------------
    # Step 3: show what will be written and confirm
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc).isoformat()

    bank_payload = {
        "worker_id": worker_id,
        "bank_name": bank_name,
        "bank_code": bank_code,
        "account_number": account_number,
        "account_name": account_name,
        "match_score": 100.00,
        "match_status": "AUTO_VERIFIED",
        "is_active": True,
        "verified_at": now,
    }
    if bmoni_wd_id:
        _ensure_bmoni_withdrawal_column(db)
        bank_payload["bmoni_withdrawal_account_id"] = bmoni_wd_id

    print("\n--- Proposed changes ---")
    print(f"  worker_bank_accounts: INSERT {bank_payload}")
    print(f"  workers:              UPDATE bank_verified=True, status=ACTIVE")
    print(f"  existing active bank: will be set to is_active=False (if any)")

    if not _confirm("\nApply these changes?"):
        print("Aborted.")
        sys.exit(0)

    # ------------------------------------------------------------------
    # Step 4: deactivate any existing active bank account for this worker
    # ------------------------------------------------------------------
    existing_active = (
        db.table("worker_bank_accounts")
        .select("*")
        .eq("worker_id", worker_id)
        .eq("is_active", True)
        .execute()
        .data
    )
    if existing_active:
        old = existing_active[0]
        logger.info("Deactivating existing bank account %s (%s)", old.get("id"), old.get("account_number"))
        db.table("worker_bank_accounts").update({"is_active": False}).eq("id", old["id"]).execute()
        db.table("bank_account_history").insert({
            "worker_id": worker_id,
            "old_account": old.get("account_number"),
            "new_account": account_number,
            "old_bank_code": old.get("bank_code"),
            "new_bank_code": bank_code,
            "reason": "TEST-ONLY manual bank verification bypass – BMONI sandbox broken (script)",
        }).execute()
        logger.info("Deactivation logged in bank_account_history.")

    # ------------------------------------------------------------------
    # Step 5: insert the new bank account record
    # ------------------------------------------------------------------
    result = db.table("worker_bank_accounts").insert(bank_payload).execute()
    if not result.data:
        logger.error("Failed to insert bank account record.")
        sys.exit(1)

    bank_row = result.data[0]
    logger.info("Inserted bank account record: id=%s", bank_row.get("id"))

    # ------------------------------------------------------------------
    # Step 6: update the worker
    # ------------------------------------------------------------------
    db.table("workers").update({
        "bank_verified": True,
        "status": "ACTIVE",
    }).eq("id", worker_id).execute()
    logger.info("Updated worker: bank_verified=True, status=ACTIVE")

    # ------------------------------------------------------------------
    # Step 7: log this action in a traceable way
    # ------------------------------------------------------------------
    try:
        db.table("audit_logs").insert({
            "actor_id": worker_id,
            "actor_type": "worker",
            "action": "MANUAL_BANK_VERIFICATION_BYPASS",
            "target_id": worker_id,
            "target_type": "worker",
            "metadata": {
                "script": "manual_verify_test_worker_bank.py",
                "account_number": account_number,
                "bank_code": bank_code,
                "account_name": account_name,
                "bank_name": bank_name,
                "note": (
                    "TEST-ONLY: Direct DB insert bypassing BMONI verify_nigerian_account(). "
                    "Operator manually confirmed name matches account. "
                    "BMONI sandbox was confirmed broken by their staff."
                ),
            },
        }).execute()
        logger.info("Audit trail written to audit_logs.")
    except Exception as exc:
        logger.warning(
            "Could not write audit_logs entry. "
            "The database insert succeeded but is not traced: %s", exc
        )

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print()
    print("=" * 75)
    print("  DONE – Test bank account is now active and marked verified.")
    print(f"  Worker:  {worker.get('first_name', '')} {worker.get('last_name', '')} ({worker.get('email', '')})")
    print(f"  Account: {account_number} @ {bank_name} ({bank_code})")
    print(f"  Name:    {account_name}")
    if bmoni_wd_id:
        print(f"  BMONI withdrawal account ID: {bmoni_wd_id}")
    print(f"  DB ID:   {bank_row.get('id')}")
    print()
    print("  REMINDER: This record was NOT verified by BMONI.  Re-do the")
    print("  real verification flow once BMONI fixes their sandbox endpoint.")
    print("=" * 75)


if __name__ == "__main__":
    main()

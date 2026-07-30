"""
Bootstrap a test company + admin + HR invite code for testing the invite-code
registration flow end-to-end.

Usage:
    python -m scripts.bootstrap_test_hr_flow [--company "Test Corp"]

Requires:
    - SUPABASE_URL and SUPABASE_SERVICE_KEY in backend/.env
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import string
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("bootstrap_hr")


def _from_dotenv(key: str) -> str | None:
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


def _env(key: str) -> str:
    val = os.environ.get(key) or _from_dotenv(key)
    if not val:
        logger.error("%s is not set. Set it in backend/.env or export it.", key)
        sys.exit(1)
    return val


def _connect():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.database import get_supabase
    return get_supabase()


def _random_email(base: str = "admin") -> str:
    ts = datetime.now().strftime("%H%M%S")
    return f"{base}.{ts}@test.ghostguard.app"


def _random_password() -> str:
    return "TestPass" + "".join(random.choices(string.digits, k=4)) + "!"


def _generate_hr_code(company_name: str) -> str:
    prefix = "".join(c for c in company_name.upper() if c.isalnum())[:4].ljust(4, "X")
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"GG-HR-{prefix}-{suffix}"


def _unique_hr_code(db, company_name: str) -> str:
    for _ in range(10):
        code = _generate_hr_code(company_name)
        existing = db.table("hr_invite_codes").select("id").eq("code", code).execute().data
        if not existing:
            return code
    logger.error("Could not generate unique HR code after 10 attempts.")
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap test company + admin + HR invite")
    parser.add_argument("--company", default="TestCorp", help="Company name (default: TestCorp)")
    parser.add_argument("--admin-email", help="Admin email (default: auto-generated)")
    parser.add_argument("--admin-password", help="Admin password (default: auto-generated)")
    args = parser.parse_args()

    db = _connect()
    logger.info("Connected to Supabase (service role).")

    company_name = args.company
    admin_email = args.admin_email or _random_email("admin")
    admin_password = args.admin_password or _random_password()
    hr_email = _random_email("hr")
    hr_first = "Test"
    hr_last = "HR"

    print("=" * 75)
    print("  BOOTSTRAPPING TEST ENVIRONMENT FOR HR INVITE-CODE FLOW")
    print("=" * 75)

    # ----------------------------------------------------------------
    # Step 1: Create Supabase auth user for admin
    # ----------------------------------------------------------------
    logger.info("Creating Supabase auth user for admin (%s) ...", admin_email)
    try:
        resp = db.auth.admin.create_user({
            "email": admin_email,
            "password": admin_password,
            "email_confirm": True,
            "user_metadata": {"user_type": "admin", "first_name": "Test", "last_name": "Admin"},
        })
    except Exception as exc:
        logger.error("Failed to create auth user: %s", exc)
        sys.exit(1)
    auth_user_id = resp.user.id if hasattr(resp, "user") else resp.dict().get("user", {}).get("id")
    logger.info("Auth user created: %s", auth_user_id)

    # ----------------------------------------------------------------
    # Step 2: Create company
    # ----------------------------------------------------------------
    logger.info("Creating company '%s' ...", company_name)
    company = db.table("companies").insert({"name": company_name}).execute().data
    if not company:
        logger.error("Failed to create company.")
        sys.exit(1)
    company_id = company[0]["id"]
    logger.info("Company created: %s", company_id)

    # ----------------------------------------------------------------
    # Step 3: Create admin DB record
    # ----------------------------------------------------------------
    logger.info("Creating admin record ...")
    admin_record = db.table("admins").insert({
        "auth_user_id": auth_user_id,
        "company_id": company_id,
        "first_name": "Test",
        "last_name": "Admin",
        "email": admin_email,
        "status": "ACTIVE",
    }).execute().data
    if not admin_record:
        logger.error("Failed to create admin record.")
        sys.exit(1)
    admin_id = admin_record[0]["id"]
    logger.info("Admin created: %s", admin_id)

    # ----------------------------------------------------------------
    # Step 4: Generate HR invite code
    # ----------------------------------------------------------------
    hr_code = _unique_hr_code(db, company_name)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
    logger.info("Generating HR invite code ...")
    invite = db.table("hr_invite_codes").insert({
        "code": hr_code,
        "company_id": company_id,
        "created_by_admin_id": admin_id,
        "first_name": hr_first,
        "last_name": hr_last,
        "email": hr_email,
        "expires_at": expires_at,
    }).execute().data
    if not invite:
        logger.error("Failed to create HR invite code.")
        sys.exit(1)

    # ----------------------------------------------------------------
    # Done
    # ----------------------------------------------------------------
    print()
    print("=" * 75)
    print("  BOOTSTRAP COMPLETE")
    print("=" * 75)
    print()
    print("  ADMIN LOGIN (use these to access the admin panel):")
    print(f"    URL:     /hr/login")
    print(f"    Email:   {admin_email}")
    print(f"    Password: {admin_password}")
    print()
    print("  HR INVITE CODE (share this with the HR officer):")
    print(f"    Code:    {hr_code}")
    print(f"    Expires: {expires_at[:10]}")
    print()
    print("  REGISTRATION LINK FOR HR OFFICER:")
    print(f"    Visit  /hr/register  and enter the invite code above.")
    print()
    print("  NOTE: The admin auth user was created with email_confirm=True,")
    print("  so you can log in immediately without verifying email.")
    print("=" * 75)


if __name__ == "__main__":
    main()

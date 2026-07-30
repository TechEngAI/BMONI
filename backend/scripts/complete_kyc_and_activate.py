"""
One-time KYC completion and BMONI wallet activation script.

Run AFTER provision_wallet.py has successfully created a BMONI user and smart wallet.
This script completes Know Your Customer (KYC) verification and activates the
desired rail (Nigeria NGN by default).

Usage:
    python -m scripts.complete_kyc_and_activate [--currency nigeria]

Requires:
    - BMONI_BASE_URL and BMONI_API_KEY set in the environment or backend/.env
    - BMONI_USER_ID, BMONI_SMART_WALLET_ID in backend/.env
    - BMONI_SMART_WALLET_ADDRESS in backend/.env (or paste at prompt)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("complete_kyc")

TIMEOUT = 30.0
POLL_INTERVAL = 3
MAX_POLL_ATTEMPTS = 5


# ---------------------------------------------------------------------------
# Helpers (duplicated from provision_wallet.py for self-contained operation)
# ---------------------------------------------------------------------------


def _api_key() -> str:
    key = os.environ.get("BMONI_API_KEY")
    if not key:
        key = _from_dotenv("BMONI_API_KEY")
    if not key:
        logger.error("BMONI_API_KEY is not set. Set it in backend/.env or export it.")
        sys.exit(1)
    return key


def _base_url() -> str:
    url = os.environ.get("BMONI_BASE_URL")
    if not url:
        url = _from_dotenv("BMONI_BASE_URL")
    if not url:
        logger.error("BMONI_BASE_URL is not set. Set it in backend/.env or export it.")
        sys.exit(1)
    return url.rstrip("/")


def _from_dotenv(key: str) -> str | None:
    """Read a single key from the .env file in the backend directory."""
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if not env_path.is_file():
        return None
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line.startswith(key + "="):
                val = line[len(key) + 1:]
                if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                    val = val[1:-1]
                return val
    return None


def _call(
    method: str,
    path: str,
    *,
    json_body: dict | None = None,
    api_key: str,
    base_url: str,
    step_label: str = "",
) -> dict:
    """Make an authenticated BMONI API call.  Exits the process on failure."""
    url = f"{base_url}{path}"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    
    # Debug: print request payload before sending
    if json_body:
        tag = f" for {step_label}" if step_label else ""
        print(f"  >>> Sending request payload{tag}: {str(json_body)[:2000]}")
    
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(method, url, json=json_body, headers=headers)
    except httpx.TimeoutException:
        logger.error("BMONI request timed out: %s %s", method, path)
        sys.exit(1)
    except httpx.RequestError as exc:
        logger.error("BMONI request failed: %s %s — %s", method, path, exc)
        sys.exit(1)

    tag = f" for {step_label}" if step_label else ""
    print(f"  >>> RAW response{tag}: {response.text[:3000]}")

    if response.status_code >= 400:
        body_text = response.text
        try:
            body = response.json()
            if isinstance(body, dict):
                body_text = body.get("message") or body.get("error") or body_text
        except ValueError:
            pass
        logger.error(
            "BMONI API error: %s %s returned %s — %s",
            method, path, response.status_code, body_text,
        )
        sys.exit(1)

    # Handle empty response bodies (e.g., 201 with no body)
    if not response.text.strip():
        print(f"  >>> Empty response body (status {response.status_code}) - treating as success")
        return {}
    
    return response.json()


def _call_multipart(
    method: str,
    path: str,
    *,
    data: dict | None = None,
    files_list: list[tuple[str, str]],
    api_key: str,
    base_url: str,
    step_label: str = "",
) -> dict:
    """Make a multipart/form-data BMONI API call for file uploads.

    files_list is a list of (field_name, file_path) tuples.
    Repeated field names produce repeated multipart parts (array fields).
    """
    url = f"{base_url}{path}"
    headers = {"x-api-key": api_key}
    httpx_files: list[tuple[str, tuple[str, bytes, str]]] = []

    # Debug: print field names being sent
    field_names = [field_name for field_name, _ in files_list]
    print(f"  >>> Sending multipart fields: {field_names}")

    for field_name, file_path in files_list:
        path_obj = Path(file_path)
        if not path_obj.is_file():
            logger.error("File not found: %s", file_path)
            sys.exit(1)

        suffix = path_obj.suffix.lower()
        content_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".pdf": "application/pdf",
        }.get(suffix, "application/octet-stream")

        try:
            with open(file_path, "rb") as f:
                file_bytes = f.read()
        except OSError as exc:
            logger.error("Failed to read %s: %s", file_path, exc)
            sys.exit(1)

        httpx_files.append((field_name, (path_obj.name, file_bytes, content_type)))

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(method, url, data=data, files=httpx_files, headers=headers)
    except httpx.TimeoutException:
        logger.error("BMONI request timed out: %s %s", method, path)
        sys.exit(1)
    except httpx.RequestError as exc:
        logger.error("BMONI request failed: %s %s — %s", method, path, exc)
        sys.exit(1)

    tag = f" for {step_label}" if step_label else ""
    print(f"  >>> RAW response{tag}: {response.text[:3000]}")

    if response.status_code >= 400:
        body_text = response.text
        try:
            body = response.json()
            if isinstance(body, dict):
                body_text = body.get("message") or body.get("error") or body_text
        except ValueError:
            pass
        logger.error(
            "BMONI API error: %s %s returned %s — %s",
            method, path, response.status_code, body_text,
        )
        sys.exit(1)

    # Handle empty response bodies (e.g., 201 with no body)
    if not response.text.strip():
        print(f"  >>> Empty response body (status {response.status_code}) - treating as success")
        return {}
    
    return response.json()


def _prompt(prompt: str, default: str | None = None) -> str:
    """Prompt for input with auto-fill support."""
    if os.environ.get("AUTO_FILL") == "true" and default is not None:
        print(f"  AUTO: {prompt} = {default}")
        return default
    
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  Input cannot be empty. Please try again.")


def _prompt_optional(prompt: str, default: str | None = None) -> str:
    """Prompt for optional input with auto-fill support."""
    if os.environ.get("AUTO_FILL") == "true" and default is not None:
        print(f"  AUTO: {prompt} = {default}")
        return default
    
    value = input(prompt).strip()
    return value if value else (default or "")


def _prompt_float(prompt: str, default: float | None = None) -> float:
    """Prompt for a float value with validation and retry."""
    if os.environ.get("AUTO_FILL") == "true" and default is not None:
        print(f"  AUTO: {prompt} = {default}")
        return default
    
    while True:
        if default is not None:
            full_prompt = f"{prompt} (default {default}): "
        else:
            full_prompt = f"{prompt}: "
        
        value = input(full_prompt).strip()
        if not value and default is not None:
            return default
        
        try:
            return float(value)
        except ValueError:
            print("  Please enter a valid number.")


def _prompt_int(prompt: str, default: int | None = None) -> int:
    """Prompt for an integer value with validation and retry."""
    if os.environ.get("AUTO_FILL") == "true" and default is not None:
        print(f"  AUTO: {prompt} = {default}")
        return default
    
    while True:
        if default is not None:
            full_prompt = f"{prompt} (default {default}): "
        else:
            full_prompt = f"{prompt}: "
        
        value = input(full_prompt).strip()
        if not value and default is not None:
            return default
        
        try:
            return int(value)
        except ValueError:
            print("  Please enter a valid integer.")


def _strip_nulls(payload: dict) -> dict:
    """Recursively remove keys with None/null values from a dictionary."""
    cleaned = {}
    for key, value in payload.items():
        if value is None:
            continue
        if isinstance(value, dict):
            cleaned[key] = _strip_nulls(value)
        elif isinstance(value, list):
            cleaned[key] = [_strip_nulls(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _validate_enum(value: str, allowed: list[str], field_name: str) -> str:
    """Validate that a value matches one of the allowed enum values."""
    if value not in allowed:
        logger.error(
            "Invalid %s: '%s'. Allowed values: %s",
            field_name, value, ", ".join(allowed)
        )
        sys.exit(1)
    return value


def _confirm(prompt: str) -> None:
    if os.environ.get("AUTO_FILL") == "true":
        return  # Auto-confirm in auto mode
    answer = input(f"{prompt} Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        logger.info("Aborted by operator.")
        sys.exit(0)


def _call_retry_only(api_key: str, base_url: str) -> None:
    """Call POST /kyc/retry as a standalone operation."""
    user_id = _from_dotenv("BMONI_USER_ID")
    if not user_id:
        logger.error("BMONI_USER_ID is not set in backend/.env.")
        sys.exit(1)
    
    print(f"  User ID: {user_id}")
    print()
    
    # Confirm operator has already updated KYC via Step 6
    if os.environ.get("AUTO_FILL") != "true":
        confirm = input("  Have you already updated your KYC fields via Step 6? (yes/no): ").strip().lower()
        if confirm != "yes":
            print("  Please run Step 6 (--patch-kyc-only) first to update your KYC fields.")
            print("  Command: python -m scripts.complete_kyc_and_activate --patch-kyc-only")
            sys.exit(1)
    
    print("\n  Calling POST /kyc/retry …")
    
    retry_payload = {
        "sumsubLevelName": "id-and-liveness"
    }
    
    retry_resp = _call(
        "POST",
        f"/v1/users/{user_id}/kyc/retry",
        json_body=retry_payload,
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/retry",
    )
    print("  KYC retry submitted. Raw response printed above.")
    print("  Note: Check the response for any guidance on required corrections.")


def _call_patch_kyc_only(api_key: str, base_url: str) -> None:
    """Run Step 6 (PATCH /kyc) as a standalone operation."""
    _run_step_6(api_key, base_url, _from_dotenv("BMONI_USER_ID"))


def _run_step_6(api_key: str, base_url: str, user_id: str) -> None:
    """Run Step 6 (PATCH /kyc) standalone."""
    print("\n" + "-" * 72)
    print("[Step 6/10] Submitting KYC personal details …")
    print()
    print("  Refer to the Step 1 /kyc/options response for valid field values.")
    print()

    print()
    print("  Personal Information:")
    first_name = _prompt("  First name: ", "John")
    last_name = _prompt("  Last name: ", "Doe")
    date_of_birth = _prompt("  Date of birth (YYYY-MM-DD): ", "1990-01-01")
    gender = _prompt("  Gender (check Step 1 response for valid values, e.g. male/female): ", "male")
    email = _prompt("  Email: ", "john.doe@example.com")
    phone_number = _prompt("  Phone number: ", "+2348012345678")
    nationality = _prompt_optional("  Nationality (default NGA): ", "NGA")

    print()
    print("  Address:")
    street_line1 = _prompt("  Street line 1: ", "123 Main Street")
    street_line2 = _prompt_optional("  Street line 2 (optional): ", "")
    city = _prompt("  City: ", "Lagos")
    state = _prompt("  State / province: ", "Lagos")
    postal_code = _prompt_optional("  Postal code (optional): ", "100001")
    country_code = _prompt_optional("  Country code (default NGA): ", "NGA")

    print()
    print("  Employment:")
    print("  Note: In standalone mode, you'll need to provide occupation code manually")
    print("  Run the full script to see available occupations from Step 2")
    occupation_code = _prompt("  Occupation code: ", "ENGINEER")
    employer_name = _prompt_optional("  Employer name (optional): ", "GhostGuard Ltd")
    employment_status = _prompt_optional("  Employment status (optional): ", "employed")
    
    # Debug print to check exact value being sent
    print(f"  >>> employment_status value being sent: [{employment_status}]")
    
    # Validate employment status against allowed values
    allowed_employment_status = ["employed", "self_employed", "retired", "student", "unemployed", "homemaker"]
    if employment_status and employment_status not in allowed_employment_status:
        logger.error(
            "Invalid employment status: '%s'. Allowed values: %s",
            employment_status, ", ".join(allowed_employment_status)
        )
        sys.exit(1)

    print()
    print("  Financial Information:")
    source_of_income = _prompt_optional("  Source of income (default salary): ", "salary")
    estimated_annual_income = _prompt_float("  Estimated annual income (NGN)", 1000000.0)
    income_currency = _prompt_optional("  Income currency (default NGN): ", "NGA")
    estimated_monthly_volume = _prompt_float("  Estimated monthly transaction volume (NGN)", 500000.0)

    print()
    print("  BVN (Bank Verification Number):")
    print("  >>> Sandbox test BVN is 22222222222 — do NOT enter a real BVN. <<<")
    bvn = _prompt("  BVN: ", "22222222222")

    print()
    print("  Account purpose (personal, business, investment, actingAsIntermediary):")
    account_purpose = _prompt_optional("  Account purpose (default personal): ", "personal")
    account_purpose = _validate_enum(
        account_purpose,
        ["personal", "business", "investment", "actingAsIntermediary"],
        "accountPurpose"
    )

    print()
    print("  Source of funds (salary, business, investments, pension, government, inheritance, savings):")
    source_of_funds = _prompt_optional("  Source of funds (default salary): ", "salary")
    source_of_funds = _validate_enum(
        source_of_funds,
        ["salary", "business", "investments", "pension", "government", "inheritance", "savings"],
        "sourceOfFunds"
    )

    # Build nested payload matching BMONI API spec
    kyc_payload: dict = {
        "accountPurpose": account_purpose,
        "personalInfo": {
            "firstName": first_name,
            "lastName": last_name,
            "dateOfBirth": date_of_birth,
            "gender": gender,
            "email": email,
            "phoneNumber": phone_number,
            "nationality": nationality,
            "occupation": occupation_code,  # Top-level in personalInfo
            "sourceOfIncome": source_of_income,
            "estimatedAnnualIncome": estimated_annual_income,
            "incomeCurrency": income_currency,
        },
        "address": {
            "streetLine1": street_line1,
            "streetLine2": street_line2,
            "city": city,
            "state": state,
            "postalCode": postal_code,
            "countryCode": country_code,
        },
        "employment": {
            "occupationCode": occupation_code,
            "employerName": employer_name,
            "employmentStatus": employment_status,
        },
        "identificationNumbers": [
            {
                "type": "bvn",
                "number": bvn,
                "issuingCountryCode": "NGA",
            }
        ],
        "sourceOfFunds": source_of_funds,
        "estimatedMonthlyVolume": estimated_monthly_volume,
    }

    # Strip null values before sending
    kyc_payload = _strip_nulls(kyc_payload)

    kyc_resp = _call(
        "PATCH",
        f"/v1/users/{user_id}/kyc",
        json_body=kyc_payload,
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/patch",
    )
    print("  KYC details submitted. Raw response printed above.")
    print("  You can now call --retry-only to resubmit for verification.")
    print("  Command: python -m scripts.complete_kyc_and_activate --retry-only")


# Placeholder functions for other steps (not yet implemented for standalone mode)
def _run_step_1(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 1 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_2(api_key: str, base_url: str, user_id: str) -> None:
    """Run Step 2 (occupation search) standalone."""
    print("\n" + "-" * 72)
    print("[Step 2/10] Fetching occupations …")
    search_term = _prompt_optional("  Search occupations (press Enter for all): ", "")
    occupations_resp = _call(
        "GET",
        f"/v1/users/{user_id}/kyc/occupations?search={search_term}",
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/occupations",
    )
    print("  (Save the occupationCode from the response — needed in Step 6)")
    print("  >>> Full occupations response structure for debugging:")
    print(json.dumps(occupations_resp, indent=2)[:2000])

def _run_step_3(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 3 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_4(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 4 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_5(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 5 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_7(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 7 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_8(api_key: str, base_url: str, user_id: str) -> None:
    print("  Step 8 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_9(api_key: str, base_url: str, user_id: str, smart_wallet_address: str) -> None:
    print("  Step 9 standalone mode not yet implemented. Use full script.")
    sys.exit(1)

def _run_step_10(api_key: str, base_url: str, user_id: str) -> None:
    """Run Step 10 (onboarding status polling) standalone."""
    # Custom polling parameters for standalone mode
    POLL_ATTEMPTS = 10
    POLL_INTERVAL = 15  # seconds
    
    print("\n" + "-" * 72)
    print("[Step 10/10] Polling onboarding status "
          f"(up to {POLL_ATTEMPTS} attempts, {POLL_INTERVAL}s interval, "
          f"{POLL_ATTEMPTS * POLL_INTERVAL}s total) …")

    rail_active = False
    first_response_seen = False
    start_time = time.time()
    
    for attempt in range(1, POLL_ATTEMPTS + 1):
        elapsed = int(time.time() - start_time)
        print(f"\n  Poll attempt {attempt}/{POLL_ATTEMPTS} (elapsed: {elapsed}s) …")
        status_resp = _call(
            "GET",
            f"/v1/users/{user_id}/onboarding/status",
            api_key=api_key,
            base_url=base_url,
            step_label=f"onboarding/status (attempt {attempt})",
        )

        # Always print full raw response on first attempt to understand structure
        if not first_response_seen:
            print("  >>> First poll attempt - full raw response structure:")
            print(json.dumps(status_resp, indent=2)[:3000])
            first_response_seen = True
            
            # If structure is unclear, stop after first attempt to avoid blind polling
            if not isinstance(status_resp, dict) or not status_resp:
                print("  WARNING: Response structure unclear - stopping polling to avoid blind attempts")
                print("  Please examine the response above and update parsing logic")
                break

        # Defensive: handle response structure - look for Nigeria-specific status
        # BMONI docs: status is "per provider/rail" - based on pattern from other rails:
        # - paytrieStatus=Canada (confirmed in docs)
        # - etherfuseStatus=Mexico (confirmed in docs)
        # - moneriumStatus=Europe (confirmed in docs)
        # INFERRED: anchorStatus=Nigeria (Anchor is a known Nigerian banking provider)
        # INFERRED: bridgeStatus=USA (Bridge is a known US banking provider)
        # NOTE: This field mapping is INFERRED, not confirmed by BMONI docs - verify with staff
        if isinstance(status_resp, dict):
            # Look for anchorStatus field for Nigeria rail
            nigeria_status = status_resp.get("anchorStatus")
            rejection_reason = status_resp.get("anchorRejectionReason") or status_resp.get("rejectionReason") or status_resp.get("reason") or status_resp.get("message")
            
            print(f"  >>> Nigeria anchorStatus: {nigeria_status}")
            
            if nigeria_status:
                status_lower = nigeria_status.lower()
                
                # Check for rejection or resubmission required
                if status_lower in ("rejected", "requires_resubmission"):
                    if rejection_reason:
                        print(f"  ERROR: Nigeria rail rejected. Reason: {rejection_reason}")
                    else:
                        print(f"  ERROR: Nigeria rail rejected or requires resubmission")
                    print("  Please check BMONI dashboard for guidance on required corrections")
                    sys.exit(1)
                
                # Check for active status
                elif status_lower == "active":
                    print(f"  SUCCESS: Nigeria rail is {nigeria_status}")
                    rail_active = True
                    break
                
                # Other statuses (not_started, pending_review, etc.)
                elif status_lower in ("not_started", "pending_review"):
                    print(f"  Nigeria rail status: {nigeria_status} (waiting for activation)")
                else:
                    print(f"  Nigeria rail status: {nigeria_status} (unknown status)")
            
            else:
                print("  WARNING: Could not find anchorStatus field in response")
                print("  NOTE: Field mapping is inferred - may need verification with BMONI staff")

        if rail_active:
            break

        if attempt < POLL_ATTEMPTS:
            print(f"  Rail not yet active. Waiting {POLL_INTERVAL}s …")
            time.sleep(POLL_INTERVAL)

    if not rail_active:
        print()
        logger.error(
            "NGN rail did not become active after %d attempts (%d seconds). "
            "Check with BMONI staff to confirm onboarding status.",
            POLL_ATTEMPTS,
            POLL_ATTEMPTS * POLL_INTERVAL,
        )
        sys.exit(1)

    print("\n  Nigeria NGN rail is ACTIVE.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Complete KYC and activate BMONI wallet rail")
    parser.add_argument(
        "--currency",
        default="nigeria",
        choices=["nigeria", "usa", "canada", "monerium"],
        help="Which rail to activate (default: nigeria)",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Auto-fill all prompts with sandbox-safe defaults (also set AUTO_FILL=true env var)",
    )
    parser.add_argument(
        "--retry",
        action="store_true",
        help="After main flow, call POST /kyc/retry to resubmit for verification",
    )
    parser.add_argument(
        "--retry-only",
        action="store_true",
        help="Skip main flow, only call POST /kyc/retry (for resubmission after KYC patch)",
    )
    parser.add_argument(
        "--patch-kyc-only",
        action="store_true",
        help="Skip main flow, only run Step 6 (PATCH /kyc) to update KYC fields",
    )
    parser.add_argument(
        "--step",
        type=int,
        choices=range(1, 11),
        metavar="1-10",
        help="Run a single step standalone (1-10) instead of full sequence",
    )
    args = parser.parse_args()

    # Set environment variable for --auto flag
    if args.auto:
        os.environ["AUTO_FILL"] = "true"
        print("  AUTO-FILL MODE: Using sandbox-safe defaults for Steps 1-6")
        print("  Note: Document uploads (Steps 3-4) must be done manually first")

    if args.currency != "nigeria":
        print(f"\n  The {args.currency} rail is not yet implemented in this script.")
        print("  Only the nigeria (NGN) path is fully implemented.")
        sys.exit(0)

    # Determine which step(s) to run
    target_step = args.step

    # Handle special modes
    if args.retry_only:
        print("\n" + "=" * 72)
        print("  RETRY-ONLY MODE: Calling POST /kyc/retry")
        print("=" * 72)
        api_key = _api_key()
        base_url = _base_url()
        _call_retry_only(api_key, base_url)
        return

    if args.patch_kyc_only:
        print("\n" + "=" * 72)
        print("  PATCH-KYC-ONLY MODE: Running Step 6 (PATCH /kyc) only")
        print("=" * 72)
        api_key = _api_key()
        base_url = _base_url()
        _call_patch_kyc_only(api_key, base_url)
        return

    api_key = _api_key()
    base_url = _base_url()

    # Handle single-step execution
    if target_step:
        print("=" * 72)
        print(f"  SINGLE-STEP MODE: Running Step {target_step} only")
        print("=" * 72)
        
        # Load common required values
        user_id = _from_dotenv("BMONI_USER_ID")
        smart_wallet_id = _from_dotenv("BMONI_SMART_WALLET_ID")
        smart_wallet_address = _from_dotenv("BMONI_SMART_WALLET_ADDRESS")
        
        if not user_id:
            logger.error("BMONI_USER_ID is not set in backend/.env.")
            sys.exit(1)
        
        print(f"  User ID: {user_id}")
        if smart_wallet_id:
            print(f"  Smart wallet ID: {smart_wallet_id}")
        if smart_wallet_address:
            print(f"  Smart wallet address: {smart_wallet_address}")
        
        # Run the requested step
        if target_step == 1:
            _run_step_1(api_key, base_url, user_id)
        elif target_step == 2:
            _run_step_2(api_key, base_url, user_id)
        elif target_step == 3:
            _run_step_3(api_key, base_url, user_id)
        elif target_step == 4:
            _run_step_4(api_key, base_url, user_id)
        elif target_step == 5:
            _run_step_5(api_key, base_url, user_id)
        elif target_step == 6:
            _run_step_6(api_key, base_url, user_id)
        elif target_step == 7:
            _run_step_7(api_key, base_url, user_id)
        elif target_step == 8:
            _run_step_8(api_key, base_url, user_id)
        elif target_step == 9:
            _run_step_9(api_key, base_url, user_id, smart_wallet_address)
        elif target_step == 10:
            _run_step_10(api_key, base_url, user_id)
        
        return

    print("=" * 72)
    print("  BMONI KYC COMPLETION & WALLET ACTIVATION")
    print("=" * 72)
    
    # Shared storage for data passed between steps
    shared_data: dict = {}

    # ------------------------------------------------------------------
    # Step 0: Load required values from .env
    # ------------------------------------------------------------------
    print("\n[Step 0] Loading BMONI credentials from environment …")

    user_id = _from_dotenv("BMONI_USER_ID")
    smart_wallet_id = _from_dotenv("BMONI_SMART_WALLET_ID")
    smart_wallet_address = _from_dotenv("BMONI_SMART_WALLET_ADDRESS")

    if not user_id:
        logger.error(
            "BMONI_USER_ID is not set in backend/.env. "
            "Run python -m scripts.provision_wallet first to create a user and wallet."
        )
        sys.exit(1)

    if not smart_wallet_id:
        logger.error(
            "BMONI_SMART_WALLET_ID is not set in backend/.env. "
            "Run python -m scripts.provision_wallet first to create a user and wallet."
        )
        sys.exit(1)

    if not smart_wallet_address:
        print()
        print("  NOTE: BMONI_SMART_WALLET_ADDRESS is not in .env.")
        print("  It was printed during provision_wallet.py but not auto-saved.")
        print("  Enter it below, or Ctrl+C to abort and add it manually.")
        
        if os.environ.get("AUTO_FILL") == "true":
            print("  ERROR: AUTO_FILL mode requires BMONI_SMART_WALLET_ADDRESS in .env")
            print("  Please add it to backend/.env and retry.")
            sys.exit(1)
        else:
            smart_wallet_address = _prompt("  BMONI smart wallet address: ")

    print(f"  User ID:               {user_id}")
    print(f"  Smart wallet ID:       {smart_wallet_id}")
    print(f"  Smart wallet address:  {smart_wallet_address}")

    # ------------------------------------------------------------------
    # Step 1: GET /v1/users/{userId}/kyc/options
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 1/10] Fetching KYC options …")
    kyc_options = _call(
        "GET",
        f"/v1/users/{user_id}/kyc/options",
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/options",
    )
    identification_types: list[str] = []
    # Defensive: handle both dict and list responses
    if isinstance(kyc_options, dict):
        raw_types = kyc_options.get("identificationTypes") or kyc_options.get("identificationTypesList") or []
    elif isinstance(kyc_options, list):
        raw_types = kyc_options
    else:
        raw_types = []
    
    if isinstance(raw_types, list):
        identification_types = raw_types
    elif isinstance(raw_types, str):
        identification_types = [raw_types]
    print()
    print("  Valid identification types for Step 3:")
    for t in identification_types:
        print(f"    - {t}")
    print()
    print("  The KYC options response above shows what fields Step 6 expects.")
    print("  Note the valid values for gender, document types, etc.")

    # ------------------------------------------------------------------
    # Step 2: GET /v1/users/{userId}/kyc/occupations
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 2/10] Fetching occupations …")
    search_term = _prompt_optional("  Search occupations (press Enter for all): ", "")
    occupations_resp = _call(
        "GET",
        f"/v1/users/{user_id}/kyc/occupations?search={search_term}",
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/occupations",
    )
    # Save occupations response for Step 6
    shared_data["occupations_response"] = occupations_resp
    print("  (Save the occupationCode from the response — needed in Step 6)")
    print("  >>> Full occupations response structure for debugging:")
    print(json.dumps(occupations_resp, indent=2)[:2000])  # Print first 2000 chars

    # ------------------------------------------------------------------
    # Step 3: POST /v1/users/{userId}/kyc/documents/identification
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 3/10] Uploading identification document …")
    print()
    print("  >>> WARNING: For sandbox testing, use a placeholder/test image. <<<")
    print("  >>> do NOT use anyone's real ID document.                    <<<")
    print()
    
    # Skip document upload in auto mode
    if os.environ.get("AUTO_FILL") == "true":
        # Check for environment variable for auto-mode testing
        id_file = os.environ.get("KYC_ID_IMAGE_PATH")
        if id_file:
            print(f"  AUTO: Using KYC_ID_IMAGE_PATH from environment: {id_file}")
            # Use placeholder values for the rest of Step 3
            id_type = "passport"
            doc_number = "1234567890"
            issuing_country = "NGA"
            expiration_date = ""
            issue_date = ""

            id_data: dict = {
                "documentNumber": doc_number,
                "issuingCountry": issuing_country,
                "type": id_type,
            }
            if expiration_date:
                id_data["expirationDate"] = expiration_date
            if issue_date:
                id_data["issueDate"] = issue_date

            id_resp = _call_multipart(
                "POST",
                f"/v1/users/{user_id}/kyc/documents/identification",
                data=id_data,
                files_list=[("files", id_file)],
                api_key=api_key,
                base_url=base_url,
                step_label="kyc/documents/identification",
            )
            print("  Identification document uploaded.")
        else:
            print("  AUTO: Skipping ID document upload in auto mode")
            print("  Note: Set KYC_ID_IMAGE_PATH env var to test ID document upload")
            # Use placeholder values for the rest of Step 3
            id_type = "passport"
            doc_number = "1234567890"
            issuing_country = "NGA"
            expiration_date = ""
            issue_date = ""
            id_resp = {"success": True}  # Mock response
    else:
        id_file = _prompt("  Path to ID image file (jpg/png/pdf): ")

        ID_TYPES = [
            "passport", "drivers_license", "national_id",
            "government_id", "nric", "fin", "other",
        ]
        # Note: These types are for document upload only, not for identificationNumbers array
        # identificationNumbers only accepts: "ssn", "bvn", "nino", "tax_id", "pan", "other", "rfc", "curp"
        print("  Identification type:")
        for i, t in enumerate(ID_TYPES, 1):
            print(f"    {i}. {t}")
        
        while True:
            choice = _prompt(f"  Select 1-{len(ID_TYPES)}: ")
            try:
                idx = int(choice)
                if 1 <= idx <= len(ID_TYPES):
                    id_type = ID_TYPES[idx - 1]
                    break
            except ValueError:
                pass
            print(f"  Please enter a number between 1 and {len(ID_TYPES)}.")

        doc_number = _prompt("  Document number: ")
        issuing_country = _prompt_optional("  Issuing country (default NGA): ", "NGA")
        expiration_date = _prompt_optional("  Expiration date (YYYY-MM-DD, optional): ")
        issue_date = _prompt_optional("  Issue date (YYYY-MM-DD, optional): ")

        id_data: dict = {
            "documentNumber": doc_number,
            "issuingCountry": issuing_country,
            "type": id_type,
        }
        if expiration_date:
            id_data["expirationDate"] = expiration_date
        if issue_date:
            id_data["issueDate"] = issue_date

        id_resp = _call_multipart(
            "POST",
            f"/v1/users/{user_id}/kyc/documents/identification",
            data=id_data,
            files_list=[("files", id_file)],
            api_key=api_key,
            base_url=base_url,
            step_label="kyc/documents/identification",
        )
        print("  Identification document uploaded.")

    # ------------------------------------------------------------------
    # Step 4: POST /v1/users/{userId}/kyc/documents/proof-of-address
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 4/10] Uploading proof-of-address document …")
    print()
    print("  >>> WARNING: For sandbox testing, use a placeholder/test image. <<<")
    print("  >>> do NOT use anyone's real proof-of-address.                  <<<")
    print()
    
    # Skip document upload in auto mode
    if os.environ.get("AUTO_FILL") == "true":
        # Check for environment variable for auto-mode testing
        poa_file = os.environ.get("KYC_ADDRESS_IMAGE_PATH")
        if poa_file:
            print(f"  AUTO: Using KYC_ADDRESS_IMAGE_PATH from environment: {poa_file}")
            poa_type = "utility_bill"  # Auto-fill with reasonable default
            print(f"  AUTO: Using POA type = {poa_type}")

            poa_resp = _call_multipart(
                "POST",
                f"/v1/users/{user_id}/kyc/documents/proof-of-address",
                data={"type": poa_type},
                files_list=[("files", poa_file)],
                api_key=api_key,
                base_url=base_url,
                step_label="kyc/documents/proof-of-address",
            )
            print("  Proof-of-address document uploaded.")
        else:
            print("  AUTO: Skipping POA upload in auto mode")
            print("  Note: Set KYC_ADDRESS_IMAGE_PATH env var to test POA document upload")
            poa_resp = {"success": True}  # Mock response
    else:
        poa_file = _prompt("  Path to proof-of-address image file (jpg/png/pdf): ")
        poa_type = _prompt("  Document type (e.g. utility_bill, bank_statement): ")

        poa_resp = _call_multipart(
            "POST",
            f"/v1/users/{user_id}/kyc/documents/proof-of-address",
            data={"type": poa_type},
            files_list=[("files", poa_file)],
            api_key=api_key,
            base_url=base_url,
            step_label="kyc/documents/proof-of-address",
        )
        print("  Proof-of-address document uploaded.")

    # ------------------------------------------------------------------
    # Step 5: POST /v1/users/{userId}/kyc/documents/biometric
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 5/10] Uploading biometric document …")
    print()
    print("  >>> WARNING: For sandbox testing, use a placeholder/test image. <<<")
    print("  >>> do NOT use anyone's real biometric photo.                        <<<")
    print()
    
    # Check if this is for Nigeria rail (biometric is optional for NGN)
    if os.environ.get("AUTO_FILL") == "true":
        # Check for environment variable for auto-mode testing
        biometric_file = os.environ.get("KYC_BIOMETRIC_IMAGE_PATH")
        if biometric_file:
            print(f"  AUTO: Using KYC_BIOMETRIC_IMAGE_PATH from environment: {biometric_file}")
            biometric_type = "selfie"  # Auto-fill with reasonable default
            print(f"  AUTO: Using biometric type = {biometric_type}")

            biometric_resp = _call_multipart(
                "POST",
                f"/v1/users/{user_id}/kyc/documents/biometric",
                data={"type": biometric_type},
                files_list=[("selfie", biometric_file)],  # Note: field name is "selfie", not "files"
                api_key=api_key,
                base_url=base_url,
                step_label="kyc/documents/biometric",
            )
            print("  Biometric document uploaded.")
        else:
            print("  AUTO: Skipping biometric upload in auto mode (optional for NGN)")
            print("  Note: Set KYC_BIOMETRIC_IMAGE_PATH env var to test biometric upload")
            biometric_resp = {"success": True}  # Mock response
    else:
        # Ask operator if they want to skip biometric for NGN
        skip_biometric_input = _prompt_optional("  Skip biometric upload? (recommended for NGN) (y/n, default y): ", "y")
        skip_biometric = skip_biometric_input.lower() == "y"
        
        if skip_biometric:
            print("  Skipping biometric upload (optional for NGN rail)")
            biometric_resp = {"success": True}  # Mock response
        else:
            # Check for environment variable first
            biometric_file = os.environ.get("KYC_BIOMETRIC_IMAGE_PATH")
            if biometric_file:
                print(f"  Using KYC_BIOMETRIC_IMAGE_PATH from environment: {biometric_file}")
            else:
                biometric_file = _prompt("  Path to biometric selfie image file (jpg/png): ")
            
            biometric_type = _prompt("  Biometric type (e.g. selfie): ")

            biometric_resp = _call_multipart(
                "POST",
                f"/v1/users/{user_id}/kyc/documents/biometric",
                data={"type": biometric_type},
                files_list=[("selfie", biometric_file)],  # Note: field name is "selfie", not "files"
                api_key=api_key,
                base_url=base_url,
                step_label="kyc/documents/biometric",
            )
            print("  Biometric document uploaded.")

    # ------------------------------------------------------------------
    # Step 6: PATCH /v1/users/{userId}/kyc
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 6/10] Submitting KYC personal details …")
    print()
    print("  Refer to the Step 1 /kyc/options response for valid field values.")
    print()

    print()
    print("  Personal Information:")
    first_name = _prompt("  First name: ", "John")
    last_name = _prompt("  Last name: ", "Doe")
    date_of_birth = _prompt("  Date of birth (YYYY-MM-DD): ", "1990-01-01")
    gender = _prompt("  Gender (check Step 1 response for valid values, e.g. male/female): ", "male")
    email = _prompt("  Email: ", "john.doe@example.com")
    phone_number = _prompt("  Phone number: ", "+2348012345678")
    nationality = _prompt_optional("  Nationality (default NGA): ", "NGA")

    print()
    print("  Address:")
    street_line1 = _prompt("  Street line 1: ", "123 Main Street")
    street_line2 = _prompt_optional("  Street line 2 (optional): ", "")
    city = _prompt("  City: ", "Lagos")
    state = _prompt("  State / province: ", "Lagos")
    postal_code = _prompt_optional("  Postal code (optional): ", "100001")
    country_code = _prompt_optional("  Country code (default NGA): ", "NGA")

    print()
    print("  Employment:")
    print("  Select occupation from Step 2's occupations response.")
    if "occupations_response" in shared_data and shared_data["occupations_response"]:
        raw = shared_data["occupations_response"]
        if isinstance(raw, list):
            occupations = raw
        elif isinstance(raw, dict):
            occupations = raw.get("data") or raw.get("occupations") or []
        else:
            occupations = []
        
        if occupations:
            print("  Available occupations from Step 2:")
            occupation_list = []
            for i, occ in enumerate(occupations[:10], 1):  # Show first 10
                if isinstance(occ, dict):
                    code = occ.get("occupationCode") or occ.get("code") or occ.get("id")
                    name = occ.get("name") or occ.get("occupationName") or occ.get("title")
                    print(f"    {i}. {name} (code: {code})")
                    occupation_list.append((i, code, name))
                else:
                    print(f"    {i}. {occ}")
                    occupation_list.append((i, str(occ), str(occ)))
            
            # Auto-select first occupation in auto mode
            if os.environ.get("AUTO_FILL") == "true" and occupation_list:
                occupation_code = occupation_list[0][1]
                print(f"  AUTO: Selected {occupation_list[0][2]} (code: {occupation_code})")
            else:
                # Force selection from list
                while True:
                    choice = _prompt(f"  Select occupation (1-{len(occupation_list)}): ")
                    try:
                        idx = int(choice)
                        if 1 <= idx <= len(occupation_list):
                            occupation_code = occupation_list[idx - 1][1]
                            print(f"  Selected: {occupation_list[idx - 1][2]} (code: {occupation_code})")
                            break
                    except ValueError:
                        pass
                    print(f"  Please enter a number between 1 and {len(occupation_list)}.")
        else:
            print("  No occupations found in Step 2 response.")
            occupation_code = _prompt("  Occupation code (manual entry): ", "ENGINEER")
    else:
        print("  No occupations response available from Step 2.")
        occupation_code = _prompt("  Occupation code (manual entry): ", "ENGINEER")
    
    employer_name = _prompt_optional("  Employer name (optional): ", "GhostGuard Ltd")
    employment_status = _prompt_optional("  Employment status (optional): ", "employed")
    
    # Debug print to check exact value being sent
    print(f"  >>> employment_status value being sent: [{employment_status}]")
    
    # Validate employment status against allowed values
    allowed_employment_status = ["employed", "self_employed", "retired", "student", "unemployed", "homemaker"]
    if employment_status and employment_status not in allowed_employment_status:
        logger.error(
            "Invalid employment status: '%s'. Allowed values: %s",
            employment_status, ", ".join(allowed_employment_status)
        )
        sys.exit(1)

    print()
    print("  Financial Information:")
    source_of_income = _prompt_optional("  Source of income (default salary): ", "salary")
    estimated_annual_income = _prompt_float("  Estimated annual income (NGN)", 1000000.0)
    income_currency = _prompt_optional("  Income currency (default NGN): ", "NGN")
    estimated_monthly_volume = _prompt_float("  Estimated monthly transaction volume (NGN)", 500000.0)

    print()
    print("  BVN (Bank Verification Number):")
    print("  >>> Sandbox test BVN is 22222222222 — do NOT enter a real BVN. <<<")
    bvn = _prompt("  BVN: ", "22222222222")

    print()
    print("  Account purpose (personal, business, investment, actingAsIntermediary):")
    account_purpose = _prompt_optional("  Account purpose (default personal): ", "personal")
    account_purpose = _validate_enum(
        account_purpose,
        ["personal", "business", "investment", "actingAsIntermediary"],
        "accountPurpose"
    )

    print()
    print("  Source of funds (salary, business, investments, pension, government, inheritance, savings):")
    source_of_funds = _prompt_optional("  Source of funds (default salary): ", "salary")
    source_of_funds = _validate_enum(
        source_of_funds,
        ["salary", "business", "investments", "pension", "government", "inheritance", "savings"],
        "sourceOfFunds"
    )

    # Build nested payload matching BMONI API spec
    kyc_payload: dict = {
        "accountPurpose": account_purpose,
        "personalInfo": {
            "firstName": first_name,
            "lastName": last_name,
            "dateOfBirth": date_of_birth,
            "gender": gender,
            "email": email,
            "phoneNumber": phone_number,
            "nationality": nationality,
            "occupation": occupation_code,  # Top-level in personalInfo
            "sourceOfIncome": source_of_income,
            "estimatedAnnualIncome": estimated_annual_income,
            "incomeCurrency": income_currency,
        },
        "address": {
            "streetLine1": street_line1,
            "streetLine2": street_line2,
            "city": city,
            "state": state,
            "postalCode": postal_code,
            "countryCode": country_code,
        },
        "employment": {
            "occupationCode": occupation_code,
            "employerName": employer_name,
            "employmentStatus": employment_status,
        },
        "identificationNumbers": [
            {
                "type": "bvn",
                "number": bvn,
                "issuingCountryCode": "NGA",
            }
        ],
        "sourceOfFunds": source_of_funds,
        "estimatedMonthlyVolume": estimated_monthly_volume,
    }

    # Strip null values before sending
    kyc_payload = _strip_nulls(kyc_payload)

    kyc_resp = _call(
        "PATCH",
        f"/v1/users/{user_id}/kyc",
        json_body=kyc_payload,
        api_key=api_key,
        base_url=base_url,
        step_label="kyc PATCH",
    )
    print("  KYC details submitted.")

    # ------------------------------------------------------------------
    # Step 7: GET /v1/users/{userId}/kyc/readiness
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 7/10] Checking KYC readiness …")
    readiness = _call(
        "GET",
        f"/v1/users/{user_id}/kyc/readiness",
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/readiness",
    )

    # Defensive: handle both dict and list responses
    if isinstance(readiness, dict):
        ready = readiness.get("ready") or readiness.get("isReady") or readiness.get("status") == "ready"
        if not ready:
            reason = readiness.get("reason") or readiness.get("message") or "unknown reason"
            print(f"\n  KYC is NOT ready. Reason: {reason}")
            print("  Fix the issue and re-run this script.")
            print("  Do NOT proceed to activation with incomplete KYC.")
            sys.exit(1)
    else:
        print(f"\n  KYC readiness check returned unexpected format: {type(readiness)}")
        print("  Proceeding with caution - verify KYC status manually.")

    print("  KYC readiness check passed.")

    # ------------------------------------------------------------------
    # Step 8: POST /v1/users/{userId}/kyc/activate
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 8/10] Activating KYC …")
    
    activate_payload = {
        "sumsubLevelName": "id-and-liveness"
    }
    
    activate_resp = _call(
        "POST",
        f"/v1/users/{user_id}/kyc/activate",
        json_body=activate_payload,
        api_key=api_key,
        base_url=base_url,
        step_label="kyc/activate",
    )
    print("  KYC activation submitted. Raw response printed above.")
    print("  Note: Success determined by HTTP status code (200/201), not response body parsing.")

    # ------------------------------------------------------------------
    # Step 9: POST /v1/users/{userId}/onboarding/start-nigeria
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print("[Step 9/10] Starting NGN onboarding …")
    print()
    print("  ###########################################################################")
    print("  #  WARNING: ngnWalletIndex is UNCONFIRMED                                 #")
    print("  #                                                                         #")
    print("  #  The BMONI docs don't specify what ngnWalletIndex should be or where    #")
    print("  #  it comes from. Possible sources:                                       #")
    print("  #                                                                         #")
    print("  #  a) A field in the smart wallet creation response (\"index\" /            #")
    print("  #     \"walletIndex\") that provision_wallet.py did not capture. The        #")
    print("  #     create-managed response should be checked for such a field.         #")
    print("  #                                                                         #")
    print("  #  b) A value provided by BMONI staff for your sandbox environment.       #")
    print("  #                                                                         #")
    print("  #  Defaulting to 0 as a guess. If onboarding fails, this is the           #")
    print("  #  likely cause — check with BMONI support for the correct value.         #")
    print("  ###########################################################################")
    print()
    ngn_wallet_index = _prompt_int("  ngnWalletIndex", 0)

    # Confirm ngnWalletAddress is the smart wallet address, not owner address
    print(f"  Using smart wallet address: {smart_wallet_address}")
    print(f"  (This should be the walletAddress from smart wallet creation, not owner address)")

    onboarding_payload = {
        "bvn": bvn,
        "ngnWalletAddress": smart_wallet_address,
        "ngnWalletIndex": ngn_wallet_index,  # Ensured to be int via _prompt_int
    }
    
    print(f"  >>> Onboarding payload: ngnWalletIndex type = {type(ngn_wallet_index).__name__}, value = {ngn_wallet_index}")
    
    onboarding_resp = _call(
        "POST",
        f"/v1/users/{user_id}/onboarding/start-nigeria",
        json_body=onboarding_payload,
        api_key=api_key,
        base_url=base_url,
        step_label="onboarding/start-nigeria",
    )
    print("  Onboarding request submitted. Raw response printed above.")
    print("  Note: Success determined by HTTP status code (200/201), not response body parsing.")
    print("  BMONI docs state: '201 on success, no body parsed' - empty response is expected.")

    # ------------------------------------------------------------------
    # Step 10: GET /v1/users/{userId}/onboarding/status (poll)
    # ------------------------------------------------------------------
    print("\n" + "-" * 72)
    print(f"[Step 10/10] Polling onboarding status "
          f"(up to {MAX_POLL_ATTEMPTS} attempts, {POLL_INTERVAL}s interval) …")

    rail_active = False
    first_response_seen = False
    
    for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
        print(f"\n  Poll attempt {attempt}/{MAX_POLL_ATTEMPTS} …")
        status_resp = _call(
            "GET",
            f"/v1/users/{user_id}/onboarding/status",
            api_key=api_key,
            base_url=base_url,
            step_label=f"onboarding/status (attempt {attempt})",
        )

        # Always print full raw response on first attempt to understand structure
        if not first_response_seen:
            print("  >>> First poll attempt - full raw response structure:")
            print(json.dumps(status_resp, indent=2)[:3000])
            first_response_seen = True
            
            # If structure is unclear, stop after first attempt to avoid blind polling
            if not isinstance(status_resp, dict) or not status_resp:
                print("  WARNING: Response structure unclear - stopping polling to avoid blind attempts")
                print("  Please examine the response above and update parsing logic")
                break

        # Defensive: handle response structure - look for Nigeria-specific status
        # BMONI docs: status is "per provider/rail" - based on pattern from other rails:
        # - paytrieStatus=Canada (confirmed in docs)
        # - etherfuseStatus=Mexico (confirmed in docs)
        # - moneriumStatus=Europe (confirmed in docs)
        # INFERRED: anchorStatus=Nigeria (Anchor is a known Nigerian banking provider)
        # INFERRED: bridgeStatus=USA (Bridge is a known US banking provider)
        # NOTE: This field mapping is INFERRED, not confirmed by BMONI docs - verify with staff
        if isinstance(status_resp, dict):
            # Look for anchorStatus field for Nigeria rail
            nigeria_status = status_resp.get("anchorStatus")
            rejection_reason = status_resp.get("anchorRejectionReason") or status_resp.get("rejectionReason") or status_resp.get("reason") or status_resp.get("message")
            
            print(f"  >>> Nigeria anchorStatus: {nigeria_status}")
            
            if nigeria_status:
                status_lower = nigeria_status.lower()
                
                # Check for rejection or resubmission required
                if status_lower in ("rejected", "requires_resubmission"):
                    if rejection_reason:
                        print(f"  ERROR: Nigeria rail rejected. Reason: {rejection_reason}")
                    else:
                        print(f"  ERROR: Nigeria rail rejected or requires resubmission")
                    print("  Please check BMONI dashboard for guidance on required corrections")
                    sys.exit(1)
                
                # Check for active status
                elif status_lower == "active":
                    print(f"  SUCCESS: Nigeria rail is {nigeria_status}")
                    rail_active = True
                    break
                
                # Other statuses (not_started, pending_review, etc.)
                elif status_lower in ("not_started", "pending_review"):
                    print(f"  Nigeria rail status: {nigeria_status} (waiting for activation)")
                else:
                    print(f"  Nigeria rail status: {nigeria_status} (unknown status)")
            
            else:
                print("  WARNING: Could not find anchorStatus field in response")
                print("  NOTE: Field mapping is inferred - may need verification with BMONI staff")

        if rail_active:
            break

        if attempt < MAX_POLL_ATTEMPTS:
            print(f"  Rail not yet active. Waiting {POLL_INTERVAL}s …")
            time.sleep(POLL_INTERVAL)

    if not rail_active:
        print()
        logger.error(
            "NGN rail did not become active after %d attempts. "
            "Check with BMONI staff to confirm onboarding status.",
            MAX_POLL_ATTEMPTS,
        )
        sys.exit(1)

    print("\n  Nigeria NGN rail is ACTIVE.")

    # ------------------------------------------------------------------
    # Optional: Retry KYC submission (if --retry flag is set)
    # ------------------------------------------------------------------
    if args.retry:
        print("\n" + "-" * 72)
        print("[Optional] Calling POST /kyc/retry …")
        print()
        
        # Confirm operator has already updated KYC via Step 6
        if os.environ.get("AUTO_FILL") != "true":
            confirm = input("  Have you already updated your KYC fields via Step 6? (yes/no): ").strip().lower()
            if confirm != "yes":
                print("  Skipping retry. You can run Step 6 separately: --patch-kyc-only")
                print("  Then retry: --retry-only")
            else:
                retry_payload = {
                    "sumsubLevelName": "id-and-liveness"
                }
                retry_resp = _call(
                    "POST",
                    f"/v1/users/{user_id}/kyc/retry",
                    json_body=retry_payload,
                    api_key=api_key,
                    base_url=base_url,
                    step_label="kyc/retry",
                )
                print("  KYC retry submitted. Raw response printed above.")
        else:
            print("  AUTO: Skipping retry confirmation in auto mode")
            retry_payload = {
                "sumsubLevelName": "id-and-liveness"
            }
            retry_resp = _call(
                "POST",
                f"/v1/users/{user_id}/kyc/retry",
                json_body=retry_payload,
                api_key=api_key,
                base_url=base_url,
                step_label="kyc/retry",
            )
            print("  KYC retry submitted. Raw response printed above.")

    # ------------------------------------------------------------------
    # Done
    # ------------------------------------------------------------------
    print()
    print("=" * 72)
    print("  KYC COMPLETED & NGN RAIL ACTIVATED")
    print("=" * 72)
    print()
    print("  The wallet is ready to be funded.")
    print()
    print("  >>> IMPORTANT: Give BMONI staff the phone number on file")
    print("      for this user so they can credit test funds to the wallet. <<<")
    print()
    print("  > NOTE: provision_wallet.py does not currently save")
    print("    BMONI_SMART_WALLET_ADDRESS to .env automatically.")
    print("    You should add that line so this script can find it next time.")
    print()
    print("  > NOTE: If onboarding failed with an API error about")
    print("    ngnWalletIndex, check whether the create-managed response")
    print("    in provision_wallet.py included an \"index\" or \"walletIndex\"")
    print("    field that wasn't captured. If so, that's the real source.")


if __name__ == "__main__":
    main()

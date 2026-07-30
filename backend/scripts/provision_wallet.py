"""
One-time BMONI smart wallet provisioning script.

Run exactly ONCE per environment (development, staging, production).
This script:
  1. Generates an EVM keypair for the employer's BMONI smart wallet owner.
  2. Creates a BMONI user for the employer.
  3. Creates a CNGN smart wallet for that user.

The operator is prompted to save the private key, BMONI user ID, and
smart wallet ID into backend/.env.  The script never writes these values
to disk automatically.

Never run against a production environment without a full security review.

Usage:
    python -m scripts.provision_wallet

Requires:
    - BMONI_BASE_URL and BMONI_API_KEY set in the environment or backend/.env
    - eth-account (pip install eth-account)
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import os
import sys

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("provision_wallet")

TIMEOUT = 30.0


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
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
    if not os.path.isfile(env_path):
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
) -> dict:
    """Make an authenticated BMONI API call.  Exits the process on failure."""
    url = f"{base_url}{path}"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }
    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.request(method, url, json=json_body, headers=headers)
    except httpx.TimeoutException:
        logger.error("BMONI request timed out: %s %s", method, path)
        sys.exit(1)
    except httpx.RequestError as exc:
        logger.error("BMONI request failed: %s %s — %s", method, path, exc)
        sys.exit(1)

    if response.status_code >= 400:
        body_text = response.text
        try:
            body = response.json()
            body_text = body.get("message") or body.get("error") or body_text
        except ValueError:
            pass
        logger.error(
            "BMONI API error: %s %s returned %s — %s",
            method, path, response.status_code, body_text,
        )
        sys.exit(1)

    return response.json()


def _prompt(prompt: str) -> str:
    """Read a non-empty string from the operator, re-prompting if blank."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("  Input cannot be empty. Please try again.")


def _prompt_email(prompt: str) -> str:
    """Read an email address, validating it contains '@' and '.'."""
    while True:
        value = input(prompt).strip().lower()
        if "@" in value and "." in value:
            return value
        print("  Invalid email address. Must contain '@' and a domain (e.g. user@example.com).")


def _prompt_phone(prompt: str) -> str:
    """Read a phone number, validating it starts with '+' followed by digits."""
    while True:
        value = input(prompt).strip()
        if value.startswith("+") and all(c.isdigit() for c in value[1:]):
            return value
        print("  Invalid phone number. Must start with '+' and contain only digits (e.g. +2348012345678).")


def _prompt_optional(prompt: str) -> str:
    """Read an optional string; returns empty if the operator enters nothing."""
    return input(prompt).strip()


def _confirm(prompt: str) -> None:
    """Require the operator to type 'yes' before proceeding."""
    answer = input(f"{prompt} Type 'yes' to continue: ").strip().lower()
    if answer != "yes":
        logger.info("Aborted by operator.")
        sys.exit(0)


def main() -> None:
    api_key = _api_key()
    base_url = _base_url()

    print("=" * 72)
    print("  BMONI SMART WALLET PROVISIONING")
    print("=" * 72)

    # ------------------------------------------------------------------
    # Resume check — can we skip key generation and user creation?
    # ------------------------------------------------------------------
    existing_user_id = _from_dotenv("BMONI_USER_ID")
    existing_private_key = _from_dotenv("BMONI_OWNER_PRIVATE_KEY")

    if existing_user_id and existing_private_key:
        print(f"\nExisting BMONI_USER_ID and private key found — skipping user creation.")
        try:
            account = Account.from_key(existing_private_key)
        except Exception as exc:
            logger.error("Saved private key is invalid: %s", exc)
            sys.exit(1)
        address = account.address
        private_key_hex = existing_private_key
        user_id = existing_user_id
        print(f"  Loaded address:  {address}")
        answer = input(f"\nResume with existing user {user_id}? (yes/no): ").strip().lower()
        if answer != "yes":
            print("  OK, starting fresh with a new keypair and user.")
            existing_user_id = None
            existing_private_key = None
        else:
            print("  Resuming at Step 3 (owner-proof challenge).")
    elif existing_user_id and not existing_private_key:
        logger.error(
            "Found BMONI_USER_ID in .env but no BMONI_OWNER_PRIVATE_KEY. "
            "Either add the private key or remove BMONI_USER_ID to start fresh."
        )
        sys.exit(1)
    elif not existing_user_id and existing_private_key:
        logger.error(
            "Found BMONI_OWNER_PRIVATE_KEY in .env but no BMONI_USER_ID. "
            "Either add BMONI_USER_ID or remove BMONI_OWNER_PRIVATE_KEY to start fresh."
        )
        sys.exit(1)

    if not existing_user_id or not existing_private_key:
        # ------------------------------------------------------------------
        # Step 1: Generate EVM keypair
        # ------------------------------------------------------------------
        print("\n[1/4] Generating EVM keypair …")
        account = Account.create()
        address = account.address
        private_key_hex = account.key.hex()

        print(f"\n  Owner address:  {address}")
        print(f"\n  >>> SAVE THIS PRIVATE KEY — it will NOT be shown again <<<")
        print(f"  Private key:    {private_key_hex}")
        print(f"\n  Add to backend/.env:")
        print(f"  BMONI_OWNER_PRIVATE_KEY={private_key_hex}")
        _confirm("\nHave you saved the private key to .env and secured it?")

        # ------------------------------------------------------------------
        # Step 2: Create BMONI user
        # ------------------------------------------------------------------
        print("\n[2/4] Creating BMONI user …")
        print()
        email = _prompt_email("  Employer email: ")
        first_name = _prompt("  Employer first name: ")
        print()
        print("  BMONI staff will use this phone number to credit test funds.")
        print("  It must be a real number the team can access, e.g. +2348012345678.")
        phone_number = _prompt_phone("  Employer phone number (e.g. +234...): ")
        last_name = _prompt_optional("  Employer last name (optional — press Enter to skip): ")

        user_payload: dict = {
            "email": email,
            "firstName": first_name,
            "phoneNumber": phone_number,
        }
        if last_name:
            user_payload["lastName"] = last_name

        user_resp = _call("POST", "/v1/users", json_body=user_payload, api_key=api_key, base_url=base_url)
        user_obj = user_resp.get("user", user_resp)
        user_id = user_obj.get("bmoniUserId") or user_obj.get("userId") or user_obj.get("id")
        if not user_id:
            logger.error("BMONI user creation did not return a user ID: %s", user_resp)
            sys.exit(1)

        print(f"\n  BMONI user ID:  {user_id}")
        print(f"\n  >>> SAVE THIS — it will NOT be shown again <<<")
        print(f"  Add to backend/.env:")
        print(f"  BMONI_USER_ID={user_id}")
        _confirm("\nHave you saved BMONI_USER_ID to .env?")

    # ------------------------------------------------------------------
    # Step 3: Request owner-proof challenge
    # ------------------------------------------------------------------
    print("\n[3/4] Requesting owner-proof challenge …")
    challenge_payload: dict = {
        "currency": "CNGN",
        "userOwnerAddress": address,
    }
    challenge_resp = _call(
        "POST",
        f"/v1/users/{user_id}/smart-wallets/owner-proof-challenges",
        json_body=challenge_payload,
        api_key=api_key,
        base_url=base_url,
    )
    print()  # TEMPORARY — remove after confirming response shape
    print("  >>> RAW challenge response:", challenge_resp)  # TEMPORARY
    challenge_id = challenge_resp.get("challengeId") or challenge_resp.get("id")
    eip191_message = challenge_resp.get("eip191Message") or challenge_resp.get("message")
    if not challenge_id or not eip191_message:
        logger.error(
            "Owner-proof challenge response missing challengeId or eip191Message: %s",
            challenge_resp,
        )
        sys.exit(1)

    expires_at_str = challenge_resp.get("expiresAt")
    if expires_at_str:
        try:
            expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
            remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                print(f"  Challenge expires in {remaining:.0f} seconds — sign promptly.")
            else:
                print("  WARNING: Challenge has already expired. The next step may fail.")
        except (ValueError, TypeError):
            print(f"  Could not parse expiresAt value: {expires_at_str}")

    # ------------------------------------------------------------------
    # Step 4: Sign the EIP-191 message
    # ------------------------------------------------------------------
    print("  Signing challenge message …")
    message_obj = encode_defunct(text=eip191_message)
    signed = Account.sign_message(message_obj, private_key_hex)
    signature_hex = signed.signature.hex()
    if not signature_hex.startswith("0x"):
        signature_hex = "0x" + signature_hex

    expected_sig_len = 132
    if len(signature_hex) != expected_sig_len:
        logger.error(
            "Signature has unexpected length: got %d chars, expected %d (65-byte 0x-prefixed hex). Signature: %s",
            len(signature_hex), expected_sig_len, signature_hex,
        )
        sys.exit(1)

    # ------------------------------------------------------------------
    # Step 5: Create managed smart wallet
    # ------------------------------------------------------------------
    print("\n[4/4] Creating managed smart wallet …")
    wallet_payload: dict = {
        "currency": "CNGN",
        "userOwnerAddress": address,
        "ownerProofChallengeId": challenge_id,
        "ownerProofSignature": signature_hex,
    }
    wallet_resp = _call(
        "POST",
        f"/v1/users/{user_id}/smart-wallets/create-managed",
        json_body=wallet_payload,
        api_key=api_key,
        base_url=base_url,
    )
    print()  # TEMPORARY — remove after confirming response shape
    print("  >>> RAW wallet response:", wallet_resp)  # TEMPORARY
    smart_wallet_id = (
        wallet_resp.get("smartWalletId")
        or wallet_resp.get("walletId")
        or wallet_resp.get("id")
    )
    smart_wallet_address = (
        wallet_resp.get("address")
        or wallet_resp.get("smartWalletAddress")
        or wallet_resp.get("walletAddress")
    )
    wallet_index = (
        wallet_resp.get("index")
        or wallet_resp.get("walletIndex")
    )

    if not smart_wallet_id:
        logger.error("Smart wallet creation did not return a wallet ID: %s", wallet_resp)
        sys.exit(1)

    print(f"\n  Smart wallet ID:      {smart_wallet_id}")
    if smart_wallet_address:
        print(f"  Smart wallet address:  {smart_wallet_address}")
    if wallet_index is not None:
        print(f"  Wallet index:          {wallet_index}")
    print(f"\n  >>> SAVE THESE — they will NOT be shown again <<<")
    print(f"  Add to backend/.env:")
    print(f"  BMONI_USER_ID={user_id}")
    print(f"  BMONI_SMART_WALLET_ID={smart_wallet_id}")
    if wallet_index is not None:
        print(f"  BMONI_SMART_WALLET_INDEX={wallet_index}")
    _confirm("\nHave you saved BMONI_SMART_WALLET_ID and BMONI_USER_ID to .env?")

    print("\n" + "=" * 72)
    print("  PROVISIONING COMPLETE")
    print("  The BMONI smart wallet is ready for use.")
    print("=" * 72)


if __name__ == "__main__":
    main()

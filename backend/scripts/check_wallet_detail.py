"""
One-off diagnostic: fetch and display the full BMONI smart wallet detail.

Usage:
    python -m scripts.check_wallet_detail

Requires:
    - BMONI_BASE_URL and BMONI_API_KEY set in the environment or backend/.env
    - BMONI_USER_ID and BMONI_SMART_WALLET_ID in backend/.env
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("check_wallet_detail")

TIMEOUT = 30.0


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


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    api_key = _api_key()
    base_url = _base_url()

    user_id = _from_dotenv("BMONI_USER_ID")
    smart_wallet_id = _from_dotenv("BMONI_SMART_WALLET_ID")

    if not user_id:
        logger.error(
            "BMONI_USER_ID is not set in backend/.env. "
            "Run python -m scripts.provision_wallet first."
        )
        sys.exit(1)

    if not smart_wallet_id:
        logger.error(
            "BMONI_SMART_WALLET_ID is not set in backend/.env. "
            "Run python -m scripts.provision_wallet first."
        )
        sys.exit(1)

    print("=" * 72)
    print("  BMONI SMART WALLET DETAIL CHECK")
    print("=" * 72)
    print(f"  User ID:         {user_id}")
    print(f"  Smart Wallet ID: {smart_wallet_id}")
    print()

    result = _call(
        "GET",
        f"/v1/users/{user_id}/smart-wallets/{smart_wallet_id}",
        api_key=api_key,
        base_url=base_url,
    )

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()

"""
One-off diagnostic script to check BMONI smart wallet balances.

Calls GET /v1/users/{userId}/smart-wallets/account/balances
and pretty-prints the full raw JSON response.

Usage:
    python -m scripts.check_balance

Requires:
    - BMONI_BASE_URL and BMONI_API_KEY set in the environment or backend/.env
    - BMONI_USER_ID in backend/.env
"""

import json
import logging
import os
import sys

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("check_balance")

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


def main() -> None:
    api_key = _api_key()
    base_url = _base_url()
    
    user_id = _from_dotenv("BMONI_USER_ID")
    if not user_id:
        logger.error("BMONI_USER_ID is not set in backend/.env.")
        sys.exit(1)

    print("=" * 72)
    print("  BMONI SMART WALLET BALANCE CHECK")
    print("=" * 72)
    print(f"  User ID: {user_id}")
    print(f"  Base URL: {base_url}")
    print()

    url = f"{base_url}/v1/users/{user_id}/smart-wallets/account/balances"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
    }

    try:
        with httpx.Client(timeout=TIMEOUT) as client:
            response = client.get(url, headers=headers)
    except httpx.TimeoutException:
        logger.error("BMONI request timed out")
        sys.exit(1)
    except httpx.RequestError as exc:
        logger.error("BMONI request failed: %s", exc)
        sys.exit(1)

    print(f"  Status Code: {response.status_code}")
    print()
    print("  Raw JSON Response:")
    print("-" * 72)

    try:
        data = response.json()
        print(json.dumps(data, indent=2))
    except ValueError:
        print(response.text)

    print("-" * 72)
    
    if response.status_code >= 400:
        logger.error("Request failed with status %d", response.status_code)
        sys.exit(1)


if __name__ == "__main__":
    main()

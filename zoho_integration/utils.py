
# zoho_integration/utils.py

import requests
from django.conf import settings


class ZohoAuthError(Exception):
    """Auth / token errors from Zoho."""
    pass


def get_zoho_access_token() -> str:
    """
    Use REFRESH TOKEN to get a fresh ACCESS TOKEN from Zoho.
    Uses:
      settings.ZOHO_AUTH_BASE_URL
      settings.ZOHO_CLIENT_ID
      settings.ZOHO_CLIENT_SECRET
      settings.ZOHO_REFRESH_TOKEN
    """
    if not settings.ZOHO_REFRESH_TOKEN:
        raise ZohoAuthError("ZOHO_REFRESH_TOKEN is not set. Fill it in .env first.")

    token_url = f"{settings.ZOHO_AUTH_BASE_URL}/token"

    data = {
        "refresh_token": settings.ZOHO_REFRESH_TOKEN,
        "client_id": settings.ZOHO_CLIENT_ID,
        "client_secret": settings.ZOHO_CLIENT_SECRET,
        "grant_type": "refresh_token",
    }

    try:
        r = requests.post(token_url, data=data, timeout=20)
    except requests.exceptions.RequestException as e:
        raise ZohoAuthError(f"Error calling Zoho token endpoint: {e}")

    try:
        j = r.json()
    except ValueError:
        raise ZohoAuthError(f"Non-JSON response from Zoho: {r.text}")

    if "access_token" not in j:
        # Print the whole error so you see the message & code
        raise ZohoAuthError(f"Failed to get access_token from Zoho: {j}")

    return j["access_token"]

class ZohoBooksError(Exception):
    pass

def _zoho_raise_if_error(resp: requests.Response, action: str) -> dict:
    try:
        data = resp.json() if resp.content else {}
    except Exception:
        data = {"raw": (resp.text or "")[:1000]}

    if resp.status_code >= 400:
        raise ZohoBooksError(f"{action} failed (HTTP {resp.status_code}): {data}")

    if isinstance(data, dict) and data.get("code") not in (None, 0):
        raise ZohoBooksError(f"{action} failed (Zoho code {data.get('code')}): {data}")

    return data



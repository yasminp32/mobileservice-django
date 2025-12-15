
# zoho_integration/zoho_books.py
# zoho_integration/zoho_books.py
import requests
from django.conf import settings
from .utils import get_zoho_access_token


class ZohoBooksError(Exception):
    pass


ACCOUNT_KEY_TO_SETTING = {
    "sales": "ZOHO_SALES_ACCOUNT_ID",
    "service_income": "ZOHO_SERVICE_INCOME_ACCOUNT_ID",
    "cogs": "ZOHO_COGS_ACCOUNT_ID",
    "other_income": "ZOHO_OTHER_INCOME_ACCOUNT_ID",
}


def _get_zoho_headers():
    token = get_zoho_access_token()
    return {"Authorization": f"Zoho-oauthtoken {token}"}


def _get_account_id(account_key: str) -> str:
    
    setting_name = ACCOUNT_KEY_TO_SETTING.get(account_key)
    if not setting_name:
        raise ZohoBooksError(f"Invalid account key: {account_key}")

    account_id = getattr(settings, setting_name, "")
    if not account_id:
        raise ZohoBooksError(
            f"Missing {setting_name} in settings/.env (needed for '{account_key}')"
        )
    return account_id


def upload_item_image_to_zoho(zoho_item_id: str, file_obj):
    access_token = get_zoho_access_token()

    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }

    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID

    # ✅ Correct endpoint
    url = f"{base_url}/items/{zoho_item_id}/images"
    params = {"organization_id": org_id}

    #  CRITICAL: reset file pointer
    file_obj.seek(0)

    files = {
        "image": (
            file_obj.name,
            file_obj,
            getattr(file_obj, "content_type", "image/jpeg"),
        )
    }

    r = requests.post(
        url,
        headers=headers,
        params=params,
        files=files,
        timeout=60,
    )

    try:
        data = r.json()
    except ValueError:
        raise ZohoBooksError(f"Zoho returned non-JSON response: {r.text}")

    #  Validate Zoho response code
    if r.status_code >= 400 or data.get("code") != 0:
        raise ZohoBooksError(
            f"Zoho image upload failed (HTTP {r.status_code}): {data}"
        )

    return data



def create_zoho_item(payload: dict):
    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID
    url = f"{base_url}/items?organization_id={org_id}"

    headers = _get_zoho_headers()
    headers["Content-Type"] = "application/json"

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    try:
        data = r.json()
    except Exception:
        raise ZohoBooksError(f"Invalid JSON from Zoho (HTTP {r.status_code})")

    if r.status_code >= 400 or data.get("code") not in (0,):
        raise ZohoBooksError(f"Zoho error (HTTP {r.status_code}): {data}")

    return data
def update_zoho_item(item_id: str, payload: dict):
    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID
    url = f"{base_url}/items/{item_id}?organization_id={org_id}"

    headers = _get_zoho_headers()
    headers["Content-Type"] = "application/json"

    r = requests.put(url, headers=headers, json=payload, timeout=60)
    data = r.json()
    if r.status_code >= 400 or data.get("code") != 0:
        raise ZohoBooksError(f"Zoho update error (HTTP {r.status_code}): {data}")
    return data

def build_zoho_item_payload_from_local(local_item) -> dict:
    # ✅ 1) Decide Zoho item_type from local booleans
    if local_item.is_sellable and local_item.is_purchasable:
        item_type = "sales_and_purchases"
    elif local_item.is_purchasable:
        item_type = "purchases"
    else:
        item_type = "sales"

    payload = {
        "name": local_item.name,
        "product_type": local_item.product_type,      # goods/service
        "unit": local_item.unit,
        "tax_preference": local_item.tax_preference,
        "hsn_or_sac": local_item.hsn_or_sac or "",
        "item_type": item_type,                       # ✅ CRITICAL for purchase fields
    }
    # ✅ SEND SKU TO ZOHO
    if local_item.sku:
        payload["sku"] = local_item.sku
    # ✅ 2) Sales fields
    if item_type in {"sales", "sales_and_purchases"}:
        if local_item.sales_account not in {"sales", "service_income", "other_income"}:
            raise ZohoBooksError("Sales items must use INCOME accounts only")

        payload["rate"] = float(local_item.selling_price or 0)
        payload["account_id"] = _get_account_id(local_item.sales_account)

        if local_item.sales_description:
            payload["description"] = local_item.sales_description

    # ✅ 3) Purchase fields
    if item_type in {"purchases", "sales_and_purchases"}:
        if local_item.purchase_account not in {"cogs"}:
            raise ZohoBooksError("Purchase items must use EXPENSE accounts (COGS)")

        payload["purchase_rate"] = float(local_item.cost_price or 0)
        payload["purchase_account_id"] = _get_account_id(local_item.purchase_account)

        if local_item.purchase_description:
            payload["purchase_description"] = local_item.purchase_description

        # preferred_vendor must be a REAL Zoho vendor_id
        if local_item.preferred_vendor:
            payload["vendor_id"] = local_item.preferred_vendor

    return payload
def delete_zoho_item(item_id: str):
    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID
    url = f"{base_url}/items/{item_id}?organization_id={org_id}"

    headers = _get_zoho_headers()

    r = requests.delete(url, headers=headers, timeout=60)
    try:
        data = r.json()
    except Exception:
        raise ZohoBooksError(f"Invalid JSON from Zoho delete (HTTP {r.status_code})")

    if r.status_code >= 400 or data.get("code") != 0:
        raise ZohoBooksError(f"Zoho delete error (HTTP {r.status_code}): {data}")

    return data


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

        #payload["rate"] = float(local_item.selling_price or 0)
        selling = float(local_item.selling_price or 0)
        svc = float(local_item.service_charge or 0) 
        payload["rate"] = selling + svc 
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

#contact
def build_zoho_contact_payload(local_customer) -> dict:
    payload = {
        "contact_name": local_customer.name,
        "contact_type": "customer",
    }

    email = (local_customer.email or "").strip()
    phone = (local_customer.phone or "").strip()
    state = (local_customer.state or "").strip()

    if email:
        payload["email"] = email  # keep (some orgs accept root email)

    if phone:
        payload["mobile"] = phone
        payload["phone"] = phone
     # ✅ 1) Custom field (will show in Custom Fields)
    if state:
        payload["custom_fields"] = [
            {"api_name": "cf_state", "value": state}
        ]

        # ✅ 2) Address state (will show in Address Region/State)
        payload["billing_address"] = {
            "state": state,
            "country": "India"
        }

        # optional
        payload["shipping_address"] = {
            "state": state,
            "country": "India"
        }
    # ✅ also set primary contact person
    cp = {}
    if email:
        cp["email"] = email
    if phone:
        cp["mobile"] = phone
        cp["phone"] = phone
    
    if cp:
        cp["is_primary_contact"] = True
        payload["contact_persons"] = [cp]

    return payload



def create_zoho_contact(payload: dict) -> dict:
    access_token = get_zoho_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID
    url = f"{base_url}/contacts?organization_id={org_id}"

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    data = r.json() if r.content else {}

    if r.status_code >= 400:
        raise ZohoBooksError(f"Zoho contact create error (HTTP {r.status_code}): {data}")

    return data


def update_zoho_contact(zoho_contact_id: str, payload: dict) -> dict:
    access_token = get_zoho_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID
    url = f"{base_url}/contacts/{zoho_contact_id}?organization_id={org_id}"

    r = requests.put(url, headers=headers, json=payload, timeout=60)
    data = r.json() if r.content else {}

    if r.status_code >= 400:
        raise ZohoBooksError(f"Zoho contact update error (HTTP {r.status_code}): {data}")

    return data

def search_zoho_contact(email: str = "", phone: str = "") -> dict:
    """
    Search Zoho Books contacts by email / phone.
    Returns API response dict.
    """
    access_token = get_zoho_access_token()
    headers = {"Authorization": f"Zoho-oauthtoken {access_token}"}

    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID

    # Zoho Books supports search_text for contacts
    search_text = email or phone
    if not search_text:
        return {"contacts": []}

    url = f"{base_url}/contacts?organization_id={org_id}&search_text={search_text}"
    r = requests.get(url, headers=headers, timeout=60)
    data = r.json() if r.content else {}

    if r.status_code >= 400:
        raise ZohoBooksError(f"Zoho contact search error (HTTP {r.status_code}): {data}")

    return data


#invoice
from decimal import Decimal
import requests
from django.conf import settings

from .models import LocalInvoice, LocalItem
from .utils import ZohoBooksError, _zoho_raise_if_error


def _gst_percent_from_choice(gst_choice: str) -> Decimal:
    if not gst_choice or gst_choice == "NO_TAX":
        return Decimal("0")
    try:
        # GST_18 -> 18, IGST_12 -> 12
        return Decimal(gst_choice.split("_")[1])
    except Exception:
        return Decimal("0")


def build_zoho_invoice_payload_from_local(invoice: LocalInvoice) -> dict:
    """
    Zoho Books create invoice arguments include:
    - customer_id (required)
    - date, due_date
    - discount, is_discount_before_tax, discount_type
    - line_items (required) :contentReference[oaicite:1]{index=1}

    Important: Zoho needs item_id for each line item. :contentReference[oaicite:2]{index=2}
    So LocalItem must have zoho_item_id.
    """
    if not getattr(invoice.customer, "zoho_contact_id", None):
        raise ZohoBooksError("Customer not synced: customer.zoho_contact_id is empty.")

    line_items = []
    bad_local_items = []

    for line in invoice.lines.select_related("item").all():
        item: LocalItem = line.item
        if not item.zoho_item_id:
            bad_local_items.append(item.id)
            continue

        tax_pct = float(_gst_percent_from_choice(line.gst_treatment))

        # Main item line
        line_items.append({
            "item_id": str(item.zoho_item_id),
            "quantity": float(line.qty),
            "rate": float(line.rate),
            "tax_percentage": tax_pct,
        })

        # Service charge handling:
        # Zoho doesn't support "service_charge per line" directly.
        # Option A (recommended): create a dedicated Zoho Item "Service Charge"
        # and set its item_id in settings.ZOHO_SERVICE_CHARGE_ITEM_ID.
        # Option B: ignore here and use invoice-level "adjustment" (less accurate).
        if getattr(line, "service_charge_amount", 0) and Decimal(line.service_charge_amount) > 0:
            sc_item_id = getattr(settings, "ZOHO_SERVICE_CHARGE_ITEM_ID", "") or ""
            if sc_item_id:
                line_items.append({
                    "item_id": str(sc_item_id),
                    "quantity": 1,
                    "rate": float(line.service_charge_amount),
                    "tax_percentage": tax_pct,
                })

    if bad_local_items:
        raise ZohoBooksError(f"These items are not synced properly to Zoho (bad zoho_item_id): {bad_local_items}")

    payload = {
        "customer_id": str(invoice.customer.zoho_contact_id),
        "date": str(invoice.invoice_date),
        "due_date": str(invoice.due_date) if invoice.due_date else None,
        "line_items": line_items,
        # discount can be % OR amount :contentReference[oaicite:3]{index=3}
        "discount_type": "entity_level",
        # We keep discount AFTER TAX to match the simple local calculation
        "is_discount_before_tax": False,  # :contentReference[oaicite:4]{index=4}
    }

    # discount value
    if invoice.discount_type == "PERCENT":
        payload["discount"] = float(invoice.discount_value or 0)
    else:
        payload["discount"] = float(invoice.discount_value or 0)

    # Optional: if you want invoice_number in Zoho
    # Zoho needs ignore_auto_number_generation=true if you send custom invoice_number :contentReference[oaicite:5]{index=5}
    # payload["invoice_number"] = invoice.invoice_number

    # Optional: add service charge total as adjustment if you are NOT using a service charge item.
    sc_item_id = getattr(settings, "ZOHO_SERVICE_CHARGE_ITEM_ID", "") or ""
    if not sc_item_id and (invoice.service_charge_total or 0) > 0:
        # adjustment exists in invoice object attributes :contentReference[oaicite:6]{index=6}
        payload["adjustment"] = float(invoice.service_charge_total)
        payload["adjustment_description"] = "Service Charge"

    # remove None due_date (Zoho sometimes dislikes nulls)
    payload = {k: v for k, v in payload.items() if v is not None}
    return payload


def create_zoho_invoice(payload: dict) -> dict:
    access_token = get_zoho_access_token()
    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID

    url = f"{base_url}/invoices?organization_id={org_id}"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers, timeout=60)
    return _zoho_raise_if_error(resp, "Create Zoho invoice")


def update_zoho_invoice(zoho_invoice_id: str, payload: dict) -> dict:
    access_token = get_zoho_access_token()
    base_url = settings.ZOHO_BOOKS_BASE_URL.rstrip("/")
    org_id = settings.ZOHO_BOOKS_ORGANIZATION_ID

    url = f"{base_url}/invoices/{zoho_invoice_id}?organization_id={org_id}"
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}",
        "Content-Type": "application/json",
    }

    resp = requests.put(url, json=payload, headers=headers, timeout=60)
    return _zoho_raise_if_error(resp, "Update Zoho invoice")

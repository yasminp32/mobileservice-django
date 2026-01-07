from zoho_integration.models import LocalCustomer
from zoho_integration.zoho_books import (
    build_zoho_contact_payload,
    create_zoho_contact,
    update_zoho_contact,
    search_zoho_contact,
    ZohoBooksError,
)

def _pick_contact_id_from_search(res: dict, email: str = "", phone: str = "") -> str:
    contacts = res.get("contacts") or []
    if not contacts:
        return ""

    email = (email or "").lower().strip()
    phone = (phone or "").strip()

    for c in contacts:
        if email and (c.get("email") or "").lower().strip() == email:
            return c.get("contact_id") or ""

        if phone and (
            (c.get("mobile") or "").strip() == phone
            or (c.get("phone") or "").strip() == phone
        ):
            return c.get("contact_id") or ""

    #  do NOT fallback to first contact
    return ""


def sync_core_customer_to_zoho_contact(core_customer) -> LocalCustomer:
    # 1) Upsert LocalCustomer (match by email first, else phone)
    lc = None
    email = getattr(core_customer, "email", None) or ""
    phone = getattr(core_customer, "customer_phone", None) or ""
    name  = getattr(core_customer, "customer_name", "") or ""
    state = getattr(core_customer, "state", "") or ""
    if email:
        lc = LocalCustomer.objects.filter(email=email).first()
    if not lc and phone:
        lc = LocalCustomer.objects.filter(phone=phone).first()

    if not lc:
        lc = LocalCustomer.objects.create(
            name=name,
            email=email or None,
            phone=phone or "",
            state=state or "",
            zoho_contact_id="",
            sync_status="PENDING",
            last_error="",
        )
    else:
        lc.name = name or lc.name
        lc.email = (email or lc.email)
        lc.phone = (phone or lc.phone)
        lc.state = (state or lc.state)
        lc.sync_status = "PENDING"
        lc.last_error = ""
        lc.save()

    payload = build_zoho_contact_payload(lc)

    try:
        # 2) If no zoho_contact_id, try to find existing in Zoho and link it
        if not lc.zoho_contact_id:
            search_res = search_zoho_contact(email=lc.email or "", phone=lc.phone or "")
            found_id = _pick_contact_id_from_search(search_res, email=lc.email or "", phone=lc.phone or "")
            if found_id:
                lc.zoho_contact_id = found_id
                lc.save(update_fields=["zoho_contact_id", "updated_at"])

        # 3) Update if linked, else create
        if lc.zoho_contact_id:
            res = update_zoho_contact(lc.zoho_contact_id, payload)
            # res may or may not include "contact" – keep current id safely
            contact = (res or {}).get("contact") or {}
            lc.zoho_contact_id = contact.get("contact_id", lc.zoho_contact_id)

        else:
            res = create_zoho_contact(payload)
            contact = (res or {}).get("contact") or {}
            contact_id = contact.get("contact_id", "")
            if not contact_id:
                raise ZohoBooksError(f"Zoho did not return contact_id: {res}")
            lc.zoho_contact_id = contact_id

        lc.sync_status = "SYNCED"
        lc.last_error = ""
        lc.save(update_fields=["zoho_contact_id", "sync_status", "last_error", "updated_at"])
        return lc

    except Exception as e:
        lc.sync_status = "FAILED"
        lc.last_error = str(e)
        lc.save(update_fields=["sync_status", "last_error", "updated_at"])
        # re-raise so your view can still print/log if you want
        raise

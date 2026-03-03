# core/audit.py
from typing import Optional
from core.models import Shop, Growtags, Customer, Complaint

def admin_label(user) -> str:
    name = (getattr(user, "get_full_name", lambda: "")() or getattr(user, "username", "") or str(user)).strip()
    return f"Admin - {name}" if name else "Admin"
#role based logic
def created_by_display(obj):
    if obj.created_by_id:
        u = obj.created_by
        return {"type": "admin", "id": u.id, "name": getattr(u, "username", str(u))}

    if obj.created_by_shop_id:
        s = obj.created_by_shop
        return {"type": "shop", "id": s.id, "name": s.shopname, "shop_type": s.shop_type}

    if obj.created_by_growtag_id:
        g = obj.created_by_growtag
        return {"type": "growtag", "id": g.id, "name": g.name}

    if obj.created_by_customer_id:
        c = obj.created_by_customer
        return {"type": "customer", "id": c.id, "name": c.customer_name}

    return None
#def created_by_display(obj) -> Optional[str]:
    """
    DISPLAY helper (works even if created_by is NULL):
    - If created_by is staff/superuser -> Admin - username
    - Else fallback by object type (Shop/Growtag/Customer)
    """

    user = getattr(obj, "created_by", None)
    if user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        return admin_label(user)

    # fallback display (NOT creator tracking; just display)
    if isinstance(obj, Shop):
        return f"Shop ({obj.shop_type}) - {obj.shopname}"

    if isinstance(obj, Growtags):
        return f"Growtag - {obj.name}"

    if isinstance(obj, Customer):
        return f"Customer - {obj.customer_name}"

    return None


#def complaint_created_by_display(obj: Complaint) -> Optional[str]:
    """
    Complaint display:
    1) Admin created -> Admin - username
    2) Customer linked -> Customer - name
    3) Fallback: show assigned entity (useful)
    """
    user = getattr(obj, "created_by", None)
    if user and (getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)):
        return admin_label(user)

    if getattr(obj, "customer_id", None) and getattr(obj, "customer", None):
        return f"Customer - {obj.customer.customer_name}"

    if getattr(obj, "assigned_shop_id", None) and getattr(obj, "assigned_shop", None):
        return f"Shop ({obj.assigned_shop.shop_type}) - {obj.assigned_shop.shopname}"

    if getattr(obj, "assigned_Growtags_id", None) and getattr(obj, "assigned_Growtags", None):
        return f"Growtag - {obj.assigned_Growtags.name}"

    return None 
def get_actor(request):
    u = getattr(request, "user", None)
    if u and getattr(u, "is_authenticated", False) and getattr(u, "is_staff", False):
        return ("admin", u)

    if getattr(request, "shop", None):
        return ("shop", request.shop)

    if getattr(request, "growtag", None):
        return ("growtag", request.growtag)

    if getattr(request, "customer", None):
        return ("customer", request.customer)

    return (None, None)

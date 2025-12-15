from typing import Optional, Tuple
import requests
from math import radians, sin, cos, asin, sqrt

from .models import Shop, Complaint, Growtags

# -------------------------------------------------------------------
#  CONSTANTS
# -------------------------------------------------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"


# -------------------------------------------------------------------
#  DISTANCE HELPERS
# -------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2) -> float:
    """
    Pure Python Haversine distance (in km).
    """
    lat1, lon1, lat2, lon2 = map(float, [lat1, lon1, lat2, lon2])

    # convert degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    # ✅ correct formula (you had *2 instead of **2 earlier)
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    a = max(0.0, min(1.0, a))  # safety
    c = 2 * asin(sqrt(a))
    r = 6371  # km
    return c * r


def km_between(lat1, lon1, lat2, lon2) -> float:
    return haversine(lat1, lon1, lat2, lon2)


# -------------------------------------------------------------------
#  GEOCODING HELPERS (only when we DON'T have lat/lon)
# -------------------------------------------------------------------
def geocode_address_pincode(area: str, pincode: str) -> Optional[Tuple[float, float]]:
    query_list = []
    # 2️⃣ Pincode only (good centroid of 673638)
    if pincode:
        query_list.append(f"{pincode}, Kerala, India")

    # 1️⃣ Most specific: area + pincode + Kerala
    if area and pincode:
        query_list.append(f"{area}, {pincode}, Kerala, India")
        query_list.append(f"{area}, {pincode}, India")

   

    # 3️⃣ Very loose: area only → keep as LAST fallback
    if area:
        query_list.append(f"{area}, Kerala, India")

    print("GEO TRY:", query_list)

    for query in query_list:
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers={"User-Agent": "mobileservice_django/1.0"},
                timeout=10,
            )
            data = resp.json()
            if data:
                lat = float(data[0]["lat"])
                lon = float(data[0]["lon"])
                print("FOUND:", query, lat, lon)
                return lat, lon
        except Exception:
            continue

    print("NO MATCH FOR ANY QUERY")
    return None



def geocode_pincode(pincode: str) -> Optional[Tuple[float, float]]:
    """
    Fallback: geocode from pincode only.
    """
    return geocode_address_pincode("", pincode)


# -------------------------------------------------------------------
#  LOW-LEVEL NEAREST FUNCTIONS (use a POINT lat/lon)
# -------------------------------------------------------------------
def find_nearest_shop(
    lat: float,
    lon: float,
    shop_type: Optional[str] = None,
) -> Optional[Tuple[Shop, float]]:
    """
    Find nearest active Shop from (lat, lon).
    Optionally filter by shop_type: "franchise" or "othershop".
    """
    best: Optional[Shop] = None
    best_km: float = float("inf")

    qs = Shop.objects.filter(status=True)
    if shop_type:
        qs = qs.filter(shop_type=shop_type.lower())

    for shop in qs:
        if shop.latitude is None or shop.longitude is None:
            origin = geocode_address_pincode(shop.area or "", shop.pincode) or geocode_pincode(shop.pincode)
            if origin:
                shop.latitude, shop.longitude = origin
                shop.save(update_fields=["latitude", "longitude"])
            else:
                continue

        d = km_between(lat, lon, shop.latitude, shop.longitude)
        if d < best_km:
            best_km = d
            best = shop

    if best is None:
        return None
    return best, best_km


def find_nearest_growtag(lat: float, lon: float) -> Optional[Tuple[Growtags, float]]:
    """
    Find nearest active GrowTag from (lat, lon).
    """
    best: Optional[Growtags] = None
    best_km: float = float("inf")

    for gt in Growtags.objects.filter(status="Active"):
        if gt.latitude is None or gt.longitude is None:
            origin = geocode_address_pincode(gt.area or "", gt.pincode) or geocode_pincode(gt.pincode)
            if origin:
                gt.latitude, gt.longitude = origin
                gt.save(update_fields=["latitude", "longitude"])
            else:
                continue

        d = km_between(lat, lon, gt.latitude, gt.longitude)
        if d < best_km:
            best_km = d
            best = gt

    if best is None:
        return None
    return best, best_km


# -------------------------------------------------------------------
#  HIGH-LEVEL: USE COMPLAINT (lat/lon from frontend + pincode fallback)
# -------------------------------------------------------------------
def _ensure_complaint_coords(complaint: Complaint):
    """
    Make sure complaint has latitude & longitude.

    1) If frontend already sent lat/lon → do nothing.
    2) Else, geocode from area + pincode / pincode.
    """
    if complaint.latitude is not None and complaint.longitude is not None:
        return

    origin = geocode_address_pincode(complaint.area or "", complaint.pincode) or geocode_pincode(complaint.pincode)
    if origin:
        complaint.latitude, complaint.longitude = origin
        complaint.save(update_fields=["latitude", "longitude"])


def get_nearest_growtag(complaint: Complaint):
    """
    Use complaint.latitude / complaint.longitude to find nearest GrowTag.
    """
    # ❗ FIX: reverse of what you had
    # before you used: if complaint.latitude or complaint.longitude: return None
    

    if complaint.latitude is None or complaint.longitude is None:
        return None

    return find_nearest_growtag(float(complaint.latitude), float(complaint.longitude))


def get_nearest_shop(complaint: Complaint, shop_type: str):
    """
    Use complaint.latitude / complaint.longitude to find nearest Shop.
    """
    

    if complaint.latitude is None or complaint.longitude is None:
        return None

    return find_nearest_shop(
        float(complaint.latitude),
        float(complaint.longitude),
        shop_type=shop_type,
    )





# -------------------------------------------------------------------
#  NEAREST LISTS FOR /nearest-options/ (2nd dropdown)
# -------------------------------------------------------------------
def nearest_lists_for_address(area: str, pincode: str):
    """
    Used by your view:

      GET /api/complaints/nearest-options/?area=...&pincode=...

    It geocodes area+pincode → user_lat/user_lon,
    then builds 3 sorted lists: franchise, othershop, growtag.
    """
    origin = geocode_address_pincode(area, pincode) or geocode_pincode(pincode)
    print("USER ORIGIN:", area, pincode, origin)
    if not origin:
        return {
            "franchise": [],
            "othershop": [],
            "growtag": [],
        }

    user_lat, user_lon = origin

    franchise_list = []
    othershop_list = []
    growtag_list = []

    # ---- Shops ----
    for shop in Shop.objects.filter(status=True):
        print("SHOP COORDS BEFORE:", shop.id, shop.shopname, shop.latitude, shop.longitude)
        if shop.latitude is None or shop.longitude is None:
            loc = geocode_address_pincode(shop.area or "", shop.pincode) or geocode_pincode(shop.pincode)
            if loc:
                shop.latitude, shop.longitude = loc
                shop.save(update_fields=["latitude", "longitude"])
            else:
                continue

        dist_km = round(haversine(user_lat, user_lon, shop.latitude, shop.longitude), 2)
        print("DIST TO SHOP:", shop.id, shop.shopname, dist_km)
        data = {
            "id": shop.id,
            "label": f"{shop.shopname} ({dist_km} km)",
            "distance_km": dist_km,
        }

        if getattr(shop, "shop_type", "") == "franchise":
            franchise_list.append(data)
        else:
            othershop_list.append(data)

    franchise_list.sort(key=lambda x: x["distance_km"])
    othershop_list.sort(key=lambda x: x["distance_km"])

    # ---- Growtags ----
    for g in Growtags.objects.filter(status="Active"):
        if g.latitude is None or g.longitude is None:
            loc = geocode_address_pincode(g.area or "", g.pincode) or geocode_pincode(g.pincode)
            if loc:
                g.latitude, g.longitude = loc
                g.save(update_fields=["latitude", "longitude"])
            else:
                continue

        dist_km = round(haversine(user_lat, user_lon, g.latitude, g.longitude), 2)

        growtag_list.append({
            "id": g.id,
            "label": f"{g.name} - {g.grow_id} ({dist_km} km)",
            "distance_km": dist_km,
        })

    growtag_list.sort(key=lambda x: x["distance_km"])

    return {
        "franchise": franchise_list,
        "othershop": othershop_list,
        "growtag": growtag_list,
    }
from django.db.models import Q

def sync_complaint_to_customer(complaint: Complaint):
    customer = complaint.customer
    if not customer:
        return

    fields_to_update = []

    sync_map = {
        "customer_name": complaint.customer_name,
        "customer_phone": complaint.customer_phone,
        "email": complaint.email,
        "password": complaint.password,
        #"phone_model": complaint.phone_model,
        #"issue_details": complaint.issue_details,
        "address": complaint.address,
        "pincode": complaint.pincode,
        #"assign_to": complaint.assign_to,
        #"assign_type": complaint.assign_to,
        #"status": complaint.status,
    }

    for field, value in sync_map.items():
        if value is not None and getattr(customer, field) != value:
            setattr(customer, field, value)
            fields_to_update.append(field)

    if fields_to_update:
        customer.save(update_fields=fields_to_update)
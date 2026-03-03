from __future__ import annotations

from typing import Optional, Tuple, Dict, Any, Union
import requests
from math import radians, sin, cos, asin, sqrt

from .models import Shop, Complaint, Growtags

# -------------------------------------------------------------------
#  CONSTANTS + CACHE
# -------------------------------------------------------------------
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "mobileservice_django/1.0"

# key -> (lat, lon, precision)
_GEOCODE_CACHE: Dict[str, Tuple[float, float, str]] = {}


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

    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    a = max(0.0, min(1.0, a))  # safety
    c = 2 * asin(sqrt(a))
    r = 6371  # km
    return c * r


def km_between(lat1, lon1, lat2, lon2) -> float:
    return haversine(lat1, lon1, lat2, lon2)


# -------------------------------------------------------------------
#  GEOCODING HELPERS
# -------------------------------------------------------------------
GeocodeResult = Tuple[float, float, str]  # (lat, lon, precision)


def _cache_key(prefix: str, area: str, pincode: str, region: str) -> str:
    area = (area or "").strip().lower()
    pincode = (str(pincode).strip().lower()) if pincode else ""
    region = (region or "").strip().lower()
    return f"{prefix}|{area}|{pincode}|{region}"



def geocode_address_pincode(area: str, pincode: str) -> Optional[GeocodeResult]:
    """
    Returns (lat, lon, precision)
      precision in {"area_pincode", "pincode", "area_only"}
    """
    pincode = str(pincode).strip() if pincode else ""
    area = (area or "").strip()

    tagged = []
    if area and pincode:
        tagged.append(("area_pincode", f"{area}, {pincode}, Kerala, India"))
        tagged.append(("area_pincode", f"{area}, {pincode}, India"))
       
    if pincode:
        tagged.append(("pincode", f"{pincode}, Kerala, India"))
    if area:
        tagged.append(("area_only", f"{area}, Kerala, India"))
    for precision, query in tagged:
       cache_key = query.lower().strip()
       if cache_key in _GEOCODE_CACHE:
          return _GEOCODE_CACHE[cache_key]
    
    print("GEO TRY:", [q for _, q in tagged])

    for precision, query in tagged:
        try:
            resp = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 3, "addressdetails": 1},
                headers={"User-Agent": USER_AGENT},
                timeout=10,
                 )
            data = resp.json()
            if not data:
                continue

            picked = None
            if pincode:
                for item in data:
                    addr = item.get("address") or {}
                    if (addr.get("postcode") or "").strip() == pincode:
                        picked = item
                        break

            picked = picked or data[0]
            lat = float(picked["lat"])
            lon = float(picked["lon"])
            print("FOUND:", query, lat, lon, "precision=", precision)

            _GEOCODE_CACHE[cache_key] = (lat, lon, precision)
            return lat, lon, precision
        except Exception:
            continue

    print("NO MATCH FOR ANY QUERY")
    return None


def geocode_pincode(pincode: str) -> Optional[GeocodeResult]:
    """
    Fallback: geocode from pincode only.
    """
    return geocode_address_pincode("", pincode)


# -------------------------------------------------------------------
#  COORD RESOLUTION (single source of truth)
# -------------------------------------------------------------------
def _should_save_precision(precision: Optional[str]) -> bool:
    """
    Save everything except pure pincode centroid.
    - "area_pincode" is GOOD and should be saved.
    - "area_only" is weak but still better than nothing (your call).
    - "pincode" is centroid-like -> do NOT save.
    """
    return precision is not None and precision != "pincode"


def get_or_geocode_shop_coords(shop: Shop) -> Optional[Tuple[float, float]]:
    """
    Returns usable (lat, lon). If geocoded, saves only when precision != "pincode".
    """
    if shop.latitude is not None and shop.longitude is not None:
        return float(shop.latitude), float(shop.longitude)

    loc = geocode_address_pincode(getattr(shop, "area", "") or "", getattr(shop, "pincode", "") or "")
    if not loc:
        loc = geocode_pincode(getattr(shop, "pincode", "") or "")
    if not loc:
        return None

    lat2, lon2, precision = loc
    if _should_save_precision(precision):
        shop.latitude, shop.longitude = lat2, lon2
        shop.save(update_fields=["latitude", "longitude"])

    return float(lat2), float(lon2)


def get_or_geocode_growtag_coords(gt: Growtags) -> Optional[Tuple[float, float]]:
    """
    Returns usable (lat, lon). If geocoded, saves only when precision != "pincode".
    """
    if gt.latitude is not None and gt.longitude is not None:
        return float(gt.latitude), float(gt.longitude)

    loc = geocode_address_pincode(getattr(gt, "area", "") or "", getattr(gt, "pincode", "") or "")
    if not loc:
        loc = geocode_pincode(getattr(gt, "pincode", "") or "")
    if not loc:
        return None

    lat2, lon2, precision = loc
    if _should_save_precision(precision):
        gt.latitude, gt.longitude = lat2, lon2
        gt.save(update_fields=["latitude", "longitude"])

    return float(lat2), float(lon2)


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
        coords = get_or_geocode_shop_coords(shop)
        if not coords:
            continue

        use_lat, use_lon = coords
        d = km_between(lat, lon, use_lat, use_lon)
        if d < best_km:
            best_km = d
            best = shop

    return None if best is None else (best, best_km)


def find_nearest_growtag(lat: float, lon: float) -> Optional[Tuple[Growtags, float]]:
    best: Optional[Growtags] = None
    best_km: float = float("inf")

    for gt in Growtags.objects.filter(status="Active"):
        coords = get_or_geocode_growtag_coords(gt)
        if not coords:
            continue

        use_lat, use_lon = coords
        d = km_between(lat, lon, use_lat, use_lon)
        if d < best_km:
            best_km = d
            best = gt

    return None if best is None else (best, best_km)


# -------------------------------------------------------------------
#  HIGH-LEVEL: USE COMPLAINT (lat/lon from frontend + pincode fallback)
# -------------------------------------------------------------------
def _ensure_complaint_coords(complaint: Complaint) -> None:
    if complaint.latitude is not None and complaint.longitude is not None:
        return

    loc = geocode_address_pincode(getattr(complaint, "area", "") or "", getattr(complaint, "pincode", "") or "")
    if not loc:
        loc = geocode_pincode(getattr(complaint, "pincode", "") or "")
    if not loc:
        return

    complaint.latitude, complaint.longitude = loc[0], loc[1]
    complaint.save(update_fields=["latitude", "longitude"])


def get_nearest_growtag(complaint: Complaint):
    _ensure_complaint_coords(complaint)
    if complaint.latitude is None or complaint.longitude is None:
        return None
    return find_nearest_growtag(float(complaint.latitude), float(complaint.longitude))


def get_nearest_shop(complaint: Complaint, shop_type: str):
    _ensure_complaint_coords(complaint)
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
def nearest_lists_for_address(area: str, pincode: str, lat=None, lon=None) -> Dict[str, list]:
    """
    Used by view:

      GET /api/complaints/nearest-options/?area=...&pincode=...&lat=...&lon=...

    Prefers frontend coords. Otherwise geocodes area+pincode/pincode.
    Builds 3 sorted lists: franchise, othershop, growtag.
    """
    # ---- USER ORIGIN ----
    def _has_coords(lat, lon) -> bool:
         return lat is not None and lon is not None and str(lat).strip() != "" and str(lon).strip() != ""
    if _has_coords(lat, lon):
        user_lat, user_lon = float(lat), float(lon)
        origin_precision = "frontend"
    else:
        res = geocode_address_pincode(area, pincode)
        if not res:
            res = geocode_pincode(pincode)
        if not res:
            return {"franchise": [], "othershop": [], "growtag": []}

        user_lat, user_lon, origin_precision = res

    print("USER ORIGIN:", area, pincode, (user_lat, user_lon), "precision=", origin_precision)

    franchise_list: list = []
    othershop_list: list = []
    growtag_list: list = []

    # ---- SHOPS ----
    for shop in Shop.objects.filter(status=True):
        coords = get_or_geocode_shop_coords(shop)
        if not coords:
            continue

        use_lat, use_lon = coords
        dist_km = round(haversine(user_lat, user_lon, use_lat, use_lon), 2)

        data = {
            "id": shop.id,
            "label": f"{shop.shopname} ({dist_km} km)",
            "distance_km": dist_km,
        }

        st = (getattr(shop, "shop_type", "") or "").lower()
        if st == "franchise":
            franchise_list.append(data)
        elif st == "othershop":
            othershop_list.append(data)

    franchise_list.sort(key=lambda x: x["distance_km"])
    othershop_list.sort(key=lambda x: x["distance_km"])

    # ---- GROWTAGS ----
    for gt in Growtags.objects.filter(status="Active"):
        coords = get_or_geocode_growtag_coords(gt)
        if not coords:
            continue

        use_lat, use_lon = coords
        dist_km = round(haversine(user_lat, user_lon, use_lat, use_lon), 2)

        growtag_list.append(
            {
                "id": gt.id,
                "label": f"{gt.name} - {gt.grow_id} ({dist_km} km)",
                "distance_km": dist_km,
            }
        )

    growtag_list.sort(key=lambda x: x["distance_km"])

    return {
        "franchise": franchise_list,
        "othershop": othershop_list,
        "growtag": growtag_list,
    }


# -------------------------------------------------------------------
#  COMPLAINT -> CUSTOMER SYNC (unchanged)
# -------------------------------------------------------------------
from django.db.models import Q  # keep your existing import location if you want


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
        "address": complaint.address,
        "pincode": complaint.pincode,
    }

    for field, value in sync_map.items():
        if value is not None and getattr(customer, field) != value:
            setattr(customer, field, value)
            fields_to_update.append(field)

    if fields_to_update:
        customer.save(update_fields=fields_to_update)

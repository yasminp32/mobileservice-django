from core.models import Shop, Growtags,Customer, ShopAuthToken, GrowtagAuthToken,CustomerAuthToken
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import check_password,make_password
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from core.authentication import (
    ShopTokenAuthentication,
    GrowtagTokenAuthentication,
    CustomerTokenAuthentication,
)
from core.permissions import IsShop, IsGrowtag, IsCustomer
from rest_framework_simplejwt.tokens import RefreshToken
from core.models import ShopAuthToken, GrowtagAuthToken, CustomerAuthToken
from rest_framework.permissions import AllowAny


def hash_password(raw_password: str) -> str:
    raw_password = (raw_password or "").strip()
    return make_password(raw_password) if raw_password else ""

def verify_password(raw_password: str, hashed_password: str) -> bool:
    return bool(raw_password and hashed_password and check_password(raw_password, hashed_password))
def get_shop_permissions(shop):
    # Franchise + OtherShop same permissions (as you want)
    return [
        "VIEW_SHOP_PROFILE",
        "EDIT_SHOP_PROFILE",
        "VIEW_COMPLAINT",
        "EDIT_COMPLAINT",
        "CREATE_INVOICE",
        "EDIT_INVOICE",
        "VIEW_CUSTOMER",
        "VIEW_VENDOR",
        "CREATE_VENDOR",
        "EDIT_VENDOR",
        "CREATE_PURCHASE_ORDER",
        "EDIT_PURCHASE_ORDER",
        "CREATE_PURCHASE_BILL",
        "EDIT_PURCHASE_BILL",
        "VIEW_STOCK",
        "VIEW_REPORT",
        "VIEW_GROWTAG",
    ]

def get_growtag_permissions(growtag):
    return [
        "VIEW_GROWTAG_PROFILE",
        "EDIT_GROWTAG_PROFILE",
        "VIEW_ASSIGNED_COMPLAINT",
        "UPDATE_COMPLAINT_STATUS",
        "VIEW_CUSTOMER",
        "VIEW_INVOICE",
        "EDIT_INVOICE",
        "CREATE_PURCHASE_BILL",
        "EDIT_PURCHASE_BILL",
        "VIEW_STOCK",
        "VIEW_REPORT",
    ]

def get_customer_permissions(customer):
    return [
        "VIEW_CUSTOMER_PROFILE",
        "EDIT_CUSTOMER_PROFILE",
        "CREATE_COMPLAINT",
        "VIEW_OWN_COMPLAINT",
        "VIEW_REPORT",
    ]

def get_admin_permissions():
    return ["ALL_PERMISSIONS"]

def ok_login(role, access_token, refresh_token, user_payload, permissions):
    return {
        "success": True,
        "message": "Login successful",
        "access_token": access_token,
        "refresh_token": refresh_token,  # None for token roles
        "user": {
            **user_payload,
            "role": role.upper(),
            "permissions": permissions,
        }
    }

def bad_login(message="Invalid credentials"):
    return {"success": False, "message": message}


class UnifiedLoginAPIView(APIView):
    """
    POST /api/auth/login/
    body: { "login": "<email or phone or username>", "password": "..." }

    Returns:
      - Admin -> JWT tokens
      - Shop/Growtag/Customer -> Token <key>
    """
    authentication_classes = []
    permission_classes = [AllowAny]
    def post(self, request):
        login_value = (request.data.get("login") or "").strip()
        login_email = login_value.lower()
        password = request.data.get("password") or ""

        if not login_value or not password:
            return Response({"detail": "login and password are required"}, status=400)

        # -------- 1) ADMIN (Django User) -> JWT --------
        user = authenticate(request, username=login_value, password=password)
        if user and user.is_staff:
            refresh = RefreshToken.for_user(user)
            data = ok_login(
                role="admin",
                access_token=str(refresh.access_token),
                refresh_token=str(refresh),
                user_payload={
                    "id": user.id,
                    "username": user.get_username(),
                    "email": getattr(user, "email", ""),
                    "name": (user.get_full_name() or user.get_username()),
                    "is_active": user.is_active,
                },
                permissions=get_admin_permissions(),
            )
            return Response(data, status=200)

        # -------- 2) SHOP --------
        shop = Shop.objects.filter(email=login_email).first() or Shop.objects.filter(phone=login_value).first()
        if shop and shop.password and verify_password(password, shop.password):
            token, _ = ShopAuthToken.objects.get_or_create(shop=shop)
            role = "franchise" if shop.shop_type == "franchise" else "othershop"
            data = ok_login(
                role=role,
                access_token=token.key,
                refresh_token=None,
                user_payload={
                    "id": shop.id,
                    "email": getattr(shop, "email", ""),
                    "name": getattr(shop, "shopname", ""),
                    "shop_type": getattr(shop, "shop_type", ""),
                    "is_active": True,
                },
                permissions=get_shop_permissions(shop),
            )
            return Response(data, status=200)
        # -------- 3) GROWTAG --------
        growtag = Growtags.objects.filter(email=login_email).first() or Growtags.objects.filter(phone=login_value).first()
        if growtag and growtag.password and verify_password(password, growtag.password):
            if getattr(growtag, "status", "") != "Active":
                return Response({"detail": "Growtag is inactive"}, status=403)

            token, _ = GrowtagAuthToken.objects.get_or_create(growtag=growtag)
            data = ok_login(
                role="growtag",
                access_token=token.key,
                refresh_token=None,
                user_payload={
                    "id": growtag.id,
                    "email": getattr(growtag, "email", ""),
                    "name": getattr(growtag, "name", ""),
                    "is_active": True,
                },
                permissions=get_growtag_permissions(growtag),
            )
            return Response(data, status=200)

        # -------- 4) CUSTOMER --------
        customer = (Customer.objects.filter(email=login_email).first()
                    or Customer.objects.filter(customer_phone=login_value).first())
        if customer and customer.password and verify_password(password, customer.password):
            token, _ = CustomerAuthToken.objects.get_or_create(customer=customer)
            data = ok_login(
                role="customer",
                access_token=token.key,
                refresh_token=None,
                user_payload={
                    "id": customer.id,
                    "email": getattr(customer, "email", ""),
                    "name": getattr(customer, "customer_name", ""),
                    "customer_phone": getattr(customer, "customer_phone", ""),
                    "is_active": True,
                },
                permissions=get_customer_permissions(customer),
            )
            return Response(data, status=200)

        return Response(bad_login("Invalid credentials"), status=400)



    
    #logout
class ShopLogoutAPIView(APIView):
    authentication_classes = [ShopTokenAuthentication]
    permission_classes = [IsShop]

    def post(self, request):
        # request.auth is the token object used in Authorization header
        if request.auth:
            request.auth.delete()
        return Response({"detail": "Shop logged out successfully"}, status=200)


class GrowtagLogoutAPIView(APIView):
    authentication_classes = [GrowtagTokenAuthentication]
    permission_classes = [IsGrowtag]

    def post(self, request):
        if request.auth:
            request.auth.delete()
        return Response({"detail": "Growtag logged out successfully"}, status=200)


class CustomerLogoutAPIView(APIView):
    authentication_classes = [CustomerTokenAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        if request.auth:
            request.auth.delete()
        return Response({"detail": "Customer logged out successfully"}, status=200)

    

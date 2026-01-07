from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.contrib.auth.hashers import check_password, make_password

from core.models import Shop, Growtags,Customer, ShopAuthToken, GrowtagAuthToken,CustomerAuthToken
from core.authentication import ShopTokenAuthentication,GrowtagTokenAuthentication,CustomerTokenAuthentication
from core.permissions import IsShop,IsGrowtag,IsCustomer

class ShopRegisterAPIView(APIView):
    """
    Optional - only if you want to create shop via API.
    Ensures password saved hashed.
    """
    def post(self, request):
        data = request.data
        password = data.get("password") or ""
        if not password:
            return Response({"detail": "password is required"}, status=400)

        shop = Shop.objects.create(
            shop_type=data.get("shop_type", "franchise"),
            shopname=data.get("shopname", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            pincode=data.get("pincode", ""),
            gst_pin=data.get("gst_pin", ""),
            password=make_password(password),
            address=data.get("address", ""),
            area=data.get("area"),
            owner=data.get("owner"),
        )
        return Response({"shop_id": shop.id}, status=201)


class ShopLoginAPIView(APIView):
    def post(self, request):
        print("DEBUG request.data =", request.data)
        login_value = (request.data.get("login") or "").strip()  # email or phone
        password = request.data.get("password") or ""

        if not login_value or not password:
            return Response({"detail": "login and password are required"}, status=400)

        # login by email OR phone
        shop = Shop.objects.filter(email=login_value).first() or Shop.objects.filter(phone=login_value).first()
        if not shop:
            return Response({"detail": "Invalid credentials"}, status=400)

        # if you already have old plain passwords stored, this will fail.
        if not shop.password or not check_password(password, shop.password):
            return Response({"detail": "Invalid credentials"}, status=400)

        # ✅ create token (or reuse existing token if you want)
        token = ShopAuthToken.objects.create(shop=shop)

        return Response({
            "token": token.key,
            "role": "shop",
            "shop_type": shop.shop_type,  # franchise / othershop
            "shop_id": shop.id,
            "shopname": shop.shopname,
        }, status=200)


class GrowtagLoginAPIView(APIView):
    def post(self, request):
        login_value = (request.data.get("login") or "").strip()  # email or phone
        password = request.data.get("password") or ""

        if not login_value or not password:
            return Response({"detail": "login and password are required"}, status=400)

        growtag = Growtags.objects.filter(email=login_value).first() or Growtags.objects.filter(phone=login_value).first()
        if not growtag:
            return Response({"detail": "Invalid credentials"}, status=400)

        if growtag.status != "Active":
            return Response({"detail": "Growtag is inactive"}, status=403)

        if not growtag.password or not check_password(password, growtag.password):
            return Response({"detail": "Invalid credentials"}, status=400)

        token = GrowtagAuthToken.objects.create(growtag=growtag)

        return Response({
            "token": token.key,
            "role": "growtag",
            "growtag_id": growtag.id,
            "name": growtag.name,
        }, status=200)
class CustomerLoginAPIView(APIView):
    def post(self, request):
        login_value = (request.data.get("login") or "").strip()   # phone or email
        password = request.data.get("password") or ""

        if not login_value or not password:
            return Response({"detail": "login and password are required"}, status=400)

        # ✅ correct fields: customer_phone / email
        customer = (
            Customer.objects.filter(email=login_value).first()
            or Customer.objects.filter(customer_phone=login_value).first()
        )

        if not customer:
            return Response({"detail": "Invalid credentials"}, status=400)

        if not customer.password or not check_password(password, customer.password):
            return Response({"detail": "Invalid credentials"}, status=400)

        # ✅ reuse one token per customer (recommended)
        token, _ = CustomerAuthToken.objects.get_or_create(customer=customer)

        return Response({
            "token": token.key,
            "role": "customer",
            "customer_id": customer.id,
            "customer_name": customer.customer_name,
            "customer_phone": customer.customer_phone,
            "email": customer.email,
        }, status=200)
    
    #logout
class ShopLogoutAPIView(APIView):
    authentication_classes = [ShopTokenAuthentication]
    permission_classes = [IsShop]

    def post(self, request):
        # 🔐 current token used in request
        token = request.auth

        if token:
            token.delete()

        return Response({"detail": "Logged out successfully"})
class GrowtagLogoutAPIView(APIView):
    authentication_classes = [GrowtagTokenAuthentication]
    permission_classes = [IsGrowtag]

    def post(self, request):
        GrowtagAuthToken.objects.filter(growtag=request.growtag).delete()
        return Response({"detail": "Logged out"}, status=200)
class CustomerLogoutAPIView(APIView):
    authentication_classes = [CustomerTokenAuthentication]
    permission_classes = [IsCustomer]

    def post(self, request):
        CustomerAuthToken.objects.filter(customer=request.customer).delete()
        return Response({"detail": "Logged out"}, status=200)


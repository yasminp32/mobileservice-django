from rest_framework import viewsets, status,permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import IntegrityError
from django.conf import settings
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer,Lead,InventoryStock, StockLedger
from .serializers import ShopSerializer, GrowtagsSerializer, ComplaintSerializer,GrowTagAssignmentSerializer,CustomerSerializer,LeadSerializer
from .serializers import  ShopViewSerializer, GrowtagViewSerializer,InventoryStockSerializer, StockLedgerSerializer,GrowtagPopupSerializer,ShopPopupSerializer
from .services import _ensure_complaint_coords,sync_complaint_to_customer
from .services import (
    geocode_address_pincode,
    nearest_lists_for_address,
    get_nearest_shop,
    get_nearest_growtag,
)
from zoho_integration.customer_sync import sync_core_customer_to_zoho_contact
from zoho_integration.zoho_books import ZohoBooksError
from django.db.models import Q,Count
from rest_framework.permissions import IsAuthenticated,IsAdminUser
from rest_framework.views import APIView
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from core.permissions import IsCustomer,IsShop, BasePermission
from core.authentication import UnifiedTokenAuthentication
from core.serializers import CustomerRegisterSerializer, CustomerLoginSerializer, PublicComplaintSerializer
from core.models import CustomerAuthToken
from core.mixins import BulkDeleteMixin
from .models import Vendor
from .serializers import VendorSerializer
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.filters import SearchFilter,OrderingFilter
from .models import PurchaseOrder,PurchaseBill, PurchaseOrderItem
from .serializers import PurchaseOrderSerializer,PurchaseOrderListSerializer,PurchaseBillListSerializer, PurchaseBillCreateUpdateSerializer,PurchaseOrderItemSerializer
from django.contrib.auth.hashers import check_password
from django.db.models import F
from django.db import transaction
from zoho_integration.models import LocalInvoice
from zoho_integration.models import LocalCustomer
from zoho_integration.serializers import LocalInvoiceReadSerializer
from core.permissions import IsFranchiseShop,IsOtherShop,IsGrowtag,CrudByRole,IsAdminOrCustomerSelf,IsAnyStaffOrShopOrGrowtagOrCustomer
from rest_framework.exceptions import PermissionDenied
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import AllowAny
from core.models import Customer, CustomerPasswordOTP
from django.contrib.auth.hashers import check_password,make_password
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from decimal import Decimal
from core.serializers import PurchaseBillPaymentSerializer, PurchaseBillCreateUpdateSerializer
from core.models import PurchaseBill, PurchaseBillPayment, PurchaseBillItem
from django.db.models import Prefetch
from .models import PostalCode
from .serializers import PostalCodeSerializer

User = get_user_model()

class CreatedByMixin:
    def perform_create(self, serializer):
        return self._set_creator_fields(serializer)
    def _set_creator_fields(self, serializer):
        req = self.request

        # Admin
        if req.user and req.user.is_authenticated and req.user.is_staff:
            return serializer.save(created_by=req.user)

        # Shop token
        if getattr(req, "shop", None):
            return serializer.save(created_by_shop=req.shop)

        # Growtag token
        if getattr(req, "growtag", None):
            return serializer.save(created_by_growtag=req.growtag)

        # Customer token
        if getattr(req, "customer", None):
            return serializer.save(created_by_customer=req.customer)

        # fallback
        return serializer.save()

class ShopViewSet(BulkDeleteMixin,CreatedByMixin, viewsets.ModelViewSet):
    authentication_classes = [
        SessionAuthentication,      # optional admin session
        JWTAuthentication,          # admin bearer token
        UnifiedTokenAuthentication, # shop/growtag/customer token
    ]
    permission_classes = [CrudByRole]
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "PATCH","PUT"},     # but only own object (enforced below)
        "othershop": {"GET", "PATCH","PUT"},     # but only own object (enforced below)
        "growtag": set(),
        "customer": set(),
    }
    def get_queryset(self):
        qs = super().get_queryset()

        # Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
           return qs

        # Shop can only see itself (prevents list leak)
        if getattr(self.request, "shop", None):
           return qs.filter(id=self.request.shop.id)

        return qs.none()

    def destroy(self, request, *args, **kwargs):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
            raise PermissionDenied("Only admin can delete shops.")
        return super().destroy(request, *args, **kwargs)


    # ---------------- MY SHOP PROFILE ----------------
    # GET /api/shops/my/
    @action(
        detail=False,
        methods=["get"],
        url_path="my",
        authentication_classes=[UnifiedTokenAuthentication],
        permission_classes=[IsShop],
    )
    def my(self, request):
      if request.method == "GET":
          return Response(ShopSerializer(request.shop).data)

      serializer = ShopSerializer(request.shop, data=request.data, partial=True)
      serializer.is_valid(raise_exception=True)
      serializer.save()
      return Response(serializer.data)
    
    @action(detail=True, methods=["get"], url_path="view")
    def view_popup(self, request, pk=None):
        shop = self.get_object()
        data = ShopViewSerializer(shop).data
        return Response(data)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        #area = data.get("area", "")
        #pincode = data.get("pincode", "")
        area = (data.get("area") or "").strip()
        pincode = (data.get("pincode") or "").strip()

        # normalize optional fields (avoid storing "")
        for f in ["email", "phone", "gst_pin"]:
           if data.get(f) in ("", None):
                data[f] = None

        lat_lon = geocode_address_pincode(area, pincode)
    
        if lat_lon is not None:
            lat, lon,precision = lat_lon
            data["latitude"] = lat
            data["longitude"] = lon

        try:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        
            
        except IntegrityError as e:

            error_message=str(e).lower()
            if "email" in error_message:
                return Response({
                       "status": "error",
                        "message": "email already exists",
                        "error": {"email": ["this email already exists"]}
                    }, status=400)
            
            if "phone" in error_message:
                return Response({
                    "status":"error",
                    "message":"phone already exists",
                    "error":{"phone":["this phone already exists"]}
                },status=status.HTTP_400_BAD_REQUEST)
                
            if "gst_pin" in error_message:
                return Response({
                    "status":"error",
                    "message":"gst pin already exists",
                    "error":{"gst_pin":["this gst pin already exists"]}
                },status=status.HTTP_400_BAD_REQUEST)
                
            return Response({
                "status":"error",
                "message":"database error",
                "error":str(e)
            },status=status.HTTP_400_BAD_REQUEST)
        return Response(
                {
                    "status": "success",
                    "message": "Shop created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
    def perform_create(self, serializer):
        raw_password = self.request.data.get("password")
        shop = self._set_creator_fields(serializer)

        # admin emails
        admin_emails = (
            User.objects.filter(is_superuser=True)
            .exclude(email__isnull=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )

        recipients = list(admin_emails)

        if shop.email:
            recipients = [shop.email] + recipients

        recipients = list(dict.fromkeys(recipients))  # unique

        if recipients:
            send_mail(
                subject="New Shop Created",
                message=(
                    "A new shop has been created.\n\n"
                    f"Shop Name: {shop.shopname}\n"
                    f"Owner: {shop.owner}\n"
                    f"Phone: {shop.phone}\n"
                    f"Login Password: {raw_password}\n\n"
                    "Please change your password after first login."

                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,
            )
     # Franchise dropdown
    # GET /api/shops/franchise/
    @action(detail=False, methods=["get"], url_path="franchise")
    def franchise_shops(self, request):
        qs = Shop.objects.filter(shop_type="franchise", status=True).order_by("shopname")
        return Response(ShopSerializer(qs, many=True).data)

    # OtherShop dropdown
    # GET /api/shops/othershop/
    @action(detail=False, methods=["get"], url_path="othershop")
    def other_shops(self, request):
        qs = Shop.objects.filter(shop_type="othershop", status=True).order_by("shopname")
        return Response(ShopSerializer(qs, many=True).data)



class GrowtagsViewSet(BulkDeleteMixin,CreatedByMixin, viewsets.ModelViewSet):
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,# optional
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]
    queryset = Growtags.objects.all()
    serializer_class = GrowtagsSerializer
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "growtag": {"GET", "PATCH","PUT"},      # own only
        "franchise": set(),
        "othershop": set(),
        "customer": set(),
    }
    def get_queryset(self):
       qs = super().get_queryset()

       if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
           return qs

       if getattr(self.request, "growtag", None):
          return qs.filter(id=self.request.growtag.id)

       return qs.none()
    

    def destroy(self, request, *args, **kwargs):
       if not (request.user and request.user.is_authenticated and request.user.is_staff):
           raise PermissionDenied("Only admin can delete growtags.")
       return super().destroy(request, *args, **kwargs)
    @action(detail=False, methods=["get"], url_path="franchise", permission_classes=[IsAdminUser])
    def franchise_shops(self, request): ...


    @action(detail=False, methods=["get","patch"], url_path="my",
        authentication_classes=[UnifiedTokenAuthentication],
        permission_classes=[IsGrowtag])
    def my(self, request):
        if request.method == "GET":
           return Response(GrowtagsSerializer(request.growtag).data)

        serializer = GrowtagsSerializer(request.growtag, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="view")
    def view_popup(self, request, pk=None):
        growtag = self.get_object()
        data = GrowtagViewSerializer(growtag).data
        return Response(data)

    def create(self, request, *args, **kwargs):
        if not (request.user and request.user.is_authenticated and request.user.is_staff):
           raise PermissionDenied("Only admin can create growtags.")
        data = request.data.copy()
        area = data.get("area", "")
        pincode = data.get("pincode", "")

        lat_lon = geocode_address_pincode(area, pincode)
        if lat_lon:
            lat, lon,precision = lat_lon
            data["latitude"] = lat
            data["longitude"] = lon

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    def perform_create(self, serializer):
        raw_password = self.request.data.get("password")
        growtag = self._set_creator_fields(serializer)

        # admin emails
        admin_emails = (
            User.objects.filter(is_superuser=True)
            .exclude(email__isnull=True)
            .exclude(email="")
            .values_list("email", flat=True)
        )

        recipients = list(admin_emails)

        # growtag email
        if growtag.email:
            recipients = [growtag.email] + recipients

        recipients = list(dict.fromkeys(recipients))  # unique

        if recipients:
            send_mail(
                subject="New Growtag Created",
                message=(
                    "A new Growtag has been created.\n\n"
                    f"Grow ID: {growtag.grow_id}\n"
                    f"Name: {growtag.name}\n"
                    f"Email: {growtag.email}\n"
                    f"Login Password: {raw_password}\n\n"
                    f"Phone: {growtag.phone or '-'}\n"
                    f"Adhar: {growtag.adhar or '-'}\n"
                    f"Area: {growtag.area or '-'}\n"
                    f"Pincode: {growtag.pincode}\n"
                    f"Status: {growtag.status}\n"
                    "Please change your password after first login."
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=recipients,
                fail_silently=True,  # set False while testing
            )
    # Active GrowTags dropdown
    # GET /api/growtags/active/
    @action(detail=False, methods=["get"], url_path="active")
    def active_growtags(self, request):
        qs = Growtags.objects.filter(status="Active").order_by("grow_id")
        return Response(self.get_serializer(qs, many=True).data)


    @action(detail=True, methods=["post"])
    def set_status(self, request, pk=None):
        """
        Simple endpoint to change tech status:
        POST /api/growtags/<id>/set_status/
        { "status": "Active" }  or  { "status": "Inactive" }
        """
        tech = self.get_object()
        new_status = request.data.get("status")

        # 💡 adjust choices to match your model's STATUS choices
        allowed = ["Active", "Inactive"]

        if new_status not in allowed:
            return Response(
                {"detail": f"Invalid status. Allowed: {allowed}"},
                status=drf_status.HTTP_400_BAD_REQUEST,
            )

        tech.status = new_status
        tech.save(update_fields=["status"])

        return Response(
            {
                "id": tech.id,
                "status": tech.status,
            }
        )

class CustomerViewSet(BulkDeleteMixin,CreatedByMixin, viewsets.ModelViewSet):
    """
    /api/customers/
    - Admin: full CRUD
    - Shop/Growtag: GET only (optional)
    - Customer: GET/PATCH only self
    """
    authentication_classes = [UnifiedTokenAuthentication,
                              JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole, IsAdminOrCustomerSelf]  # both: role + object self-check
    queryset = Customer.objects.all().prefetch_related("complaints")  # ⚡ faster
    serializer_class = CustomerSerializer
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET"},   # optional
        "othershop": {"GET"},   # optional
        "growtag": {"GET"},     # optional
        "customer": {"GET", "PATCH","PUT"},
    }
    def get_queryset(self):
        qs = super().get_queryset()

        # Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # Customer sees only self
        if getattr(self.request, "customer", None):
            return qs.filter(id=self.request.customer.id)

        # Shop/Growtag - if you allow GET list, keep it limited (recommended: only customers from their complaints)
        if getattr(self.request, "shop", None):
            # Example: customers who have complaints assigned to this shop
            return qs.filter(complaint__assigned_shop=self.request.shop).distinct()

        if getattr(self.request, "growtag", None):
            return qs.filter(complaint__assigned_Growtags=self.request.growtag).distinct()

        return qs.none()

    def perform_create(self, serializer):
        # If you already have CustomerRegisterAPIView, you may NOT want POST here except admin.
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            self._set_creator_fields(serializer)   # will set created_by=request.user
            return
        raise PermissionDenied("Only admin can create customers here (use public register API)")
    # GET /api/customers/my/
    @action(
        detail=False,
        methods=["get"],
        url_path="my",
        authentication_classes=[UnifiedTokenAuthentication],
        permission_classes=[IsCustomer],
    )
    def my(self, request):
        return Response(CustomerSerializer(request.customer).data)


class ComplaintViewSet(BulkDeleteMixin,CreatedByMixin,viewsets.ModelViewSet):
    authentication_classes = [
        SessionAuthentication,
       UnifiedTokenAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [CrudByRole]  # default
    queryset = Complaint.objects.all().order_by("-created_at")
    serializer_class = ComplaintSerializer
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "PATCH","PUT"},
        "othershop": {"GET", "PATCH","PUT"},
        "growtag": {"GET", "PATCH","PUT"},
        "customer": {"GET", "POST"},   # customer can create complaint
    }

    def get_queryset(self):
        qs = super().get_queryset()

        # admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # shop sees their assigned complaints
        if getattr(self.request, "shop", None):
            return qs.filter(assigned_shop=self.request.shop)

        # growtag sees their assigned complaints
        if getattr(self.request, "growtag", None):
            return qs.filter(assigned_Growtags=self.request.growtag)

        # customer sees only their complaints
        if getattr(self.request, "customer", None):
            return qs.filter(customer=self.request.customer)

        return qs.none()
        

    # ----------------- CREATE -----------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer_name = data.get("customer_name")
        customer_phone = data.get("customer_phone")
        email = data.get("email")
        password = data.get("password")
        raw_password = password 
        phone_model = data.get("phone_model")
        issue_details = data.get("issue_details")
        address = data.get("address")
        state = data.get("state")
        pincode = data.get("pincode")
        assign_to = data.get("assign_to")
        status_value = data.get("status", "Pending")
        area = data.get("area", "")  # ✅ define area

        # 3️⃣ Find existing customer by phone OR email
        lookup = Q()
        if customer_phone:
            lookup |= Q(customer_phone=customer_phone)
        if email:
            lookup |= Q(email=email)

        customer = None
        if lookup:
            customer = Customer.objects.filter(lookup).first()

        # 4️⃣ If customer already exists, check for conflicts
        if customer:
            conflict_messages = {}

            # Name mismatch
            if customer_name and customer.customer_name and customer.customer_name != customer_name:
                conflict_messages["customer_name"] = "Customer name does not match the existing account."

            # Password mismatch
            if password and customer.password and not check_password(password, customer.password):
                conflict_messages["password"] = "Password does not match the existing account."
            if conflict_messages:
                return Response(conflict_messages, status=status.HTTP_400_BAD_REQUEST)

            # ✅ No conflict → reuse same customer

        else:
            # 5️⃣ No existing customer → create a new one
            customer = Customer.objects.create(
                customer_name=customer_name,
                customer_phone=customer_phone,
                email=email,
                password=make_password(password) if password else "",
                address=address,
                state=state,
                pincode=pincode,
                area=area,
                created_by=request.user if request.user.is_authenticated and request.user.is_staff else None,

            )

        # ✅ Zoho sync (best-effort)
        try:
            local_customer = sync_core_customer_to_zoho_contact(customer)
            print("Zoho contact synced:", local_customer.zoho_contact_id)
        except Exception as e:
            print("Zoho customer sync failed:", str(e))

        # 6️⃣ Create complaint linked to that customer
        complaint = Complaint.objects.create(
            customer=customer,
            customer_name=customer.customer_name,
            customer_phone=customer.customer_phone,
            email=customer.email,
            password=customer.password,
            phone_model=phone_model,
            issue_details=issue_details,
            address=address,
            state=state,
            pincode=pincode,
            area=area,
            assign_to=assign_to,
            status=status_value,
            created_by = request.user if (request.user.is_authenticated and request.user.is_staff) else None,
            #created_by_shop = getattr(request, "shop", None),
            #created_by_growtag = getattr(request, "growtag", None),
            #created_by_customer = getattr(request, "customer", None),


        )

        # ✅ Ensure coords
        _ensure_complaint_coords(complaint)

        # ✅ Auto-Assign Shop/GrowTag
        assigned_shop = None
        assigned_gt = None
        distance_km = None

        if assign_to == "franchise":
            result = get_nearest_shop(complaint, "franchise")
            if result:
                assigned_shop, distance_km = result

        elif assign_to == "othershop":
            result = get_nearest_shop(complaint, "othershop")
            if result:
                assigned_shop, distance_km = result

        elif assign_to == "growtag":
            result = get_nearest_growtag(complaint)
            if result:
                assigned_gt, distance_km = result

        # ✅ Apply assignment
        if assigned_shop:
            complaint.assigned_shop = assigned_shop
            complaint.status = "Assigned"

        if assigned_gt:
            complaint.assigned_Growtags = assigned_gt
            complaint.status = "Assigned"

        complaint.save()

        # 🔁 Sync COMPLAINT → CUSTOMER
        sync_complaint_to_customer(complaint)

        # 5️⃣ Send email
        if complaint.email:
            subject = f"Complaint Registered Successfully (ID: {complaint.id})"
            message = (
                f"Dear {complaint.customer_name},\n\n"
                f"Your complaint has been registered successfully.\n\n"
                f"Customer Details:\n"
                #f"Customer ID: {complaint.id}\n"
                f"Customer ID: {customer.id}\n"
                f"Complaint ID: {complaint.id}\n"
                f"Customer Name: {complaint.customer_name}\n"
                f"Mobile No: {complaint.customer_phone}\n"
                f"Email: {complaint.email}\n"
                #f"Password: {complaint.password or ''}\n"
                f"Password: {raw_password or ''}\n"
                f"Phone Model: {complaint.phone_model}\n"
                f"Address: {complaint.address}\n"
                f"state: {complaint.state}\n"
                f"Pincode: {complaint.pincode}\n"
                f"Issue: {complaint.issue_details}\n"
                f"Assign To: {complaint.assign_to}\n"
                f"Assigned Shop: {getattr(complaint, 'assigned_shop_name', '')}\n"
                f"Status: {complaint.status}\n\n"
                f"Thank you for contacting us.\n"
                f"Support Team"
            )

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[complaint.email],
                    fail_silently=True,
                )
            except Exception as e:
                print("Email Error:", e)

        out = ComplaintSerializer(complaint)
        return Response(out.data, status=status.HTTP_201_CREATED)

    # ----------------- UPDATE -----------------
    def update(self, request, *args, **kwargs):
        """
        Make sure complaint is assigned EITHER to shop OR to growtag,
        and auto-assign nearest based on assign_to.
        """
        partial = kwargs.pop("partial", False)
        complaint = self.get_object()

        serializer = self.get_serializer(complaint, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        # did client send status in this request?
        status_in_request = "status" in data

        # ✅ For PUT: require these fields
        if not partial:
            required = [
                "customer_name",
                "customer_phone",
                "phone_model",
                "issue_details",
                "address",
                "state",
                "pincode",
                "assign_to",
                "area",
            ]
            missing = [f for f in required if f not in data]
            if missing:
                return Response(
                    {"detail": f"PUT requires fields: {', '.join(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # ====== 1️⃣ CUSTOMER LOGIC ======
        customer_name = data.get("customer_name", complaint.customer_name)
        customer_phone = data.get("customer_phone", complaint.customer_phone)
        email = data.get("email", complaint.email)
        password = data.get("password", complaint.password)
        address = data.get("address", complaint.address)
        state = data.get("state", complaint.state)
        pincode = data.get("pincode", complaint.pincode)
        area = data.get("area", complaint.area)

        customer = complaint.customer  # may be None

        # 🔍 find any customer with same phone/email
        lookup = Q()
        if customer_phone:
            lookup |= Q(customer_phone=customer_phone)
        if email:
            lookup |= Q(email=email)

        existing_customer = Customer.objects.filter(lookup).first() if lookup else None

        if existing_customer:
            conflict_messages = {}

            # ✅ If found customer is NOT the same as currently linked customer,
            # block only when user is trying to impersonate (name/pass mismatch)
            if customer and existing_customer.id != customer.id:
                if customer_name and existing_customer.customer_name != customer_name:
                    conflict_messages["customer_name"] = "Customer name does not match the existing account."
                if password and not check_password(password, existing_customer.password):
                    conflict_messages["password"] = "Password does not match the existing account."
                if conflict_messages:
                    return Response(conflict_messages, status=status.HTTP_400_BAD_REQUEST)

                # ✅ link complaint to found customer
                customer = existing_customer

            # If complaint had no customer, link it
            if customer is None:
                customer = existing_customer

        # If still no customer → create
        if customer is None:
            customer = Customer.objects.create(
                customer_name=customer_name,
                customer_phone=customer_phone,
                email=email,
                password=make_password(password) if password else "",
                address=address,
                state=state,
                pincode=pincode,
                area=area,
            )

        else:
            # Update customer (PUT updates all, PATCH updates sent fields only)
            if not partial:
                customer.customer_name = customer_name
                customer.customer_phone = customer_phone
                customer.email = email
                customer.password = make_password(password) if password else ""
                customer.address = address
                customer.state= state
                customer.pincode = pincode
                customer.area = area
            else:
                if "customer_name" in data:
                    customer.customer_name = customer_name
                if "customer_phone" in data:
                    customer.customer_phone = customer_phone
                if "email" in data:
                    customer.email = email
                if "password" in data:
                    customer.password = make_password(password) if password else ""
                if "address" in data:
                    customer.address = address
                if "state" in data:
                    customer.state = state    
                if "pincode" in data:
                    customer.pincode = pincode
                if "area" in data:
                    customer.area = area

            customer.save()

        # ✅ Zoho sync (best-effort)
        try:
            local_customer = sync_core_customer_to_zoho_contact(customer)
            print("Zoho contact synced:", local_customer.zoho_contact_id)
        except Exception as e:
            print("Zoho customer sync failed:", str(e))

        # ====== 2️⃣ SAVE COMPLAINT WITH CORRECT CUSTOMER ======
        complaint = serializer.save(customer=customer)

        # Keep complaint fields in sync with customer
        complaint.customer_name = customer.customer_name
        complaint.customer_phone = customer.customer_phone
        complaint.email = customer.email
        complaint.password = customer.password
        complaint.address = customer.address
        complaint.state = customer.state
        complaint.pincode = customer.pincode
        complaint.area = customer.area
        complaint.save(
            update_fields=[
                "customer_name",
                "customer_phone",
                "email",
                "password",
                "address",
                "state",
                "pincode",
                "area",
            ]
        )

        # ✅ Ensure coords
        _ensure_complaint_coords(complaint)

        assign_to = data.get("assign_to", complaint.assign_to)
        complaint.assign_to = assign_to

        assigned_shop = None
        assigned_gt = None
        distance_km = None

        if assign_to == "growtag":
            complaint.assigned_shop = None
            result = get_nearest_growtag(complaint)
            if result:
                assigned_gt, distance_km = result

        elif assign_to in ["franchise", "othershop"]:
            complaint.assigned_Growtags = None
            result = get_nearest_shop(complaint, assign_to)
            if result:
                assigned_shop, distance_km = result

        if assigned_shop:
            complaint.assigned_shop = assigned_shop
            if not status_in_request:
                complaint.status = "Assigned"

        if assigned_gt:
            complaint.assigned_Growtags = assigned_gt
            if not status_in_request:
                complaint.status = "Assigned"

        complaint.save()

        # 🔁 Sync COMPLAINT → CUSTOMER
        sync_complaint_to_customer(complaint)

        return Response(self.get_serializer(complaint).data)

    # ----------------- PATCH -----------------
    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    # ----------------- NEAREST OPTIONS (for 2nd dropdown) -----------------
    @action(detail=False, methods=["get"], url_path="nearest-options")
    def nearest_options(self, request):
        """
        GET /api/complaints/nearest-options/?area=...&pincode=...&assign_to=franchise|othershop|growtag
        """
        area = request.query_params.get("area", "")
        #pincode = request.query_params.get("pincode", "")
        pincode = str(request.query_params.get("pincode", "")).strip()

        assign_to = request.query_params.get("assign_to", "").lower()
        lat = request.query_params.get("lat")
        lon = request.query_params.get("lon")


        if not area or not pincode:
            return Response(
                {"error": "area and pincode required"},
                status=400
            )

        # call helper
        lists = nearest_lists_for_address(area, pincode,lat=lat, lon=lon)

        # return based on selection
        #if assign_to == "franchise":
            #return Response(lists["franchise"])

        #if assign_to == "othershop":
            #return Response(lists["othershop"])

        #if assign_to == "growtag":
            #return Response(lists["growtag"])

        # otherwise return all
        #return Response(lists)  
        return Response({
        "franchise_shops": lists.get("franchise", []),
        "other_shops": lists.get("othershop", []),
        "growtags": lists.get("growtag", []),
         }) 
    
    

     
    @action(detail=True, methods=["POST"], url_path="create-invoice")
    @transaction.atomic
    def create_invoice(self, request, pk=None):
        complaint = self.get_object()

        # ✅ prevent duplicate invoice (OneToOne)
        if LocalInvoice.objects.filter(complaint=complaint).exists():
          return Response(
            {"detail": "Invoice already created for this complaint"},
            status=status.HTTP_400_BAD_REQUEST
        )

        # -----------------------------
        # ✅ Map core.Customer -> LocalCustomer
        # -----------------------------
        cust = complaint.customer  # core.Customer (can be None if your complaint allows null)
        if not cust:
            return Response({"detail": "Complaint has no linked customer."}, status=400)

        local_customer, _ = LocalCustomer.objects.get_or_create(
            phone=cust.customer_phone,
            defaults={
            "name": cust.customer_name,
            "email": cust.email,
            "state": cust.state,
        }
        )

        # -----------------------------
        # ✅ Decide assignment (ONLY ONE)
        # -----------------------------
        assigned_shop = None
        assigned_growtag = None

        if complaint.assign_to in ["franchise", "othershop"]:
            assigned_shop = getattr(complaint, "assigned_shop", None)
            if not assigned_shop:
               return Response({"detail": "Complaint is not assigned to a shop."}, status=400)

            assigned_growtag = None  # ✅ important

        elif complaint.assign_to == "growtag":
            assigned_growtag = getattr(complaint, "assigned_Growtags", None)
            if not assigned_growtag:
                return Response({"detail": "Complaint is not assigned to a growtag."}, status=400)

            assigned_shop = None  # ✅ important

        else:
           return Response({"detail": "Complaint assign_to is missing/invalid."}, status=400)

        # -----------------------------
        # ✅ Create invoice
        # -----------------------------
        try:
            invoice = LocalInvoice.objects.create(
                complaint=complaint,
                customer=local_customer,
                invoice_date=timezone.localdate(),  # ✅ required
                status="DRAFT",
                assigned_shop=assigned_shop,        # ✅ only one will be set
                assigned_growtag=assigned_growtag,  # ✅ only one will be set
                created_by=request.user
            )
        except ValidationError as e:
            return Response(e.message_dict, status=400)

        return Response(LocalInvoiceReadSerializer(invoice).data, status=status.HTTP_201_CREATED)

class GrowTagAssignmentViewSet(BulkDeleteMixin,CreatedByMixin, viewsets.ModelViewSet):
    authentication_classes = [SessionAuthentication, JWTAuthentication]
    permission_classes = [IsAdminUser]
    queryset = GrowTagAssignment.objects.select_related("growtag", "shop").order_by("-assigned_at")
    serializer_class = GrowTagAssignmentSerializer

    # GET list (for the table)
    # GET /api/growtag-assignments/
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    # Assign button
    # POST /api/growtag-assignments/assign/
    @action(detail=False, methods=["post"], url_path="assign")
    def assign(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        growtag_id = request.data.get("growtag") or request.data.get("growtag_id")
        franchise_shop_id = serializer.validated_data.get("franchise_shop_id")
        othershop_shop_id = serializer.validated_data.get("othershop_shop_id")

        # Active GrowTag only
        try:
            growtag = Growtags.objects.get(id=growtag_id, status="Active")
        except Growtags.DoesNotExist:
            return Response({"error": "GrowTag not found or inactive"}, status=404)

        # pick shop based on dropdown selection
        shop_id = franchise_shop_id or othershop_shop_id
        try:
            shop = Shop.objects.get(id=shop_id, status=True)
        except Shop.DoesNotExist:
            return Response({"error": "Shop not found"}, status=404)

        # ensure dropdown matches shop type
        if franchise_shop_id and shop.shop_type != "franchise":
            return Response({"error": "Selected shop is not Franchise"}, status=400)

        if othershop_shop_id and shop.shop_type != "othershop":
            return Response({"error": "Selected shop is not Other Shop"}, status=400)

        # One assignment per GrowTag (update if exists)
        assignment, created = GrowTagAssignment.objects.update_or_create(
            growtag=growtag,
            defaults={"shop": shop}
        )
        self._send_assignment_email(assignment, created)
        return Response(self.get_serializer(assignment).data, status=201)

    # Unassign Selected
    # DELETE /api/growtag-assignments/<id>/unassign/
    @action(detail=True, methods=["delete"], url_path="unassign")
    def unassign(self, request, pk=None):
        assignment = self.get_object()
        assignment.delete()
        return Response(status=204)
       #email
    def _send_assignment_email(self, assignment, created: bool):
       growtag = assignment.growtag
       shop = assignment.shop

       # admin emails
       admin_emails = (
          User.objects.filter(is_superuser=True)
        .exclude(email__isnull=True)
        .exclude(email="")
        .values_list("email", flat=True)
       )

       recipients = list(admin_emails)

       # growtag email
       if getattr(growtag, "email", None):
            recipients = [growtag.email] + recipients

       recipients = list(dict.fromkeys(recipients))  # unique

       if not recipients:
            return

       subject = "Growtag Assigned to Shop" if created else "Growtag Re-Assigned to Shop"

       message = (
        f"{'New' if created else 'Updated'} Growtag Assignment\n\n"
        f"Grow ID: {growtag.grow_id}\n"
        f"Growtag Name: {growtag.name}\n"
        f"Growtag Email: {growtag.email}\n"
        f"Shop: {shop.shopname}\n"
        f"Shop Type: {shop.shop_type}\n"
        f"Shop Phone: {shop.phone or '-'}\n"
        f"Assigned At: {assignment.assigned_at}\n"
        )

       send_mail(
          subject=subject,
          message=message,
          from_email=settings.DEFAULT_FROM_EMAIL,
          recipient_list=recipients,
          fail_silently=True,  # set False while testing
        )

#not confirmed
class ConfirmComplaintAPIView(APIView):
    
    authentication_classes = [
    SessionAuthentication,
    JWTAuthentication,
    UnifiedTokenAuthentication,
]


    def patch(self, request, pk):
        complaint = get_object_or_404(Complaint, pk=pk)

        # 🔐 ROLE CHECK
        if request.user.is_staff:
           pass

        elif getattr(request, "shop", None):
           if complaint.assigned_shop_id != request.shop.id:
              return Response({"error": "Not your complaint"}, status=403)

        elif getattr(request, "growtag", None):
           if complaint.assigned_Growtags_id != request.growtag.id:
              return Response({"error": "Not your complaint"}, status=403)

        else:
           return Response({"error": "Not allowed"}, status=403)
        # 🔄 READ STATUS FROM BODY
        new_status = request.data.get("confirm_status")

        if new_status not in ["CONFIRMED", "NOT CONFIRMED"]:
          return Response(
            {"error": "confirm_status must be CONFIRMED or NOT CONFIRMED"},
            status=400
            )
        # ✅ CONFIRM
        if new_status == "CONFIRMED":
            complaint.confirm_status = "CONFIRMED"
            complaint.confirmed_by = request.user if request.user.is_authenticated else None
            complaint.confirmed_at = timezone.now()

        # 🔁 UNCONFIRM
        if new_status == "NOT CONFIRMED":
           complaint.confirm_status = "NOT CONFIRMED"
           complaint.confirmed_by = None
           complaint.confirmed_at = None

        
        complaint.save(update_fields=[
            "confirm_status",
            "confirmed_by",
            "confirmed_at"
        ])

        # Prepare proper message
        if new_status == "CONFIRMED":
          message = "Complaint confirmed successfully"
        else:
          message = "Complaint unconfirmed successfully"

        return Response(
            {
             "message": message,
             "confirm_status": complaint.confirm_status,
             "confirmed_at": complaint.confirmed_at,
             "confirmed_by": (
                  complaint.confirmed_by.username
                  if complaint.confirmed_by
                  else None
              ),
            },
        status=status.HTTP_200_OK,
        )
#public customer
from django.db import transaction
from .models import Customer
from rest_framework.exceptions import ValidationError
class CustomerRegisterView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        ser = CustomerRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        customer = ser.save()

        token, _ = CustomerAuthToken.objects.get_or_create(
            customer=customer,
            defaults={"key": CustomerAuthToken.generate_key()}
        )
        return Response({"customer": ser.data, "token": token.key}, status=status.HTTP_201_CREATED)


class CustomerLoginView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        ser = CustomerLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        email = ser.validated_data["email"]
        password = ser.validated_data["password"]

        customer = Customer.objects.filter(email=email).first()
        if not customer or not check_password(password, customer.password):
            return Response({"detail": "Invalid email or password"}, status=status.HTTP_400_BAD_REQUEST)

        token, _ = CustomerAuthToken.objects.get_or_create(
            customer=customer,
            defaults={"key": CustomerAuthToken.generate_key()}
        )
        return Response({"token": token.key, "customer_id": customer.id, "customer_name": customer.customer_name})
    
class PublicComplaintViewSet(BulkDeleteMixin,CreatedByMixin,viewsets.ModelViewSet):
    
    serializer_class = PublicComplaintSerializer
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole]
    role_perms = {
    "admin": {"GET"},
    "customer": {"GET", "POST"},
    "franchise": set(),
    "othershop": set(),
    "growtag": set(),
}
    
    def get_queryset(self):
        customer = getattr(self.request, "customer", None)
        if not customer:
            return Complaint.objects.none()

        # ✅ filtered by token customer id
        return Complaint.objects.filter(customer_id=customer.id).order_by("-created_at")
        #customer = self.request.user # Customer
        #return Complaint.objects.filter(customer=customer).order_by("-created_at")

    def perform_create(self, serializer):
        token_customer = getattr(self.request, "customer", None)
        print("TOKEN CUSTOMER:", token_customer)
         # ✅ DEBUG (keep for 1 test, then remove)
        print("validated_data:", serializer.validated_data)
        print("address in validated_data:", serializer.validated_data.get("address"))
       
        #customer = self.request.user
        data = serializer.validated_data
        # ✅ If customer logged in (Token), use that customer ONLY
        if token_customer:
           customer = token_customer
        else:
           phone = (data.get("customer_phone") or "").strip()
           name  = (data.get("customer_name") or "").strip()
           email = data.get("email") or None

           if not phone:
              raise ValidationError({"customer_phone": ["This field is required."]})
           if not name:
              raise ValidationError({"customer_name": ["This field is required."]})

           with transaction.atomic():
            customer, created = Customer.objects.get_or_create(
             customer_phone=phone,
               defaults={
                "customer_name": name,
                "email": email,
                "address": data.get("address") or "",
                "state": data.get("state") or "",
                "pincode": data.get("pincode") or "",
                "area": data.get("area") or "",
            },
            )

            # If customer already exists, keep it updated (optional)
            updates = []
            if name and customer.customer_name != name:
                customer.customer_name = name
                updates.append("customer_name")
            if email and customer.email != email:
                customer.email = email
                updates.append("email")
            if updates:
                customer.save(update_fields=updates)

        complaint = serializer.save(
                   customer=customer,
                   customer_name=customer.customer_name,
                   customer_phone=customer.customer_phone,
                   address=data.get("address"),
                   state=data.get("state"),
                   pincode=data.get("pincode"),
                   area=data.get("area"),
                   status="Pending",
                   

        )

        _ensure_complaint_coords(complaint)

        if complaint.assign_to == "franchise":
            result = get_nearest_shop(complaint, "franchise")
            if result:
                complaint.assigned_shop, _ = result
                complaint.status = "Assigned"

        elif complaint.assign_to == "othershop":
             result = get_nearest_shop(complaint, "othershop")
             if result:
                 complaint.assigned_shop, _ = result
                 complaint.status = "Assigned"

        elif complaint.assign_to == "growtag":
            result = get_nearest_growtag(complaint)
            if result:
                complaint.assigned_Growtags, _ = result
                complaint.status = "Assigned"

        complaint.save()
        sync_complaint_to_customer(complaint)
#lead viewset
from core.services import geocode_address_pincode
class LeadViewSet(BulkDeleteMixin,CreatedByMixin,viewsets.ModelViewSet):
    """
    Admin: full CRUD
    Shop: create/view/update own leads
    Growtag: view own assigned leads (optional PATCH status)
    """
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole]
    queryset = Lead.objects.all().order_by("-created_at")
    serializer_class = LeadSerializer
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH"},
        "othershop": {"GET", "POST", "PATCH"},
        "growtag": {"GET", "PATCH"},  # optional: allow PATCH only for status fields
        # "customer": {"POST"}  # only if you want public lead create
    }
    def get_queryset(self):
        qs = super().get_queryset()

        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        if getattr(self.request, "shop", None):
            return qs.filter(assigned_shop=self.request.shop)

        if getattr(self.request, "growtag", None):
            return qs.filter(assigned_growtag=self.request.growtag)

        if getattr(self.request, "customer", None):
            return qs.filter(created_by_customer=self.request.customer)

        return qs.none()
    def perform_create(self, serializer):
       # Admin
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
           serializer.save(created_by=self.request.user)
           return

         # Shop
        if getattr(self.request, "shop", None):
           serializer.save(assigned_shop=self.request.shop)
           return

        # Customer (optional)
        if getattr(self.request, "customer", None):
           serializer.save(created_by_customer=self.request.customer)
           return

        raise PermissionDenied("Not allowed to create leads")
    
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def register_complaint(self, request, pk=None):
        lead = self.get_object()
        if lead.status == "CONVERTED":
            return Response(
               {"error": "Lead already converted"},
                status=400
            )

        #lead = self.get_object()

        assign_to = request.data.get("assign_to")
        assigned_shop_id = request.data.get("assigned_shop")              # shop id
        assigned_growtag_id = request.data.get("assigned_Growtags")       # growtag id

        if assign_to not in ["franchise", "othershop", "growtag"]:
            return Response({"error": "assign_to is required"}, status=400)

        # ✅ manual assignment validation
        assigned_shop = None
        assigned_growtag = None

        if assign_to in ["franchise", "othershop"]:
            if not assigned_shop_id:
                return Response({"error": "assigned_shop is required"}, status=400)
            assigned_shop = Shop.objects.filter(id=assigned_shop_id).first()
            if not assigned_shop:
                return Response({"error": "assigned_shop invalid"}, status=400)

        if assign_to == "growtag":
            if not assigned_growtag_id:
                return Response({"error": "assigned_Growtags is required"}, status=400)
            assigned_growtag = Growtags.objects.filter(id=assigned_growtag_id).first()
            if not assigned_growtag:
                return Response({"error": "assigned_Growtags invalid"}, status=400)
        # ✅ Check existing by phone
        customer_by_phone = Customer.objects.filter(customer_phone=lead.customer_phone).first()

        # ✅ Check existing by email (ignore empty)
        customer_by_email = None
        if lead.email:
            customer_by_email = Customer.objects.filter(email=lead.email).first()

        # 🚫 Phone and email belong to different customers
        if customer_by_phone and customer_by_email and customer_by_phone.id != customer_by_email.id:
           return Response({"error": "Phone number and email belong to different customers"}, status=400)

        # 🚫 Email exists but phone different (optional strict rule)
        if customer_by_email and not customer_by_phone and lead.customer_phone:
        # If you want reuse instead of block, remove this return.
          return Response({"error": "Email already exists with another customer"}, status=400)

        # ✅ Choose existing customer if any
        customer = customer_by_phone or customer_by_email
        lead_pwd = getattr(lead, "password", None)
        # ✅ If no existing customer → create new
        if not customer:
               customer = Customer.objects.create(
               customer_phone=lead.customer_phone,
               customer_name=lead.customer_name,
               email=lead.email,
               address=lead.address,
               pincode=lead.pincode,
               state=lead.state,
               password=(
               lead_pwd if (lead_pwd and str(lead_pwd).startswith("pbkdf2_"))
                else (make_password(lead_pwd) if lead_pwd else None)
             ),
            )
        else:
           customer.customer_name = lead.customer_name
           customer.email = lead.email
           customer.address = lead.address
           customer.pincode = lead.pincode
           customer.state = lead.state
           # ✅ Copy password from lead -> customer (only if lead has password)
           lead_pwd = getattr(lead, "password", None)
           if lead_pwd:
                pwd = lead_pwd
                if not str(pwd).startswith("pbkdf2_"):
                    pwd = make_password(pwd)
                customer.password = pwd

            # ✅ Save including password if set
           update_fields = ["customer_name", "email", "address", "pincode", "state"]
           if lead_pwd:
                update_fields.append("password")

           customer.save(update_fields=update_fields)

        complaint = Complaint.objects.create(
            customer=customer,
            customer_name=lead.customer_name,
            customer_phone=lead.customer_phone,
            email=lead.email,
            phone_model=lead.phone_model,
            issue_details=lead.issue_detail,
            address=lead.address,
            pincode=lead.pincode,
            area=getattr(lead, "area", None),
            state=getattr(lead, "state", None),
            assign_to=assign_to,
            assigned_shop=assigned_shop,
            assigned_Growtags=assigned_growtag,

            status="Assigned",  # since manually assigned now
            created_by=request.user if request.user and request.user.is_staff else None,
        )
        # call your geocode function that sets latitude/longitude and saves
        # ✅ call correct function and unpack 3 values
        res = geocode_address_pincode(complaint.area, complaint.pincode)

        if not res:
          return Response(
            {
            "error": "Geocode returned None",
            "area": complaint.area,
            "pincode": complaint.pincode,
             },
           status=400,
           )

        lat, lon, precision = res  # precision = "area_pincode" / "pincode" / "area_only"

        complaint.latitude = lat
        complaint.longitude = lon
        complaint.save(update_fields=["latitude", "longitude"])
        # mark lead as converted
        #lead.status = "CONVERTED"
        #lead.save(update_fields=["status"])
        lead.complaint = complaint
        lead.status = Lead.STATUS_COMPLAINT  # "COMPLAINT_REGISTERED"
        lead.save(update_fields=["complaint", "status"])

        return Response(
            {"message": "Complaint created (manual assignment)", "complaint_id": complaint.id,
             "latitude": complaint.latitude,
            "longitude": complaint.longitude,},
            status=status.HTTP_201_CREATED
        )
    @action(detail=True, methods=["get"])
    def complaint_prefill(self, request, pk=None):
        lead = self.get_object()

        return Response({
            "customer_name": lead.customer_name,
            "customer_phone": lead.customer_phone,
            "email": lead.email,
            "phone_model": lead.phone_model,
            "issue_details": lead.issue_detail,
            "address": lead.address,
            "pincode": lead.pincode,
            "area": getattr(lead, "area", None),
            "state": getattr(lead, "state", None),
            # defaults for form
            "assign_to": "franchise",
            "assigned_shop": None,
            "assigned_Growtags": None,
        })
    
class SalesIQLeadWebhook(APIView):
    authentication_classes = []
    permission_classes = []   
    def post(self, request):
        payload = request.data or {}

        visitor = payload.get("visitor") or {}
        chat = payload.get("chat") or {}

        # ✅ extract from visitor
        phone = (visitor.get("phone") or "").strip()
        email = (visitor.get("email") or "").strip() or None
        name = (visitor.get("name") or "Unknown").strip()

        # ✅ visitor id (if present)
        visitor_id = (
            payload.get("visitor_id")
            or visitor.get("id")
            or payload.get("salesiq_visitor_id")
        )

        # ✅ issue from chat (optional but recommended)
        subject = (chat.get("subject") or "").strip()
        message = (chat.get("message") or "").strip()
        issue_detail = " - ".join([x for x in [subject, message] if x])

        # dedupe: prefer phone else visitor_id
        lead = None
        if phone:
            lead = Lead.objects.filter(customer_phone=phone).first()
        if not lead and visitor_id:
            lead = Lead.objects.filter(salesiq_visitor_id=visitor_id).first()

        if lead:
            lead.customer_name = name or lead.customer_name
            lead.customer_phone = phone or lead.customer_phone
            lead.email = email or lead.email
            lead.source = "SALESIQ"
            lead.raw_payload = payload

            # save issue if your Lead model has it
            if hasattr(lead, "issue_detail") and issue_detail:
                lead.issue_detail = issue_detail

            lead.save()
            return Response({"message": "Lead updated", "lead_code": lead.lead_code})

        create_kwargs = dict(
            customer_name=name,
            customer_phone=phone or "",
            email=email,
            source="SALESIQ",
            salesiq_visitor_id=visitor_id,
            raw_payload=payload,
        )
        if hasattr(Lead, "issue_detail") and issue_detail:
            create_kwargs["issue_detail"] = issue_detail

        lead = Lead.objects.create(**create_kwargs)
        return Response({"message": "Lead created", "lead_code": lead.lead_code}, status=201)

#vendor
from django.db.models import Q, Count

from .models import Vendor
from .serializers import VendorSerializer

class VendorListCreateAPIView(APIView):
    """
    Vendors page API:
    - GET: list vendors + search + status filter + counts (active/inactive)
    - POST: create vendor (Add Vendor popup)
    """
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole]
    queryset = Vendor.objects.all().order_by("-id")
    serializer_class = VendorSerializer

    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH","PUT"},
        "othershop": {"GET", "POST", "PATCH","PUT"},
        "growtag": {"GET"},   # optional
    }
    def base_queryset(self, request):
        qs = Vendor.objects.all()

        # Admin sees all vendors
        if request.user and request.user.is_authenticated and request.user.is_staff:
            return qs

        # Shop sees only its vendors
        if getattr(request, "shop", None):
            return qs.filter(shop=request.shop)

        # Growtag sees none (as per your rule)
        if getattr(request, "growtag", None):
            return qs.none()

        return qs.none()

    def perform_create(self, serializer):
        # Admin can create vendor (if vendor.shop is nullable or admin sends shop in payload)
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # Shop creates vendor for itself only
        if getattr(self.request, "shop", None):
            serializer.save(shop=self.request.shop)
            return

        raise PermissionDenied("Not allowed to create vendor")

    def get(self, request):
        search = (request.query_params.get("search") or "").strip()
        status_filter = (request.query_params.get("status") or "").strip().lower()
        ordering = (request.query_params.get("ordering") or "-created_at").strip()

        qs = self.base_queryset(request)

        if status_filter in ["active", "inactive"]:
            qs = qs.filter(status=status_filter)

        if search:
            qs = qs.filter(
                Q(name__icontains=search)
                | Q(email__icontains=search)
                | Q(phone__icontains=search)
                | Q(website__icontains=search)
                | Q(address__icontains=search)
            )

        allowed_ordering = {"name", "-name", "created_at", "-created_at", "id", "-id"}
        if ordering not in allowed_ordering:
            ordering = "-created_at"
        qs = qs.order_by(ordering)

        data = VendorSerializer(qs, many=True).data

        counts = qs.values("status").annotate(total=Count("id"))
        counts_map = {c["status"]: c["total"] for c in counts}

        return Response(
            {
                "success": True,
                "message": "Vendors fetched successfully",
                "count": len(data),
                "counts": {
                    "active": counts_map.get("active", 0),
                    "inactive": counts_map.get("inactive", 0),
                },
                "data": data,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = VendorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)  # ✅ important
        return Response(
            {
                "success": True,
                "message": "Vendor created successfully",
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


class VendorDetailAPIView(APIView):
    """
    Row Actions API:
    - PATCH: edit vendor (pencil)
    - DELETE: delete vendor (trash)
    - GET: optional (fetch single vendor for edit form)
    """
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "PATCH","PUT"},
        "othershop": {"GET", "PATCH","PUT"},
        "growtag": {"GET"},   # optional (or remove)
    }

    def get_object(self, pk):
        vendor = get_object_or_404(Vendor, pk=pk)

        # Admin can access any vendor
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return vendor

        # Shop can access ONLY its own vendors
        if getattr(self.request, "shop", None):
            if getattr(vendor, "shop_id", None) != self.request.shop.id:
                raise PermissionDenied("You cannot access this vendor.")
            return vendor

        # Growtag (optional): block or allow read-only depending on your rule
        if getattr(self.request, "growtag", None):
            raise PermissionDenied("Growtag cannot access vendors.")
            # or return vendor if you have mapping logic

        raise PermissionDenied("Not allowed.")

    def get(self, request, pk):
        vendor = self.get_object(pk)
        return Response({"success": True, "data": VendorSerializer(vendor).data}, status=200)

    def patch(self, request, pk):
        vendor = self.get_object(pk)
        serializer = VendorSerializer(vendor, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"success": True, "message": "Vendor updated successfully", "data": serializer.data},
            status=200,
        )

    def delete(self, request, pk):
        vendor = self.get_object(pk)
        vendor.delete()
        return Response({"success": True, "message": "Vendor deleted successfully"}, status=200)
    def put(self, request, pk):
        vendor = self.get_object(pk)
        serializer = VendorSerializer(vendor, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {
            "success": True,
            "message": "Vendor updated successfully",
            "data": serializer.data,
            },
           status=200,
        )
    
#purchase order
class PurchaseOrderItemViewSet(viewsets.ModelViewSet):
    authentication_classes = [
        SessionAuthentication,
       JWTAuthentication,
       UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]
    queryset = PurchaseOrderItem.objects.select_related("purchase_order").all().order_by("-created_at")
    serializer_class = PurchaseOrderItemSerializer

    # same style permissions
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH","PUT"},
        "othershop": {"GET", "POST", "PATCH","PUT"},
        "growtag": {"GET", "POST", "PATCH","PUT"},      # view only (change if you want)
        "customer": set(),
    }

    def get_queryset(self):
        qs = super().get_queryset()

        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
           return qs

        if getattr(self.request, "shop", None):
           return qs.filter(purchase_order__shop=self.request.shop)

        if getattr(self.request, "growtag", None):
            return qs.filter(purchase_order__growtag=self.request.growtag)  

        return qs.none()


    def perform_create(self, serializer):
        po = serializer.validated_data.get("purchase_order")
        if not po:
            raise PermissionDenied("purchase_order is required")

        # Admin can create for any PO
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # Shop can add item only to its own PO
        if getattr(self.request, "shop", None):
            if getattr(po, "shop_id", None) != self.request.shop.id:
                raise PermissionDenied("You cannot add items to another shop's PurchaseOrder.")
            serializer.save()
            return

        # ✅ Growtag creates PO for itself
        if getattr(self.request, "growtag", None):
            if getattr(po, "growtag_id", None) != self.request.growtag.id:  # ✅ ADDED
                raise PermissionDenied("You cannot add items to another growtag's PurchaseOrder.")  # ✅ ADDED
            serializer.save()  # ✅ CHANGED
            return

        raise PermissionDenied("Not allowed")

    def perform_update(self, serializer):
        # Admin can update anything
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # Shop can update only its own PO items (already restricted by get_queryset)
        if getattr(self.request, "shop", None):
             # ✅ Block editing if the PurchaseOrder is confirmed/cancelled
            po = serializer.instance.purchase_order
            if getattr(po, "status", "").upper() in ("CONFIRMED", "CANCELLED"):
                raise PermissionDenied("Cannot edit items after PO confirmed/cancelled")
            serializer.save()
            return
        if getattr(self.request, "growtag", None):
            po = serializer.instance.purchase_order
            if getattr(po, "growtag_id", None) != self.request.growtag.id:
                raise PermissionDenied("You cannot edit items of another growtag's PurchaseOrder.")
            if getattr(po, "status", "").upper() in ("CONFIRMED", "CANCELLED"):
                raise PermissionDenied("Cannot edit items after PO confirmed/cancelled")
            serializer.save()
            return
        raise PermissionDenied("Not allowed to update purchase order items")
class PurchaseOrderListCreateAPIView(ListCreateAPIView):
    
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]
    filter_backends = [SearchFilter]
    search_fields = ["po_number", "vendor__name", "status"]
    role_perms = {
        "admin": {"GET", "POST","PATCH","PUT","DELETE"},
        "franchise": {"GET", "POST","PATCH","PUT"},
        "othershop": {"GET", "POST","PATCH","PUT"},
        "growtag": {"GET", "POST", "PATCH","PUT"},   # usually view only
        "customer": set(),
    }
    
    def get_queryset(self):
        qs = (PurchaseOrder.objects
               .select_related("vendor", "shop")
               .prefetch_related(
                   Prefetch(
                           "items",
                  queryset=PurchaseOrderItem.objects.select_related("item")
              )
            )
            .order_by("-id")
        )

        # Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # Shop sees only its purchase orders (CHANGE FIELD NAME if needed)
        if getattr(self.request, "shop", None):
            return qs.filter(shop=self.request.shop)

        # Growtag sees only its purchase orders (if your model has growtag)
        if getattr(self.request, "growtag", None):
            return qs.filter(growtag=self.request.growtag)

        return qs.none()

    def get_serializer_class(self):
        if self.request.method == "GET":
            return PurchaseOrderListSerializer
        return PurchaseOrderSerializer  # POST create uses full serializer
    def perform_create(self, serializer):
        # Admin can create any
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # Shop creates PO for itself (force)
        if getattr(self.request, "shop", None):
            serializer.save(shop=self.request.shop, growtag=None) 
            return
        if getattr(self.request, "growtag", None):
            serializer.save(growtag=self.request.growtag, shop=None)  # ✅ ADDED
            return
        raise PermissionDenied("Not allowed to create Purchase Order")


class PurchaseOrderDetailAPIView(RetrieveUpdateDestroyAPIView):
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
    ]
    permission_classes = [CrudByRole]
    serializer_class = PurchaseOrderSerializer
    role_perms = {
        "admin": {"GET", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "PATCH","PUT"},
        "othershop": {"GET", "PATCH","PUT"},
        "growtag": {"GET", "POST", "PATCH","PUT"},
        "customer": set(),
    }
    
    def get_queryset(self):
        qs = (
              PurchaseOrder.objects
              .select_related("vendor", "shop")
              .prefetch_related(
                    Prefetch(
                         "items",
                          queryset=PurchaseOrderItem.objects.select_related("item")
                    )
                )
                .order_by("-id")
              )
        # Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # Shop sees only its POs (CHANGE FIELD NAME if needed)
        if getattr(self.request, "shop", None):
            return qs.filter(shop=self.request.shop)

        # Growtag sees only its POs (if model has)
        if getattr(self.request, "growtag", None):
            return qs.filter(growtag=self.request.growtag)

        return qs.none()

    def perform_update(self, serializer):
        obj = self.get_object()

        # Admin can update anything
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # Shop can update ONLY if not confirmed
        if getattr(self.request, "shop", None):
            if getattr(obj, "status", "").upper() in ("CONFIRMED", "CANCELLED"):
                raise PermissionDenied("Cannot edit after confirmed/cancelled")
            serializer.save()
            return
        if getattr(self.request, "growtag", None):
            if getattr(obj, "growtag_id", None) != self.request.growtag.id:
                raise PermissionDenied("You cannot edit another growtag's PurchaseOrder.")
            if getattr(obj, "status", "").upper() in ("CONFIRMED", "CANCELLED"):
                raise PermissionDenied("Cannot edit after confirmed/cancelled")
            serializer.save()
            return
        raise PermissionDenied("Not allowed to update Purchase Order")
#bills
class PurchaseBillViewSet(viewsets.ModelViewSet):
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["bill_number", "vendor_name", "payment_status", "status"]
    ordering_fields = ["bill_date", "due_date", "created_at", "total", "balance_due"]
    ordering = ["-created_at"]
    queryset = PurchaseBill.objects.prefetch_related(
                  Prefetch("items", queryset=PurchaseBillItem.objects.select_related("item")),
                  "payments"
               )
    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH","PUT"},   # shop users
        "othershop": {"GET", "POST", "PATCH","PUT"},   # shop users
        "growtag": {"GET", "POST", "PATCH","PUT"},     # allow create/update for their own bills
        "customer": set(),
    }
   


    def get_serializer_class(self):
        if self.action == "list":
            return PurchaseBillListSerializer
        return PurchaseBillCreateUpdateSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # ✅ Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # ✅ Shop sees only its own bills (owner_type=shop AND shop=request.shop)
        if getattr(self.request, "shop", None):
            return qs.filter(created_by_shop=self.request.shop)

        # ✅ Growtag sees only its own bills (owner_type=growtag AND growtag=request.growtag)
        if getattr(self.request, "growtag", None):
            return qs.filter(created_by_growtag=self.request.growtag)

        return qs.none()

    def perform_create(self, serializer):
        # ✅ Admin can create any
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # ✅ Shop: force owner fields from token (ignore request body)
        if getattr(self.request, "shop", None):
            serializer.save(
                 created_by_shop=self.request.shop,     # ✅ ADDED / CHANGED
                created_by_growtag=None,        
            )
            return

        # ✅ Growtag: force owner fields from token (ignore request body)
        if getattr(self.request, "growtag", None):
            serializer.save(
                created_by_growtag=self.request.growtag,  # ✅ ADDED / CHANGED
                created_by_shop=None,  
            )
            return

        raise PermissionDenied("Not allowed to create PurchaseBill")

    def perform_update(self, serializer):
        obj = self.get_object()
        # ✅ Admin can update any
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save()
            return

        # ✅ Shop: cannot change ownership; keep owner_type/shop/growtag locked
        if getattr(self.request, "shop", None):
            if getattr(obj, "created_by_shop_id", None) != self.request.shop.id:
                raise PermissionDenied("You cannot update another shop's PurchaseBill.")
            serializer.save(
                created_by_shop=self.request.shop,  # ✅ keep locked
                created_by_growtag=None,            # ✅ keep locked
            )
            return

        # ✅ Growtag can update only its own bill (lock creator fields)
        if getattr(self.request, "growtag", None):
            if getattr(obj, "created_by_growtag_id", None) != self.request.growtag.id:
                raise PermissionDenied("You cannot update another growtag's PurchaseBill.")
            serializer.save(
                created_by_growtag=self.request.growtag,  # ✅ keep locked
                created_by_shop=None,                     # ✅ keep locked
            )
            return

        raise PermissionDenied("Not allowed to update PurchaseBill")

    def perform_destroy(self, instance):
        # ✅ Admin only delete (recommended for accounting)
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            instance.delete()
            return
        raise PermissionDenied("Only admin can delete PurchaseBill")
     # ✅ helper: check bill belongs to current actor (admin/shop/growtag)
    def _can_access_bill(self, bill):
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return True
        if getattr(self.request, "shop", None):
            return getattr(bill, "created_by_shop_id", None) == self.request.shop.id
        if getattr(self.request, "growtag", None):
            return getattr(bill, "created_by_growtag_id", None) == self.request.growtag.id
        return False
    @action(detail=True, methods=["post"], url_path="add-payment")
    @transaction.atomic
    def add_payment(self, request, pk=None):
        # lock bill row so balance_due can't change mid-request
        bill = PurchaseBill.objects.select_for_update().get(pk=pk)
        # ✅ ADDED: owner check for add-payment
        if not self._can_access_bill(bill):
            raise PermissionDenied("You cannot add payment to this bill.")
        ser = PurchaseBillPaymentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        amount = ser.validated_data.get("amount") or Decimal("0.00")
        if amount <= 0:
            raise ValidationError({"amount": "Amount must be greater than 0."})

        # IMPORTANT: make sure bill balance_due is fresh
        bill.recalc_totals()
        bill.refresh_from_db(fields=["balance_due", "total", "amount_paid", "payment_status"])

        if bill.balance_due <= 0:
            raise ValidationError({"detail": "Bill is already fully paid. No further payment allowed."})

        if amount > bill.balance_due:
            raise ValidationError({"amount": f"Amount cannot exceed balance due ({bill.balance_due})."})

        PurchaseBillPayment.objects.create(
            bill=bill,
            payment_date=ser.validated_data.get("payment_date"),
            amount=amount,
            method=ser.validated_data.get("method", ""),
            reference=ser.validated_data.get("reference", ""),
        )

        bill.recalc_totals()
        bill.refresh_from_db()

        out = PurchaseBillCreateUpdateSerializer(bill, context={"request": request})
        return Response(out.data, status=status.HTTP_200_OK)
#stock
# Replace these permissions with your real ones:
class IsShopOrGrowtag(BasePermission):
    def has_permission(self, request, view):
        return bool(getattr(request, "shop", None) or getattr(request, "growtag", None))

class InventoryStockViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Admin: can filter by owner_type + owner_id.
    Shop: can access only their own stock via /my/stock/
    Growtag: can access only their own stock via /my/stock/
    """
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]
    queryset = InventoryStock.objects.select_related("item", "shop", "growtag").all().order_by("-updated_at")
    serializer_class = InventoryStockSerializer
    role_perms = {
        "admin": {"GET"},
        "franchise": {"GET"},
        "othershop": {"GET"},
        "growtag": {"GET"},
        "customer": set(),
    }

    def get_queryset(self):
        qs = super().get_queryset()

        # ✅ Admin view
        if self.request.user.is_staff:
            group = self.request.query_params.get("group")  # franchise | othershop | growtag
            shop_id = self.request.query_params.get("shop_id")
            growtag_id = self.request.query_params.get("growtag_id")
            item_id = self.request.query_params.get("item")
            # ✅ Invalid filter combos
            if group == "growtag" and shop_id:
               return qs.none()

            if group in ("franchise", "othershop") and growtag_id:
               return qs.none()


            # --- TAB filters ---
            if group == "franchise":
                qs = qs.filter(owner_type="shop", shop__shop_type="franchise")
            elif group == "othershop":
                qs = qs.filter(owner_type="shop", shop__shop_type="othershop")
            elif group == "growtag":
                qs = qs.filter(owner_type="growtag")

            # --- DROPDOWN filters ---
            if shop_id:
                qs = qs.filter(owner_type="shop", shop_id=shop_id)
            if growtag_id:
                qs = qs.filter(owner_type="growtag", growtag_id=growtag_id)

            # --- Optional search by item ---
            if item_id:
                qs = qs.filter(item_id=item_id)

            return qs

        # Non-admin: empty here; use /my
        return qs.none()
    
    @action(detail=False, methods=["GET"], url_path="filters")
    def filters(self, request):
        """
        Dropdown options for admin:
        - franchise shops list
        - other shops list
        - growtags list
        """
        if not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=403)

        franchise_shops = Shop.objects.filter(shop_type="franchise", status=True).values("id", "shopname")
        other_shops = Shop.objects.filter(shop_type="othershop", status=True).values("id", "shopname")
        growtags = Growtags.objects.filter(status="Active").values("id", "name", "grow_id")

        return Response({
            "franchises": list(franchise_shops),
            "other_shops": list(other_shops),
            "growtags": list(growtags),
        })

    @action(detail=False, methods=["GET"], url_path="summary")
    def summary(self, request):
        """
        Cards like your UI:
        - total_items
        - in_stock
        - low_stock  (qty_on_hand <= reorder_level, and qty_on_hand > 0)
        """
        if not request.user.is_staff:
            return Response({"detail": "Forbidden"}, status=403)

        qs = self.get_queryset()

        total_items = qs.count()
        in_stock = qs.filter(qty_on_hand__gt=0).count()
        low_stock = qs.filter(qty_on_hand__gt=0, qty_on_hand__lte=F("reorder_level")).count()

        return Response({
            "total_items": total_items,
            "in_stock": in_stock,
            "low_stock": low_stock,
        })
    @action(detail=False, methods=["GET"], url_path="my")
    def my_stock(self, request):
        qs = InventoryStock.objects.select_related("item", "shop", "growtag").order_by("-updated_at")

        # ✅ Shop token
        if getattr(request, "shop", None):
            qs = qs.filter(owner_type="shop", shop=request.shop)
            return Response(self.get_serializer(qs, many=True).data)

        # ✅ Growtag token
        if getattr(request, "growtag", None):
            qs = qs.filter(owner_type="growtag", growtag=request.growtag)
            return Response(self.get_serializer(qs, many=True).data)

        return Response({"detail": "User has no stock ownership"}, status=403)


    @action(detail=False, methods=["GET"], url_path="my/summary")
    def my_summary(self, request):
        if getattr(request, "shop", None):
           qs = InventoryStock.objects.filter(owner_type="shop", shop=request.shop)
        elif getattr(request, "growtag", None):
           qs = InventoryStock.objects.filter(owner_type="growtag", growtag=request.growtag)
        else:
           return Response({"detail": "User has no stock ownership"}, status=403)

        return Response({
        "total_items": qs.count(),
        "in_stock": qs.filter(qty_on_hand__gt=0).count(),
        "low_stock": qs.filter(qty_on_hand__gt=0, qty_on_hand__lte=F("reorder_level")).count(),
    })


class StockLedgerViewSet(viewsets.ReadOnlyModelViewSet):

    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication,SessionAuthentication]
    permission_classes = [CrudByRole]
    queryset = StockLedger.objects.select_related("item", "shop", "growtag").all()
    serializer_class = StockLedgerSerializer
    role_perms = {
        "admin": {"GET"},
        "franchise": {"GET"},
        "othershop": {"GET"},
        "growtag": {"GET"},
    }


    def get_queryset(self):
        qs = super().get_queryset()

        if self.request.user.is_staff:
            group = self.request.query_params.get("group")  # franchise | othershop | growtag
            shop_id = self.request.query_params.get("shop_id")
            growtag_id = self.request.query_params.get("growtag_id")

            item_id = self.request.query_params.get("item")
            ref_type = self.request.query_params.get("ref_type")
            ref_id = self.request.query_params.get("ref_id")
            # ✅ Invalid combos (ADD HERE)
            if group == "growtag" and shop_id:
               return qs.none()
            if group in ("franchise", "othershop") and growtag_id:
               return qs.none()

            if group == "franchise":
                qs = qs.filter(owner_type="shop", shop__shop_type="franchise")
            elif group == "othershop":
                qs = qs.filter(owner_type="shop", shop__shop_type="othershop")
            elif group == "growtag":
                qs = qs.filter(owner_type="growtag")

            if shop_id:
                qs = qs.filter(owner_type="shop", shop_id=shop_id)
            if growtag_id:
                qs = qs.filter(owner_type="growtag", growtag_id=growtag_id)

            if item_id:
                qs = qs.filter(item_id=item_id)
            if ref_type:
                qs = qs.filter(ref_type=ref_type)
            if ref_id:
                qs = qs.filter(ref_id=ref_id)

            return qs

        return qs.none()
    
#password reset  api
class SendResetOTPAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")

        if not email:
            return Response({"detail": "Email required"}, status=400)

        customer = Customer.objects.filter(email=email).first()

        if not customer:
            return Response({"detail": "If account exists, OTP sent."}, status=200)

        # Delete old OTPs
        CustomerPasswordOTP.objects.filter(customer=customer).delete()

        raw_otp, otp_obj = CustomerPasswordOTP.create_otp_for_customer(customer)

        send_mail(
            subject="Your Password Reset OTP",
            message=f"Your OTP is: {raw_otp}. It expires in 5 minutes.",
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[customer.email],
        )

        return Response({"detail": "If account exists, OTP sent."}, status=200)
class VerifyResetOTPAPIView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get("email")
        otp = request.data.get("otp")
        new_password = request.data.get("new_password")
        confirm_password = request.data.get("confirm_password")

        if not email or not otp or not new_password:
            return Response({"detail": "All fields required"}, status=400)
        # ✅ Check password match
        if new_password != confirm_password:
            return Response({"detail": "Passwords do not match"}, status=400)


        customer = Customer.objects.filter(email=email).first()
        if not customer:
            return Response({"detail": "Invalid OTP"}, status=400)

        otp_obj = CustomerPasswordOTP.objects.filter(customer=customer).first()
        if not otp_obj:
            return Response({"detail": "Invalid OTP"}, status=400)

        if otp_obj.is_expired():
            otp_obj.delete()
            return Response({"detail": "OTP expired"}, status=400)

        if not check_password(otp, otp_obj.otp_hash):
            return Response({"detail": "Invalid OTP"}, status=400)
        try:
            validate_password(new_password, user=customer)
        except DjangoValidationError as e:
            return Response({"new_password": list(e.messages)}, status=400)
        # Reset password
        customer.set_password(new_password)
        customer.save()

        otp_obj.delete()

        return Response({"detail": "Password reset successful"}, status=200)
#growtag/shop popup viewset
# -----------------------------
# GET /api/growtags/<id>/
# -----------------------------
class GrowtagPopupViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only because you asked only for popup GET APIs.
    """
    queryset = Growtags.objects.all().order_by("-id")
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication, SessionAuthentication]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET"},
        "franchise": {"GET"},
        "othershop": {"GET"},
        "growtag": {"GET"},
        "customer": set(),
    }

    serializer_class = GrowtagPopupSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # Admin/staff -> all growtags
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # Growtag token -> only self
        if getattr(self.request, "growtag", None):
            return qs.filter(id=self.request.growtag.id)

        # Shop token -> only growtags mapped to this shop
        if getattr(self.request, "shop", None):
            growtag_ids = GrowTagAssignment.objects.filter(shop=self.request.shop)\
                .values_list("growtag_id", flat=True)
            return qs.filter(id__in=growtag_ids)

        return qs.none()


# -----------------------------
# GET /api/shops/<id>/
# -----------------------------
class ShopPopupViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Shop.objects.all().order_by("-id")
    authentication_classes = [UnifiedTokenAuthentication,JWTAuthentication, SessionAuthentication]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET"},
        "franchise": {"GET"},
        "othershop": {"GET"},
        "growtag": {"GET"},
        "customer": set(),
    }

    serializer_class = ShopPopupSerializer

    def get_queryset(self):
        qs = super().get_queryset()

        # Admin/staff -> all shops
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # Shop token -> only self shop
        if getattr(self.request, "shop", None):
            return qs.filter(id=self.request.shop.id)

        # Growtag token -> shops mapped to this growtag
        if getattr(self.request, "growtag", None):
            return qs.filter(growtag_assignments__growtag=self.request.growtag).distinct()

        return qs.none()
    
class PostalCodeViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [AllowAny]
    queryset = PostalCode.objects.all().order_by("country", "code")
    serializer_class = PostalCodeSerializer

    @action(detail=False, methods=["GET"], url_path="lookup")
    def lookup(self, request):
        code = (request.query_params.get("code") or "").strip()
        code = code.replace(" ", "") 
        country = (request.query_params.get("country") or "IN").strip().upper()

        if not code:
            return Response({"success": False, "message": "code is required", "data": None}, status=400)

        obj = PostalCode.objects.filter(country=country, code=code).first()
        if not obj:
            return Response({"success": False, "message": "Postal code not found", "data": None}, status=404)

        return Response({"success": True, "message": "OK", "data": PostalCodeSerializer(obj).data})
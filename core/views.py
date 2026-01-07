from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.db import IntegrityError
from django.conf import settings
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer,Lead
from .serializers import ShopSerializer, GrowtagsSerializer, ComplaintSerializer,GrowTagAssignmentSerializer,CustomerSerializer,LeadSerializer
from .serializers import  ShopViewSerializer, GrowtagViewSerializer
from .services import _ensure_complaint_coords,sync_complaint_to_customer
from .services import (
    geocode_address_pincode,
    nearest_lists_for_address,
    get_nearest_shop,
    get_nearest_growtag,
)
from zoho_integration.customer_sync import sync_core_customer_to_zoho_contact
from zoho_integration.zoho_books import ZohoBooksError
from django.db.models import Q
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated,AllowAny
from rest_framework.views import APIView
from django.utils import timezone
from django.shortcuts import get_object_or_404
from django.core.mail import send_mail
from django.contrib.auth import get_user_model

from core.permissions import IsCustomer
from core.authentication import CustomerTokenAuthentication
from core.serializers import CustomerRegisterSerializer, CustomerLoginSerializer, PublicComplaintSerializer
from core.models import CustomerAuthToken
from django.contrib.auth.hashers import check_password
User = get_user_model()

class CreatedByMixin:
    def perform_create(self, serializer):
        user = self.request.user if self.request.user.is_authenticated else None
        serializer.save(created_by=user)

class ShopViewSet(CreatedByMixin, viewsets.ModelViewSet):
    
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer
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
            lat, lon = lat_lon
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
        shop = serializer.save()

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


class GrowtagsViewSet(CreatedByMixin, viewsets.ModelViewSet):
    queryset = Growtags.objects.all()
    serializer_class = GrowtagsSerializer
    @action(detail=True, methods=["get"], url_path="view")
    def view_popup(self, request, pk=None):
        growtag = self.get_object()
        data = GrowtagViewSerializer(growtag).data
        return Response(data)

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        area = data.get("area", "")
        pincode = data.get("pincode", "")

        lat_lon = geocode_address_pincode(area, pincode)
        if lat_lon:
            lat, lon = lat_lon
            data["latitude"] = lat
            data["longitude"] = lon

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)
    def perform_create(self, serializer):
        growtag = serializer.save()

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
                    f"Phone: {growtag.phone or '-'}\n"
                    f"Adhar: {growtag.adhar or '-'}\n"
                    f"Area: {growtag.area or '-'}\n"
                    f"Pincode: {growtag.pincode}\n"
                    f"Status: {growtag.status}\n"
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

class CustomerViewSet(CreatedByMixin, viewsets.ModelViewSet):
    #queryset = Customer.objects.all().order_by("-created_at")
    queryset = Customer.objects.all().prefetch_related("complaints")  # ⚡ faster
    serializer_class = CustomerSerializer



class ComplaintViewSet(CreatedByMixin,viewsets.ModelViewSet):
    queryset = Complaint.objects.all().order_by("-created_at")
    serializer_class = ComplaintSerializer

    # ----------------- CREATE -----------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer_name = data.get("customer_name")
        customer_phone = data.get("customer_phone")
        email = data.get("email")
        password = data.get("password")
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
            if password and customer.password and customer.password != password:
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
                password=password,
                address=address,
                state=state,
                pincode=pincode,
                area=area,
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
                f"Customer ID: {complaint.id}\n"
                f"Customer Name: {complaint.customer_name}\n"
                f"Mobile No: {complaint.customer_phone}\n"
                f"Email: {complaint.email}\n"
                f"Password: {complaint.password or ''}\n"
                f"Phone Model: {complaint.phone_model}\n"
                f"Address: {complaint.address}\n"
                f"Address: {complaint.state}\n"
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
                if password and existing_customer.password != password:
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
                password=password,
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
                customer.password = password
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
                    customer.password = password
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
        pincode = request.query_params.get("pincode", "")
        assign_to = request.query_params.get("assign_to", "").lower()

        if not area or not pincode:
            return Response(
                {"error": "area and pincode required"},
                status=400
            )

        # call helper
        lists = nearest_lists_for_address(area, pincode)

        # return based on selection
        if assign_to == "franchise":
            return Response(lists["franchise"])

        if assign_to == "othershop":
            return Response(lists["othershop"])

        if assign_to == "growtag":
            return Response(lists["growtag"])

        # otherwise return all
        return Response(lists)   

      

class GrowTagAssignmentViewSet(CreatedByMixin, viewsets.ModelViewSet):
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
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        complaint = get_object_or_404(Complaint, pk=pk)

        # 🔐 ROLE CHECK
        if not (
            request.user.is_staff
            or hasattr(request.user, "shop")
            or hasattr(request.user, "growtag")
        ):
            return Response(
                {"error": "You are not allowed to confirm this complaint"},
                status=status.HTTP_403_FORBIDDEN,
            )

        # ⚠️ ALREADY CONFIRMED
        if complaint.confirm_status == "CONFIRMED":
            return Response(
                {"error": "Complaint already confirmed"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ✅ CONFIRM
        complaint.confirm_status = "CONFIRMED"
        complaint.confirmed_by = request.user
        complaint.confirmed_at = timezone.now()
        complaint.save(update_fields=[
            "confirm_status",
            "confirmed_by",
            "confirmed_at"
        ])

        return Response(
            {
                "message": "Complaint confirmed successfully",
                "confirm_status": complaint.confirm_status,
                "confirmed_at": complaint.confirmed_at,
                "confirmed_by": request.user.username,
            },
            status=status.HTTP_200_OK,
        )
    
#public customer
from django.db import transaction
from .models import Customer
from rest_framework.exceptions import ValidationError
class CustomerRegisterView(APIView):
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
    
class PublicComplaintViewSet(viewsets.ModelViewSet):
    serializer_class = PublicComplaintSerializer
    authentication_classes = [CustomerTokenAuthentication]
    permission_classes = [IsCustomer]
    
    def get_queryset(self):
        customer = getattr(self.request, "customer", None)
        if not customer:
            return Complaint.objects.none()

        # ✅ filtered by token customer id
        return Complaint.objects.filter(customer_id=customer.id).order_by("-created_at")
        #customer = self.request.user # Customer
        #return Complaint.objects.filter(customer=customer).order_by("-created_at")

    def perform_create(self, serializer):
        customer = getattr(self.request, "customer", None)
         # ✅ DEBUG (keep for 1 test, then remove)
        print("validated_data:", serializer.validated_data)
        print("address in validated_data:", serializer.validated_data.get("address"))

        #customer = self.request.user
        data = serializer.validated_data

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
class LeadViewSet(viewsets.ModelViewSet):
    queryset = Lead.objects.all().order_by("-created_at")
    serializer_class = LeadSerializer

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

        # ✅ Create/find customer by phone (recommended)
        customer, _ = Customer.objects.get_or_create(
            customer_phone=lead.customer_phone,
            defaults={
                "customer_name": lead.customer_name,
                "email": lead.email,
                "address": lead.address,
                "pincode": lead.pincode,
            }
        )

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

            assign_to=assign_to,
            assigned_shop=assigned_shop,
            assigned_Growtags=assigned_growtag,

            status="Assigned",  # since manually assigned now
        )

        # mark lead as converted
        lead.status = "CONVERTED"
        lead.save(update_fields=["status"])

        return Response(
            {"message": "Complaint created (manual assignment)", "complaint_id": complaint.id},
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
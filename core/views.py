from rest_framework import viewsets, status
from rest_framework.decorators import action, api_view
from rest_framework.response import Response
from django.db import IntegrityError
from django.conf import settings
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer
from .serializers import ShopSerializer, GrowtagsSerializer, ComplaintSerializer,GrowTagAssignmentSerializer,CustomerSerializer
from .services import _ensure_complaint_coords,sync_complaint_to_customer
from .services import (
    geocode_address_pincode,
    nearest_lists_for_address,
    get_nearest_shop,
    get_nearest_growtag,
)


from django.db.models import Q

from django.core.mail import send_mail

class ShopViewSet(viewsets.ModelViewSet):
    
    queryset = Shop.objects.all()
    serializer_class = ShopSerializer

    def create(self, request, *args, **kwargs):
        data = request.data.copy()
        area = data.get("area", "")
        pincode = data.get("pincode", "")

        lat_lon = geocode_address_pincode(area, pincode)
    
        if lat_lon is not None:
            lat, lon = lat_lon
            data["latitude"] = lat
            data["longitude"] = lon
        try:
            serializer = self.get_serializer(data=data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
        #return Response(serializer.data, status=status.HTTP_201_CREATED)
            return Response(
                {
                    "status": "success",
                    "message": "Shop created successfully",
                    "data": serializer.data,
                },
                status=status.HTTP_201_CREATED,
            )
        except IntegrityError as e:

            error_message=str(e).lower()
            
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


class GrowtagsViewSet(viewsets.ModelViewSet):
    queryset = Growtags.objects.all()
    serializer_class = GrowtagsSerializer

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

class CustomerViewSet(viewsets.ModelViewSet):
    #queryset = Customer.objects.all().order_by("-created_at")
    queryset = Customer.objects.all().prefetch_related("complaints")  # ⚡ faster
    serializer_class = CustomerSerializer



class ComplaintViewSet(viewsets.ModelViewSet):
    queryset = Complaint.objects.all().order_by("-created_at")
    serializer_class = ComplaintSerializer

    # ----------------- CREATE -----------------
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data


        customer_name   = data.get("customer_name")
        customer_phone  = data.get("customer_phone")
        email           = data.get("email")
        password        = data.get("password")
        phone_model     = data.get("phone_model")
        issue_details   = data.get("issue_details")
        address         = data.get("address")
        pincode         = data.get("pincode")
        assign_to       = data.get("assign_to")
        status_value    = data.get("status", "Pending")
        area            = data.get("area", "")   # ✅ define area
        
        # 3️⃣ Find existing customer by phone OR email
        lookup = Q()
        if customer_phone:
            lookup |= Q(customer_phone=customer_phone)
        if email:
            lookup |= Q(email=email)

        customer = None
        if lookup:
            customer = Customer.objects.filter(lookup).first()

        # 4️⃣ If customer already exists, check for conflicts (phone/email/name/password)
        if customer:
            conflict_messages = {}

            # 🔹 Phone is sent AND belongs to another existing customer
            if customer_phone and customer.customer_phone != customer_phone:
                conflict_messages["phone"] = "This phone number is already registered to another customer."

            # 🔹 Email is sent AND belongs to another existing customer
            if email and customer.email and customer.email != email:
                conflict_messages["email"] = "This email is already registered to another customer."

            # 🔹 Name mismatch (trying to use someone else’s account)
            if customer_name and customer.customer_name and customer.customer_name != customer_name:
                conflict_messages["customer_name"] = "Customer name does not match the existing account."

            # 🔹 Password mismatch (wrong user using same phone/email)
            if password and customer.password and customer.password != password:
                conflict_messages["password"] = "Password does not match the existing account."

            # ❌ If any conflicts exist → reject request
            if conflict_messages:
                return Response(conflict_messages, status=status.HTTP_400_BAD_REQUEST)
                

            # ✅ No conflict → reuse same customer as-is

        else:
            # 5️⃣ No existing customer → create a new one
            customer = Customer.objects.create(
                customer_name=customer_name,
                customer_phone=customer_phone,
                email=email,
                password=password,
                address=address,
                pincode=pincode,
            )

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
            pincode=pincode,
            area=area,
            assign_to=assign_to,
            status=status_value,
        )
        # Geocode via helper
        # 3️⃣ Ensure complaint has coordinates (centralized helper)
        _ensure_complaint_coords(complaint)    

        # 4️⃣ Auto-Assign Shop/GrowTag
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

        # ✅ Apply to complaint
        if assigned_shop:
            complaint.assigned_shop = assigned_shop
            complaint.status = "Assigned"

        if assigned_gt:
            complaint.assigned_Growtags = assigned_gt
            complaint.status = "Assigned"

        complaint.save()
         #  🔁 Sync COMPLAINT → CUSTOMER
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
        complaint= self.get_object()

        serializer = self.get_serializer(complaint, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        # 👇 did client send status in this request?
        status_in_request = "status" in serializer.validated_data
        # ====== 1️⃣ CUSTOMER LOGIC (SAME STYLE AS create()) ======

        # 🌟 For partial update: fall back to existing values on complaint
        customer_name   = data.get("customer_name", complaint.customer_name)
        customer_phone  = data.get("customer_phone", complaint.customer_phone)
        email           = data.get("email", complaint.email)
        password        = data.get("password", complaint.password)
        address         = data.get("address", complaint.address)
        pincode         = data.get("pincode", complaint.pincode)
        area            = data.get("area", complaint.area)

        # Currently linked customer (may be None)
        customer = complaint.customer
        # 🔍 Lookup existing customer by phone OR email
        #phone = serializer.validated_data.get("customer_phone")
        #email = serializer.validated_data.get("email")
        #existing_customer = None
        # 🔍 Build lookup by phone/email
        lookup = Q()
        if customer_phone:
            lookup |= Q(customer_phone=customer_phone)
        if email:
            lookup |= Q(email=email)

        existing_customer = None
        if lookup:
            existing_customer = Customer.objects.filter(lookup).first()
        
    # 🔗 If we found an existing customer, link the complaint to that customer
        if existing_customer:
            # ✅ There IS a customer with this phone/email
            conflict_messages = {}

            # These checks are same idea as in create()

            # 🔹 Phone conflict (trying to use some other customer's phone)
            if (
                customer_phone
                and existing_customer.customer_phone
                and existing_customer.customer_phone != customer_phone
            ):
                conflict_messages["phone"] = (
                    "This phone number is already registered to another customer."
                )

            # 🔹 Email conflict (trying to use some other customer's email)
            if (
                email
                and existing_customer.email
                and existing_customer.email != email
            ):
                conflict_messages["email"] = (
                    "This email is already registered to another customer."
                )

            # 🔹 Name mismatch (wrong name for this phone/email)
            if (
                customer_name
                and existing_customer.customer_name
                and existing_customer.customer_name != customer_name
            ):
                conflict_messages["customer_name"] = (
                    "Customer name does not match the existing account."
                )

            # 🔹 Password mismatch (wrong password for this phone/email)
            if (
                password
                and existing_customer.password
                and existing_customer.password != password
            ):
                conflict_messages["password"] = (
                    "Password does not match the existing account."
                )

            # ❌ If any conflicts → block update
            if conflict_messages:
                return Response(conflict_messages, status=status.HTTP_400_BAD_REQUEST)

            # ✅ No conflict → reuse the existing customer
            customer = existing_customer

        else:
            # ❌ No existing customer with this phone/email
            if customer is None:
                # There was no customer before → create new
                customer = Customer.objects.create(
                    customer_name=customer_name,
                    customer_phone=customer_phone,
                    email=email,
                    password=password,
                    address=address,
                    pincode=pincode,
                    area=area,
                )
            else:
                # Complaint already linked to a customer → update THAT customer
                # only if fields were sent in this request
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
                if "pincode" in data:
                    customer.pincode = pincode
                if "area" in data:
                    customer.area = area
                customer.save()

        # ====== 2️⃣ SAVE COMPLAINT WITH CORRECT CUSTOMER ======
        complaint = serializer.save(customer=customer)

        # Keep complaint fields in sync with customer table
        if customer:
            complaint.customer_name = customer.customer_name
            complaint.customer_phone = customer.customer_phone
            complaint.email = customer.email
            complaint.password = customer.password
            complaint.address = customer.address
            complaint.pincode = customer.pincode
            complaint.area = customer.area
            complaint.save(
                update_fields=[
                    "customer_name",
                    "customer_phone",
                    "email",
                    "password",
                    "address",
                    "pincode",
                    "area",
                ]
            )
          
        
         
        #complaint = serializer.save()
         # ✅ Ensure we have coordinates (frontend or geocode fallback)
        _ensure_complaint_coords(complaint)
        assign_to = serializer.validated_data.get("assign_to", complaint.assign_to)
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
            if not status_in_request: # 👈 only override IF client didn’t send status
              complaint.status = "Assigned"

        if assigned_gt:
            complaint.assigned_Growtags = assigned_gt
            if not status_in_request: # 👈 same here
              complaint.status = "Assigned"

        complaint.save()
        # 🔁 SYNC COMPLAINT → CUSTOMER (single helper, no duplicated code)
        sync_complaint_to_customer(complaint)
        return Response(self.get_serializer(complaint).data)

    # 🔹 PATCH handler (place this right after update)
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

      

class GrowTagAssignmentViewSet(viewsets.ModelViewSet):
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

        return Response(self.get_serializer(assignment).data, status=201)

    # Unassign Selected
    # DELETE /api/growtag-assignments/<id>/unassign/
    @action(detail=True, methods=["delete"], url_path="unassign")
    def unassign(self, request, pk=None):
        assignment = self.get_object()
        assignment.delete()
        return Response(status=204)

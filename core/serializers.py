from rest_framework import serializers
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer
from rest_framework.validators import UniqueValidator
from django.contrib.auth.hashers import make_password
from django.conf import settings
from core.models import Customer
from core.models import Complaint
from core.models import Lead
class ShopSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        required=False,
        allow_null=True,
        validators=[
            UniqueValidator(
                queryset=Shop.objects.all(),
                message="This email is already registered to another shop."
            )
        ]
    )

    phone = serializers.CharField(
        required=False,
        allow_null=True,
        validators=[
            UniqueValidator(
                queryset=Shop.objects.all(),
                message="This phone number is already registered to another shop."
            )
        ]
    )

    gst_pin = serializers.CharField(
        required=False,
        allow_null=True,
        validators=[
            UniqueValidator(
                queryset=Shop.objects.all(),
                message="This GST number is already registered to another shop."
            )
        ]
    )
    class Meta:
        model = Shop
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "created_on", "created_by")
    
    
class GrowtagsSerializer(serializers.ModelSerializer):
    grow_id = serializers.CharField(
          validators=[
            UniqueValidator(
                queryset=Growtags.objects.all(),
                message="This GrowTag ID is already in use."
            )
        ]
       )

    phone = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[
            UniqueValidator(
                queryset=Growtags.objects.all(),
                message="This phone number is already registered to another GrowTag."
            )
        ],
       )

    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=Growtags.objects.all(),
                message="This email is already registered to another GrowTag."
            )
        ]
       )

    adhar = serializers.CharField(
        required=False,
        allow_null=True,
        allow_blank=True,
        validators=[
            UniqueValidator(
                queryset=Growtags.objects.all(),
                message="This Aadhaar number is already registered to another GrowTag."
            )
        ],
    )

    class Meta:
        model = Growtags
        fields = "__all__"
        read_only_fields = ("created_at", "updated_at", "created_on", "created_by")
        
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        obj = super().create(validated_data)
        if password:
            obj.password = make_password(password)   # ✅ hash
            obj.save(update_fields=["password"])
        return obj

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        obj = super().update(instance, validated_data)
        if password:
            obj.password = make_password(password)   # ✅ hash
            obj.save(update_fields=["password"])
        return obj
class ComplaintHistorySerializer(serializers.ModelSerializer):
    """Lightweight complaint view for customer history."""

    class Meta:
        model = Complaint
        fields = [
            "id",
            "phone_model",
            "issue_details",
            "status",
            "assign_to",
            "created_at",
        ]


class CustomerSerializer(serializers.ModelSerializer):
    
    customer_phone = serializers.CharField(
    validators=[
        UniqueValidator(
            queryset=Customer.objects.all(),
            message="This phone number is already registered to another customer."
        )
    ]
)

    email = serializers.EmailField(
         required=False,
         allow_null=True,
         validators=[
          UniqueValidator(
            queryset=Customer.objects.all(),
            message="This email is already registered to another customer."
        )
       ]
     )
     # 🔹 All complaints linked to this customer (via Complaint.customer FK, related_name="complaints")
    complaints_history = ComplaintHistorySerializer(
        source="complaints",  # uses related_name="complaints"
        many=True,
        read_only=True,
    )

    # 🔹 NEW: include all complaints of this customer
    #complaints = ComplaintSerializer(many=True, read_only=True)  # uses related_name="complaints"

    class Meta:
        model = Customer
        fields = "__all__"           
        read_only_fields = ("created_at", "updated_at", "created_on", "created_by")
class CustomerBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "customer_name",
            "customer_phone",
            "email",
            "address",
            "state",  
            "pincode",
        ]


    
class ComplaintSerializer(serializers.ModelSerializer):
    ASSIGN_CHOICES = ["franchise", "othershop", "growtag"]

    assign_to = serializers.ChoiceField(
         choices=ASSIGN_CHOICES,
         required=True
        )

    # 🔹 Assigned shop / growtag as IDs (for write)
    assigned_shop = serializers.PrimaryKeyRelatedField(
        queryset=Shop.objects.all(), required=False, allow_null=True
    )
    assigned_Growtags = serializers.PrimaryKeyRelatedField(
        queryset=Growtags.objects.all(), required=False, allow_null=True
    )

    # 🔹 Convenience: show which entity it is assigned to (id + name)
    assigned_to_details = serializers.SerializerMethodField(read_only=True)
    
    # 🔹 Nested, read-only view of the linked customer (optional but very nice for frontend)
    #customer_details = CustomerSerializer(source="customer", read_only=True)
      # ✅ NEW: use basic customer without complaints_history
    customer_details = CustomerBasicSerializer(source="customer", read_only=True)
    # 🔒 We don’t want frontend to control this;
    #     it will always come from Customer table via view logic
    

    class Meta:
        model = Complaint
        fields = [
            "id",
            "customer",
            "customer_name",
            "customer_phone",
            "email",
            "password",
            "phone_model",
            "issue_details",
            "address",
            "state",  
            "pincode",
            "area",
            "assign_to",
            "latitude",
            "longitude",
            "status",
            "created_at",
            "assigned_shop",
            "assigned_Growtags",
            "assigned_to_details",
           "customer_details", 
            
        ]
        read_only_fields = (
            
            "created_at", "updated_at", "created_on", "created_by",
            "customer","confirm_status", "confirmed_by","confirmed_at",
        )
    
    def get_assigned_to_details(self, obj):
        # if complaint assigned to GrowTag
        if obj.assign_to == "growtag" and obj.assigned_Growtags:
            gt = obj.assigned_Growtags
            return {
                "type": "growtag",
                "id": gt.id,
                "name": getattr(gt, "name", None),
            }

        # if complaint assigned to a shop (franchise / othershop)
        if obj.assign_to in ["franchise", "othershop"] and obj.assigned_shop:
            shop = obj.assigned_shop
            return {
                "type": obj.assign_to,
                "id": shop.id,
                "name": getattr(shop, "shopname", None),
            }

        return None

class GrowTagAssignmentSerializer(serializers.ModelSerializer):
    grow_id = serializers.CharField(source="growtag.grow_id", read_only=True)
    name = serializers.CharField(source="growtag.name", read_only=True)
    shop_name = serializers.CharField(source="shop.shopname", read_only=True)
    shop_type = serializers.CharField(source="shop.shop_type", read_only=True)

    # inputs from two dropdowns
    franchise_shop_id = serializers.IntegerField(write_only=True, required=False)
    othershop_shop_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = GrowTagAssignment
        fields = [
            "id",
            "growtag",
            "shop",
            "grow_id",
            "name",
            "shop_name",
            "shop_type",
            "assigned_at",
            "franchise_shop_id",
            "othershop_shop_id",
        ]
        read_only_fields = ["shop", "assigned_at","created_at", "updated_at", "created_on", "created_by"]
        
    def validate(self, attrs):
        f_id = attrs.get("franchise_shop_id")
        o_id = attrs.get("othershop_shop_id")

        if not f_id and not o_id:
            raise serializers.ValidationError("Select either Franchise shop or Other Shop.")

        if f_id and o_id:
            raise serializers.ValidationError("Select only one shop type (not both).")

        return attrs
    def create(self, validated_data):
        # extract dropdown IDs
        f_id = validated_data.pop("franchise_shop_id", None)
        o_id = validated_data.pop("othershop_shop_id", None)

        # convert selected ID → actual shop object
        shop_id = f_id or o_id

        try:
            shop = Shop.objects.get(id=shop_id)
        except Shop.DoesNotExist:
            raise serializers.ValidationError({"shop": "Invalid shop selected. Please select a valid shop from the dropdown."})

        validated_data["shop"] = shop

        return GrowTagAssignment.objects.create(**validated_data)
    

       #assigned compliant view


class ComplaintMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Complaint
        fields = [
            "id",
            "customer_name",
            "customer_phone",
            "phone_model",
            "issue_details",
            "status",
            "created_at",
        ]


class ShopViewSerializer(serializers.ModelSerializer):
    assigned_complaints = serializers.SerializerMethodField()
    assigned_complaints_count = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            "id",
            "shop_type",
            "shopname",
            "owner",
            "email",
            "phone",
            "address",
            "area",
            "pincode",
            "gst_pin",
            "status",
            "latitude",
            "longitude",
            "assigned_complaints_count",
            "assigned_complaints",
        ]

    def get_assigned_complaints(self, obj):
        qs = Complaint.objects.filter(
            assigned_shop=obj,
            assign_to__in=["franchise", "othershop"],
        ).order_by("-created_at")
        return ComplaintMiniSerializer(qs, many=True).data

    def get_assigned_complaints_count(self, obj):
        return Complaint.objects.filter(
            assigned_shop=obj,
            assign_to__in=["franchise", "othershop"],
        ).count()


class GrowtagViewSerializer(serializers.ModelSerializer):
    assigned_complaints = serializers.SerializerMethodField()
    assigned_complaints_count = serializers.SerializerMethodField()

    class Meta:
        model = Growtags
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "address",
            "area",
            "pincode",
            "status",
            "assigned_complaints_count",
            "assigned_complaints",
        ]

    def get_assigned_complaints(self, obj):
        qs = Complaint.objects.filter(
            assigned_Growtags=obj,
            assign_to="growtag",
        ).order_by("-created_at")
        return ComplaintMiniSerializer(qs, many=True).data

    def get_assigned_complaints_count(self, obj):
        return Complaint.objects.filter(
            assigned_Growtags=obj,
            assign_to="growtag",
        ).count()
    
#public customer
class CustomerRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)
    confirm_password = serializers.CharField(write_only=True)

    class Meta:
        model = Customer
        fields = [
            "id",
            "customer_name",
            "customer_phone",
            "email",
            "password",
            "confirm_password",
        ]
    def validate(self, attrs):
        if attrs["password"] != attrs["confirm_password"]:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match"})
        return attrs
    def create(self, validated_data):
        validated_data.pop("confirm_password")
        raw_password = validated_data.pop("password")
        customer = Customer(**validated_data)
        customer.password = make_password(raw_password)  # ✅ hash
        customer.save()
        return customer


class CustomerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
class PublicComplaintSerializer(serializers.ModelSerializer):
    ASSIGN_CHOICES = [("franchise", "Franchise"), ("othershop", "Other Shop"), ("growtag", "GrowTag")]

    assign_to = serializers.ChoiceField(choices=ASSIGN_CHOICES, required=True)

    # ✅ screenshot fields
    email = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    #password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    address_line = serializers.CharField(source="address", required=True, allow_blank=False)   # uses Complaint.address
    pincode = serializers.CharField(required=True)
    area = serializers.CharField(required=True)
    state = serializers.CharField(required=True)

    # Optional if you have "Select Type" in UI
    #complaint_type = serializers.CharField(required=False, allow_blank=True)

    # ✅ UI shows "Assigned" (should be read-only details)
    assigned_to_details = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id",

            # UI: Customer Name / Mobile Number / Email / Password
            "customer_name",
            "customer_phone",
            "email",
            #"password",

            # UI: Phone Model
            "phone_model",

            # UI: Address Line / Pincode / Area / State
            "address_line",
            "pincode",
            "area",
            "state",

            # UI: Issue Details
            "issue_details",

            # UI: Assign To / Select Type
            "assign_to",
            #"complaint_type",

            # system
            "status",
            "created_at",
            "assigned_shop",
            "assigned_Growtags",
            "assigned_to_details",
        ]

        read_only_fields = [
            "id",
            "status",
            "created_at",
            "assigned_shop",
            "assigned_Growtags",
            "assigned_to_details",
        ]
    
    def validate(self, attrs):
        # normalize blanks -> None
        email = (attrs.get("email") or "").strip()
        if email == "":
            attrs["email"] = None

        pwd = (attrs.get("password") or "").strip()
        if pwd == "":
            attrs["password"] = None

        # required checks (to match UI)
        if not (attrs.get("customer_name") or "").strip():
            raise serializers.ValidationError({"customer_name": "Customer Name is required."})

        if not (attrs.get("customer_phone") or "").strip():
            raise serializers.ValidationError({"customer_phone": "Mobile Number is required."})

        if not (attrs.get("address", "") or "").strip():
            raise serializers.ValidationError({"address_line": "Address Line is required."})

        if not (attrs.get("pincode") or "").strip():
            raise serializers.ValidationError({"pincode": "Pincode is required."})

        if not (attrs.get("area") or "").strip():
            raise serializers.ValidationError({"area": "Area is required."})

        if not (attrs.get("state") or "").strip():
            raise serializers.ValidationError({"state": "State is required."})

        return attrs

    def get_assigned_to_details(self, obj):
        if obj.assign_to == "growtag" and obj.assigned_Growtags:
            gt = obj.assigned_Growtags
            return {"type": "growtag", "id": gt.id, "name": getattr(gt, "name", None)}

        if obj.assign_to in ["franchise", "othershop"] and obj.assigned_shop:
            shop = obj.assigned_shop
            return {"type": obj.assign_to, "id": shop.id, "name": getattr(shop, "shopname", None)}

        return None
#lead serializer
class LeadSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lead
        fields = "__all__"
        read_only_fields = ["id", "lead_code", "created_at", "updated_at"]
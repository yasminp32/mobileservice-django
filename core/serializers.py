from rest_framework import serializers
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer
from rest_framework.validators import UniqueValidator
from django.contrib.auth.hashers import make_password
from django.conf import settings
from core.models import Customer
from core.models import Complaint
from core.models import Lead
from .models import Vendor
from core.models import InventoryStock, StockLedger
from django.db import transaction
from .models import PurchaseOrder, PurchaseOrderItem,PurchaseBill, PurchaseBillItem, PurchaseBillPayment
from core.stock_service import add_stock, reverse_stock_for_ref
from core.audit import created_by_display
from .models import PostalCode

class ShopSerializer(serializers.ModelSerializer):
    #password = serializers.CharField(write_only=True,min_length=4)
    created_by_display = serializers.SerializerMethodField()
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
        read_only_fields = ("created_at", "updated_at", "created_on","created_by")
    def create(self, validated_data):
        raw_password = validated_data.pop("password")
        validated_data["password"] = make_password(raw_password)  # ✅ hash
        shop = super().create(validated_data)
        shop._raw_password = raw_password  # keep for response (not saved)
        return shop
    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", None)

        if raw_password:
            instance.password = make_password(raw_password)

        return super().update(instance, validated_data)
    def get_created_by_display(self, obj):
       return created_by_display(obj)

    
class GrowtagsSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
    password = serializers.CharField(
        required=False,
        allow_blank=False,
        min_length=4
    )

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
        read_only_fields = ("created_at", "updated_at", "created_on","created_by")

    def create(self, validated_data):
        raw_password = validated_data.pop("password", None)
        if raw_password:
            validated_data["password"] = make_password(raw_password)
        return super().create(validated_data)

    # ✅ UPDATE
    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", None)
        if raw_password:
            instance.password = make_password(raw_password)
        return super().update(instance, validated_data)
    def get_created_by_display(self, obj):
        return created_by_display(obj)
    
class ComplaintHistorySerializer(serializers.ModelSerializer):
    """Lightweight complaint view for customer history."""
    invoice_created = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    assigned_to_display = serializers.SerializerMethodField()
    class Meta:
        model = Complaint
        fields = [
            "id",
            "phone_model",
            "issue_details",
            "status",
            "assign_to",
            "created_at",
            "invoice_created",
            "invoice_id",
            "assigned_to_display",
        ]
    
    def get_invoice_created(self, obj):
        # OneToOneField => exists or not
        return hasattr(obj, "invoice")

    def get_invoice_id(self, obj):
        return obj.invoice.id if hasattr(obj, "invoice") else None
    def get_created_by(self, obj):
        # who created THIS complaint (admin/shop/growtag/customer)
        return created_by_display(obj)

    def get_assigned_to_display(self, obj):
        """
        Adjust field names here to match your Complaint model:
        - If you have obj.assigned_shop / obj.assigned_growtag use below.
        - If your fields are different, replace accordingly.
        """
        # ✅ if assigned to shop
        shop = getattr(obj, "assigned_shop", None) or getattr(obj, "shop", None)
        if shop:
            st = getattr(shop, "shop_type", None)
            st_name = getattr(st, "name", None) if st else None
            return {
                "assign_type": "shop",
                "shop_type": st_name,     # Franchise / Other Shop etc
                "id": shop.id,
                "name": getattr(shop, "shopname", None) or getattr(shop, "shop_name", None) or str(shop),
            }

        # ✅ if assigned to growtag
        growtag = getattr(obj, "assigned_growtag", None) or getattr(obj, "growtag", None)
        if growtag:
            return {
                "assign_type": "growtag",
                "id": growtag.id,
                "name": growtag.name,
            }

        return None

class CustomerSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
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
        read_only_fields = ("created_at", "updated_at", "created_on","created_by")
    def create(self, validated_data):
        raw_password = validated_data.pop("password", None)
        if raw_password:
            validated_data["password"] = make_password(raw_password)
        return super().create(validated_data)

    # ✅ UPDATE
    def update(self, instance, validated_data):
        raw_password = validated_data.pop("password", None)
        if raw_password:
            instance.password = make_password(raw_password)
        return super().update(instance, validated_data)
    def get_created_by_display(self, obj):
        return created_by_display(obj)
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
    invoice_created = serializers.SerializerMethodField() 
    invoice_id = serializers.IntegerField(source="invoice.id", read_only=True)    
    created_by_display = serializers.SerializerMethodField()
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
            "confirm_status", 
            "confirmed_by",
            "confirmed_at",
            "created_at",
            "assigned_shop",
            "assigned_Growtags",
            "assigned_to_details",
           "customer_details", 
           "created_by",
           "invoice_created",
           "invoice_id",
           "created_by_display", 
            
        ]
        read_only_fields = (
            
             "updated_at", "created_on", 
            "customer","created_by",
        )
    
    def get_invoice_created(self, obj):
        return hasattr(obj, "invoice")  # OneToOne: exists or not    
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
    def get_created_by_display(self, obj):
        return created_by_display(obj)
    def get_invoice_created(self, obj):
       return hasattr(obj, "invoice")


class GrowTagAssignmentSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
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
    def get_created_by_display(self, obj):
       return created_by_display(obj)

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
    #created_by_display = serializers.SerializerMethodField()
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
    #def get_created_by_display(self, obj):
        return created_by_display(obj)

class CustomerLoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField()
class PublicComplaintSerializer(serializers.ModelSerializer):
    #created_by_display = serializers.SerializerMethodField()
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
    #def get_created_by_display(self, obj):
        return created_by_display(obj)
#lead serializer
class LeadSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
    password = serializers.CharField(
        write_only=True,
        required=False,
        allow_null=True,
        allow_blank=True,
        min_length=4
    )
    class Meta:
        model = Lead
        fields = "__all__"
        read_only_fields = ["id", "lead_code", "created_at", "updated_at","assigned_shop","assigned_growtag ","created_by_customer"]
    def create(self, validated_data):
        password = validated_data.get("password")

        if password:
          validated_data["password"] = make_password(password)

        return super().create(validated_data)
    def update(self, instance, validated_data):
        password = validated_data.get("password")

        if password:
            validated_data["password"] = make_password(password)

        return super().update(instance, validated_data)
    def get_created_by_display(self, obj):
        return created_by_display(obj)
#vendor

class VendorSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
    class Meta:
        model = Vendor
        fields = ["id", "name", "email", "phone", "address", "website", "status", "created_at"]
        read_only_fields = ["id", "created_at","shop"]

    def validate(self, data):
        # For CREATE: enforce required fields (like popup required labels)
        if self.instance is None:
            required_fields = ["name", "email", "phone", "address"]
            for field in required_fields:
                if not data.get(field):
                    raise serializers.ValidationError({field: "This field is required"})
        return data
    def get_created_by_display(self, obj):
         return created_by_display(obj)
    
    
#puchase order

from .utils import generate_po_number, recompute_purchase_order_totals
class VendorMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vendor
        fields = ["id", "name", "email", "phone", "address"]


class PurchaseOrderItemSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_name_master = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = PurchaseOrderItem
        fields = [
            "id",
            "item",          # (optional) pk input/update
            "item_id", 
            "item_name_master", 
            "item_name",
            "description",
            "qty",
            "unit_price",
            "tax_percent",
            "discount_percent",
            "line_subtotal",
            "discount_amount",
            "tax_amount",
            "line_total",
        ]
        read_only_fields = [
            "purchase_order","line_subtotal", "discount_amount", "tax_amount", "line_total","item_name_master",
        ]
    def validate(self, attrs):
        # basic numeric validation (optional)
        qty = attrs.get("qty", None)
        unit_price = attrs.get("unit_price", None)
        if qty is not None and qty <= 0:
            raise serializers.ValidationError({"qty": "qty must be > 0"})
        if unit_price is not None and unit_price < 0:
            raise serializers.ValidationError({"unit_price": "unit_price must be >= 0"})
        return attrs
    def get_created_by_display(self, obj):
        return created_by_display(obj)


class PurchaseOrderSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    vendor_details = VendorMiniSerializer(source="vendor", read_only=True)
    items = PurchaseOrderItemSerializer(many=True)

    class Meta:
        model = PurchaseOrder
        fields = "__all__"
        read_only_fields = ["po_number", "subtotal", "total_discount", "total_tax", "grand_total"]

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items")
        validated_data["po_number"] = generate_po_number()

        po = PurchaseOrder.objects.create(**validated_data)

        for item in items_data:
            PurchaseOrderItem.objects.create(purchase_order=po, **item)

        recompute_purchase_order_totals(po)
        po.refresh_from_db()   # 🔹 recommended

        return po
    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        old_status = instance.status
        new_status = validated_data.get("status", instance.status)

        # 🚫 Block item edits when PO is OPEN
        if (
            old_status == "OPEN"
            and new_status == "OPEN"
            and items_data is not None
        ):
            raise serializers.ValidationError(
                "Cannot edit items when Purchase Order is OPEN. "
                "Cancel and recreate or move to DRAFT."
            )


        # update PO fields
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        # replace items if provided
        if items_data is not None:
            instance.items.all().delete()
            for item in items_data:
                PurchaseOrderItem.objects.create(purchase_order=instance, **item)

        recompute_purchase_order_totals(instance)
        instance.refresh_from_db()
        return instance
    def get_created_by_display(self, obj):
        return created_by_display(obj)

class PurchaseOrderListSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = [
            "id",
            "po_number",
            "vendor_name",
            "po_date",
            "expected_delivery_date",
            "status",
            "grand_total",
        ]
    def get_created_by_display(self, obj):
        return created_by_display(obj)

#bills
class PurchaseBillItemSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    item_id = serializers.IntegerField(source="item.id", read_only=True)
    item_name_master = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = PurchaseBillItem
        fields = [
            "id", "item", "item_id",     # ✅ LocalItem id
            "item_name_master","name", "description", "account",
            "qty", "rate", "tax_percent", "discount_percent",
            "line_subtotal", "discount_amount", "tax_amount", "amount"
        ]
        read_only_fields = ["line_subtotal", "discount_amount", "tax_amount", "amount","item_id", "item_name_master",]
    def get_created_by_display(self, obj):
        return created_by_display(obj)


class PurchaseBillPaymentSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseBillPayment
        fields = ["id", "payment_date", "amount", "method", "reference", "created_at"]
        read_only_fields = ["created_at"]
    def get_created_by_display(self, obj):
        return created_by_display(obj)


class PurchaseBillListSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseBill
        fields = [
            "id", "bill_number", "vendor_name", "bill_date", "due_date",
            "status", "payment_status",
            "amount_paid", "total", "balance_due",
            "created_at"
        ]


class PurchaseBillCreateUpdateSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    items = PurchaseBillItemSerializer(many=True)
    payments = PurchaseBillPaymentSerializer(many=True, required=False)

    class Meta:
        model = PurchaseBill
        fields = [
            "id",
            "owner_type", "shop", "growtag",
            "shop",
            "vendor",
            "bill_number",
            "order_number",
            "bill_date",
            "due_date",
            "status",
            "payment_status",
           # "payment_terms",

            "vendor_name", "vendor_email", "vendor_phone", "vendor_gstin", "vendor_address",

            "ship_to", "bill_to",

            "tds_percent", "shipping_charges", "adjustment",

            "subtotal", "total_discount", "total_tax", "tds_amount",
            "total", "amount_paid", "balance_due",

            "notes", "terms_and_conditions",
            "items", "payments",
            "created_at"
        ]
        read_only_fields = [
            "vendor_name","vendor_email","vendor_phone","vendor_gstin","vendor_address",
            "subtotal","total_discount","total_tax","tds_amount","total","amount_paid","balance_due",
            "created_at"
        ]

    def validate(self, attrs):
        """
        ✅ Ensure owner rules:
        - owner_type=shop => shop required, growtag must be null
        - owner_type=growtag => growtag required, shop must be null
        """
        owner_type = attrs.get("owner_type") or getattr(self.instance, "owner_type", None)
        shop = attrs.get("shop") if "shop" in attrs else getattr(self.instance, "shop", None)
        growtag = attrs.get("growtag") if "growtag" in attrs else getattr(self.instance, "growtag", None)

        if owner_type == "shop":
            if not shop or growtag:
                raise serializers.ValidationError("owner_type='shop' requires shop and growtag must be null.")
        elif owner_type == "growtag":
            if not growtag or shop:
                raise serializers.ValidationError("owner_type='growtag' requires growtag and shop must be null.")
        else:
            raise serializers.ValidationError("owner_type must be 'shop' or 'growtag'.")

        return attrs

    @transaction.atomic
    def create(self, validated_data):
        items_data = validated_data.pop("items", [])
        payments_data = validated_data.pop("payments", [])

        bill = PurchaseBill.objects.create(**validated_data)

        for it in items_data:
            PurchaseBillItem.objects.create(bill=bill, **it)

        for p in payments_data:
            PurchaseBillPayment.objects.create(bill=bill, **p)

        bill.recalc_totals()

        # ✅ Add stock only if bill is OPEN
        if bill.status == "OPEN":
            self._apply_stock_increase(bill)

        return bill

    @transaction.atomic
    def update(self, instance, validated_data):
        items_data = validated_data.pop("items", None)
        payments_data = validated_data.pop("payments", None)

        old_status = instance.status

        # update main fields
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()

        # update items
        if items_data is not None:
            instance.items.all().delete()
            for it in items_data:
                PurchaseBillItem.objects.create(bill=instance, **it)

        # update payments
        if payments_data is not None:
            #instance.payments.all().delete()
            for p in payments_data:
                PurchaseBillPayment.objects.create(bill=instance, **p)

        instance.recalc_totals()

        # ✅ Apply stock when status changes DRAFT -> OPEN
        if old_status != "OPEN" and instance.status == "OPEN":
            self._apply_stock_increase(instance)

        # ✅ Optional: reverse stock when OPEN -> CANCELLED
        # (Only enable if you want cancellation to rollback stock)
        if old_status == "OPEN" and instance.status == "CANCELLED":
            reverse_stock_for_ref(
                shop=instance.shop if instance.shop_id else None,           # ✅ CHANGED
                growtag=instance.growtag if instance.growtag_id else None,  # ✅ CHANGED
                ref_type="PURCHASE_BILL",
                ref_id=instance.id,
            )

        return instance

    def _apply_stock_increase(self, bill: PurchaseBill):
        shop = bill.shop if bill.shop_id else None
        growtag = bill.growtag if bill.growtag_id else None
        if bool(shop) == bool(growtag):
           raise serializers.ValidationError("Invalid bill owner: set either shop OR growtag.")

        for it in bill.items.all():
            if not it.item_id:
                continue  # skip non-linked items if allowed

            add_stock(
                shop=shop,                 # ✅ CHANGED
                growtag=growtag, 
                item=it.item,
                qty=it.qty,
                ref_type="PURCHASE_BILL",
                ref_id=bill.id,
                note=f"Stock added from PurchaseBill {bill.bill_number}",
            )

    def get_created_by_display(self, obj):
        return created_by_display(obj)

#stock
class InventoryStockSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    item_name = serializers.CharField(source="item.name", read_only=True)
    item_sku = serializers.CharField(source="item.sku", read_only=True)

    shop_name = serializers.CharField(source="shop.shopname", read_only=True)
    shop_type = serializers.CharField(source="shop.shop_type", read_only=True)

    growtag_name = serializers.CharField(source="growtag.name", read_only=True)
    growtag_status = serializers.CharField(source="growtag.status", read_only=True)

    class Meta:
        model = InventoryStock
        fields = [
            "id",
            "owner_type",

            "shop", "shop_name", "shop_type",
            "growtag", "growtag_name", "growtag_status",

            "item", "item_name", "item_sku",
            "qty_on_hand",
            "reorder_level",
            "updated_at",
        ]
        read_only_fields = ["qty_on_hand", "updated_at"]
    def get_created_by_display(self, obj):
        return created_by_display(obj)


class StockLedgerSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()

    item_name = serializers.CharField(source="item.name", read_only=True)
    item_sku = serializers.CharField(source="item.sku", read_only=True)

    class Meta:
        model = StockLedger
        fields = [
            "id",
            "owner_type",
            "shop",
            "growtag",
            "item",
            "item_name",
            "item_sku",
            "qty_change",
            "balance_after",
            "ref_type",
            "ref_id",
            "note",
            "created_at",
        ]
    def get_created_by_display(self, obj):
        return created_by_display(obj)

# To view growtag and shop popup

# -----------------------------
# Complaint card (for popups)
# -----------------------------
class PopupComplaintSerializer(serializers.ModelSerializer):
    created_by_display = serializers.SerializerMethodField()
    complaint_id = serializers.SerializerMethodField()
    title = serializers.SerializerMethodField()
    created_on = serializers.SerializerMethodField()
    created_at_time = serializers.SerializerMethodField()
    updated_at_time = serializers.SerializerMethodField()

    class Meta:
        model = Complaint
        fields = [
            "id",
            "complaint_id",
            "title",
            "area",
            "pincode",
            "status",
            "confirm_status",
            "assign_to",
            "created_on",
            "created_at_time",
            "updated_at_time",
        ]

    def get_complaint_id(self, obj):
        return f"COMP{obj.id:03d}"  # COMP001 format

    def get_title(self, obj):
        return (obj.issue_details or "N/A")[:60]

    def get_created_on(self, obj):
        return obj.created_at.strftime("%d/%m/%Y") if getattr(obj, "created_at", None) else None

    def get_created_at_time(self, obj):
        return obj.created_at.strftime("%d/%m/%Y, %H:%M:%S") if getattr(obj, "created_at", None) else None

    def get_updated_at_time(self, obj):
        return obj.updated_at.strftime("%d/%m/%Y, %H:%M:%S") if getattr(obj, "updated_at", None) else None


# -----------------------------
# Mini shop (inside growtag popup)
# -----------------------------
class ShopMiniSerializer(serializers.ModelSerializer):
    shop_type_display = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            "id",
            "shop_type",
            "shop_type_display",
            "shopname",
            "phone",
            "email",
            "owner",
            "area",
            "pincode",
            "address",
            "state",
            "gst_pin",
            "status",
            "latitude",
            "longitude",
        ]

    def get_shop_type_display(self, obj):
        return dict(Shop.SHOP_TYPE_CHOICES).get(obj.shop_type, obj.shop_type)


# -----------------------------
# Mini growtag (inside shop popup)
# -----------------------------
class GrowtagMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Growtags
        fields = [
            "id",
            "grow_id",
            "name",
            "phone",
            "email",
            "area",
            "pincode",
            "status",
            "image",
            "latitude",
            "longitude",
        ]


# -----------------------------
# Growtag popup serializer
# GET /api/growtags/<id>/
# -----------------------------
class GrowtagPopupSerializer(serializers.ModelSerializer):
    assigned_shop = serializers.SerializerMethodField()
    assigned_complaints_count = serializers.SerializerMethodField()
    assigned_complaints = serializers.SerializerMethodField()

    class Meta:
        model = Growtags
        fields = [
            "id",
            "grow_id",
            "name",
            "phone",
            "email",
            "address",
            "state",
            "pincode",
            "area",
            "latitude",
            "longitude",
            "adhar",
            "status",
            "image",
            "assigned_shop",
            "assigned_complaints_count",
            "assigned_complaints",
        ]

    def get_assigned_shop(self, obj):
        # related_name="assignment" (OneToOne)
        assignment = getattr(obj, "assignment", None)
        if not assignment:
            return None
        return ShopMiniSerializer(assignment.shop).data

    def get_assigned_complaints_count(self, obj):
        return Complaint.objects.filter(assigned_Growtags=obj).count()

    def get_assigned_complaints(self, obj):
        qs = Complaint.objects.filter(assigned_Growtags=obj).order_by("-id")[:50]
        return PopupComplaintSerializer(qs, many=True).data


# -----------------------------
# Shop popup serializer
# GET /api/shops/<id>/
# -----------------------------
class ShopPopupSerializer(serializers.ModelSerializer):
    shop_type_display = serializers.SerializerMethodField()

    assigned_growtags_count = serializers.SerializerMethodField()
    assigned_growtags = serializers.SerializerMethodField()

    assigned_complaints_count = serializers.SerializerMethodField()
    assigned_complaints = serializers.SerializerMethodField()

    class Meta:
        model = Shop
        fields = [
            "id",
            "shop_type",
            "shop_type_display",
            "shopname",
            "phone",
            "email",
            "owner",
            "area",
            "pincode",
            "address",
            "state",
            "gst_pin",
            "status",
            "latitude",
            "longitude",
            "assigned_growtags_count",
            "assigned_growtags",
            "assigned_complaints_count",
            "assigned_complaints",
        ]

    def get_shop_type_display(self, obj):
        return dict(Shop.SHOP_TYPE_CHOICES).get(obj.shop_type, obj.shop_type)

    def get_assigned_growtags_count(self, obj):
        return GrowTagAssignment.objects.filter(shop=obj).count()

    def get_assigned_growtags(self, obj):
        qs = GrowTagAssignment.objects.filter(shop=obj).select_related("growtag").order_by("-id")[:50]
        growtags = [x.growtag for x in qs]
        return GrowtagMiniSerializer(growtags, many=True).data

    def get_assigned_complaints_count(self, obj):
        return Complaint.objects.filter(assigned_shop=obj).count()

    def get_assigned_complaints(self, obj):
        qs = Complaint.objects.filter(assigned_shop=obj).order_by("-id")[:50]
        return PopupComplaintSerializer(qs, many=True).data
    
class PostalCodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PostalCode
        fields = ["id", "country", "code", "city","district", "state"]


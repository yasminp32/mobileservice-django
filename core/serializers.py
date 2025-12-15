from rest_framework import serializers
from .models import Shop, Growtags, Complaint,GrowTagAssignment,Customer
from rest_framework.validators import UniqueValidator
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

class CustomerBasicSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = [
            "id",
            "customer_name",
            "customer_phone",
            "email",
            "address",
            "pincode",
        ]


    
class ComplaintSerializer(serializers.ModelSerializer):
    
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
            
            "created_at",
            "customer",
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
        read_only_fields = ["shop", "assigned_at"]
        
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
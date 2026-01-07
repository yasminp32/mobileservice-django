from rest_framework import serializers
from decimal import Decimal
from .models import LocalInvoice, LocalInvoiceLine, LocalCustomer, LocalItem
class LocalItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalItem
        fields = "__all__"
        read_only_fields = ("zoho_item_id", "sync_status", "created_at","created_on","created_by","updated_at")
    def validate(self, attrs):
        # If not sellable → force selling_price = 0
        if attrs.get("is_sellable") is False:
            attrs["selling_price"] = 0

        # If not purchasable → force cost_price = 0
        if attrs.get("is_purchasable") is False:
            attrs["cost_price"] = 0

        return attrs
    
    #invoice

from rest_framework import serializers
from django.db import transaction
from .models import LocalInvoice, LocalInvoiceLine, LocalItem


class LocalInvoiceLineReadSerializer(serializers.ModelSerializer):
    item_name = serializers.CharField(source="item.name", read_only=True)

    class Meta:
        model = LocalInvoiceLine
        fields = [
            "id",
            "item",
            "item_name",
            "qty",
            "rate",
            "description",
            "service_charge_type",
            "service_charge_value",
            "gst_treatment",
            "line_amount",
            "service_charge_amount",
            "taxable_amount",
            "line_tax",
            "line_total",
            "created_at",
            "created_on",
            "created_by",
            "updated_at",
            
        ]


class LocalInvoiceLineWriteSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default="1.00")
    rate = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, default="0.00")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    service_charge_type = serializers.ChoiceField(
        choices=LocalInvoiceLine.SERVICE_CHARGE_TYPE_CHOICES, required=False
    )
    service_charge_value = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, default="0.00"
    )

    gst_treatment = serializers.ChoiceField(
        choices=LocalInvoiceLine.GST_CHOICES, required=False
    )


class LocalInvoiceReadSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    lines = LocalInvoiceLineReadSerializer(many=True, read_only=True)
    assigned_growtag = serializers.IntegerField(source="assigned_growtag_id", read_only=True)
    assigned_shop = serializers.IntegerField(source="assigned_shop_id", read_only=True)
    assigned_shop_type = serializers.CharField(source="assigned_shop.shop_type", read_only=True)
    assigned_shop_name = serializers.CharField(source="assigned_shop.shopname", read_only=True)
    growtag_name = serializers.CharField(source="assigned_growtag.name", read_only=True)

    class Meta:
        model = LocalInvoice
        fields = [
            "id",
            "customer",
            "customer_name",
            "invoice_number",
            "status",
            "invoice_date",
            "due_date",
            "apply_gst_to_all_items",

            "sub_total",
            "service_charge_total",
            "discount_type",
            "discount_value",
            "discount_amount",
            "taxable_amount",
            "gst_breakdown",
            "grand_total",
            "terms_conditions",
             "assigned_growtag",
             "growtag_name",
             "assigned_shop",
             "assigned_shop_name",
             "assigned_shop_type",

            "zoho_invoice_id",
            "sync_status",
            "last_error",
            "created_at",
            "created_on",
            "created_by",
            "updated_at",
            "lines",
        ]


class LocalInvoiceWriteSerializer(serializers.ModelSerializer):
    # 👇 list of line items (POST/PUT/PATCH in JSON "Raw data")
    lines_payload = LocalInvoiceLineWriteSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = LocalInvoice
        fields = [
            "customer",
            "assigned_growtag",   
            "assigned_shop",      
            "status",
            "invoice_date",
            "due_date",
            "apply_gst_to_all_items",
            "terms_conditions", 
            "discount_type",
            "discount_value",
            "lines_payload",
        ]
    def validate(self, attrs):
        # ✅ If frontend sends discount_value but forgets discount_type,
        # treat it as AMOUNT (₹) instead of default PERCENT
        if "discount_value" in attrs and "discount_type" not in attrs:
            attrs["discount_type"] = "AMOUNT"

        # Safety checks
        dt = attrs.get("discount_type")
        dv = Decimal(attrs.get("discount_value") or 0)

        if dt == "PERCENT" and (dv < 0 or dv > 100):
            raise serializers.ValidationError({"discount_value": "Percent must be 0..100"})
        if dt == "AMOUNT" and dv < 0:
            raise serializers.ValidationError({"discount_value": "Amount cannot be negative"})

        return attrs
    def validate_lines_payload(self, lines):
        if not lines:
            return lines

        item_ids = [x["item_id"] for x in lines]
        existing = set(LocalItem.objects.filter(id__in=item_ids).values_list("id", flat=True))
        missing = [i for i in item_ids if i not in existing]
        if missing:
            raise serializers.ValidationError(f"Invalid item_id(s): {missing}")
        return lines

from rest_framework import serializers
from decimal import Decimal
from .models import LocalInvoice, LocalInvoiceLine, LocalCustomer, LocalItem
from django.urls import reverse
class LocalItemSerializer(serializers.ModelSerializer):
    status = serializers.BooleanField(source="is_active",read_only=True)
    class Meta:
        model = LocalItem
        fields = "__all__"
        read_only_fields = ("zoho_item_id", "sync_status",  "created_at","created_on","created_by","updated_at")
    
    #invoice


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
            #"created_on",
            #"created_by",
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
    created_by_display = serializers.SerializerMethodField()
    pdf_url = serializers.SerializerMethodField()
    def get_created_by_display(self, obj):
        # admin
        if obj.created_by_id:
           u = obj.created_by
           return {"type": "admin", "id": u.id, "name": getattr(u, "username", str(u))}

        # shop
        if obj.created_by_shop_id:
           s = obj.created_by_shop
           return {"type": "shop", "id": s.id, "name": getattr(s, "shopname", ""), "shop_type": getattr(s, "shop_type", None)}

        # growtag
        if obj.created_by_growtag_id:
           g = obj.created_by_growtag
           return {"type": "growtag", "id": g.id, "name": getattr(g, "name", "")}

        # customer
        if obj.created_by_customer_id:
           c = obj.created_by_customer
           return {"type": "customer", "id": c.id, "name": getattr(c, "name", "")}

        return None
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
            #"created_on",
            #"created_by",
            "updated_at",
            "lines",
            "created_by_display",
            "pdf_url", 
           
        ]
    def get_pdf_url(self, obj):
        request = self.context.get("request")
        url = reverse("invoice-pdf", kwargs={"pk": obj.pk})
        return request.build_absolute_uri(url) if request else url

class LocalInvoiceWriteSerializer(serializers.ModelSerializer):
    # 👇 list of line items (POST/PUT/PATCH in JSON "Raw data")
    lines_payload = LocalInvoiceLineWriteSerializer(many=True, write_only=True, required=False)

    class Meta:
        model = LocalInvoice
        fields = [
            "customer",
            "complaint",
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
        # ✅ NEW: invoice must be for shop OR growtag (not both)
        # ✅ owner mandatory always
        shop = attrs.get("assigned_shop") if "assigned_shop" in attrs else getattr(self.instance, "assigned_shop", None)
        growtag = attrs.get("assigned_growtag") if "assigned_growtag" in attrs else getattr(self.instance, "assigned_growtag", None)

        if shop and growtag:
            raise serializers.ValidationError("Invoice cannot be assigned to both shop and growtag.")
        if not shop and not growtag:
            raise serializers.ValidationError("Invoice must be assigned to either shop or growtag.")

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
    

    def _upsert_lines(self, invoice, lines_payload):
        """
        Creates invoice lines from payload.
        (Simple version: always create new lines)
        """
        if not lines_payload:
            return

        for row in lines_payload:
            LocalInvoiceLine.objects.create(
                invoice=invoice,
                item_id=row["item_id"],
                qty=row.get("qty", Decimal("1.00")),
                rate=row.get("rate", Decimal("0.00")),
                description=row.get("description", ""),
                service_charge_type=row.get("service_charge_type", "AMOUNT"),
                service_charge_value=row.get("service_charge_value", Decimal("0.00")),
                gst_treatment=row.get("gst_treatment", "NO_TAX"),
            )

    
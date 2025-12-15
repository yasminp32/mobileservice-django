
# zoho_integration/admin.py
from django.contrib import admin
from .models import LocalItem


@admin.register(LocalItem)
class LocalZohoItemAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "product_type",
        "selling_price",
        "cost_price",
        "sales_account",
        "purchase_account",
        "zoho_item_id",
        "created_at",
    )
    search_fields = ("name", "zoho_item_id")

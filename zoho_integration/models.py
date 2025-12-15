from django.db import models

class LocalItem(models.Model):
    # Basic fields
    product_type = models.CharField(
        max_length=20,
        choices=[("goods", "Goods"), ("service", "Service")],
        default="goods"
    )

    name = models.CharField(max_length=150)
    sku = models.CharField(
        max_length=100,
        unique=True,
        blank=True,
        null=True,
        help_text="Unique Stock Keeping Unit"
    )
    UNIT_CHOICES = [
        ("PIECE", "PIECE"),
        ("BOX", "BOX"),
        ("SET", "SET"),
        ("UNIT", "UNIT"),
    ]

    unit = models.CharField(
        max_length=20,
        choices=UNIT_CHOICES,
        default="PIECE"
    )
    TAX_PREFERENCE_CHOICES = [
        ("taxable", "Taxable"),
        ("non_taxable", "Non-Taxable"),
    ]
    tax_preference = models.CharField(
        max_length=20,
        choices=TAX_PREFERENCE_CHOICES,
        default="taxable"
    )
    
    hsn_or_sac = models.CharField(max_length=30, blank=True, default="")
    item_image = models.ImageField(upload_to="zoho_items/", null=True, blank=True)

    # Sales
    is_sellable = models.BooleanField(default=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    SALES_ACCOUNT_CHOICES = [
        ("sales", "Sales"),
        ("service_income", "Service Income"),
        ("cogs", "Cost of Goods Sold"),
        ("other_income", "Other Income"),
    ]
    sales_account = models.CharField(
        max_length=50,
        choices=SALES_ACCOUNT_CHOICES,
        default="sales",
        blank=True
    )
    sales_description = models.TextField(blank=True, default="")

    # Purchase
    is_purchasable = models.BooleanField(default=False)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    PURCHASE_ACCOUNT_CHOICES = [
        ("sales", "Sales"),
        ("service_income", "Service Income"),
        ("cogs", "Cost of Goods Sold"),
        ("other_income", "Other Income"),
        
        #("expenses", "Expenses"),  # if you add ZOHO_EXPENSES_ACCOUNT_ID
    ]
    purchase_account = models.CharField(        # ✅ Purchase Account dropdown
        max_length=50,
        choices=PURCHASE_ACCOUNT_CHOICES,
        default="cogs",
        blank=True
    )
    VENDOR_CHOICES = [
        ("", "None"),
        ("vendor_a_id", "Vendor A (Mobile Wholesaler)"),
        ("vendor_b_id", "Vendor B (Component Supplier)"),
    ]
    preferred_vendor = models.CharField(        # ✅ Vendor dropdown
        max_length=50,
        choices=VENDOR_CHOICES,
        default="",
        blank=True
    )
    purchase_description = models.TextField(blank=True, default="")

    # Zoho sync
    zoho_item_id = models.CharField(max_length=100, blank=True, null=True)
    sync_status = models.CharField(max_length=20, default="PENDING")  # PENDING/SYNCED/FAILED
 
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
from django.db import models
from django.conf import settings
from django.db.models import Max
from django.db import transaction
from core.models import Growtags, Shop


class AuditFields(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)   # datetime created
    updated_at = models.DateTimeField(auto_now=True)       # datetime updated

    created_on = models.DateField(null=True, blank=True)   # optional date-only
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created"
    )

    class Meta:
        abstract = True
class LocalItem(AuditFields):
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
    
    GST_TREATMENT_CHOICES = [
        ("NO_TAX", "No Tax (0%)"),
        ("IGST_5", "5% IGST"),
        ("IGST_12", "12% IGST"),
        ("IGST_18", "18% IGST"),
        ("IGST_28", "28% IGST"),
        ("GST_5", "5% GST (2.5% CGST + 2.5% SGST)"),
        ("GST_12", "12% GST (6% CGST + 6% SGST)"),
        ("GST_18", "18% GST (9% CGST + 9% SGST)"),
        ("GST_28", "28% GST (14% CGST + 14% SGST)"),
    ]

    gst_treatment = models.CharField(
        max_length=20,
        choices=GST_TREATMENT_CHOICES,
        default="NO_TAX",
        blank=True,
    )
    hsn_or_sac = models.CharField(max_length=30, blank=True, default="")
    item_image = models.ImageField(upload_to="zoho_items/", null=True, blank=True)

    # Sales
    is_sellable = models.BooleanField(default=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge = models.DecimalField(max_digits=12,decimal_places=2,default=0)

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
 
# =========================
# CUSTOMER (already exists)
# =========================
class LocalCustomer(AuditFields):
    name = models.CharField(max_length=150)

    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, default="")
    state = models.CharField(max_length=60,null=True,blank=True)
    # Zoho reference
    zoho_contact_id = models.CharField(max_length=80,blank=True,default="",help_text="Zoho Books contact_id")
    # ✅ Sync tracking (add)
    sync_status = models.CharField(max_length=20, default="PENDING")  # PENDING/SYNCED/FAILED
    last_error = models.TextField(blank=True, default="")
    
    def __str__(self):
        return f"{self.name} - {self.state}"

    # =========================
    # INVOICE
    # =========================
class LocalInvoice(AuditFields):
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PAID", "Paid"),
        ("PARTIALLY_PAID",  "Partially Paid"),
    ]

    GST_APPLY_CHOICES = [
        ("NO_TAX", "No Tax (0%)"),

        ("GST_5", "5% GST (2.5% CGST + 2.5% SGST)"),
        ("GST_12", "12% GST (6% CGST + 6% SGST)"),
        ("GST_18", "18% GST (9% CGST + 9% SGST)"),
        ("GST_28", "28% GST (14% CGST + 14% SGST)"),

        ("IGST_5", "5% IGST"),
        ("IGST_12", "12% IGST"),
        ("IGST_18", "18% IGST"),
        ("IGST_28", "28% IGST"),
    ]

    customer = models.ForeignKey(LocalCustomer, on_delete=models.PROTECT)
    invoice_number = models.CharField(max_length=50, null=True, blank=True,unique=True, db_index=True)  # INV-001
    def _generate_next_invoice_number(self) -> str:
        """
        Generates next invoice number like INV-0001, INV-0002...
        Safe under concurrency.
        """
        # Lock the latest invoice row so only one request can generate next number at a time
        last_invoice = (
            LocalInvoice.objects
            .select_for_update()
            .filter(invoice_number__startswith="INV-")
            .order_by("-id")
            .first()
        )

        if not last_invoice or not last_invoice.invoice_number:
            return "INV-0001"

        try:
            last_num = int(last_invoice.invoice_number.split("-")[-1])
        except Exception:
            last_num = 0

        return f"INV-{last_num + 1:04d}"

    def save(self, *args, **kwargs):
        # Generate only on create
        if not self.pk and not self.invoice_number:
            with transaction.atomic():
                self.invoice_number = self._generate_next_invoice_number()
                super().save(*args, **kwargs)   # ✅ save INSIDE the transaction
            return

        super().save(*args, **kwargs)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    invoice_date = models.DateField()
    due_date = models.DateField(blank=True, null=True)
    apply_gst_to_all_items = models.CharField(max_length=20,choices=GST_APPLY_CHOICES,default="NO_TAX")

    sub_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    service_charge_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    DISCOUNT_TYPE_CHOICES = [
    ("AMOUNT", "Rupees (₹)"),
    ("PERCENT", "Percentage (%)"),
      ]

    discount_type = models.CharField(max_length=10,choices=DISCOUNT_TYPE_CHOICES,default="PERCENT")

    discount_value = models.DecimalField(max_digits=12,decimal_places=2,default=0,help_text="If type=PERCENT → %, if type=AMOUNT → ₹")

    discount_amount = models.DecimalField(max_digits=12,decimal_places=2,default=0,help_text="Computed final discount in ₹")
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # optional: store GST breakup like {"GST_5": {"tax": 12.5, "amount": 250}, ...}
    gst_breakdown = models.JSONField(default=dict, blank=True)

    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    terms_conditions = models.TextField(blank=True, default="") 
    zoho_invoice_id = models.CharField(max_length=80,blank=True,default="",db_index=True,help_text="Zoho Books invoice_id") 
    assigned_growtag = models.ForeignKey(
        Growtags,
        on_delete=models.PROTECT,
        null=True, blank=True,
        db_index=True,
        related_name="local_invoices"
    )

    assigned_shop = models.ForeignKey(
        Shop,
        on_delete=models.PROTECT,
        null=True, blank=True,
        db_index=True,
        related_name="local_invoices"
    )
    sync_status = models.CharField(max_length=20,default="PENDING",blank=True)
    last_error = models.TextField(default="",blank=True)
    

    def __str__(self):
        return self.invoice_number or f"INV-{self.id}"

from decimal import Decimal, ROUND_HALF_UP
class LocalInvoiceLine(AuditFields):
    GST_CHOICES = LocalInvoice.GST_APPLY_CHOICES

    invoice = models.ForeignKey(LocalInvoice, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(LocalItem, on_delete=models.PROTECT)

    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    description = models.TextField(blank=True, default="")
    SERVICE_CHARGE_TYPE_CHOICES = [
    ("AMOUNT", "Rupees (₹)"),
    ("PERCENT", "Percentage (%)"),
     ]

    service_charge_type = models.CharField(max_length=10, choices=SERVICE_CHARGE_TYPE_CHOICES, default="AMOUNT")
    service_charge_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    gst_treatment = models.CharField(max_length=20, choices=GST_CHOICES, default="NO_TAX")

    line_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)          # qty*rate
    service_charge_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    taxable_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)       # line_amount + service_charge_amount
    line_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)           # taxable_amount + line_tax
    
    def __str__(self):
        return f"Line #{self.id} - {self.item_id} (inv:{self.invoice_id})"
    # -----------------------------
    # Helpers
    # -----------------------------
    def _gst_rate_percent(self) -> Decimal:
        """Return GST/IGST percent as Decimal (e.g., 18)."""
        if not self.gst_treatment or self.gst_treatment == "NO_TAX":
            return Decimal("0")

        # Handles GST_18, IGST_18 etc.
        try:
            pct = self.gst_treatment.split("_")[1]
            return Decimal(pct)
        except Exception:
            return Decimal("0")

    def _q2(self, val: Decimal) -> Decimal:
        """Quantize to 2 decimals."""
        return (val or Decimal("0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def recalc(self, save: bool = False):
        """Recalculate stored totals based on qty/rate/service charge/gst."""
        qty = Decimal(self.qty or 0)
        rate = Decimal(self.rate or 0)
        sc_val = Decimal(self.service_charge_value or 0)

        base_amount = qty * rate  # qty * rate
        base_amount = self._q2(base_amount)

        # service charge amount
        if self.service_charge_type == "PERCENT":
            sc_amount = (base_amount * sc_val) / Decimal("100")
        else:
            sc_amount = sc_val

        sc_amount = self._q2(sc_amount)

        taxable = self._q2(base_amount + sc_amount)

        gst_pct = self._gst_rate_percent()
        tax = self._q2((taxable * gst_pct) / Decimal("100"))

        total = self._q2(taxable + tax)

        self.line_amount = base_amount
        self.service_charge_amount = sc_amount
        self.taxable_amount = taxable
        self.line_tax = tax
        self.line_total = total

        if save:
            self.save(update_fields=[
                "line_amount", "service_charge_amount", "taxable_amount",
                "line_tax", "line_total", "updated_at"
            ])

    def save(self, *args, **kwargs):
        # auto-calc every save
        self.recalc(save=False)
        super().save(*args, **kwargs)
    
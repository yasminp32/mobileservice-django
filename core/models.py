from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from datetime import timedelta
from django.core.validators import MinLengthValidator
from decimal import Decimal
from django.core.exceptions import ValidationError
import secrets
from django.db.models import Q

#class AuditModel(models.Model):
    #created_at = models.DateTimeField(auto_now_add=True)   # auto datetime
    #updated_at = models.DateTimeField(auto_now=True)       # auto datetime
    #created_on = models.DateField(auto_now_add=True)       # auto date

    #created_by = models.ForeignKey(
        #settings.AUTH_USER_MODEL,
        #null=True,
        #blank=True,
        #on_delete=models.SET_NULL,
        #related_name="%(class)s_created",
    #)   
    #class Meta:
        #abstract = True
class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_on = models.DateField(auto_now_add=True)

    created_by_role = models.CharField(
        max_length=20,
        null=True,
        blank=True,
        choices=[
            ("admin", "Admin"),
            ("franchise", "Franchise"),
            ("othershop", "Other Shop"),
            ("growtag", "Growtag"),
            ("customer", "Customer"),
        ]
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created_admin",
    )

    created_by_shop = models.ForeignKey(
        "core.Shop",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created_shop",
    )

    created_by_growtag = models.ForeignKey(
        "core.Growtags",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created_growtag",
    )

    created_by_customer = models.ForeignKey(
        "core.Customer",
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created_customer",
    )

    class Meta:
        abstract = True

class Shop(AuditModel):
    SHOP_TYPE_CHOICES = [
        ('franchise', 'Franchise'),
        ('othershop', 'Other Shop'),
    ]
    shop_type = models.CharField(
        max_length=20,
        choices=SHOP_TYPE_CHOICES,
        default='franchise'
    )
    shopname = models.CharField(max_length=120)
    pincode = models.CharField(
        max_length=12,
        db_index=True,
        validators=[RegexValidator(r'^\d+$', 'Pincode must contain digits only')],
    )
    phone = models.CharField(
        max_length=20,
        unique=True,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],
    )
    owner = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True)
    state = models.CharField(max_length=60, null=True, blank=True)
    email = models.EmailField(unique=True,null=False, blank=False)   
    password = models.CharField(max_length=120, null=True, blank=True,validators=[MinLengthValidator(4)])  
    area = models.CharField(max_length=120, blank=True, null=True)   
    gst_pin = models.CharField(max_length=20,unique=True)
    status = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    
    def __str__(self):
        return self.shopname
    

class Growtags(AuditModel):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Inactive', 'Inactive'),
    ]
    image = models.ImageField(upload_to='Growtags/', blank=True, null=True)
    grow_id = models.CharField(max_length=50, unique=True)  
    name = models.CharField(max_length=120)
    phone = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],
    )
    email = models.EmailField(unique=True)
    password = models.CharField(max_length=120, null=True, blank=True,validators=[MinLengthValidator(4)]) 
    address = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=60, null=True, blank=True)
    pincode = models.CharField(
        max_length=12,
        db_index=True,
        validators=[RegexValidator(r'^\d+$', 'Pincode must contain digits only')],
    )
    area = models.CharField(max_length=120, blank=True, null=True) 
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    adhar = models.CharField(
        max_length=20,
        unique=True,
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d+$', 'Adhar must contain digits only')],
    )
   
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Active')
    
    
    def __str__(self):
        return f"{self.name} - {self.grow_id} ({self.status})"
    
       
class Customer(AuditModel):
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(
        max_length=20,unique=True,blank=True,null=True,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],
    )
    email = models.EmailField(unique=True,null=True)
    password = models.CharField(max_length=120, null=True, blank=True,validators=[MinLengthValidator(4)])
    address = models.TextField(blank=True, null=True)
    state = models.CharField(max_length=60,null=True,blank=True)
    pincode = models.CharField(
        max_length=12,
        validators=[RegexValidator(r'^\d+$', 'Pincode must contain digits only')],
    )
    area = models.CharField(max_length=120, blank=True, null=True)
    

    def set_password(self, raw_password: str):
        self.password = make_password(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password(raw_password, self.password)

    def __str__(self):
        return f"{self.customer_name} ({self.customer_phone})"

class Complaint(AuditModel):
    

    STATUS = [
        ("Pending", "Pending"),
        ("Assigned", "Assigned"),
        ("In Progress", "In Progress"),
        ("Resolved", "Resolved"),
    ]

    ASSIGN_TO_CHOICES = [
        ("franchise", "Franchise"),
        ("othershop", "Other Shop"),
        ("growtag", "GrowTag"),
    ]
    # 🔗 NEW: link to Customer
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name="complaints",
        null=True,
        blank=True,
    )
    
    customer_name = models.CharField(max_length=120)
    customer_phone= models.CharField(
        max_length=20,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],    
    )
    email = models.EmailField(null=True)
    password = models.CharField(max_length=120, null=True, blank=True,validators=[MinLengthValidator(4)])
    phone_model = models.CharField(max_length=120)
    issue_details = models.TextField()
    address = models.TextField()
    state = models.CharField(max_length=60,null=True,blank=True)
    pincode = models.CharField(
        max_length=12,
        validators=[RegexValidator(r'^\d+$', 'Pincode must contain digits only')],
    )
    area = models.CharField(max_length=120, blank=True, null=True)
    # “Assign To” dropdown (GrowTag / etc.)
    assign_to = models.CharField(
        max_length=20,
        choices=ASSIGN_TO_CHOICES,
        default="franchise",
    )

    # Selected shop / technician (e.g. GT-1001 — 1.8 km)
    assigned_shop = models.ForeignKey(
        "core.Shop",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_complaints",
    )
    assigned_Growtags = models.ForeignKey(
        "core.Growtags",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="assigned_complaints_for_growtag",
    )
   
    # Geocoded from pincode
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS, default="Pending")
    CONFIRM_STATUS = [
        ("NOT CONFIRMED", "Not confirmed"),
        ("CONFIRMED", "Confirmed"),
    ]

    confirm_status = models.CharField(
        max_length=20,
        choices=CONFIRM_STATUS,
        default="NOT CONFIRMED"   #NOT confirmed by default
    )

    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_complaints"
    )
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.customer_name} - {self.issue_details[:24]}"
    @property
    def assigned_shop_name(self):
        """
        Used in email & serializer.
        Returns a human-readable assigned name.
        """
        if self.assigned_shop:
            return self.assigned_shop.shopname  # adjust field name if different

        if self.assigned_Growtags:
            # you can customize this
            return str(self.assigned_Growtags)

        return ""
    @property
    def invoice_created(self) -> bool:
      return hasattr(self, "invoice") and self.invoice is not None
 
class GrowTagAssignment(AuditModel):
    growtag = models.OneToOneField(
        "Growtags",
        on_delete=models.CASCADE,
        related_name="assignment"
    )
    shop = models.ForeignKey(
        "Shop",
        on_delete=models.CASCADE,
        related_name="growtag_assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.growtag.grow_id} → {self.shop.shopname}"
#public customer

class CustomerAuthToken(models.Model):
    customer = models.OneToOneField(
        "Customer",
        on_delete=models.CASCADE,
        related_name="auth_token"
    )

    key = models.CharField(
        max_length=64,
        unique=True,
        db_index=True,
        editable=False
    )

    created_at = models.DateTimeField(auto_now_add=True)

    @classmethod
    def generate_key(cls) -> str:
        """Generate a secure 64-char token"""
        return secrets.token_hex(32)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Customer {self.customer_id} | {self.key[:8]}..."
    
    #growtag
class GrowtagAuthToken(models.Model):
    key = models.CharField(max_length=64, unique=True, db_index=True)
    growtag = models.ForeignKey("core.Growtags", on_delete=models.CASCADE, related_name="auth_tokens")
    created_at = models.DateTimeField(default=timezone.now)

    @staticmethod
    def generate_key():
        return secrets.token_hex(32)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)
    #shop
class ShopAuthToken(models.Model):
    key = models.CharField(max_length=64, unique=True, db_index=True)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="auth_tokens")
    created_at = models.DateTimeField(default=timezone.now)

    @staticmethod
    def generate_key():
        return secrets.token_hex(32)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)
    
    #leads model
class Lead(AuditModel):
    STATUS_NEW = "NEW"
    STATUS_COMPLAINT = "COMPLAINT_REGISTERED"
    STATUS_CONVERTED = "CONVERTED"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_COMPLAINT, "Complaint Registered"),
        (STATUS_CONVERTED, "Converted"),
    ]
    SOURCE_CHOICES = [
        ("MANUAL", "Manual"),
        ("SALESIQ", "SalesIQ"),
    ]

    lead_code = models.CharField(max_length=20, unique=True, blank=True)  # LD-001

    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=120, null=True, blank=True,validators=[MinLengthValidator(4)])
    phone_model = models.CharField(max_length=120, blank=True, default="")
    issue_detail = models.TextField(blank=True, default="")

    address = models.TextField(blank=True, default="")
    area = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=60, blank=True, null=True)

    pincode = models.CharField(max_length=10, blank=True, default="")

    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="NEW")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="MANUAL")
    complaint = models.OneToOneField("core.Complaint",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="lead"
    )


    # SalesIQ identifiers (optional)
    salesiq_visitor_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    raw_payload = models.JSONField(null=True, blank=True)

    assigned_shop = models.ForeignKey(
    "core.Shop", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="leads"
    )
    assigned_growtag = models.ForeignKey(
    "core.Growtags", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="leads"
    )
    created_by_customer = models.ForeignKey(
    "core.Customer", on_delete=models.SET_NULL,
    null=True, blank=True, related_name="leads"
    )


    def save(self, *args, **kwargs):
       creating = self.pk is None

       # Only auto-set status on creation
       if creating:
          if self.complaint:
             self.status = "COMPLAINT_REGISTERED"
          elif not self.status:
            self.status = "NEW"

       super().save(*args, **kwargs)

       # Generate lead code after first save
       if creating and not self.lead_code:
          self.lead_code = f"LD-{self.id:03d}"
          super().save(update_fields=["lead_code"])


   #customer password reset         
class CustomerPasswordResetToken(AuditModel):
    customer = models.ForeignKey("core.Customer", on_delete=models.CASCADE, related_name="password_reset_tokens")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    expires_at = models.DateTimeField()

    @staticmethod
    def generate_token():
        return secrets.token_urlsafe(48)

    @classmethod
    def create_for_customer(cls, customer, minutes=15):
        return cls.objects.create(
            customer=customer,
            token=cls.generate_token(),
            expires_at=timezone.now() + timedelta(minutes=minutes),
        )

    def is_expired(self):
        return timezone.now() > self.expires_at   
#vendor

class Vendor(AuditModel):
    STATUS_CHOICES = (
        ("active", "Active"),
        ("inactive", "Inactive"),
    )
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, related_name="vendors",null=True, blank=True)
    name = models.CharField(max_length=150)
    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20,unique=True)
    address = models.TextField()
    website = models.URLField(blank=True, null=True)
    status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default="active"
    )

    def __str__(self):
        return self.name
         
#purchase order

class PurchaseOrder(AuditModel):
    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("SENT", "Sent"),
        ("RECEIVED", "Received"),
        ("CANCELLED", "Cancelled"),
    )
    shop = models.ForeignKey(
        "core.Shop",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="purchase_orders",
    )
    growtag = models.ForeignKey("core.Growtags", null=True, blank=True, on_delete=models.SET_NULL, related_name="purchase_orders")
    po_number = models.CharField(max_length=30, unique=True, db_index=True)
    po_date = models.DateField(default=timezone.localdate)
    expected_delivery_date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")

    # ✅ Vendor relation
    vendor = models.ForeignKey(
        Vendor,
        on_delete=models.PROTECT,
        related_name="purchase_orders"
    )

    # Shipping & Billing
    ship_to = models.TextField(blank=True, null=True)
    bill_to = models.TextField(blank=True, null=True)

    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    shipping_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    terms_and_conditions = models.TextField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    def __str__(self):
        return self.po_number


class PurchaseOrderItem(AuditModel):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.CASCADE, related_name="items"
    )
    item = models.ForeignKey(
        "zoho_integration.LocalItem",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="purchase_order_items"
    )
    item_name = models.CharField(max_length=200)
    description = models.CharField(max_length=500, blank=True, null=True)

    qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

#Bills
class PurchaseBill(AuditModel):
    STATUS_CHOICES = (
        ("DRAFT", "Draft"),
        ("OPEN", "Open"),
        ("CANCELLED", "Cancelled"),
    )

    PAYMENT_STATUS_CHOICES = (
        ("UNPAID", "Unpaid"),
        ("PARTIALLY_PAID", "Partially Paid"),
        ("PAID", "Paid"),
        ("OVERDUE", "Overdue"),
    )
    
    shop = models.ForeignKey("core.Shop", null=True, blank=True, on_delete=models.PROTECT)
    growtag = models.ForeignKey("core.Growtags", null=True, blank=True, on_delete=models.PROTECT)

    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default="DRAFT")
    vendor = models.ForeignKey("core.Vendor", on_delete=models.PROTECT, related_name="purchase_bills")

    bill_number = models.CharField(max_length=50, unique=True)
    order_number = models.CharField(max_length=50, blank=True, default="")

    bill_date = models.DateField(default=timezone.localdate)
    due_date = models.DateField(null=True, blank=True)

    #status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default="UNPAID")
    #payment_terms = models.CharField(max_length=20, choices=PAYMENT_TERMS_CHOICES, default="NET_30")

    # Vendor snapshot fields (to show in UI)
    vendor_name = models.CharField(max_length=150, blank=True, default="")
    vendor_email = models.EmailField(blank=True, default="")
    vendor_phone = models.CharField(max_length=30, blank=True, default="")
    vendor_gstin = models.CharField(max_length=30, blank=True, default="")
    vendor_address = models.TextField(blank=True, default="")

    # Shipping/Billing Addresses
    ship_to = models.TextField(blank=True, default="")
    bill_to = models.TextField(blank=True, default="")

    # Totals
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    tds_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)     # e.g 1.00
    tds_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    shipping_charges = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    adjustment = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance_due = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    notes = models.TextField(blank=True, default="")
    terms_and_conditions = models.TextField(blank=True, default="")


    def fill_vendor_snapshot(self):
        v = self.vendor
        self.vendor_name = getattr(v, "name", "") or ""
        self.vendor_email = getattr(v, "email", "") or ""
        self.vendor_phone = getattr(v, "phone", "") or ""
        self.vendor_address = getattr(v, "address", "") or ""
        self.vendor_gstin = getattr(v, "gstin", "") or getattr(v, "gst_no", "") or ""

    def recalc_totals(self):
        items = self.items.all()

        subtotal = Decimal("0.00")
        disc_total = Decimal("0.00")
        tax_total = Decimal("0.00")

        for it in items:
            subtotal += it.line_subtotal
            disc_total += it.discount_amount
            tax_total += it.tax_amount

        tds_amt = (subtotal * (self.tds_percent or 0)) / Decimal("100.00")
        total = (subtotal - disc_total + tax_total - tds_amt +
                 (self.shipping_charges or 0) + (self.adjustment or 0))

        paid = self.payments.aggregate(s=models.Sum("amount"))["s"] or Decimal("0.00")
        balance = total - paid

        # Payment status auto
        if self.status == "CANCELLED":
            pay_status = "UNPAID"
        else:
            if total <= 0:
                pay_status = "UNPAID"
            elif paid <= 0:
                pay_status = "UNPAID"
            elif balance <= 0:
                pay_status = "PAID"
                balance = Decimal("0.00")
            else:
                pay_status = "PARTIALLY_PAID"

        self.subtotal = subtotal
        self.total_discount = disc_total
        self.total_tax = tax_total
        self.tds_amount = tds_amt
        self.total = total

        self.amount_paid = paid
        self.balance_due = balance
        self.payment_status = pay_status

        self.save(update_fields=[
            "subtotal", "total_discount", "total_tax", "tds_amount",
            "total", "amount_paid", "balance_due", "payment_status"
        ])
    def clean(self):
      if self.owner_type == "shop":
        if not self.shop or self.growtag:
            raise ValidationError("For owner_type='shop', shop must be set and growtag must be null.")
      elif self.owner_type == "growtag":
        if not self.growtag or self.shop:
            raise ValidationError("For owner_type='growtag', growtag must be set and shop must be null.")

    def save(self, *args, **kwargs):
        # Keep vendor fields auto-filled
        if self.vendor_id:
            self.fill_vendor_snapshot()
        super().save(*args, **kwargs)


class PurchaseBillItem(AuditModel):
    bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name="items")

    item = models.ForeignKey("zoho_integration.LocalItem", on_delete=models.PROTECT, null=True, blank=True)

    name = models.CharField(max_length=150)
    description = models.CharField(max_length=255, blank=True, default="")
    account = models.CharField(max_length=120, blank=True, default="Cost of Goods Sold")  # dropdown in UI

    qty = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    rate = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    tax_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    line_subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)     # qty*rate
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)           # final line amount

    def save(self, *args, **kwargs):
        qty = self.qty or 0
        rate = self.rate or 0
        base = qty * rate

        disc = (base * (self.discount_percent or 0)) / Decimal("100.00")
        taxable = base - disc
        tax = (taxable * (self.tax_percent or 0)) / Decimal("100.00")
        final = taxable + tax

        self.line_subtotal = base
        self.discount_amount = disc
        self.tax_amount = tax
        self.amount = final

        super().save(*args, **kwargs)


class PurchaseBillPayment(AuditModel):
    bill = models.ForeignKey(PurchaseBill, on_delete=models.CASCADE, related_name="payments")
    payment_date = models.DateField(default=timezone.localdate)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=50, blank=True, default="")
    reference = models.CharField(max_length=120, blank=True, default="")
    def clean(self):
        # ensure bill is up-to-date
        self.bill.recalc_totals()
        self.bill.refresh_from_db(fields=["balance_due"])

        if self.amount <= 0:
            raise ValidationError("Amount must be greater than 0.")

        if self.bill.balance_due <= 0:
            raise ValidationError("Bill is already fully paid.")

        if self.amount > self.bill.balance_due:
            raise ValidationError(f"Amount cannot exceed balance due ({self.bill.balance_due}).")

#stock
class InventoryStock(AuditModel):
    OWNER_CHOICES = (
        ("shop", "Shop"),
        ("growtag", "Growtag"),
    )

    owner_type = models.CharField(max_length=10, choices=OWNER_CHOICES)
    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, null=True, blank=True)
    growtag = models.ForeignKey("core.Growtags", on_delete=models.CASCADE, null=True, blank=True)

    item = models.ForeignKey("zoho_integration.LocalItem", on_delete=models.CASCADE, related_name="inventory_stocks")
    qty_on_hand = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    reorder_level = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    

    class Meta:
     constraints = [
         models.UniqueConstraint(
             fields=["shop", "item"],
             condition=Q(owner_type="shop"),
             name="uniq_shop_item_stock",
            ),
         models.UniqueConstraint(
            fields=["growtag", "item"],
            condition=Q(owner_type="growtag"),
            name="uniq_growtag_item_stock",
            ),
        ]
    def clean(self):
        # Enforce correct owner FK usage
        if self.owner_type == "shop":
            if not self.shop or self.growtag:
                raise ValidationError("For owner_type='shop', shop must be set and growtag must be null.")
        if self.owner_type == "growtag":
            if not self.growtag or self.shop:
                raise ValidationError("For owner_type='growtag', growtag must be set and shop must be null.")
    def save(self, *args, **kwargs):
       self.full_clean()
       return super().save(*args, **kwargs)

    def __str__(self):
        owner = self.shop_id if self.owner_type == "shop" else self.growtag_id
        return f"{self.owner_type}:{owner} - {self.item_id} = {self.qty_on_hand}"


class StockLedger(AuditModel):
    REF_CHOICES = (
        ("PURCHASE_BILL", "Purchase Bill"),
        ("INVOICE", "Invoice"),
        ("ADJUSTMENT", "Adjustment"),
        ("REVERSAL", "Reversal"),
    )

    owner_type = models.CharField(max_length=10, choices=InventoryStock.OWNER_CHOICES)

    shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, null=True, blank=True)
    growtag = models.ForeignKey("core.Growtags", on_delete=models.CASCADE, null=True, blank=True)

    item = models.ForeignKey("zoho_integration.LocalItem", on_delete=models.CASCADE, related_name="stock_ledgers")
    qty_change = models.DecimalField(max_digits=12, decimal_places=2)  # +purchase, -invoice
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    ref_type = models.CharField(max_length=20, choices=REF_CHOICES, default="ADJUSTMENT")
    ref_id = models.PositiveIntegerField(null=True, blank=True)

    note = models.CharField(max_length=255, blank=True, default="")
    
    class Meta:
       ordering = ["-id"]
       indexes = [
        models.Index(fields=["owner_type", "shop", "growtag", "item"]),
        models.Index(fields=["ref_type", "ref_id"]),
    ]


    def clean(self):
        if self.owner_type == "shop":
            if not self.shop or self.growtag:
                raise ValidationError("For owner_type='shop', shop must be set and growtag must be null.")
        if self.owner_type == "growtag":
            if not self.growtag or self.shop:
                raise ValidationError("For owner_type='growtag', growtag must be set and shop must be null.")
    def save(self, *args, **kwargs):
       self.full_clean()
       return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ref_type} {self.ref_id} {self.item_id} {self.qty_change}"
    
#password reset API
class CustomerPasswordOTP(models.Model):
    customer = models.ForeignKey("core.Customer", on_delete=models.CASCADE)
    otp_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    @staticmethod
    def generate_otp():
        import random
        return str(random.randint(100000, 999999))

    def is_expired(self):
        return timezone.now() > self.expires_at

    @classmethod
    def create_otp_for_customer(cls, customer, minutes=5):
        raw_otp = cls.generate_otp()
        otp_obj = cls.objects.create(
            customer=customer,
            otp_hash=make_password(raw_otp),
            expires_at=timezone.now() + timedelta(minutes=minutes)
        )
        return raw_otp, otp_obj

#postal code
class PostalCode(models.Model):
    country = models.CharField(max_length=2, default="IN", db_index=True)
    code = models.CharField(max_length=20, db_index=True)
    city = models.CharField(max_length=120, blank=True, default="")
    state = models.CharField(max_length=120, blank=True, default="")
    district = models.CharField(max_length=120, blank=True, default="")
    #area = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        unique_together = ("country", "code")

    def __str__(self):
        return f"{self.country}-{self.code}"


from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator
from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
import secrets
class AuditModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)   # auto datetime
    updated_at = models.DateTimeField(auto_now=True)       # auto datetime
    created_on = models.DateField(auto_now_add=True)       # auto date

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="%(class)s_created",
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
    password = models.CharField(max_length=120, null=True, blank=True)  
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
    password = models.CharField(max_length=120, null=True, blank=True) 
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
    password = models.CharField(max_length=120, null=True, blank=True)
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
    password = models.CharField(max_length=120, null=True, blank=True)
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
class Lead(models.Model):
    STATUS_CHOICES = [
        ("NEW", "New"),
        ("CONTACTED", "Contacted"),
        ("QUALIFIED", "Qualified"),
        ("LOST", "Lost"),
        ("CONVERTED", "Converted"),
    ]
    SOURCE_CHOICES = [
        ("MANUAL", "Manual"),
        ("SALESIQ", "SalesIQ"),
    ]

    lead_code = models.CharField(max_length=20, unique=True, blank=True)  # LD-001

    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(null=True, blank=True)

    phone_model = models.CharField(max_length=120, blank=True, default="")
    issue_detail = models.TextField(blank=True, default="")

    address = models.TextField(blank=True, default="")
    area = models.CharField(max_length=120, blank=True, default="")
    pincode = models.CharField(max_length=10, blank=True, default="")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="NEW")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="MANUAL")

    # SalesIQ identifiers (optional)
    salesiq_visitor_id = models.CharField(max_length=120, null=True, blank=True, db_index=True)
    raw_payload = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.lead_code:
            self.lead_code = f"LD-{self.id:03d}"
            super().save(update_fields=["lead_code"])



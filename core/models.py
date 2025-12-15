from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator

class Shop(models.Model):
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
        blank=True,
        null=True,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],
    )
    owner = models.CharField(max_length=120, blank=True, null=True)
    address = models.TextField(blank=True)
    email = models.EmailField(unique=True, null=True, blank=True)   
    password = models.CharField(max_length=120, null=True, blank=True)  
    area = models.CharField(max_length=120, blank=True, null=True)   
    gst_pin = models.CharField(max_length=20,unique=True, blank=True, null=True)
    status = models.BooleanField(default=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    
    def __str__(self):
        return self.shopname
    

class Growtags(models.Model):
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
    
    #created_at = models.DateTimeField(auto_now_add=True)
    #updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} - {self.grow_id} ({self.status})"
    
       
class Customer(models.Model):
    customer_name = models.CharField(max_length=120)
    customer_phone = models.CharField(
        max_length=20,unique=True,blank=True,null=True,
        validators=[RegexValidator(r'^\d+$', 'Phone number must contain digits only')],
    )
    email = models.EmailField(unique=True,null=True)
    password = models.CharField(max_length=120, null=True, blank=True)

    #phone_model = models.CharField(max_length=120, blank=True, null=True)
    #issue_details = models.TextField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    pincode = models.CharField(
        max_length=12,
        validators=[RegexValidator(r'^\d+$', 'Pincode must contain digits only')],
    )
    #area = models.CharField(max_length=120, blank=True, null=True)
    # These are more "complaint-like", but you requested them — we’ll store for now
    #assign_to = models.CharField(max_length=50, blank=True, null=True)
    #assign_type = models.CharField(max_length=50, blank=True, null=True)
    #status = models.CharField(max_length=50, blank=True, null=True)

    created_at = models.DateTimeField(default=timezone.now) 

    def __str__(self):
        return f"{self.customer_name} ({self.customer_phone})"


class Complaint(models.Model):
    

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
    created_at = models.DateTimeField(default=timezone.now)

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
    
 
class GrowTagAssignment(models.Model):
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


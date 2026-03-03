from django.conf import settings
from django.db import models
from django.core.exceptions import ValidationError

class ExpenseCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Expense(models.Model):
    PAYMENT_METHOD_CHOICES = [
        ("CASH", "Cash"),
        ("CREDIT_CARD", "Credit Card"),
        ("DEBIT_CARD", "Debit Card"),
        ("COMPANY_CARD", "Company Card"),
        ("BANK_TRANSFER", "Bank Transfer"),
        ("CHECK", "Check"),
        ("PAYPAL", "PayPal"),
        ("OTHER", "Other"),
    ]

    STATUS_CHOICES = [
        ("PENDING", "Pending"),
        ("APPROVED", "Approved"),
        ("REJECTED", "Rejected"),
    ]
    OWNER_CHOICES = [
        ("shop", "Shop"),
        ("growtag", "Growtag"),
        ("admin", "Admin"),
    ]
    owner_type = models.CharField(max_length=10, choices=OWNER_CHOICES, default="admin")
    owner_shop = models.ForeignKey("core.Shop", on_delete=models.CASCADE, null=True, blank=True)
    owner_growtag = models.ForeignKey("core.Growtags", on_delete=models.CASCADE, null=True, blank=True)

    title = models.CharField(max_length=150)
    merchant = models.CharField(max_length=150)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField()

    category = models.ForeignKey(
        ExpenseCategory, on_delete=models.PROTECT, related_name="expenses"
    )

    payment_method = models.CharField(
        max_length=20, choices=PAYMENT_METHOD_CHOICES
    )

    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="PENDING"
    )

    # receipt upload (max 5MB validation will be in serializer)
    receipt = models.FileField(upload_to="expense_receipts/", null=True, blank=True)

    #notes = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="expenses_created"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
     # ✅ validation so data stays correct
    def clean(self):
        if self.owner_type == "shop":
            if not self.owner_shop:
                raise ValidationError({"owner_shop": "owner_shop is required when owner_type=shop"})
            if self.owner_growtag:
                raise ValidationError({"owner_growtag": "must be empty when owner_type=shop"})

        if self.owner_type == "growtag":
            if not self.owner_growtag:
                raise ValidationError({"owner_growtag": "owner_growtag is required when owner_type=growtag"})
            if self.owner_shop:
                raise ValidationError({"owner_shop": "must be empty when owner_type=growtag"})

        if self.owner_type == "admin":
            if self.owner_shop or self.owner_growtag:
                raise ValidationError("Admin expense must not have owner_shop/owner_growtag")

    def save(self, *args, **kwargs):
        self.full_clean()  # enforce the above rules
        return super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.title} - {self.amount}"


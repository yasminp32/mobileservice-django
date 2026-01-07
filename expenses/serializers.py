from decimal import Decimal
from rest_framework import serializers
from .models import Expense, ExpenseCategory


MAX_RECEIPT_SIZE = 5 * 1024 * 1024  # 5MB


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["id", "created_at"]


class ExpenseReadSerializer(serializers.ModelSerializer):
    category = ExpenseCategorySerializer(read_only=True)
    category_id = serializers.IntegerField(source="category.id", read_only=True)

    payment_method_label = serializers.CharField(source="get_payment_method_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "title", "merchant", "amount", "date",
            "category", "category_id",
            "payment_method", "payment_method_label",
            "status", "status_label",
            "receipt", 
            "created_by", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class ExpenseWriteSerializer(serializers.ModelSerializer):
    # Dropdown uses category_id (frontend selects from category list)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=ExpenseCategory.objects.filter(is_active=True),
        source="category",
        write_only=True
    )

    receipt = serializers.FileField(required=False, allow_null=True)

    class Meta:
        model = Expense
        fields = [
            "id",
            "title", "merchant", "amount", "date",
            "category_id",
            "payment_method",
            "status",
            "receipt",
            
        ]
        read_only_fields = ["id"]

    def validate_amount(self, value: Decimal):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than 0.")
        return value

    def validate_receipt(self, file):
        if not file:
            return file
        if file.size > MAX_RECEIPT_SIZE:
            raise serializers.ValidationError("Receipt must be <= 5MB.")
        return file

from rest_framework import serializers
from .models import LocalItem

class LocalItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = LocalItem
        fields = "__all__"
        read_only_fields = ("zoho_item_id", "sync_status", "last_error", "created_at", "updated_at")
    def validate(self, attrs):
        # If not sellable → force selling_price = 0
        if attrs.get("is_sellable") is False:
            attrs["selling_price"] = 0

        # If not purchasable → force cost_price = 0
        if attrs.get("is_purchasable") is False:
            attrs["cost_price"] = 0

        return attrs
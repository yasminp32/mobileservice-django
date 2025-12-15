from django.contrib import admin
from .models import Shop, Growtags, Complaint

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("id", "shopname", "owner", "phone","address","pincode","gst_pin", "status","latitude","longitude",)
    search_fields = ("name", "pincode")

@admin.register(Growtags)
class GrowTagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "status")
    #list_filter = ( "status")
    search_fields = ("name", "grow_id")

@admin.register(Complaint)
class ComplaintAdmin(admin.ModelAdmin):
    
    
    list_display = ("id", "customer_name","customer_phone","phone_model", "issue_details",  "address","pincode", "assign_to",  "status","created_at")
    #list_filter = ("status", "assigned_shop")
    search_fields = ("customer_name", "customer_phone", "issue", "pincode")


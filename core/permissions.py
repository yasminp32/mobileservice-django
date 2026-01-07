from rest_framework.permissions import BasePermission


class IsCustomer(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "customer") and request.customer is not None

class IsGrowtag(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "growtag") and request.growtag is not None

class IsShop(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "shop") and request.shop is not None

class IsFranchiseShop(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "shop") and request.shop and request.shop.shop_type == "franchise"

class IsOtherShop(BasePermission):
    def has_permission(self, request, view):
        return hasattr(request, "shop") and request.shop and request.shop.shop_type == "othershop"
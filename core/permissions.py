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
class IsAnyStaffOrShopOrGrowtagOrCustomer(BasePermission):
    def has_permission(self, request, view):
        is_admin = bool(getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff)
        is_shop = bool(getattr(request, "shop", None))
        is_growtag = bool(getattr(request, "growtag", None))
        is_customer = bool(getattr(request, "customer", None))
        return is_admin or is_shop or is_growtag or is_customer
class IsAdminOrShopSelf(BasePermission):
    def has_permission(self, request, view):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True
        return getattr(request, "shop", None) is not None

    def has_object_permission(self, request, view, obj):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True
        shop = getattr(request, "shop", None)
        return bool(shop and obj and shop.id == obj.id)


class IsAdminOrGrowtagSelf(BasePermission):
    def has_permission(self, request, view):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True
        return getattr(request, "growtag", None) is not None

    def has_object_permission(self, request, view, obj):
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True
        g = getattr(request, "growtag", None)
        return bool(g and obj and g.id == obj.id)

class IsAdminOrCustomerSelf(BasePermission):
    """
    Admin can access any customer.
    Customer can access only their own record.
    """

    def has_permission(self, request, view):
        # Admin (Django user)
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True

        # Logged-in customer token
        return getattr(request, "customer", None) is not None

    def has_object_permission(self, request, view, obj):
        # Admin
        if getattr(request, "user", None) and request.user.is_authenticated and request.user.is_staff:
            return True

        # Customer self
        c = getattr(request, "customer", None)
        return bool(c and obj and obj.id == c.id)

def role_from_request(request):
        # Admin (Django user)
        u = getattr(request, "user", None)
        if u and u.is_authenticated and u.is_staff:
            return "admin"

        s = getattr(request, "shop", None)
        if s:
           return "franchise" if s.shop_type == "franchise" else "othershop"

        if getattr(request, "growtag", None):
           return "growtag"

        if getattr(request, "customer", None):
           return "customer"

        return "anon"


class CrudByRole(BasePermission):
    """
    View must define:
      role_perms = {
        "admin": {"GET","POST","PATCH","DELETE"},
        ...
      }
    """
    def has_permission(self, request, view):
        role = role_from_request(request)
        allowed = getattr(view, "role_perms", {})
        return request.method.upper() in allowed.get(role, set())
        
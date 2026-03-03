from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from core.mixins import BulkDeleteMixin
from .models import Expense, ExpenseCategory
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseReadSerializer,
    ExpenseWriteSerializer,
)
from core.permissions import CrudByRole
from core.authentication import UnifiedTokenAuthentication
from rest_framework.authentication import SessionAuthentication
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import PermissionDenied
class ExpenseCategoryViewSet(BulkDeleteMixin,viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all().order_by("name")
    serializer_class = ExpenseCategorySerializer
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "othershop": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "growtag": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "customer": set(),
    }
    def get_queryset(self):
        if self.action == "list":
            return ExpenseCategory.objects.filter(is_active=True).order_by("name")
        return super().get_queryset()

class ExpenseViewSet(BulkDeleteMixin,viewsets.ModelViewSet):
    """
    Admin: full access
    Shop: CRUD only its own expenses
    Growtag: CRUD only its own expenses
    Customer: no access
    """
    authentication_classes = [
        SessionAuthentication,
        JWTAuthentication,
        UnifiedTokenAuthentication
    ]
    permission_classes = [CrudByRole]

    role_perms = {
        "admin": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "franchise": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "othershop": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "growtag": {"GET", "POST", "PATCH", "DELETE","PUT"},
        "customer": set(),
    }
    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return ExpenseReadSerializer
        return ExpenseWriteSerializer

    def get_queryset(self):
        qs = Expense.objects.select_related("category").all().order_by("-id")

        # ✅ Admin sees all
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            return qs

        # ✅ Shop sees only its expenses
        if getattr(self.request, "shop", None):
            return qs.filter(owner_type="shop", owner_shop=self.request.shop)

        # ✅ Growtag sees only its expenses
        if getattr(self.request, "growtag", None):
            return qs.filter(owner_type="growtag", owner_growtag=self.request.growtag)

        return qs.none()

    def perform_create(self, serializer):
        # ✅ Admin can create any expense (owner fields allowed from payload)
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
            serializer.save(created_by=self.request.user)
            return

        # ✅ Shop creates expense for itself only (ignore incoming owner fields)
        if getattr(self.request, "shop", None):
            serializer.save(
                owner_type="shop",
                owner_shop=self.request.shop,
                owner_growtag=None,
                created_by=None,
            )
            return

        # ✅ Growtag creates expense for itself only
        if getattr(self.request, "growtag", None):
            serializer.save(
                owner_type="growtag",
                owner_growtag=self.request.growtag,
                owner_shop=None,
                created_by=None,
            )
            return

        raise PermissionDenied("Not allowed to create expense")

    def perform_update(self, serializer):
        """
        Prevent spoofing owner fields on update as well.
        """
        instance = self.get_object()

        # ✅ Admin can update anything
        if self.request.user and self.request.user.is_authenticated and self.request.user.is_staff:
          serializer.save(
            owner_type="admin",
            owner_shop=None,
            owner_growtag=None,
            created_by=self.request.user
        )
        return

        # ✅ Shop can update only its own expense AND cannot change owner
        if getattr(self.request, "shop", None):
            if instance.owner_type != "shop" or instance.owner_shop_id != self.request.shop.id:
                raise PermissionDenied("You cannot update this expense.")
            serializer.save(
                owner_type="shop",
                owner_shop=self.request.shop,
                owner_growtag=None,
                created_by=None,
            )
            return

        # ✅ Growtag can update only its own expense AND cannot change owner
        if getattr(self.request, "growtag", None):
            if instance.owner_type != "growtag" or instance.owner_growtag_id != self.request.growtag.id:
                raise PermissionDenied("You cannot update this expense.")
            serializer.save(
                owner_type="growtag",
                owner_growtag=self.request.growtag,
                owner_shop=None,
                created_by=None,
            )
            return

        raise PermissionDenied("Not allowed to update expense")
    

    # Optional: approve/reject buttons (like status dropdown)
    @action(detail=True, methods=["patch"])
    def approve(self, request, pk=None):
        expense = self.get_object()
        expense.status = "APPROVED"
        expense.save(update_fields=["status"])
        return Response({"message": "Expense approved", "status": expense.status})

    @action(detail=True, methods=["patch"])
    def reject(self, request, pk=None):
        expense = self.get_object()
        expense.status = "REJECTED"
        expense.save(update_fields=["status"])
        return Response({"message": "Expense rejected", "status": expense.status})

    # Optional: send dropdown options to frontend (no hardcode needed)
    @action(detail=False, methods=["get"])
    def meta(self, request):
        return Response({
            "payment_methods": [{"value": k, "label": v} for k, v in Expense.PAYMENT_METHOD_CHOICES],
            "statuses": [{"value": k, "label": v} for k, v in Expense.STATUS_CHOICES],
        })


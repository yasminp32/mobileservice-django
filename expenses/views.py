from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Expense, ExpenseCategory
from .serializers import (
    ExpenseCategorySerializer,
    ExpenseReadSerializer,
    ExpenseWriteSerializer,
)


class ExpenseCategoryViewSet(viewsets.ModelViewSet):
    queryset = ExpenseCategory.objects.all().order_by("name")
    serializer_class = ExpenseCategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # only active categories for dropdown
        if self.action in {"list"}:
            return ExpenseCategory.objects.filter(is_active=True).order_by("name")
        return super().get_queryset()


class ExpenseViewSet(viewsets.ModelViewSet):
    queryset = Expense.objects.select_related("category").all().order_by("-id")
    permission_classes = [permissions.IsAuthenticated]

    def get_serializer_class(self):
        if self.action in {"list", "retrieve"}:
            return ExpenseReadSerializer
        return ExpenseWriteSerializer

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def get_queryset(self):
        # If you want per-user expenses only, keep this:
        return Expense.objects.select_related("category").filter(created_by=self.request.user).order_by("-id")

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


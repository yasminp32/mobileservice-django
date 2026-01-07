from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ExpenseViewSet, ExpenseCategoryViewSet

router = DefaultRouter()
router.register("expense-categories", ExpenseCategoryViewSet, basename="expense-categories")
router.register("expenses", ExpenseViewSet, basename="expenses")

urlpatterns = [
    path("", include(router.urls)),
]

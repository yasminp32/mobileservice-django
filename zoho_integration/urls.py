
# zoho_integration/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import LocalItemDetailSyncView,LocalItemListCreateView,LocalInvoiceViewSet
from .views import zoho_callback
from .views import invoice_pdf_view
router = DefaultRouter()
router.register("local-invoices", LocalInvoiceViewSet, basename="local-invoices")

urlpatterns = [
    path("callback/", zoho_callback, name="zoho-callback"),
    path("local-items/", LocalItemListCreateView.as_view(), name="local-item-list-create"),
    path("local-items/<int:pk>/", LocalItemDetailSyncView.as_view(), name="local-item-detail-sync"),
    path("invoices/<int:pk>/pdf/", invoice_pdf_view, name="invoice-pdf"),
    path("", include(router.urls)),

]

    



from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import (
                         ShopViewSet, GrowtagsViewSet, ComplaintViewSet,
                         GrowTagAssignmentViewSet,CustomerViewSet,ConfirmComplaintAPIView,
                         SalesIQLeadWebhook,GrowtagPopupViewSet,ShopPopupViewSet)
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core.views import ( CustomerRegisterView, CustomerLoginView, PublicComplaintViewSet,
                        LeadViewSet,VendorListCreateAPIView, VendorDetailAPIView,
                        PurchaseOrderListCreateAPIView, PurchaseOrderDetailAPIView, PurchaseBillViewSet,InventoryStockViewSet, 
                        StockLedgerViewSet,PurchaseOrderItemViewSet,SendResetOTPAPIView,VerifyResetOTPAPIView
                        )
from core.views_admin_dashboard import (AdminDashboardMetaAPIView,AdminDashboardAPIView,GrowtagDashboardMetaAPIView,
                                         GrowtagDashboardAPIView,ShopDashboardMetaAPIView,OtherShopDashboardAPIView,
                                         FranchiseDashboardAPIView
                                        )

from core.views_reports import (
    ComplaintsReportAPIView,
    GrowtagsReportAPIView,
    CustomersReportAPIView,
    SalesSummaryReportAPIView,
    ProfitShareReportAPIView,
    ExpenseReportAPIView,
    
)
from zoho_integration import views as zoho_views
from core.views_auth import ( UnifiedLoginAPIView,
    ShopLogoutAPIView,
    GrowtagLogoutAPIView,
    CustomerLogoutAPIView,)
from core.views import PostalCodeViewSet
public_router = DefaultRouter()
public_router.register(r'complaints', PublicComplaintViewSet, basename='public-complaint')

router = DefaultRouter()
router.register(r'shops', ShopViewSet, basename='shop')
router.register(r'growtags', GrowtagsViewSet, basename='growtag')
router.register(r'complaints', ComplaintViewSet, basename='complaint')
router.register(r"growtag-assignments", GrowTagAssignmentViewSet, basename="growtag-assignments")
router.register(r"customers", CustomerViewSet, basename="customer")
router.register(r"leads", LeadViewSet, basename="lead")
router.register(r"purchase-order-items", PurchaseOrderItemViewSet, basename="purchase-order-items")
router.register(r"bills", PurchaseBillViewSet, basename="bills")
router.register(r"stocks", InventoryStockViewSet, basename="stocks")
router.register(r"stock-ledger", StockLedgerViewSet, basename="stock-ledger")
router.register(r"growtags-popup", GrowtagPopupViewSet, basename="growtags-popup")
router.register(r"shops-popup", ShopPopupViewSet, basename="shops-popup")
router.register(r"postal-codes", PostalCodeViewSet, basename="postal-codes")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/dashboard/meta/", AdminDashboardMetaAPIView.as_view()),
    path("api/admin/dashboard/", AdminDashboardAPIView.as_view(), name="admin-dashboard"),
    path("api/growtag/dashboard/meta/", GrowtagDashboardMetaAPIView.as_view()),
    path("api/growtag/dashboard/", GrowtagDashboardAPIView.as_view(), name="growtag-dashboard"),
    path("api/shop/dashboard/meta/", ShopDashboardMetaAPIView.as_view()),
    path("api/othershop/dashboard/", OtherShopDashboardAPIView.as_view(), name="othershop-dashboard"),
    path("api/franchise/dashboard/", FranchiseDashboardAPIView.as_view(), name="franchise-dashboard"),
    path("auth/login/", UnifiedLoginAPIView.as_view(), name="auth-login"),
    
    path("auth/shop/logout/", ShopLogoutAPIView.as_view()),
    path("auth/growtag/logout/", GrowtagLogoutAPIView.as_view()),
    path("auth/customer/logout/", CustomerLogoutAPIView.as_view()),

    path("api/", include(router.urls)),
    path("zoho/", include("zoho_integration.urls")),
    path("api/complaints/<int:pk>/confirm/",ConfirmComplaintAPIView.as_view(),name="confirm-complaint"),
    path("api/token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),
    path("api/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    
    path("api-auth/", include("rest_framework.urls")),
    path("api/public/customers/register/", CustomerRegisterView.as_view()),
    path("api/public/customers/login/", CustomerLoginView.as_view()),
    path("api/public/", include(public_router.urls)),
    path("api/integrations/salesiq/leads/", SalesIQLeadWebhook.as_view()),
    
    

    path("api/auth/send-reset-otp/", SendResetOTPAPIView.as_view()),
    path("api/auth/verify-reset-otp/", VerifyResetOTPAPIView.as_view()),

    
    path("reports/complaints/", ComplaintsReportAPIView.as_view()),
    path("reports/growtags/", GrowtagsReportAPIView.as_view()),
    path("reports/customers/", CustomersReportAPIView.as_view()),
    path("reports/sales-summary/", SalesSummaryReportAPIView.as_view()),
    path("reports/profit-share/", ProfitShareReportAPIView.as_view()),
    path("reports/expenses/", ExpenseReportAPIView.as_view()),
    path("api/vendors/", VendorListCreateAPIView.as_view(), name="vendor-list-create"),
    path("api/vendors/<int:pk>/", VendorDetailAPIView.as_view(), name="vendor-detail"),
    path("api/purchase-orders/", PurchaseOrderListCreateAPIView.as_view(), name="purchase-order-list-create"),
    path("api/purchase-orders/<int:pk>/", PurchaseOrderDetailAPIView.as_view(), name="purchase-order-detail"),
    path("api/", include("expenses.urls")),
    
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
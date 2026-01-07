from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import ShopViewSet, GrowtagsViewSet, ComplaintViewSet,GrowTagAssignmentViewSet,CustomerViewSet,ConfirmComplaintAPIView,SalesIQLeadWebhook
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from core.views import CustomerRegisterView, CustomerLoginView, PublicComplaintViewSet,LeadViewSet
from core.views_admin_dashboard import (
    AdminDashboardAPIView,GrowtagDashboardAPIView,OtherShopDashboardAPIView,
    FranchiseDashboardAPIView)

from core.views_auth import (
    GrowtagLoginAPIView, GrowtagLogoutAPIView,ShopLoginAPIView,ShopLogoutAPIView,
    CustomerLoginAPIView, CustomerLogoutAPIView,
)

from zoho_integration import views as zoho_views
public_router = DefaultRouter()
public_router.register(r'complaints', PublicComplaintViewSet, basename='public-complaint')

router = DefaultRouter()
router.register(r'shops', ShopViewSet, basename='shop')
router.register(r'growtags', GrowtagsViewSet, basename='growtag')
router.register(r'complaints', ComplaintViewSet, basename='complaint')
router.register(r"growtag-assignments", GrowTagAssignmentViewSet, basename="growtag-assignments")
router.register(r"customers", CustomerViewSet, basename="customer")
router.register(r"leads", LeadViewSet, basename="lead")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/admin/dashboard/", AdminDashboardAPIView.as_view(), name="admin-dashboard"),
    path("api/growtag/dashboard/", GrowtagDashboardAPIView.as_view(), name="growtag-dashboard"),
    path("api/othershop/dashboard/", OtherShopDashboardAPIView.as_view(), name="othershop-dashboard"),
    path("api/franchise/dashboard/", FranchiseDashboardAPIView.as_view(), name="franchise-dashboard"),
    path("api/auth/shop/login/", ShopLoginAPIView.as_view()),
    path("api/auth/shop/logout/", ShopLogoutAPIView.as_view()),
    path("api/auth/growtag/login/", GrowtagLoginAPIView.as_view()),
    path("api/auth/growtag/logout/", GrowtagLogoutAPIView.as_view()),
    path("api/auth/customer/login/", CustomerLoginAPIView.as_view()),
    path("api/auth/customer/logout/", CustomerLogoutAPIView.as_view()),
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
    path("api/", include("expenses.urls")),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
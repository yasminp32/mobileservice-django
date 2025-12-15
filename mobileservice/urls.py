from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import ShopViewSet, GrowtagsViewSet, ComplaintViewSet,GrowTagAssignmentViewSet,CustomerViewSet
from django.conf import settings
from django.conf.urls.static import static
from zoho_integration import views as zoho_views
router = DefaultRouter()
router.register(r'shops', ShopViewSet, basename='shop')
router.register(r'growtags', GrowtagsViewSet, basename='growtag')
router.register(r'complaints', ComplaintViewSet, basename='complaint')
router.register(r"growtag-assignments", GrowTagAssignmentViewSet, basename="growtag-assignments")
router.register(r"customers", CustomerViewSet, basename="customer")
urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include(router.urls)),
    path("zoho/", include("zoho_integration.urls")),
    #path("api/ping/", ping),
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
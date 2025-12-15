
# zoho_integration/urls.py

#from django.urls import path
#from .views import zoho_callback, ZohoItemCreateView,ZohoItemDetailView


# zoho_integration/urls.py
from django.urls import path
from .views import LocalItemDetailSyncView,LocalItemListCreateView
from .views import zoho_callback

urlpatterns = [
    path("callback/", zoho_callback, name="zoho-callback"),
     path("local-items/", LocalItemListCreateView.as_view(), name="local-item-list-create"),
    path("local-items/<int:pk>/", LocalItemDetailSyncView.as_view(), name="local-item-detail-sync"),
]

    



from django.contrib import admin
from django.urls import path
from auto_sell.api import api
from apps.tenants.admin_site import tenant_admin
from apps.dashboard.views import dashboard_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("tenant/", tenant_admin.urls),
    path("tenant/dashboard/", dashboard_view, name="dashboard"),
    path("api/", api.urls),
]

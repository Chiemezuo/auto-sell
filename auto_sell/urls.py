from django.contrib import admin
from django.urls import path
from auto_sell.api import api
from apps.tenants.admin_site import tenant_admin

urlpatterns = [
    path("admin/", admin.site.urls),       # platform admins (superusers)
    path("tenant/", tenant_admin.urls),    # business owners
    path("api/", api.urls),
]

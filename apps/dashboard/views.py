from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from apps.tenants.models import TenantUser


@login_required
def dashboard_view(request):
    tenant = request.user.tenant_profile.tenant
    return render(request, "dashboard/index.html", {"tenant": tenant})

from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.forms import AuthenticationForm


class TenantModelAdmin(admin.ModelAdmin):
    """Base class for all tenant-facing ModelAdmin classes.

    Django's default permission checks require is_staff + explicit model
    permissions. TenantUsers have neither, so we override the two checks
    that gate the index page (has_module_perms) and list/detail views
    (has_view_permission) to return True. Access is already scoped by
    get_queryset on every subclass.
    """

    def has_module_permission(self, request):
        return True

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request):
        return True

    def has_change_permission(self, request, obj=None):
        return True

    def has_delete_permission(self, request, obj=None):
        return True


class TenantAdminSite(AdminSite):
    site_header = "Business Dashboard"
    site_title = "Business Dashboard"
    index_title = "Welcome to your store"

    # Django's admin uses AdminAuthenticationForm by default, which rejects
    # anyone without is_staff=True before has_permission is even called.
    # Swapping it for the standard AuthenticationForm removes that check,
    # leaving has_permission below as the sole gatekeeper.
    login_form = AuthenticationForm

    def has_permission(self, request):
        # Only active users linked to a tenant can access this site.
        # Superusers use /admin/ instead.
        return (
            request.user.is_active
            and not request.user.is_superuser
            and hasattr(request.user, "tenant_profile")
        )


tenant_admin = TenantAdminSite(name="tenant_admin")

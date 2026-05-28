from django.contrib.admin import AdminSite


class TenantAdminSite(AdminSite):
    site_header = "Business Dashboard"
    site_title = "Business Dashboard"
    index_title = "Welcome to your store"

    def has_permission(self, request):
        # Only active users who have been linked to a tenant can log in here.
        # Superusers use /admin/ instead.
        return (
            request.user.is_active
            and not request.user.is_superuser
            and hasattr(request.user, "tenant_profile")
        )


tenant_admin = TenantAdminSite(name="tenant_admin")

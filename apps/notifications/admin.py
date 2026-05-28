from django.contrib import admin
from .models import NotificationLog
from apps.tenants.admin_site import tenant_admin


# --- Platform admin (superusers at /admin/) ---

@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["tenant", "sale", "channel", "status", "sent_at"]
    list_filter = ["tenant", "channel", "status"]
    readonly_fields = ["sent_at", "error"]


# --- Tenant admin (business owners at /tenant/) ---

class TenantNotificationLogAdmin(admin.ModelAdmin):
    list_display = ["sale", "channel", "status", "sent_at"]
    list_filter = ["channel", "status"]
    readonly_fields = ["sale", "channel", "status", "error", "sent_at"]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            tenant=request.user.tenant_profile.tenant
        )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


tenant_admin.register(NotificationLog, TenantNotificationLogAdmin)

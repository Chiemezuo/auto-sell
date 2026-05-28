from django.contrib import admin
from .models import PaymentLink, Sale
from apps.tenants.admin_site import tenant_admin


# --- Platform admin (superusers at /admin/) ---

@admin.register(PaymentLink)
class PaymentLinkAdmin(admin.ModelAdmin):
    list_display = ["gateway_reference", "tenant", "amount", "currency", "status", "created_at", "paid_at"]
    list_filter = ["tenant", "status", "gateway"]
    search_fields = ["gateway_reference", "conversation__customer_wa_id"]
    readonly_fields = ["id", "created_at", "paid_at"]


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ["id", "tenant", "customer_wa_id", "amount_paid", "created_at"]
    list_filter = ["tenant"]
    search_fields = ["customer_wa_id"]
    readonly_fields = ["id", "created_at", "gateway_payload", "items_snapshot"]


# --- Tenant admin (business owners at /tenant/) ---

class TenantSaleAdmin(admin.ModelAdmin):
    list_display = ["customer_wa_id", "amount_paid", "created_at"]
    search_fields = ["customer_wa_id"]
    readonly_fields = ["id", "customer_wa_id", "amount_paid", "items_snapshot", "created_at"]

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


tenant_admin.register(Sale, TenantSaleAdmin)

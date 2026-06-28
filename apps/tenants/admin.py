from django.contrib import admin
from .models import Tenant, TenantUser
from .admin_site import tenant_admin, TenantModelAdmin


class TenantUserInline(admin.TabularInline):
    model = TenantUser
    extra = 1


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "owner_email", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name", "slug", "owner_email"]
    prepopulated_fields = {"slug": ("name",)}
    readonly_fields = ["created_at"]
    inlines = [TenantUserInline]
    fieldsets = [
        (None, {"fields": ["name", "slug", "is_active"]}),
        ("WhatsApp Credentials", {"fields": ["wa_phone_number_id", "wa_business_account_id", "wa_access_token", "wa_app_secret", "wa_webhook_verify_token"], "classes": ["collapse"]}),
        ("Owner Contact", {"fields": ["owner_phone", "owner_email"]}),
        ("LLM Instructions", {"fields": ["platform_instructions", "custom_instructions"], "classes": ["collapse"]}),
        ("Metadata", {"fields": ["created_at"]}),
    ]


@admin.register(TenantUser)
class TenantUserAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "created_at"]
    list_filter = ["tenant"]
    search_fields = ["user__email", "tenant__name"]


class TenantProfileAdmin(TenantModelAdmin):
    """Tenant-facing view: owners can read their store info and edit custom_instructions only."""

    readonly_fields = ["name", "slug", "owner_phone", "owner_email", "platform_instructions", "created_at"]
    fieldsets = [
        ("Store Info", {"fields": ["name", "slug"]}),
        ("Contact", {"fields": ["owner_phone", "owner_email"]}),
        ("Bot Instructions", {
            "fields": ["platform_instructions", "custom_instructions"],
            "description": "Use 'Bot Instructions' to personalise your assistant — add delivery rules, a custom name, language preferences, or upsell hints. The fields above this box are set by the platform and are read-only.",
        }),
        ("Metadata", {"fields": ["created_at"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(pk=request.user.tenant_profile.tenant_id)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


tenant_admin.register(Tenant, TenantProfileAdmin)

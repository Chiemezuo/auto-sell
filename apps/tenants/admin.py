from django.contrib import admin
from .models import Tenant, TenantUser


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
        ("Metadata", {"fields": ["created_at"]}),
    ]


@admin.register(TenantUser)
class TenantUserAdmin(admin.ModelAdmin):
    list_display = ["user", "tenant", "created_at"]
    list_filter = ["tenant"]
    search_fields = ["user__email", "tenant__name"]

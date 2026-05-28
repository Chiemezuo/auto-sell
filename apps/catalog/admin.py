from django.contrib import admin
from .models import Product, ProductMedia
from apps.tenants.admin_site import tenant_admin


class ProductMediaInline(admin.TabularInline):
    model = ProductMedia
    extra = 1
    readonly_fields = ["wa_media_id"]
    fields = ["media_type", "s3_key", "cdn_url", "sort_order", "wa_media_id"]


# --- Platform admin (superusers at /admin/) ---

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "tenant", "price_min", "price_max", "currency", "is_available", "updated_at"]
    list_filter = ["tenant", "is_available", "currency"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at", "search_vector"]
    inlines = [ProductMediaInline]
    fieldsets = [
        (None, {"fields": ["tenant", "name", "description", "is_available"]}),
        ("Pricing", {"fields": ["price_min", "price_max", "currency"]}),
        ("Metadata", {"fields": ["created_at", "updated_at", "search_vector"]}),
    ]


@admin.register(ProductMedia)
class ProductMediaAdmin(admin.ModelAdmin):
    list_display = ["product", "media_type", "sort_order", "wa_media_id"]
    list_filter = ["media_type"]
    readonly_fields = ["wa_media_id"]


# --- Tenant admin (business owners at /tenant/) ---

class TenantProductAdmin(admin.ModelAdmin):
    list_display = ["name", "price_min", "price_max", "currency", "is_available", "updated_at"]
    list_filter = ["is_available", "currency"]
    search_fields = ["name", "description"]
    readonly_fields = ["created_at", "updated_at", "search_vector"]
    inlines = [ProductMediaInline]
    fieldsets = [
        (None, {"fields": ["name", "description", "is_available"]}),
        ("Pricing", {"fields": ["price_min", "price_max", "currency"]}),
        ("Metadata", {"fields": ["created_at", "updated_at"]}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            tenant=request.user.tenant_profile.tenant
        )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.tenant = request.user.tenant_profile.tenant
        super().save_model(request, obj, form, change)


tenant_admin.register(Product, TenantProductAdmin)

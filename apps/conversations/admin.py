from django.contrib import admin
from .models import Conversation, Message
from apps.tenants.admin_site import tenant_admin, TenantModelAdmin


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ["role", "content", "wa_message_id", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


# --- Platform admin (superusers at /admin/) ---

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["customer_wa_id", "tenant", "state", "created_at", "last_message_at"]
    list_filter = ["tenant", "state"]
    search_fields = ["customer_wa_id"]
    readonly_fields = ["id", "created_at", "last_message_at"]
    inlines = [MessageInline]


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ["conversation", "role", "created_at"]
    list_filter = ["role"]
    search_fields = ["content", "wa_message_id"]
    readonly_fields = ["created_at"]


# --- Tenant admin (business owners at /tenant/) ---

class TenantMessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ["role", "content", "wa_message_id", "created_at"]
    can_delete = False

    def has_view_permission(self, request, obj=None):
        return True

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


class TenantConversationAdmin(TenantModelAdmin):
    list_display = ["customer_wa_id", "state", "created_at", "last_message_at"]
    list_filter = ["state"]
    search_fields = ["customer_wa_id"]
    readonly_fields = ["id", "customer_wa_id", "state", "context_summary", "created_at", "last_message_at"]
    inlines = [TenantMessageInline]

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


tenant_admin.register(Conversation, TenantConversationAdmin)

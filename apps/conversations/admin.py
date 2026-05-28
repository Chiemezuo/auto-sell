from django.contrib import admin
from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ["role", "content", "wa_message_id", "created_at"]
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


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

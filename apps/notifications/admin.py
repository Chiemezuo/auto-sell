from django.contrib import admin
from .models import NotificationLog


@admin.register(NotificationLog)
class NotificationLogAdmin(admin.ModelAdmin):
    list_display = ["tenant", "sale", "channel", "status", "sent_at"]
    list_filter = ["tenant", "channel", "status"]
    readonly_fields = ["sent_at", "error"]

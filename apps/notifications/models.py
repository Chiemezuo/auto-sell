from django.db import models
from apps.tenants.models import Tenant
from apps.payments.models import Sale


class NotificationLog(models.Model):
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNELS = [(CHANNEL_WHATSAPP, "WhatsApp")]

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUSES = [(STATUS_SENT, "Sent"), (STATUS_FAILED, "Failed")]

    EVENT_SALE = "sale"
    EVENT_ESCALATION = "escalation"
    EVENT_STOCK_OUT = "stock_out"
    EVENT_DAILY_DIGEST = "daily_digest"
    EVENTS = [
        (EVENT_SALE, "Sale confirmed"),
        (EVENT_ESCALATION, "Escalation alert"),
        (EVENT_STOCK_OUT, "Stock out"),
        (EVENT_DAILY_DIGEST, "Daily digest"),
    ]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="notifications")
    sale = models.ForeignKey(
        Sale, on_delete=models.CASCADE, related_name="notifications", null=True, blank=True
    )
    event_type = models.CharField(max_length=32, choices=EVENTS, default=EVENT_SALE)
    channel = models.CharField(max_length=32, choices=CHANNELS, default=CHANNEL_WHATSAPP)
    status = models.CharField(max_length=16, choices=STATUSES)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        target = f"sale {self.sale_id}" if self.sale_id else self.event_type
        return f"{self.channel} {target} — {self.status}"

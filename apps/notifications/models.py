from django.db import models
from apps.tenants.models import Tenant
from apps.payments.models import Sale


class NotificationLog(models.Model):
    CHANNEL_WHATSAPP = "whatsapp"
    CHANNELS = [(CHANNEL_WHATSAPP, "WhatsApp")]

    STATUS_SENT = "sent"
    STATUS_FAILED = "failed"
    STATUSES = [(STATUS_SENT, "Sent"), (STATUS_FAILED, "Failed")]

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="notifications")
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="notifications")
    channel = models.CharField(max_length=32, choices=CHANNELS, default=CHANNEL_WHATSAPP)
    status = models.CharField(max_length=16, choices=STATUSES)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-sent_at"]

    def __str__(self):
        return f"{self.channel} alert for sale {self.sale_id} — {self.status}"

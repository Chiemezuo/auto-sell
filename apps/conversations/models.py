from uuid import uuid4
from django.db import models
from apps.tenants.models import Tenant


class Conversation(models.Model):
    STATE_ACTIVE = "active"
    STATE_AWAITING_PAYMENT = "awaiting_payment"
    STATE_COMPLETED = "completed"
    STATE_ABANDONED = "abandoned"
    STATES = [
        (STATE_ACTIVE, "Active"),
        (STATE_AWAITING_PAYMENT, "Awaiting Payment"),
        (STATE_COMPLETED, "Completed"),
        (STATE_ABANDONED, "Abandoned"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="conversations")
    customer_wa_id = models.CharField(max_length=32, help_text="Customer's WhatsApp phone number")
    state = models.CharField(max_length=32, choices=STATES, default=STATE_ACTIVE)
    context_summary = models.TextField(blank=True, help_text="Written to DB when conversation ends")
    created_at = models.DateTimeField(auto_now_add=True)
    last_message_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("tenant", "customer_wa_id")]
        ordering = ["-last_message_at"]

    def __str__(self):
        return f"{self.customer_wa_id} @ {self.tenant.name} [{self.state}]"


class Message(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_SYSTEM, "System"),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=ROLES)
    content = models.TextField()
    wa_message_id = models.CharField(max_length=128, blank=True, db_index=True, help_text="Used for deduplication")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"

from uuid import uuid4
from django.db import models
from apps.tenants.models import Tenant


class Conversation(models.Model):
    STATE_ACTIVE = "active"
    STATE_AWAITING_PAYMENT = "awaiting_payment"
    STATE_COMPLETED = "completed"
    STATE_ABANDONED = "abandoned"
    STATE_ESCALATED = "escalated"
    STATE_OWNER_HANDLING = "owner_handling"
    STATE_CO_PILOT_DRAFTING = "co_pilot_drafting"
    STATES = [
        (STATE_ACTIVE, "Active"),
        (STATE_AWAITING_PAYMENT, "Awaiting Payment"),
        (STATE_COMPLETED, "Completed"),
        (STATE_ABANDONED, "Abandoned"),
        (STATE_ESCALATED, "Escalated"),
        (STATE_OWNER_HANDLING, "Owner Handling"),
        (STATE_CO_PILOT_DRAFTING, "Co-Pilot Drafting"),
    ]

    PHASE_GREETING = "greeting"
    PHASE_DISCOVERY = "discovery"
    PHASE_RECOMMENDATION = "recommendation"
    PHASE_NEGOTIATION = "negotiation"
    PHASE_CLOSE = "close"
    PHASES = [
        (PHASE_GREETING, "Greeting"),
        (PHASE_DISCOVERY, "Discovery"),
        (PHASE_RECOMMENDATION, "Recommendation"),
        (PHASE_NEGOTIATION, "Negotiation"),
        (PHASE_CLOSE, "Close"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="conversations")
    customer_wa_id = models.CharField(max_length=32, help_text="Customer's WhatsApp phone number")
    state = models.CharField(max_length=32, choices=STATES, default=STATE_ACTIVE)
    phase = models.CharField(max_length=32, choices=PHASES, default=PHASE_GREETING)
    co_pilot_mode = models.CharField(
        max_length=32,
        default="inherit",
        choices=[("inherit", "Inherit"), ("autonomous", "Autonomous"), ("co_pilot", "Co-Pilot")],
        help_text="Per-conversation override for co-pilot mode. 'inherit' uses the tenant default.",
    )
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
    prompt_version = models.CharField(max_length=64, blank=True, help_text="Identifier for the prompt version that generated this message")
    sent_by_owner = models.BooleanField(default=False, help_text="True if sent by the business owner via dashboard")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"[{self.role}] {self.content[:60]}"


class BotFeedback(models.Model):
    FEEDBACK_GOOD = "good"
    FEEDBACK_BAD = "bad"
    FEEDBACK_EDITED = "edited"
    FEEDBACK_TYPES = [
        (FEEDBACK_GOOD, "Good"),
        (FEEDBACK_BAD, "Bad"),
        (FEEDBACK_EDITED, "Edited"),
    ]

    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="feedback")
    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="feedback", help_text="The bot message that received feedback")
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="feedback")
    feedback_type = models.CharField(max_length=16, choices=FEEDBACK_TYPES)
    owner_note = models.TextField(blank=True)
    edited_response = models.TextField(blank=True, help_text="Owner's corrected version when type is 'edited'")
    context_snapshot = models.JSONField(default=list, help_text="Last 5 messages for context")
    prompt_version = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.feedback_type} on message {self.message_id}"

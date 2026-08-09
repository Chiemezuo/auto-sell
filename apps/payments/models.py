from uuid import uuid4
from django.db import models
from apps.tenants.models import Tenant
from apps.conversations.models import Conversation


class PaymentLink(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUS_REFUNDED = "refunded"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_FAILED, "Failed"),
        (STATUS_REFUNDED, "Refunded"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="payment_links")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="payment_links")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    gateway = models.CharField(max_length=32, default="paystack")
    gateway_reference = models.CharField(max_length=255, unique=True)
    payment_url = models.URLField()
    status = models.CharField(max_length=16, choices=STATUSES, default=STATUS_PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.gateway_reference} — {self.status}"


class Sale(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    payment_link = models.OneToOneField(PaymentLink, on_delete=models.PROTECT, related_name="sale")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="sales")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="sales")
    customer_wa_id = models.CharField(max_length=32)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2)
    items_snapshot = models.JSONField(help_text="What the customer agreed to buy")
    gateway_payload = models.JSONField(help_text="Raw webhook body from payment gateway")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sale {self.id} — {self.customer_wa_id} — {self.amount_paid} {self.payment_link.currency}"


class PostSaleFollowUp(models.Model):
    SCHEDULE_DAY_1 = "day_1"
    SCHEDULE_DAY_5 = "day_5"
    SCHEDULE_DAY_14 = "day_14"
    SCHEDULE_DAY_30 = "day_30"
    SCHEDULE_CART_2H = "cart_2h"
    SCHEDULE_CART_6H = "cart_6h"
    SCHEDULE_TYPES = [
        (SCHEDULE_DAY_1, "Day 1 — Delivery Check-In"),
        (SCHEDULE_DAY_5, "Day 5 — Feedback Request"),
        (SCHEDULE_DAY_14, "Day 14 — Re-Engagement"),
        (SCHEDULE_DAY_30, "Day 30 — Win-Back"),
        (SCHEDULE_CART_2H, "Cart 2h — First Nudge"),
        (SCHEDULE_CART_6H, "Cart 6h — Second Nudge"),
    ]

    STATUS_PENDING = "pending"
    STATUS_SENT = "sent"
    STATUS_CANCELLED = "cancelled"
    STATUS_FAILED = "failed"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SENT, "Sent"),
        (STATUS_CANCELLED, "Cancelled"),
        (STATUS_FAILED, "Failed"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="follow_ups", null=True, blank=True)
    payment_link = models.ForeignKey(PaymentLink, on_delete=models.CASCADE, related_name="follow_ups", null=True, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="follow_ups")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="follow_ups")
    schedule_type = models.CharField(max_length=16, choices=SCHEDULE_TYPES)
    scheduled_at = models.DateTimeField()
    status = models.CharField(max_length=16, choices=STATUSES, default=STATUS_PENDING)
    message_content = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheduled_at"]

    def __str__(self):
        return f"{self.schedule_type} for {self.conversation_id} — {self.status}"

from uuid import uuid4
from django.db import models
from apps.tenants.models import Tenant
from apps.conversations.models import Conversation


class PaymentLink(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_EXPIRED = "expired"
    STATUS_FAILED = "failed"
    STATUSES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_EXPIRED, "Expired"),
        (STATUS_FAILED, "Failed"),
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

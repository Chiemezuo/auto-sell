from uuid import uuid4
from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()


class Tenant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, help_text="Used in webhook URL: /api/webhooks/whatsapp/{slug}/")

    wa_phone_number_id = models.CharField(max_length=64, unique=True)
    wa_business_account_id = models.CharField(max_length=64)
    wa_access_token = models.TextField(help_text="WhatsApp Cloud API access token")
    wa_webhook_verify_token = models.CharField(max_length=128)

    owner_phone = models.CharField(max_length=32, help_text="Phone number for sale alerts (with country code, e.g. 2348012345678)")
    owner_email = models.EmailField()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class TenantUser(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="users")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="tenant_profile")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tenant"]

    def __str__(self):
        return f"{self.user.email} @ {self.tenant.name}"

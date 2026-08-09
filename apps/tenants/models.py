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
    wa_app_secret = models.CharField(max_length=255, help_text="Meta App Secret — used to verify inbound webhook signatures")
    wa_webhook_verify_token = models.CharField(max_length=128)

    owner_phone = models.CharField(max_length=32, help_text="Phone number for sale alerts (with country code, e.g. 2348012345678)")
    owner_email = models.EmailField()

    platform_instructions = models.TextField(
        blank=True,
        help_text="Platform-level LLM instructions: persona, language rules, delivery constraints. Injected into the system prompt after core pricing/tool rules.",
    )
    custom_instructions = models.TextField(
        blank=True,
        help_text="Tenant-editable extras: upsell rules, persona name tweaks, product-specific notes. Appended after platform instructions.",
    )

    personality = models.JSONField(
        default=dict,
        blank=True,
        help_text="Bot personality config: tone (friendly/professional/enthusiastic/casual/formal), formality (casual/professional/formal), emoji_level (none/moderate/liberal)",
    )
    primary_llm_provider = models.CharField(
        max_length=32,
        default="deepseek",
        help_text="LLM provider key for response generation: deepseek, openai, anthropic",
    )
    classification_llm_provider = models.CharField(
        max_length=32,
        default="deepseek",
        help_text="LLM provider key for sentiment/intent classification",
    )
    co_pilot_mode = models.CharField(
        max_length=32,
        default="autonomous",
        choices=[("autonomous", "Autonomous"), ("co_pilot", "Co-Pilot")],
        help_text="Default mode for new conversations: autonomous (bot replies directly) or co_pilot (bot drafts, owner approves)",
    )

    is_active = models.BooleanField(default=True)
    bot_paused = models.BooleanField(
        default=False,
        help_text="When True, the bot replies 'temporarily unavailable' to all customer messages.",
    )
    follow_up_enabled = models.BooleanField(
        default=False,
        help_text="When True, post-purchase follow-up messages are sent to customers.",
    )
    follow_up_templates = models.JSONField(
        default=dict,
        blank=True,
        help_text="Customized follow-up message templates. Keys: day_1, day_5, day_14, day_30, cart_2h, cart_6h.",
    )
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

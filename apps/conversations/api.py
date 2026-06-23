import hmac
import hashlib
import json
import logging
from ninja import Router
from ninja.errors import HttpError
from pydantic import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from apps.tenants.models import Tenant
from .models import Message
from .schemas import WAWebhookPayload
from .tasks import process_message, reply_unsupported_message

logger = logging.getLogger(__name__)

router = Router(tags=["Webhooks"])


@router.get("/whatsapp/{tenant_slug}/")
def verify_webhook(request: HttpRequest, tenant_slug: str):
    hub_mode = request.GET.get("hub.mode", "")
    hub_verify_token = request.GET.get("hub.verify_token", "")
    hub_challenge = request.GET.get("hub.challenge", "")

    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)
    if hub_mode == "subscribe" and hub_verify_token == tenant.wa_webhook_verify_token:
        return HttpResponse(hub_challenge, content_type="text/plain")
    raise HttpError(403, "Forbidden")


@router.post("/whatsapp/{tenant_slug}/")
def receive_message(request: HttpRequest, tenant_slug: str):
    tenant = get_object_or_404(Tenant, slug=tenant_slug, is_active=True)

    signature = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        tenant.wa_app_secret.encode(),
        request.body,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise HttpError(403, "Invalid signature")

    try:
        payload = WAWebhookPayload.model_validate(json.loads(request.body))
    except ValidationError:
        logger.warning("Malformed WhatsApp webhook payload from tenant %s", tenant_slug)
        return {"status": "ok"}  # always 200 to Meta; bad shape means nothing to process

    for entry in payload.entry:
        for change in entry.changes:
            for message in change.value.messages:
                if message.type != "text":
                    reply_unsupported_message.delay(str(tenant.id), message.from_)
                    continue

                if Message.objects.filter(wa_message_id=message.id).exists():
                    continue  # already processed — Meta is retrying

                process_message.delay(
                    tenant_id=str(tenant.id),
                    customer_wa_id=message.from_,
                    message_text=message.text.body,
                    wa_message_id=message.id,
                )

    return {"status": "ok"}

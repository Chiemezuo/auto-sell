import json
import logging
import mimetypes
import redis
from celery import shared_task
from datetime import timedelta

logger = logging.getLogger(__name__)
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.catalog.models import Product
from apps.catalog.search import get_relevant_products
from .models import Conversation, Message
from .whatsapp import WhatsAppClient
from .llm import chat
from .prompts import build_system_prompt, TOOLS

HISTORY_TTL = 72 * 3600
HISTORY_MAX = 20
LOCK_TTL = 30
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60  # seconds


def _check_rate_limit(r, tenant_id: str, customer_wa_id: str) -> bool:
    rate_key = f"rate:{tenant_id}:{customer_wa_id}"
    count = r.incr(rate_key)
    if count == 1:
        r.expire(rate_key, RATE_LIMIT_WINDOW)
    return count > RATE_LIMIT_MAX


def _redis():
    return redis.from_url(settings.REDIS_URL)


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_message(self, tenant_id: str, customer_wa_id: str, message_text: str, wa_message_id: str):
    r = _redis()
    if _check_rate_limit(r, tenant_id, customer_wa_id):
        logger.info("Rate limit hit for customer %s on tenant %s", customer_wa_id, tenant_id)
        try:
            tenant = Tenant.objects.get(id=tenant_id, is_active=True)
        except Tenant.DoesNotExist:
            return
        WhatsAppClient(tenant).send_text(
            customer_wa_id,
            "You're sending messages too fast. Please wait a moment and try again.",
        )
        return
    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return

    conversation, created = Conversation.objects.get_or_create(
        tenant=tenant,
        customer_wa_id=customer_wa_id,
        defaults={"state": Conversation.STATE_ACTIVE},
    )
    if not created and conversation.state in (
        Conversation.STATE_COMPLETED,
        Conversation.STATE_ABANDONED,
    ):
        conversation.state = Conversation.STATE_ACTIVE
        conversation.save(update_fields=["state"])
        r.delete(f"conversation:{conversation.id}:history")
        r.delete(f"conversation:{conversation.id}:products")

    lock_key = f"conversation:{conversation.id}:lock"
    if not r.set(lock_key, "1", nx=True, ex=LOCK_TTL):
        return  # another worker is already processing this conversation

    try:
        if conversation.state == Conversation.STATE_ESCALATED:
            return  # human has taken over — bot stays silent

        if conversation.state == Conversation.STATE_AWAITING_PAYMENT:
            from apps.payments.models import PaymentLink
            latest_link = conversation.payment_links.order_by("-created_at").first()
            if latest_link and latest_link.status == PaymentLink.STATUS_PENDING:
                WhatsAppClient(tenant).send_text(
                    customer_wa_id,
                    "Your payment link is still active — please complete the payment to confirm your order.",
                )
                return
            # Link expired, failed, or absent — reset so the LLM can re-engage
            conversation.state = Conversation.STATE_ACTIVE
            conversation.save(update_fields=["state"])

        history_key = f"conversation:{conversation.id}:history"
        products_key = f"conversation:{conversation.id}:products"
        history = [json.loads(m) for m in r.lrange(history_key, 0, -1)]

        user_msg = {"role": "user", "content": message_text}

        fresh_products = get_relevant_products(tenant.id, message_text)
        if fresh_products:
            # New or changed product interest — update the cache
            r.set(products_key, json.dumps([str(p.id) for p in fresh_products]), ex=HISTORY_TTL)
            products = fresh_products
        else:
            # Conversational message — reuse previously matched products
            cached_ids = json.loads(r.get(products_key) or "[]")
            products = Product.objects.prefetch_related("media").filter(id__in=cached_ids)

        system_prompt = build_system_prompt(tenant, products)

        messages = [{"role": "system", "content": system_prompt}] + history + [user_msg]
        response = chat(messages, tools=TOOLS)
        assistant_msg = response.choices[0].message

        wa_client = WhatsAppClient(tenant)

        new_history = [json.dumps(user_msg)]

        if assistant_msg.tool_calls:
            new_history.append(json.dumps({
                "role": "assistant",
                "content": assistant_msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in assistant_msg.tool_calls
                ],
            }))
            for tool_call in assistant_msg.tool_calls:
                _dispatch_tool(tool_call, tenant, conversation, customer_wa_id, wa_client)
                new_history.append(json.dumps({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": "done",
                }))

        reply_text = assistant_msg.content or ""
        if reply_text:
            wa_client.send_text(customer_wa_id, reply_text)

        if not assistant_msg.tool_calls:
            new_history.append(json.dumps({"role": "assistant", "content": reply_text}))

        r.rpush(history_key, *new_history)
        r.ltrim(history_key, -HISTORY_MAX, -1)
        r.expire(history_key, HISTORY_TTL)

        with transaction.atomic():
            Message.objects.create(
                conversation=conversation,
                role=Message.ROLE_USER,
                content=message_text,
                wa_message_id=wa_message_id,
            )
            Message.objects.create(
                conversation=conversation,
                role=Message.ROLE_ASSISTANT,
                content=reply_text,
            )
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=["last_message_at"])
    except Exception as exc:
        logger.exception("process_message failed for conversation %s (tenant %s): %s", customer_wa_id, tenant_id, exc)
        r.delete(lock_key)
        raise self.retry(exc=exc)
    finally:
        r.delete(lock_key)


@shared_task
def reply_unsupported_message(tenant_id: str, customer_wa_id: str):
    r = _redis()
    if _check_rate_limit(r, tenant_id, customer_wa_id):
        return  # silent drop — sending another reply would worsen the spam
    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return
    WhatsAppClient(tenant).send_text(
        customer_wa_id,
        "Hi! I can only read text messages. Please type your question and I'll be happy to help.",
    )


@shared_task
def sweep_abandoned_conversations():
    logger.info("Running abandoned conversation sweep")
    now = timezone.now()
    Conversation.objects.filter(
        state=Conversation.STATE_ACTIVE,
        last_message_at__lt=now - timedelta(hours=24),
    ).update(state=Conversation.STATE_ABANDONED)

    Conversation.objects.filter(
        state=Conversation.STATE_AWAITING_PAYMENT,
        last_message_at__lt=now - timedelta(hours=48),
    ).update(state=Conversation.STATE_ABANDONED)


def _dispatch_tool(tool_call, tenant, conversation, customer_wa_id, wa_client):
    name = tool_call.function.name
    args = json.loads(tool_call.function.arguments)

    if name == "send_product_media":
        try:
            product = Product.objects.prefetch_related("media").get(
                id=args["product_id"], tenant=tenant
            )
        except Product.DoesNotExist:
            return
        media = product.media.first()
        if not media:
            return
        if not media.wa_media_id:
            import httpx
            response = httpx.get(media.cdn_url, follow_redirects=True)
            response.raise_for_status()
            file_bytes = response.content
            content_type, _ = mimetypes.guess_type(media.s3_key)
            media.wa_media_id = wa_client.upload_media(file_bytes, content_type or "image/jpeg")
            media.save(update_fields=["wa_media_id"])
        wa_client.send_media(customer_wa_id, media.media_type, media.wa_media_id)

    elif name == "generate_payment_link":
        from apps.payments.tasks import create_payment_link
        create_payment_link.delay(
            conversation_id=str(conversation.id),
            items_snapshot=args.get("items_snapshot", []),
            agreed_price=args["agreed_price"],
        )

    elif name == "escalate_to_human":
        wa_client.send_text(
            customer_wa_id,
            "Let me connect you with our team. Someone will be in touch shortly.",
        )
        conversation.state = Conversation.STATE_ESCALATED
        conversation.save(update_fields=["state"])
        from apps.notifications.tasks import notify_owner_escalation
        notify_owner_escalation.delay(str(conversation.id), args.get("reason", ""))

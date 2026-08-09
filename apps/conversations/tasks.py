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
from apps.catalog.search import hybrid_search
from .models import Conversation, Message
from .whatsapp import WhatsAppClient
from .llm import get_provider
from .prompts import build_system_prompt, TOOLS, PROMPT_VERSION

HISTORY_TTL = 72 * 3600
HISTORY_MAX = 20
LOCK_TTL = 30
RATE_LIMIT_MAX = 10
RATE_LIMIT_WINDOW = 60

SENTIMENT_LABELS = ["happy", "neutral", "frustrated", "confused", "excited", "hesitant"]
NEGOTIATION_KEYWORDS = ["discount", "cheaper", "too much", "too expensive", "last price", "best price",
                         "reduce", "lower", "budget is", "can you do", "will you take", "negotiate"]
PURCHASE_INTENT_KEYWORDS = ["i'll take", "i will take", "send the link", "how do i pay", "how to pay",
                             "i want to buy", "let me pay", "proceed", "checkout", "go ahead", "pay now"]
VAGUE_KEYWORDS = ["what do you have", "what's available", "show me", "something", "anything",
                  "what can i get", "browse", "looking for", "i need a", "i want a"]


def _determine_phase(message_text: str, current_phase: str, products_found: bool) -> str:
    text_lower = message_text.lower().strip()

    if current_phase == Conversation.PHASE_GREETING:
        if any(kw in text_lower for kw in PURCHASE_INTENT_KEYWORDS):
            return Conversation.PHASE_CLOSE
        if any(kw in text_lower for kw in NEGOTIATION_KEYWORDS):
            return Conversation.PHASE_NEGOTIATION
        if any(kw in text_lower for kw in VAGUE_KEYWORDS):
            return Conversation.PHASE_DISCOVERY
        if len(text_lower.split()) <= 2:
            return Conversation.PHASE_DISCOVERY if products_found else Conversation.PHASE_GREETING
        return Conversation.PHASE_RECOMMENDATION

    if current_phase == Conversation.PHASE_DISCOVERY:
        if any(kw in text_lower for kw in PURCHASE_INTENT_KEYWORDS):
            return Conversation.PHASE_CLOSE
        if any(kw in text_lower for kw in NEGOTIATION_KEYWORDS):
            return Conversation.PHASE_NEGOTIATION
        return Conversation.PHASE_RECOMMENDATION

    if current_phase == Conversation.PHASE_RECOMMENDATION:
        if any(kw in text_lower for kw in PURCHASE_INTENT_KEYWORDS):
            return Conversation.PHASE_CLOSE
        if any(kw in text_lower for kw in NEGOTIATION_KEYWORDS):
            return Conversation.PHASE_NEGOTIATION
        return Conversation.PHASE_RECOMMENDATION

    if current_phase == Conversation.PHASE_NEGOTIATION:
        if any(kw in text_lower for kw in PURCHASE_INTENT_KEYWORDS):
            return Conversation.PHASE_CLOSE
        return Conversation.PHASE_NEGOTIATION

    if current_phase == Conversation.PHASE_CLOSE:
        return Conversation.PHASE_CLOSE

    return current_phase


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
            "Whoa, you're faster than I can type! 😅 Give me a moment — what were you looking for?",
        )
        return
    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return

    if tenant.bot_paused:
        WhatsAppClient(tenant).send_text(
            customer_wa_id,
            f"Hi! You're speaking directly with the {tenant.name} team. Please share what you need and we'll respond shortly.",
        )
        return

    conversation, created = Conversation.objects.get_or_create(
        tenant=tenant,
        customer_wa_id=customer_wa_id,
        defaults={"state": Conversation.STATE_ACTIVE, "phase": Conversation.PHASE_GREETING},
    )

    returning = False
    if not created and conversation.state == Conversation.STATE_ABANDONED:
        conversation.state = Conversation.STATE_ACTIVE
        conversation.phase = Conversation.PHASE_GREETING
        conversation.save(update_fields=["state", "phase"])
        r.delete(f"conversation:{conversation.id}:history")
        r.delete(f"conversation:{conversation.id}:products")
        returning = True

    lock_key = f"conversation:{conversation.id}:lock"
    if not r.set(lock_key, "1", nx=True, ex=LOCK_TTL):
        return

    try:
        if conversation.state in (Conversation.STATE_ESCALATED, Conversation.STATE_COMPLETED):
            return

        if conversation.state in (Conversation.STATE_OWNER_HANDLING, Conversation.STATE_CO_PILOT_DRAFTING):
            return

        if conversation.state == Conversation.STATE_AWAITING_PAYMENT:
            from apps.payments.models import PaymentLink
            latest_link = conversation.payment_links.order_by("-created_at").first()
            if latest_link and latest_link.status == PaymentLink.STATUS_PENDING:
                WhatsAppClient(tenant).send_text(
                    customer_wa_id,
                    "Your payment link is still active — please complete the payment to confirm your order.",
                )
                return
            conversation.state = Conversation.STATE_ACTIVE
            conversation.save(update_fields=["state"])

        # Sentiment classification (Tier 1)
        sentiment = None
        try:
            classification_provider = get_provider(tenant, "classification")
            sentiment = classification_provider.classify(message_text, SENTIMENT_LABELS)
            logger.info("Sentiment for %s: %s", customer_wa_id, sentiment)
        except Exception:
            logger.exception("Sentiment classification failed, continuing without sentiment")

        # Phase determination
        products_key = f"conversation:{conversation.id}:products"
        fresh_products = hybrid_search(tenant.id, message_text)
        if fresh_products:
            r.set(products_key, json.dumps([str(p.id) for p in fresh_products]), ex=HISTORY_TTL)
            products = fresh_products
        else:
            cached_ids = json.loads(r.get(products_key) or "[]")
            products = Product.objects.prefetch_related("media").filter(id__in=cached_ids)

        new_phase = _determine_phase(message_text, conversation.phase, bool(fresh_products))
        conversation.phase = new_phase
        conversation.save(update_fields=["phase"])

        history_key = f"conversation:{conversation.id}:history"
        history = [json.loads(m) for m in r.lrange(history_key, 0, -1)]

        # Returning customer acknowledgment
        if returning or (not created and conversation.context_summary and len(history) == 0):
            returning_note = ""
            if conversation.context_summary:
                returning_note = f"\n\nThe customer is returning after a previous interaction. Context: {conversation.context_summary}"
            message_text_with_context = message_text + returning_note
        else:
            message_text_with_context = message_text

        user_msg = {"role": "user", "content": message_text}

        system_prompt = build_system_prompt(tenant, products, phase=new_phase, sentiment=sentiment)

        messages = [{"role": "system", "content": system_prompt}] + history + [user_msg]
        provider = get_provider(tenant, "primary")
        response = provider.chat(messages, tools=TOOLS)
        assistant_msg = response.choices[0].message

        wa_client = WhatsAppClient(tenant)

        new_history = [json.dumps(user_msg)]

        reply_text = assistant_msg.content or ""
        if reply_text:
            wa_client.send_text(customer_wa_id, reply_text)

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
        else:
            new_history.append(json.dumps({"role": "assistant", "content": reply_text}))

        r.rpush(history_key, *new_history)
        r.ltrim(history_key, -HISTORY_MAX, -1)
        r.expire(history_key, HISTORY_TTL)

        while True:
            head = r.lindex(history_key, 0)
            if head is None or json.loads(head).get("role") != "tool":
                break
            r.lpop(history_key)

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
                prompt_version=PROMPT_VERSION,
            )
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=["last_message_at"])

        _publish_conversation_event(tenant_id, conversation, reply_text)
    except Exception as exc:
        logger.exception("process_message failed for conversation %s (tenant %s): %s", customer_wa_id, tenant_id, exc)
        r.delete(lock_key)
        raise self.retry(exc=exc)
    finally:
        r.delete(lock_key)


UNSUPPORTED_REPLIES = {
    "image": "I see you sent a photo! 👀 I can only read text right now — could you describe what you're looking for instead?",
    "audio": "I received your voice note! 🎤 I can only work with text at the moment. Could you type your question? I'd love to help.",
    "voice": "I received your voice note! 🎤 I can only work with text at the moment. Could you type your question? I'd love to help.",
    "video": "I see you sent a video! 📹 I can only work with text right now. Tell me what you're looking for and I'll help you out.",
    "sticker": "Nice sticker! 😄 I can only read text though — type what you need and I'm all ears.",
    "document": "I see you sent a document! 📄 I can only work with text right now. Describe what you need and I'll help.",
    "location": "I see you shared a location! 📍 I can only work with text — what can I help you find?",
}


@shared_task
def reply_unsupported_message(tenant_id: str, customer_wa_id: str, message_type: str = "unknown"):
    r = _redis()
    if _check_rate_limit(r, tenant_id, customer_wa_id):
        return
    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return
    reply = UNSUPPORTED_REPLIES.get(message_type, "I can only read text messages right now. Please type your question and I'll be happy to help.")
    WhatsAppClient(tenant).send_text(customer_wa_id, reply)


@shared_task
def handle_owner_command(tenant_id: str, text: str):
    from .owner_commands import dispatch
    dispatch(tenant_id, text)


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


def _publish_conversation_event(tenant_id: str, conversation, reply_text: str):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer:
            group = f"dashboard_{tenant_id}"
            async_to_sync(channel_layer.group_send)(
                group,
                {
                    "type": "new_message",
                    "conversation_id": str(conversation.id),
                    "role": "assistant",
                    "content": reply_text[:200],
                    "created_at": timezone.now().isoformat(),
                },
            )
            async_to_sync(channel_layer.group_send)(
                group,
                {
                    "type": "conversation_update",
                    "conversation_id": str(conversation.id),
                    "customer_wa_id": conversation.customer_wa_id,
                    "state": conversation.state,
                    "last_message_at": timezone.now().isoformat(),
                },
            )
    except Exception:
        logger.debug("Failed to publish dashboard event", exc_info=True)


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
        agreed_price = float(args["agreed_price"])
        items = args.get("items_snapshot", [])
        for item in items:
            try:
                product = Product.objects.get(id=item.get("product_id"), tenant=tenant)
            except Product.DoesNotExist:
                continue
            if agreed_price < float(product.price_min):
                logger.warning("generate_payment_link rejected: agreed_price %s < floor_price %s for product %s",
                               agreed_price, product.price_min, product.id)
                return
        from apps.payments.tasks import create_payment_link
        create_payment_link.delay(
            conversation_id=str(conversation.id),
            items_snapshot=items,
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

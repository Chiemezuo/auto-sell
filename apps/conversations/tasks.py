import json
import mimetypes
import redis
from celery import shared_task
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


def _redis():
    return redis.from_url(settings.REDIS_URL)


@shared_task
def process_message(tenant_id: str, customer_wa_id: str, message_text: str, wa_message_id: str):
    r = _redis()
    try:
        tenant = Tenant.objects.get(id=tenant_id, is_active=True)
    except Tenant.DoesNotExist:
        return

    conversation, _ = Conversation.objects.get_or_create(
        tenant=tenant,
        customer_wa_id=customer_wa_id,
        defaults={"state": Conversation.STATE_ACTIVE},
    )

    lock_key = f"conversation:{conversation.id}:lock"
    if not r.set(lock_key, "1", nx=True, ex=LOCK_TTL):
        return  # another worker is already processing this conversation

    try:
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

        if assistant_msg.tool_calls:
            for tool_call in assistant_msg.tool_calls:
                _dispatch_tool(tool_call, tenant, conversation, customer_wa_id, wa_client)

        reply_text = assistant_msg.content or ""
        if reply_text:
            wa_client.send_text(customer_wa_id, reply_text)

        r.rpush(history_key, json.dumps(user_msg), json.dumps({"role": "assistant", "content": reply_text}))
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
    finally:
        r.delete(lock_key)


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
            file_bytes = httpx.get(media.cdn_url).content
            content_type, _ = mimetypes.guess_type(media.s3_key)
            media.wa_media_id = wa_client.upload_media(file_bytes, content_type or "image/jpeg")
            media.save(update_fields=["wa_media_id"])
        wa_client.send_media(customer_wa_id, media.media_type, media.wa_media_id)

    elif name == "generate_payment_link":
        from apps.payments.tasks import create_payment_link  # implemented in Step 3
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

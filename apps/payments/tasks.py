import logging
from datetime import timedelta
from decimal import Decimal
from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)
from apps.conversations.models import Conversation
from apps.conversations.whatsapp import WhatsAppClient
from .models import PaymentLink, PostSaleFollowUp
from .gateways.paystack import PaystackGateway


@shared_task
def create_payment_link(conversation_id: str, items_snapshot: list, agreed_price: float):
    try:
        conversation = Conversation.objects.select_related("tenant").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return

    tenant = conversation.tenant
    gateway = PaystackGateway()

    email = f"{conversation.customer_wa_id}@autosell.app"

    result = gateway.initialize_transaction(
        amount=float(agreed_price),
        email=email,
        metadata={
            "conversation_id": str(conversation.id),
            "customer_wa_id": conversation.customer_wa_id,
            "items_snapshot": items_snapshot,
        },
    )

    with transaction.atomic():
        payment_link = PaymentLink.objects.create(
            conversation=conversation,
            tenant=tenant,
            amount=Decimal(str(agreed_price)),
            currency="NGN",
            gateway="paystack",
            gateway_reference=result["reference"],
            payment_url=result["authorization_url"],
        )
        conversation.state = Conversation.STATE_AWAITING_PAYMENT
        conversation.save(update_fields=["state"])

    logger.info("Payment link created for conversation %s (ref: %s)", conversation_id, result["reference"])

    _schedule_cart_follow_ups(tenant, conversation, payment_link)

    wa_client = WhatsAppClient(tenant)
    wa_client.send_text(
        conversation.customer_wa_id,
        f"Great! Here's your secure payment link:\n\n{payment_link.payment_url}\n\n"
        "Complete your payment to confirm the order.",
    )


def _schedule_cart_follow_ups(tenant, conversation, payment_link):
    if not tenant.follow_up_enabled:
        return
    now = timezone.now()
    PostSaleFollowUp.objects.create(
        payment_link=payment_link,
        tenant=tenant,
        conversation=conversation,
        schedule_type=PostSaleFollowUp.SCHEDULE_CART_2H,
        scheduled_at=now + timedelta(hours=2),
    )
    PostSaleFollowUp.objects.create(
        payment_link=payment_link,
        tenant=tenant,
        conversation=conversation,
        schedule_type=PostSaleFollowUp.SCHEDULE_CART_6H,
        scheduled_at=now + timedelta(hours=6),
    )


def schedule_post_sale_follow_ups(tenant, conversation, sale):
    if not tenant.follow_up_enabled:
        return
    now = timezone.now()
    for schedule_type, days in [
        (PostSaleFollowUp.SCHEDULE_DAY_1, 1),
        (PostSaleFollowUp.SCHEDULE_DAY_5, 5),
        (PostSaleFollowUp.SCHEDULE_DAY_14, 14),
        (PostSaleFollowUp.SCHEDULE_DAY_30, 30),
    ]:
        PostSaleFollowUp.objects.create(
            sale=sale,
            tenant=tenant,
            conversation=conversation,
            schedule_type=schedule_type,
            scheduled_at=now + timedelta(days=days),
        )


@shared_task
def send_follow_up(follow_up_id: str):
    try:
        follow_up = PostSaleFollowUp.objects.select_related("tenant", "conversation", "sale").get(id=follow_up_id)
    except PostSaleFollowUp.DoesNotExist:
        return

    if follow_up.status != PostSaleFollowUp.STATUS_PENDING:
        return

    tenant = follow_up.tenant
    customer_wa_id = follow_up.conversation.customer_wa_id
    wa_client = WhatsAppClient(tenant)

    messages = {
        PostSaleFollowUp.SCHEDULE_DAY_1: "Hey! Just checking in — did you receive your order? Everything good with it? Let us know if you need anything! 😊",
        PostSaleFollowUp.SCHEDULE_DAY_5: "Hope you're enjoying your purchase! We'd love to hear what you think — your feedback helps us serve you better.",
        PostSaleFollowUp.SCHEDULE_DAY_14: "Hey! We just got some fresh stock in. If you need any accessories or another device, I'm here to help!",
        PostSaleFollowUp.SCHEDULE_DAY_30: "It's been a month! We've got new products this week. Anything you're looking for? Same great prices 😊",
        PostSaleFollowUp.SCHEDULE_CART_2H: "Hey! Still thinking about it? No pressure at all — just want to make sure you got all the info you need. I'm here if you have questions!",
        PostSaleFollowUp.SCHEDULE_CART_6H: "Just checking in one more time — your payment link is still active if you're ready. If the price was an issue, maybe I can suggest an alternative? Let me know!",
    }

    content = tenant.follow_up_templates.get(follow_up.schedule_type) if tenant.follow_up_templates else None
    if not content:
        content = messages.get(follow_up.schedule_type, "")

    if not content:
        return

    try:
        wa_client.send_text(customer_wa_id, content)
        follow_up.status = PostSaleFollowUp.STATUS_SENT
        follow_up.message_content = content
        follow_up.save(update_fields=["status", "message_content"])
        logger.info("Follow-up %s sent to %s", follow_up.schedule_type, customer_wa_id)
    except Exception:
        logger.exception("Failed to send follow-up %s", follow_up_id)
        follow_up.status = PostSaleFollowUp.STATUS_FAILED
        follow_up.save(update_fields=["status"])


@shared_task
def dispatch_due_follow_ups():
    now = timezone.now()
    pending = PostSaleFollowUp.objects.filter(status=PostSaleFollowUp.STATUS_PENDING, scheduled_at__lte=now)
    for follow_up in pending:
        send_follow_up.delay(str(follow_up.id))

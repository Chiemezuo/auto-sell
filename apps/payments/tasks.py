import logging
from decimal import Decimal
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)
from apps.conversations.models import Conversation
from apps.conversations.whatsapp import WhatsAppClient
from .models import PaymentLink
from .gateways.paystack import PaystackGateway


@shared_task
def create_payment_link(conversation_id: str, items_snapshot: list, agreed_price: float):
    try:
        conversation = Conversation.objects.select_related("tenant").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return

    tenant = conversation.tenant
    gateway = PaystackGateway()

    # Paystack requires an email; use a placeholder derived from the WA ID
    # since we only have the customer's phone number at this stage
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
            amount=Decimal(str(agreed_price)),  # via str to avoid float precision loss
            currency="NGN",
            gateway="paystack",
            gateway_reference=result["reference"],
            payment_url=result["authorization_url"],
        )
        conversation.state = Conversation.STATE_AWAITING_PAYMENT
        conversation.save(update_fields=["state"])

    logger.info("Payment link created for conversation %s (ref: %s)", conversation_id, result["reference"])
    # Send outside the transaction — a failed WhatsApp send should not roll back
    # the PaymentLink (it already exists on Paystack's side)
    wa_client = WhatsAppClient(tenant)
    wa_client.send_text(
        conversation.customer_wa_id,
        f"Great! Here's your secure payment link:\n\n{payment_link.payment_url}\n\n"
        "Complete your payment to confirm the order.",
    )

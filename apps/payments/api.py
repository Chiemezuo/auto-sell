import json
from ninja import Router
from ninja.errors import HttpError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from apps.conversations.models import Conversation
from .gateways.paystack import PaystackGateway
from .models import PaymentLink, Sale

router = Router(tags=["Payments"])
_gateway = PaystackGateway()


@router.post("/paystack/webhook/")
def paystack_webhook(request: HttpRequest):
    signature = request.headers.get("X-Paystack-Signature", "")
    if not _gateway.verify_webhook_signature(request.body, signature):
        raise HttpError(403, "Invalid signature")

    payload = json.loads(request.body)
    if payload.get("event") != "charge.success":
        return {"status": "ignored"}

    data = payload["data"]
    reference = data["reference"]

    try:
        payment_link = PaymentLink.objects.select_related("conversation", "tenant").get(
            gateway_reference=reference
        )
    except PaymentLink.DoesNotExist:
        return {"status": "not_found"}

    if payment_link.status == PaymentLink.STATUS_PAID:
        return {"status": "already_processed"}  # idempotency guard

    items_snapshot = data.get("metadata", {}).get("items_snapshot", [])

    with transaction.atomic():
        payment_link.status = PaymentLink.STATUS_PAID
        payment_link.paid_at = timezone.now()
        payment_link.save(update_fields=["status", "paid_at"])

        sale = Sale.objects.create(
            payment_link=payment_link,
            tenant=payment_link.tenant,
            conversation=payment_link.conversation,
            customer_wa_id=payment_link.conversation.customer_wa_id,
            amount_paid=payment_link.amount,
            items_snapshot=items_snapshot,
            gateway_payload=data,
        )

        payment_link.conversation.state = Conversation.STATE_COMPLETED
        payment_link.conversation.save(update_fields=["state"])

    # Enqueue after the transaction commits so tasks see a fully-persisted Sale
    from apps.notifications.tasks import alert_owner, send_confirmation
    alert_owner.delay(str(sale.id))
    send_confirmation.delay(str(payment_link.conversation.id))

    return {"status": "ok"}

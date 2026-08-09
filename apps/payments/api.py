import json
import logging
from ninja import Router
from ninja.errors import HttpError
from django.db import transaction
from django.db.models import F
from django.http import HttpRequest
from django.utils import timezone
from apps.conversations.models import Conversation
from apps.catalog.models import Product
from .gateways.paystack import PaystackGateway
from .models import PaymentLink, Sale, PostSaleFollowUp

logger = logging.getLogger(__name__)

router = Router(tags=["Payments"])
_gateway = PaystackGateway()


@router.post("/paystack/webhook/")
def paystack_webhook(request: HttpRequest):
    signature = request.headers.get("X-Paystack-Signature", "")
    if not _gateway.verify_webhook_signature(request.body, signature):
        raise HttpError(403, "Invalid signature")

    payload = json.loads(request.body)
    event = payload.get("event")

    if event == "charge.failed":
        data = payload.get("data", {})
        reference = data.get("reference")
        if reference:
            try:
                payment_link = PaymentLink.objects.select_related("conversation").get(
                    gateway_reference=reference, status=PaymentLink.STATUS_PENDING
                )
                with transaction.atomic():
                    payment_link.status = PaymentLink.STATUS_FAILED
                    payment_link.save(update_fields=["status"])
                    payment_link.conversation.state = Conversation.STATE_ACTIVE
                    payment_link.conversation.save(update_fields=["state"])
            except PaymentLink.DoesNotExist:
                pass
        return {"status": "ok"}

    if event == "refund.processed":
        data = payload.get("data", {})
        reference = data.get("transaction_reference")
        if reference:
            try:
                payment_link = PaymentLink.objects.select_related("tenant").get(
                    gateway_reference=reference, status=PaymentLink.STATUS_PAID
                )
            except PaymentLink.DoesNotExist:
                return {"status": "not_found"}

            if payment_link.status == PaymentLink.STATUS_REFUNDED:
                return {"status": "already_processed"}  # idempotency guard

            try:
                sale = payment_link.sale
            except Sale.DoesNotExist:
                return {"status": "no_sale"}

            with transaction.atomic():
                payment_link.status = PaymentLink.STATUS_REFUNDED
                payment_link.save(update_fields=["status"])
                _restore_stock(payment_link.tenant_id, sale.items_snapshot)

        return {"status": "ok"}

    if event != "charge.success":
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

        sold_out_names = _decrement_stock(payment_link.tenant_id, items_snapshot)

    # Enqueue after the transaction commits so tasks see a fully-persisted Sale
    from apps.notifications.tasks import alert_owner, send_confirmation, notify_owner_stock_out
    alert_owner.delay(str(sale.id))
    send_confirmation.delay(str(payment_link.conversation.id))
    for name in sold_out_names:
        notify_owner_stock_out.delay(str(payment_link.tenant_id), name)

    # Schedule post-sale follow-ups
    from .tasks import schedule_post_sale_follow_ups, _schedule_cart_follow_ups
    schedule_post_sale_follow_ups(payment_link.tenant, payment_link.conversation, sale)
    # Cancel any pending cart re-engagement follow-ups for this link
    PostSaleFollowUp.objects.filter(payment_link=payment_link, status=PostSaleFollowUp.STATUS_PENDING).update(
        status=PostSaleFollowUp.STATUS_CANCELLED
    )

    return {"status": "ok"}


def _restore_stock(tenant_id, items_snapshot: list) -> None:
    """Restores stock for each item in a refunded sale."""
    for item in items_snapshot:
        product_id = item.get("product_id")
        if not product_id:
            continue
        qty = max(int(item.get("qty", 1)), 1)
        try:
            product = Product.objects.select_for_update().get(
                id=product_id, tenant_id=tenant_id, stock_quantity__isnull=False
            )
        except Product.DoesNotExist:
            continue
        product.stock_quantity += qty
        update_fields = ["stock_quantity"]
        if not product.is_available:
            product.is_available = True
            update_fields.append("is_available")
        product.save(update_fields=update_fields)
        logger.info("Stock restored: %s (%s) +%d units", product.name, product_id, qty)


def _decrement_stock(tenant_id, items_snapshot: list) -> list:
    """Decrements stock for each item sold. Returns names of products that just hit zero."""
    sold_out = []
    for item in items_snapshot:
        product_id = item.get("product_id")
        if not product_id:
            continue
        qty = max(int(item.get("qty", 1)), 1)
        try:
            product = Product.objects.select_for_update().get(
                id=product_id, tenant_id=tenant_id, stock_quantity__isnull=False
            )
        except Product.DoesNotExist:
            continue
        product.stock_quantity = max(product.stock_quantity - qty, 0)
        update_fields = ["stock_quantity"]
        if product.stock_quantity == 0:
            product.is_available = False
            update_fields.append("is_available")
            sold_out.append(product.name)
            logger.info("Product %s (%s) sold out", product.name, product_id)
        product.save(update_fields=update_fields)
    return sold_out

import logging
from datetime import timedelta
from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.utils import timezone

logger = logging.getLogger(__name__)
from apps.conversations.models import Conversation
from apps.conversations.whatsapp import WhatsAppClient
from apps.payments.models import Sale
from .models import NotificationLog


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def alert_owner(self, sale_id: str):
    try:
        sale = Sale.objects.select_related("tenant", "conversation", "payment_link").get(id=sale_id)
    except Sale.DoesNotExist:
        return

    tenant = sale.tenant
    wa_client = WhatsAppClient(tenant)

    items_summary = (
        ", ".join(item.get("name", "item") for item in sale.items_snapshot)
        if sale.items_snapshot
        else "items"
    )

    message = (
        f"New sale confirmed!\n\n"
        f"Customer: {sale.customer_wa_id}\n"
        f"Items: {items_summary}\n"
        f"Amount paid: {sale.amount_paid} {sale.payment_link.currency}"
    )

    try:
        wa_client.send_text(tenant.owner_phone, message)
        NotificationLog.objects.create(
            tenant=tenant,
            sale=sale,
            event_type=NotificationLog.EVENT_SALE,
            channel=NotificationLog.CHANNEL_WHATSAPP,
            status=NotificationLog.STATUS_SENT,
        )
    except Exception as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            logger.error("alert_owner exhausted retries for sale %s: %s", sale_id, exc)
            NotificationLog.objects.create(
                tenant=tenant,
                sale=sale,
                event_type=NotificationLog.EVENT_SALE,
                channel=NotificationLog.CHANNEL_WHATSAPP,
                status=NotificationLog.STATUS_FAILED,
                error=str(exc),
            )


@shared_task(bind=True, max_retries=5, default_retry_delay=60)
def notify_owner_escalation(self, conversation_id: str, reason: str):
    from apps.conversations.models import Conversation
    try:
        conversation = Conversation.objects.select_related("tenant").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return
    tenant = conversation.tenant
    message = (
        f"A customer ({conversation.customer_wa_id}) has requested to speak with a human.\n"
        f"Reason: {reason or 'Not specified'}\n"
        f"Please follow up with them directly on WhatsApp.\n\n"
        f"Send RESOLVE to reactivate the bot for this customer."
    )
    try:
        WhatsAppClient(tenant).send_text(tenant.owner_phone, message)
    except Exception as exc:
        raise self.retry(exc=exc)


@shared_task
def notify_owner_stock_out(tenant_id: str, product_name: str):
    from apps.tenants.models import Tenant
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        return
    message = (
        f"Stock out: *{product_name}* has sold out and been marked unavailable.\n\n"
        f"Reply: STOCK {product_name} [qty] to restock."
    )
    try:
        WhatsAppClient(tenant).send_text(tenant.owner_phone, message)
        NotificationLog.objects.create(
            tenant=tenant,
            event_type=NotificationLog.EVENT_STOCK_OUT,
            channel=NotificationLog.CHANNEL_WHATSAPP,
            status=NotificationLog.STATUS_SENT,
        )
    except Exception as exc:
        logger.error("notify_owner_stock_out failed for tenant %s: %s", tenant_id, exc)
        NotificationLog.objects.create(
            tenant=tenant,
            event_type=NotificationLog.EVENT_STOCK_OUT,
            channel=NotificationLog.CHANNEL_WHATSAPP,
            status=NotificationLog.STATUS_FAILED,
            error=str(exc),
        )


@shared_task
def notify_owner_daily_digest():
    from apps.tenants.models import Tenant
    from apps.payments.models import PaymentLink
    from apps.catalog.models import Product

    since = timezone.now() - timedelta(hours=24)

    for tenant in Tenant.objects.filter(is_active=True):
        sales = list(Sale.objects.filter(tenant=tenant, created_at__gte=since))
        sale_count = len(sales)
        active_convos = Conversation.objects.filter(tenant=tenant, state=Conversation.STATE_ACTIVE).count()
        pending_payments = PaymentLink.objects.filter(tenant=tenant, status=PaymentLink.STATUS_PENDING).count()
        escalated = Conversation.objects.filter(tenant=tenant, state=Conversation.STATE_ESCALATED).count()

        if sale_count == 0 and active_convos == 0:
            continue  # nothing to report

        sale_total = sum(s.amount_paid for s in sales)
        currency = tenant.products.values_list("currency", flat=True).first() or "NGN"

        lines = [f"*Daily summary — {tenant.name}*"]
        if sale_count > 0:
            lines.append(f"Sales today: {sale_count} | {currency} {sale_total:,.0f}")
        else:
            lines.append("Sales today: none")
        lines.append(f"Active chats: {active_convos}")
        if pending_payments:
            lines.append(f"Pending payments: {pending_payments}")
        if escalated:
            lines.append(f"Needs attention: {escalated} escalated chat(s) — send RESOLVE")

        try:
            WhatsAppClient(tenant).send_text(tenant.owner_phone, "\n".join(lines))
            NotificationLog.objects.create(
                tenant=tenant,
                event_type=NotificationLog.EVENT_DAILY_DIGEST,
                channel=NotificationLog.CHANNEL_WHATSAPP,
                status=NotificationLog.STATUS_SENT,
            )
        except Exception as exc:
            logger.error("Daily digest failed for tenant %s: %s", tenant.id, exc)
            NotificationLog.objects.create(
                tenant=tenant,
                event_type=NotificationLog.EVENT_DAILY_DIGEST,
                channel=NotificationLog.CHANNEL_WHATSAPP,
                status=NotificationLog.STATUS_FAILED,
                error=str(exc),
            )


@shared_task
def send_confirmation(conversation_id: str):
    try:
        conversation = Conversation.objects.select_related("tenant").get(id=conversation_id)
    except Conversation.DoesNotExist:
        return

    wa_client = WhatsAppClient(conversation.tenant)
    wa_client.send_text(
        conversation.customer_wa_id,
        "Your payment has been confirmed! Thank you for your order. "
        "The business owner will be in touch shortly.",
    )

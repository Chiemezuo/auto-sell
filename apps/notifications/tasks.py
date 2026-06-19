from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
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
            channel=NotificationLog.CHANNEL_WHATSAPP,
            status=NotificationLog.STATUS_SENT,
        )
    except Exception as exc:
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            NotificationLog.objects.create(
                tenant=tenant,
                sale=sale,
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
        f"Please follow up with them directly on WhatsApp."
    )
    try:
        WhatsAppClient(tenant).send_text(tenant.owner_phone, message)
    except Exception as exc:
        raise self.retry(exc=exc)


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

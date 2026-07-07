import logging
from datetime import timedelta
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.catalog.models import Product
from apps.conversations.models import Conversation
from apps.conversations.whatsapp import WhatsAppClient

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Available commands:\n"
    "SALES TODAY — today's sales summary\n"
    "SALES WEEK — this week's sales\n"
    "STOCK [product] [qty] — update stock\n"
    "PAUSE — pause bot (customers are told to speak with you directly)\n"
    "RESUME — resume bot\n"
    "RESOLVE [number] — reactivate an escalated chat (omit number if only one)\n"
    "STATUS — active chats, pending payments, alerts\n"
    "HELP — show this list"
)


def dispatch(tenant_id: str, text: str) -> None:
    try:
        tenant = Tenant.objects.get(id=tenant_id)
    except Tenant.DoesNotExist:
        return

    wa = WhatsAppClient(tenant)
    owner = tenant.owner_phone
    parts = text.strip().split()
    if not parts:
        _reply(wa, owner, HELP_TEXT)
        return

    cmd = parts[0].upper()

    if cmd == "HELP":
        _reply(wa, owner, HELP_TEXT)

    elif cmd == "SALES":
        if len(parts) < 2:
            _reply(wa, owner, "Usage: SALES TODAY or SALES WEEK")
            return
        period = parts[1].upper()
        if period == "TODAY":
            _cmd_sales(wa, tenant, hours=24, label="today")
        elif period == "WEEK":
            _cmd_sales(wa, tenant, hours=168, label="this week")
        else:
            _reply(wa, owner, "Usage: SALES TODAY or SALES WEEK")

    elif cmd == "STOCK":
        if len(parts) < 3:
            _reply(wa, owner, "Usage: STOCK [product name] [quantity]\nExample: STOCK Ankara Blue 5")
            return
        try:
            qty = int(parts[-1])
        except ValueError:
            _reply(wa, owner, "Quantity must be a whole number.\nExample: STOCK Ankara Blue 5")
            return
        name_query = " ".join(parts[1:-1])
        _cmd_stock(wa, tenant, name_query, qty)

    elif cmd == "PAUSE":
        tenant.bot_paused = True
        tenant.save(update_fields=["bot_paused"])
        _reply(wa, owner, "Bot paused. Customers will be told they're speaking with your team directly. Send RESUME to hand back to the bot.")

    elif cmd == "RESUME":
        tenant.bot_paused = False
        tenant.save(update_fields=["bot_paused"])
        _reply(wa, owner, "Bot resumed. Customers can chat normally again.")

    elif cmd == "RESOLVE":
        identifier = parts[1] if len(parts) >= 2 else None
        _cmd_resolve(wa, tenant, identifier)

    elif cmd == "STATUS":
        _cmd_status(wa, tenant)

    else:
        _reply(wa, owner, f"Unknown command: {cmd}\n\n{HELP_TEXT}")


def _reply(wa: WhatsAppClient, to: str, text: str) -> None:
    try:
        wa.send_text(to, text)
    except Exception:
        logger.exception("Failed to send owner command reply to %s", to)


def _cmd_sales(wa, tenant, hours: int, label: str) -> None:
    from apps.payments.models import Sale
    since = timezone.now() - timedelta(hours=hours)
    sales = list(Sale.objects.filter(tenant=tenant, created_at__gte=since))
    count = len(sales)
    if count == 0:
        _reply(wa, tenant.owner_phone, f"No sales {label}.")
        return
    total = sum(s.amount_paid for s in sales)
    currency = tenant.products.values_list("currency", flat=True).first() or "NGN"
    _reply(wa, tenant.owner_phone, f"Sales {label}: {count} order{'s' if count != 1 else ''} | {currency} {total:,.0f} total")


def _cmd_stock(wa, tenant, name_query: str, qty: int) -> None:
    matches = list(Product.objects.filter(tenant=tenant, name__icontains=name_query))
    if not matches:
        _reply(wa, tenant.owner_phone, f"No products found matching '{name_query}'.")
        return
    if len(matches) > 3:
        names = "\n".join(f"• {p.name}" for p in matches[:5])
        _reply(wa, tenant.owner_phone, f"Multiple products match '{name_query}':\n{names}\n\nBe more specific.")
        return
    updated = []
    for product in matches:
        product.stock_quantity = qty
        fields = ["stock_quantity"]
        if qty > 0 and not product.is_available:
            product.is_available = True
            fields.append("is_available")
        product.save(update_fields=fields)
        updated.append(product.name)
    _reply(wa, tenant.owner_phone, f"Stock updated to {qty} for: {', '.join(updated)}")


def _cmd_resolve(wa, tenant, identifier: str | None) -> None:
    escalated = list(
        Conversation.objects.filter(tenant=tenant, state=Conversation.STATE_ESCALATED)
        .order_by("-last_message_at")
    )
    if not escalated:
        _reply(wa, tenant.owner_phone, "No escalated conversations found.")
        return

    if identifier:
        matches = [c for c in escalated if identifier in c.customer_wa_id]
        if not matches:
            _reply(wa, tenant.owner_phone, f"No escalated conversation found for '{identifier}'.")
            return
        if len(matches) > 1:
            lines = ["Multiple matches — be more specific:"]
            lines += [f"• {c.customer_wa_id}" for c in matches]
            _reply(wa, tenant.owner_phone, "\n".join(lines))
            return
        convo = matches[0]
    elif len(escalated) == 1:
        convo = escalated[0]
    else:
        lines = [f"{len(escalated)} escalated conversations — use RESOLVE [number] to specify:"]
        lines += [f"• {c.customer_wa_id}" for c in escalated]
        _reply(wa, tenant.owner_phone, "\n".join(lines))
        return

    convo.state = Conversation.STATE_ACTIVE
    convo.save(update_fields=["state"])
    _reply(wa, tenant.owner_phone, f"Conversation with {convo.customer_wa_id} reactivated. The bot will respond on their next message.")


def _cmd_status(wa, tenant) -> None:
    from apps.payments.models import PaymentLink
    active = Conversation.objects.filter(tenant=tenant, state=Conversation.STATE_ACTIVE).count()
    escalated = Conversation.objects.filter(tenant=tenant, state=Conversation.STATE_ESCALATED).count()
    pending = PaymentLink.objects.filter(tenant=tenant, status=PaymentLink.STATUS_PENDING).count()
    sold_out = Product.objects.filter(tenant=tenant, stock_quantity=0).count()

    lines = [f"Status for {tenant.name}:"]
    lines.append(f"Active chats: {active}")
    if pending:
        lines.append(f"Pending payments: {pending}")
    if escalated:
        lines.append(f"Escalated (needs attention): {escalated} — send RESOLVE to reset the most recent")
    if sold_out:
        lines.append(f"Sold-out products: {sold_out}")
    _reply(wa, tenant.owner_phone, "\n".join(lines))

import pytest
from unittest.mock import MagicMock
from apps.conversations.models import Conversation
from apps.conversations.owner_commands import dispatch, HELP_TEXT


@pytest.fixture
def mock_wa(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.owner_commands.WhatsAppClient", lambda t: mock_client)
    return mock_client


@pytest.fixture
def paid_link(db, tenant, conversation):
    from apps.payments.models import PaymentLink
    return PaymentLink.objects.create(
        conversation=conversation,
        tenant=tenant,
        amount="1500.00",
        currency="NGN",
        gateway="paystack",
        gateway_reference="ref_cmd_paid_001",
        payment_url="https://paystack.com/pay/ref_cmd_paid_001",
        status=PaymentLink.STATUS_PAID,
    )


@pytest.fixture
def sale(db, tenant, conversation, paid_link):
    from apps.payments.models import Sale
    return Sale.objects.create(
        payment_link=paid_link,
        tenant=tenant,
        conversation=conversation,
        customer_wa_id=conversation.customer_wa_id,
        amount_paid="1500.00",
        items_snapshot=[{"name": "Test Product", "qty": 1}],
        gateway_payload={"reference": "ref_cmd_paid_001"},
    )


@pytest.fixture
def escalated_convo(db, tenant):
    return Conversation.objects.create(
        tenant=tenant,
        customer_wa_id="2348011111111",
        state=Conversation.STATE_ESCALATED,
    )


# ---------------------------------------------------------------------------
# HELP / empty / unknown / nonexistent tenant
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_help(tenant, mock_wa):
    dispatch(str(tenant.id), "HELP")
    mock_wa.send_text.assert_called_once_with(tenant.owner_phone, HELP_TEXT)


@pytest.mark.django_db
def test_dispatch_empty_sends_help(tenant, mock_wa):
    dispatch(str(tenant.id), "   ")
    mock_wa.send_text.assert_called_once_with(tenant.owner_phone, HELP_TEXT)


@pytest.mark.django_db
def test_dispatch_unknown_command_includes_help(tenant, mock_wa):
    dispatch(str(tenant.id), "FOOBAR")
    text = mock_wa.send_text.call_args[0][1]
    assert "Unknown command" in text
    assert "FOOBAR" in text


@pytest.mark.django_db
def test_dispatch_nonexistent_tenant_returns_silently(mock_wa):
    dispatch("00000000-0000-0000-0000-000000000000", "HELP")
    mock_wa.send_text.assert_not_called()


# ---------------------------------------------------------------------------
# SALES
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_sales_today_no_sales(tenant, mock_wa):
    dispatch(str(tenant.id), "SALES TODAY")
    text = mock_wa.send_text.call_args[0][1]
    assert "No sales today" in text


@pytest.mark.django_db
def test_dispatch_sales_today_with_sales(tenant, sale, product, mock_wa):
    dispatch(str(tenant.id), "SALES TODAY")
    text = mock_wa.send_text.call_args[0][1]
    assert "1 order" in text
    assert "1,500" in text


@pytest.mark.django_db
def test_dispatch_sales_week_label(tenant, sale, mock_wa):
    dispatch(str(tenant.id), "SALES WEEK")
    text = mock_wa.send_text.call_args[0][1]
    assert "this week" in text


@pytest.mark.django_db
def test_dispatch_sales_missing_period_shows_usage(tenant, mock_wa):
    dispatch(str(tenant.id), "SALES")
    text = mock_wa.send_text.call_args[0][1]
    assert "Usage" in text


@pytest.mark.django_db
def test_dispatch_sales_invalid_period_shows_usage(tenant, mock_wa):
    dispatch(str(tenant.id), "SALES MONTH")
    text = mock_wa.send_text.call_args[0][1]
    assert "Usage" in text


# ---------------------------------------------------------------------------
# STOCK
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_stock_updates_quantity(tenant, product, mock_wa):
    dispatch(str(tenant.id), f"STOCK {product.name} 10")
    product.refresh_from_db()
    assert product.stock_quantity == 10
    text = mock_wa.send_text.call_args[0][1]
    assert "Stock updated" in text


@pytest.mark.django_db
def test_dispatch_stock_restores_availability_when_qty_positive(tenant, mock_wa):
    from apps.catalog.models import Product
    p = Product.objects.create(
        tenant=tenant, name="Sold Out Shirt", description="desc",
        price_min="500", price_max="1000", currency="NGN",
        is_available=False, stock_quantity=0,
    )
    dispatch(str(tenant.id), "STOCK Sold Out Shirt 5")
    p.refresh_from_db()
    assert p.stock_quantity == 5
    assert p.is_available is True


@pytest.mark.django_db
def test_dispatch_stock_no_match(tenant, mock_wa):
    dispatch(str(tenant.id), "STOCK NonExistentItem 5")
    text = mock_wa.send_text.call_args[0][1]
    assert "No products found" in text


@pytest.mark.django_db
def test_dispatch_stock_too_many_matches(tenant, mock_wa):
    from apps.catalog.models import Product
    for i in range(4):
        Product.objects.create(
            tenant=tenant, name=f"Blue Shirt {i}", description="desc",
            price_min="500", price_max="1000",
        )
    dispatch(str(tenant.id), "STOCK Blue 5")
    text = mock_wa.send_text.call_args[0][1]
    assert "Multiple products match" in text
    assert "Be more specific" in text


@pytest.mark.django_db
def test_dispatch_stock_missing_args_shows_usage(tenant, mock_wa):
    dispatch(str(tenant.id), "STOCK OnlyName")
    text = mock_wa.send_text.call_args[0][1]
    assert "Usage" in text


@pytest.mark.django_db
def test_dispatch_stock_non_integer_qty(tenant, product, mock_wa):
    dispatch(str(tenant.id), f"STOCK {product.name} notanumber")
    text = mock_wa.send_text.call_args[0][1]
    assert "whole number" in text.lower()


# ---------------------------------------------------------------------------
# PAUSE / RESUME
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_pause_sets_bot_paused(tenant, mock_wa):
    dispatch(str(tenant.id), "PAUSE")
    tenant.refresh_from_db()
    assert tenant.bot_paused is True
    text = mock_wa.send_text.call_args[0][1]
    assert "paused" in text.lower()


@pytest.mark.django_db
def test_dispatch_resume_clears_bot_paused(tenant, mock_wa):
    tenant.bot_paused = True
    tenant.save()
    dispatch(str(tenant.id), "RESUME")
    tenant.refresh_from_db()
    assert tenant.bot_paused is False
    text = mock_wa.send_text.call_args[0][1]
    assert "resumed" in text.lower()


# ---------------------------------------------------------------------------
# RESOLVE
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_resolve_no_escalated_conversations(tenant, mock_wa):
    dispatch(str(tenant.id), "RESOLVE")
    text = mock_wa.send_text.call_args[0][1]
    assert "No escalated" in text


@pytest.mark.django_db
def test_dispatch_resolve_single_escalated_no_identifier(tenant, escalated_convo, mock_wa):
    dispatch(str(tenant.id), "RESOLVE")
    escalated_convo.refresh_from_db()
    assert escalated_convo.state == Conversation.STATE_ACTIVE
    text = mock_wa.send_text.call_args[0][1]
    assert "reactivated" in text


@pytest.mark.django_db
def test_dispatch_resolve_multiple_without_identifier_lists_all(tenant, escalated_convo, mock_wa):
    Conversation.objects.create(
        tenant=tenant,
        customer_wa_id="2348022222222",
        state=Conversation.STATE_ESCALATED,
    )
    dispatch(str(tenant.id), "RESOLVE")
    text = mock_wa.send_text.call_args[0][1]
    assert "escalated conversations" in text.lower()
    assert "2348011111111" in text
    assert "2348022222222" in text


@pytest.mark.django_db
def test_dispatch_resolve_with_matching_identifier(tenant, escalated_convo, mock_wa):
    dispatch(str(tenant.id), "RESOLVE 11111")
    escalated_convo.refresh_from_db()
    assert escalated_convo.state == Conversation.STATE_ACTIVE


@pytest.mark.django_db
def test_dispatch_resolve_identifier_no_match(tenant, escalated_convo, mock_wa):
    dispatch(str(tenant.id), "RESOLVE 99999")
    text = mock_wa.send_text.call_args[0][1]
    assert "No escalated conversation found" in text
    escalated_convo.refresh_from_db()
    assert escalated_convo.state == Conversation.STATE_ESCALATED


@pytest.mark.django_db
def test_dispatch_resolve_identifier_multiple_matches(tenant, mock_wa):
    for wa_id in ("2348099111111", "2348099222222"):
        Conversation.objects.create(
            tenant=tenant, customer_wa_id=wa_id, state=Conversation.STATE_ESCALATED,
        )
    dispatch(str(tenant.id), "RESOLVE 099")
    text = mock_wa.send_text.call_args[0][1]
    assert "Multiple matches" in text


# ---------------------------------------------------------------------------
# STATUS
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_dispatch_status_shows_active_chat_count(tenant, conversation, mock_wa):
    dispatch(str(tenant.id), "STATUS")
    text = mock_wa.send_text.call_args[0][1]
    assert "Active chats: 1" in text


@pytest.mark.django_db
def test_dispatch_status_shows_escalated_and_pending_payments(
    tenant, conversation, escalated_convo, mock_wa
):
    from apps.payments.models import PaymentLink
    PaymentLink.objects.create(
        conversation=conversation, tenant=tenant, amount="1000", currency="NGN",
        gateway="paystack", gateway_reference="ref_status_p01",
        payment_url="https://paystack.com/pay/ref_status_p01",
        status=PaymentLink.STATUS_PENDING,
    )
    dispatch(str(tenant.id), "STATUS")
    text = mock_wa.send_text.call_args[0][1]
    assert "Pending payments" in text
    assert "Escalated" in text

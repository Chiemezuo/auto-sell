import pytest
from unittest.mock import MagicMock
from apps.conversations.models import Conversation
from apps.notifications.models import NotificationLog
from apps.notifications.tasks import notify_owner_stock_out, notify_owner_daily_digest


@pytest.fixture
def mock_wa(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppClient", lambda t: mock_client)
    return mock_client


# ---------------------------------------------------------------------------
# notify_owner_stock_out
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_stock_out_sends_whatsapp_and_logs_sent(tenant, mock_wa):
    notify_owner_stock_out.apply(kwargs={
        "tenant_id": str(tenant.id),
        "product_name": "Ankara Fabric",
    })

    mock_wa.send_text.assert_called_once()
    recipient, message = mock_wa.send_text.call_args[0]
    assert recipient == tenant.owner_phone
    assert "Ankara Fabric" in message

    log = NotificationLog.objects.get(tenant=tenant)
    assert log.event_type == NotificationLog.EVENT_STOCK_OUT
    assert log.status == NotificationLog.STATUS_SENT
    assert log.sale is None


@pytest.mark.django_db
def test_stock_out_nonexistent_tenant_returns_silently(mock_wa):
    notify_owner_stock_out.apply(kwargs={
        "tenant_id": "00000000-0000-0000-0000-000000000000",
        "product_name": "Ghost Product",
    })
    mock_wa.send_text.assert_not_called()
    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_stock_out_wa_failure_logs_failed(tenant, mock_wa):
    mock_wa.send_text.side_effect = Exception("WA API unavailable")

    notify_owner_stock_out.apply(kwargs={
        "tenant_id": str(tenant.id),
        "product_name": "Silk Wrapper",
    })

    log = NotificationLog.objects.get(tenant=tenant)
    assert log.event_type == NotificationLog.EVENT_STOCK_OUT
    assert log.status == NotificationLog.STATUS_FAILED
    assert "WA API unavailable" in log.error


# ---------------------------------------------------------------------------
# notify_owner_daily_digest
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_daily_digest_sends_for_tenant_with_active_conversation(tenant, conversation, mock_wa):
    notify_owner_daily_digest.apply()

    mock_wa.send_text.assert_called_once()
    recipient, message = mock_wa.send_text.call_args[0]
    assert recipient == tenant.owner_phone
    assert "Daily summary" in message
    assert "Active chats: 1" in message

    log = NotificationLog.objects.get(tenant=tenant)
    assert log.event_type == NotificationLog.EVENT_DAILY_DIGEST
    assert log.status == NotificationLog.STATUS_SENT


@pytest.mark.django_db
def test_daily_digest_skips_tenant_with_no_activity(tenant, mock_wa):
    # no active conversations, no sales → skip
    notify_owner_daily_digest.apply()
    mock_wa.send_text.assert_not_called()
    assert NotificationLog.objects.count() == 0


@pytest.mark.django_db
def test_daily_digest_skips_inactive_tenants(db, mock_wa):
    from apps.tenants.models import Tenant
    inactive = Tenant.objects.create(
        name="Inactive Shop", slug="inactive-shop",
        wa_phone_number_id="9999999991", wa_business_account_id="8888888881",
        wa_access_token="token", wa_app_secret="secret",
        wa_webhook_verify_token="verify",
        owner_phone="2348099991111", owner_email="inactive@example.com",
        is_active=False,
    )
    Conversation.objects.create(
        tenant=inactive, customer_wa_id="2348011110000", state=Conversation.STATE_ACTIVE,
    )
    notify_owner_daily_digest.apply()
    mock_wa.send_text.assert_not_called()


@pytest.mark.django_db
def test_daily_digest_includes_escalated_and_pending_in_message(tenant, conversation, mock_wa):
    from apps.payments.models import PaymentLink
    Conversation.objects.create(
        tenant=tenant, customer_wa_id="2348033333333", state=Conversation.STATE_ESCALATED,
    )
    PaymentLink.objects.create(
        conversation=conversation, tenant=tenant, amount="1000", currency="NGN",
        gateway="paystack", gateway_reference="ref_digest_p01",
        payment_url="https://paystack.com/pay/ref_digest_p01",
        status=PaymentLink.STATUS_PENDING,
    )
    notify_owner_daily_digest.apply()
    _, message = mock_wa.send_text.call_args[0]
    assert "Pending payments" in message
    assert "escalated" in message.lower()


@pytest.mark.django_db
def test_daily_digest_wa_failure_logs_failed(tenant, conversation, mock_wa):
    mock_wa.send_text.side_effect = Exception("timeout")

    notify_owner_daily_digest.apply()

    log = NotificationLog.objects.get(tenant=tenant)
    assert log.event_type == NotificationLog.EVENT_DAILY_DIGEST
    assert log.status == NotificationLog.STATUS_FAILED
    assert "timeout" in log.error

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from apps.conversations.models import Conversation
from apps.payments.models import PaymentLink
from apps.payments.tasks import create_payment_link


@pytest.fixture
def mock_paystack(monkeypatch):
    gateway = MagicMock()
    gateway.initialize_transaction.return_value = {
        "reference": "ref_test_001",
        "authorization_url": "https://paystack.com/pay/ref_test_001",
    }
    monkeypatch.setattr("apps.payments.tasks.PaystackGateway", lambda: gateway)
    return gateway


@pytest.fixture
def mock_whatsapp_payments(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.payments.tasks.WhatsAppClient", lambda t: mock_client)
    return mock_client


@pytest.mark.django_db
def test_create_payment_link_calls_paystack(tenant, conversation, mock_paystack, mock_whatsapp_payments):
    create_payment_link.apply(kwargs={
        "conversation_id": str(conversation.id),
        "items_snapshot": [{"name": "Test Product", "qty": 1}],
        "agreed_price": 1500.0,
    })

    mock_paystack.initialize_transaction.assert_called_once()
    call_kwargs = mock_paystack.initialize_transaction.call_args[1]
    assert call_kwargs["amount"] == 1500.0
    assert "@autosell.app" in call_kwargs["email"]


@pytest.mark.django_db
def test_create_payment_link_creates_db_record(tenant, conversation, mock_paystack, mock_whatsapp_payments):
    create_payment_link.apply(kwargs={
        "conversation_id": str(conversation.id),
        "items_snapshot": [],
        "agreed_price": 1500.0,
    })

    link = PaymentLink.objects.get(conversation=conversation)
    assert link.gateway_reference == "ref_test_001"
    assert link.payment_url == "https://paystack.com/pay/ref_test_001"
    assert link.amount == Decimal("1500.0")
    assert link.status == PaymentLink.STATUS_PENDING


@pytest.mark.django_db
def test_create_payment_link_sets_awaiting_payment_state(tenant, conversation, mock_paystack, mock_whatsapp_payments):
    create_payment_link.apply(kwargs={
        "conversation_id": str(conversation.id),
        "items_snapshot": [],
        "agreed_price": 1500.0,
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_AWAITING_PAYMENT


@pytest.mark.django_db
def test_create_payment_link_sends_whatsapp_with_url(tenant, conversation, mock_paystack, mock_whatsapp_payments):
    create_payment_link.apply(kwargs={
        "conversation_id": str(conversation.id),
        "items_snapshot": [],
        "agreed_price": 1500.0,
    })

    mock_whatsapp_payments.send_text.assert_called_once()
    _wa_id, message = mock_whatsapp_payments.send_text.call_args[0]
    assert "https://paystack.com/pay/ref_test_001" in message


@pytest.mark.django_db
def test_create_payment_link_nonexistent_conversation(mock_paystack, mock_whatsapp_payments):
    create_payment_link.apply(kwargs={
        "conversation_id": "00000000-0000-0000-0000-000000000000",
        "items_snapshot": [],
        "agreed_price": 1500.0,
    })

    mock_paystack.initialize_transaction.assert_not_called()

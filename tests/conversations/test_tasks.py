import pytest
from unittest.mock import MagicMock
from apps.conversations.models import Conversation
from apps.conversations.tasks import process_message, reply_unsupported_message


@pytest.mark.django_db
def test_process_message_lock_prevents_double_processing(tenant, conversation, fake_redis, mock_chat):
    lock_key = f"conversation:{conversation.id}:lock"
    fake_redis.set(lock_key, "1", ex=30)

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_lock_test",
    })

    mock_chat.assert_not_called()


@pytest.mark.django_db
def test_returning_customer_resets_completed_conversation(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    conversation.state = Conversation.STATE_COMPLETED
    conversation.save()

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello again",
        "wa_message_id": "msg_reopen_1",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE
    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_returning_customer_resets_abandoned_conversation(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    conversation.state = Conversation.STATE_ABANDONED
    conversation.save()

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Anyone there?",
        "wa_message_id": "msg_abandoned_1",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE
    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_awaiting_payment_sends_reminder_when_link_pending(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    from apps.payments.models import PaymentLink
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()
    PaymentLink.objects.create(
        conversation=conversation, tenant=tenant, amount="1500.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_active_001",
        payment_url="https://paystack.com/pay/ref_active_001",
        status=PaymentLink.STATUS_PENDING,
    )

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Are you there?",
        "wa_message_id": "msg_awaiting_1",
    })

    mock_chat.assert_not_called()
    mock_whatsapp.send_text.assert_called_once()
    _wa_id, reminder_text = mock_whatsapp.send_text.call_args[0]
    assert "payment" in reminder_text.lower()


@pytest.mark.django_db
def test_awaiting_payment_resets_when_link_expired(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    from apps.payments.models import PaymentLink
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()
    PaymentLink.objects.create(
        conversation=conversation, tenant=tenant, amount="1500.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_expired_001",
        payment_url="https://paystack.com/pay/ref_expired_001",
        status=PaymentLink.STATUS_EXPIRED,
    )

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Is the link still valid?",
        "wa_message_id": "msg_expired_1",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE
    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_awaiting_payment_resets_when_link_failed(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    from apps.payments.models import PaymentLink
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()
    PaymentLink.objects.create(
        conversation=conversation, tenant=tenant, amount="1500.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_failed_001",
        payment_url="https://paystack.com/pay/ref_failed_001",
        status=PaymentLink.STATUS_FAILED,
    )

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "My payment failed",
        "wa_message_id": "msg_failed_1",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE
    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_awaiting_payment_resets_when_no_link(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp
):
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_nolink_1",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE
    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_reply_unsupported_message_sends_text(tenant, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda t: mock_client)

    reply_unsupported_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": "2348099999999",
    })

    mock_client.send_text.assert_called_once()
    _wa_id, text = mock_client.send_text.call_args[0]
    assert "text" in text.lower()

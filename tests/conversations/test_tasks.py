import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from django.utils import timezone
from apps.conversations.models import Conversation
from apps.conversations.tasks import process_message, reply_unsupported_message, sweep_abandoned_conversations


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
def test_reply_unsupported_message_sends_text(tenant, fake_redis, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda t: mock_client)

    reply_unsupported_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": "2348099999999",
    })

    mock_client.send_text.assert_called_once()
    _wa_id, text = mock_client.send_text.call_args[0]
    assert "text" in text.lower()


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_rate_limit_under_threshold_passes_through(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    rate_key = f"rate:{tenant.id}:{conversation.customer_wa_id}"
    fake_redis.set(rate_key, 9)

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_rate_under_1",
    })

    mock_chat.assert_called_once()


@pytest.mark.django_db
def test_rate_limit_over_threshold_blocks_llm_and_sends_reply(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    rate_key = f"rate:{tenant.id}:{conversation.customer_wa_id}"
    fake_redis.set(rate_key, 10)

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_rate_over_1",
    })

    mock_chat.assert_not_called()
    mock_whatsapp.send_text.assert_called_once()
    _wa_id, reply_text = mock_whatsapp.send_text.call_args[0]
    assert any(word in reply_text.lower() for word in ("wait", "fast"))


@pytest.mark.django_db
def test_rate_limit_ttl_set_on_first_hit(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    rate_key = f"rate:{tenant.id}:{conversation.customer_wa_id}"

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_rate_ttl_1",
    })

    assert fake_redis.ttl(rate_key) > 0


@pytest.mark.django_db
def test_unsupported_message_rate_limited_returns_silently(tenant, fake_redis, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda t: mock_client)
    rate_key = f"rate:{tenant.id}:2348099999999"
    fake_redis.set(rate_key, 11)

    reply_unsupported_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": "2348099999999",
    })

    mock_client.send_text.assert_not_called()


# ---------------------------------------------------------------------------
# Abandoned conversation sweep
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sweep_active_over_24h_becomes_abandoned(tenant, conversation):
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=timezone.now() - timedelta(hours=25)
    )

    sweep_abandoned_conversations.apply()

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ABANDONED


@pytest.mark.django_db
def test_sweep_active_within_24h_untouched(tenant, conversation):
    sweep_abandoned_conversations.apply()

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE


@pytest.mark.django_db
def test_sweep_awaiting_payment_over_48h_becomes_abandoned(tenant, conversation):
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=timezone.now() - timedelta(hours=49)
    )

    sweep_abandoned_conversations.apply()

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ABANDONED


@pytest.mark.django_db
def test_sweep_awaiting_payment_within_48h_untouched(tenant, conversation):
    conversation.state = Conversation.STATE_AWAITING_PAYMENT
    conversation.save()
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=timezone.now() - timedelta(hours=25)
    )

    sweep_abandoned_conversations.apply()

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_AWAITING_PAYMENT


@pytest.mark.django_db
def test_sweep_completed_conversations_not_touched(tenant, conversation):
    conversation.state = Conversation.STATE_COMPLETED
    conversation.save()
    Conversation.objects.filter(pk=conversation.pk).update(
        last_message_at=timezone.now() - timedelta(hours=100)
    )

    sweep_abandoned_conversations.apply()

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_COMPLETED

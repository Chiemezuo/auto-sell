import pytest
from datetime import timedelta
from unittest.mock import MagicMock
from django.utils import timezone
from apps.conversations.models import Conversation
from apps.conversations.tasks import process_message, reply_unsupported_message, sweep_abandoned_conversations
from apps.notifications.tasks import notify_owner_escalation


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

    mock_chat.chat.assert_not_called()


@pytest.mark.django_db
def test_completed_conversation_stays_silent(
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
    assert conversation.state == Conversation.STATE_COMPLETED
    mock_chat.chat.assert_not_called()
    mock_whatsapp.send_text.assert_not_called()


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
    mock_chat.chat.assert_called_once()


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

    mock_chat.chat.assert_not_called()
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
    mock_chat.chat.assert_called_once()


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
    mock_chat.chat.assert_called_once()


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
    mock_chat.chat.assert_called_once()


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

    mock_chat.chat.assert_called_once()


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

    mock_chat.chat.assert_not_called()
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


# ---------------------------------------------------------------------------
# Escalation
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_escalated_conversation_is_silent(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.state = Conversation.STATE_ESCALATED
    conversation.save()

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello?",
        "wa_message_id": "msg_escalated_1",
    })

    mock_chat.chat.assert_not_called()
    mock_whatsapp.send_text.assert_not_called()


@pytest.mark.django_db
def test_escalation_tool_sets_state_and_notifies_owner(
    tenant, conversation, fake_redis, mock_chat, mock_whatsapp, monkeypatch
):
    tool_call = MagicMock()
    tool_call.id = "tc_esc_1"
    tool_call.function.name = "escalate_to_human"
    tool_call.function.arguments = '{"reason": "customer wants a refund"}'

    mock_chat.chat.return_value.choices[0].message.content = None
    mock_chat.chat.return_value.choices[0].message.tool_calls = [tool_call]

    mock_notify = MagicMock()
    monkeypatch.setattr("apps.notifications.tasks.notify_owner_escalation", mock_notify)

    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "I want a refund",
        "wa_message_id": "msg_escalated_2",
    })

    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ESCALATED
    mock_notify.delay.assert_called_once_with(str(conversation.id), "customer wants a refund")


@pytest.mark.django_db
def test_notify_owner_escalation_sends_whatsapp(tenant, conversation, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.notifications.tasks.WhatsAppClient", lambda t: mock_client)

    notify_owner_escalation.apply(kwargs={
        "conversation_id": str(conversation.id),
        "reason": "customer wants a refund",
    })

    mock_client.send_text.assert_called_once()
    recipient, message = mock_client.send_text.call_args[0]
    assert recipient == tenant.owner_phone
    assert conversation.customer_wa_id in message
    assert "customer wants a refund" in message


# ---------------------------------------------------------------------------
# Phase transitions
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_phase_greeting_to_recommendation(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.phase = Conversation.PHASE_GREETING
    conversation.save()
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Do you have iPhones?",
        "wa_message_id": "msg_phase_1",
    })
    conversation.refresh_from_db()
    assert conversation.phase == Conversation.PHASE_RECOMMENDATION


@pytest.mark.django_db
def test_phase_discovery_to_negotiation(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.phase = Conversation.PHASE_DISCOVERY
    conversation.save()
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "That's too expensive, can you give me a discount?",
        "wa_message_id": "msg_phase_2",
    })
    conversation.refresh_from_db()
    assert conversation.phase == Conversation.PHASE_NEGOTIATION


@pytest.mark.django_db
def test_phase_recommendation_to_close(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.phase = Conversation.PHASE_RECOMMENDATION
    conversation.save()
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "I'll take it! Send me the payment link.",
        "wa_message_id": "msg_phase_3",
    })
    conversation.refresh_from_db()
    assert conversation.phase == Conversation.PHASE_CLOSE


# ---------------------------------------------------------------------------
# New conversation state guards
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_owner_handling_conversation_is_silent(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.state = Conversation.STATE_OWNER_HANDLING
    conversation.save()
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello?",
        "wa_message_id": "msg_owner_1",
    })
    mock_chat.chat.assert_not_called()


@pytest.mark.django_db
def test_co_pilot_drafting_conversation_is_silent(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    conversation.state = Conversation.STATE_CO_PILOT_DRAFTING
    conversation.save()
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello?",
        "wa_message_id": "msg_copilot_1",
    })
    mock_chat.chat.assert_not_called()


# ---------------------------------------------------------------------------
# Non-text reply variety
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_unsupported_image_gets_specific_reply(tenant, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda t: mock_client)
    reply_unsupported_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": "2348099999999",
        "message_type": "image",
    })
    _wa_id, text = mock_client.send_text.call_args[0]
    assert "photo" in text.lower()


@pytest.mark.django_db
def test_unsupported_voice_gets_specific_reply(tenant, monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda t: mock_client)
    reply_unsupported_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": "2348099999999",
        "message_type": "voice",
    })
    _wa_id, text = mock_client.send_text.call_args[0]
    assert "voice" in text.lower()


# ---------------------------------------------------------------------------
# Prompt version tracking
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_assistant_message_stores_prompt_version(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    from apps.conversations.prompts import PROMPT_VERSION
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_version_1",
    })
    msg = conversation.messages.filter(role="assistant").first()
    assert msg is not None
    assert msg.prompt_version == PROMPT_VERSION


# ---------------------------------------------------------------------------
# Sentiment-aware prompt selection
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_sentiment_classified_on_process(tenant, conversation, fake_redis, mock_chat, mock_whatsapp, monkeypatch):
    from apps.conversations.llm import LLMProvider
    mock_provider = MagicMock(spec=LLMProvider)
    mock_provider.classify.return_value = "frustrated"
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "I understand your frustration."
    mock_response.choices[0].message.tool_calls = None
    mock_provider.chat.return_value = mock_response

    get_provider_original = None
    try:
        from apps.conversations.tasks import get_provider as task_get_provider
        def mock_get(tenant, tier="primary"):
            return mock_provider
        monkeypatch.setattr("apps.conversations.tasks.get_provider", mock_get)
        process_message.apply(kwargs={
            "tenant_id": str(tenant.id),
            "customer_wa_id": conversation.customer_wa_id,
            "message_text": "This is way too expensive!",
            "wa_message_id": "msg_sentiment_1",
        })
    finally:
        pass

    mock_provider.classify.assert_called()
    mock_provider.chat.assert_called()


# ---------------------------------------------------------------------------
# Feedback model
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_create_feedback_record(tenant, conversation):
    from apps.conversations.models import BotFeedback
    msg = conversation.messages.create(
        conversation=conversation,
        role="assistant",
        content="How can I help?",
        prompt_version="v1.0",
    )
    feedback = BotFeedback.objects.create(
        conversation=conversation,
        message=msg,
        tenant=tenant,
        feedback_type=BotFeedback.FEEDBACK_GOOD,
        prompt_version="v1.0",
        context_snapshot=[{"role": "user", "content": "Hi"}],
    )
    assert feedback.id is not None
    assert feedback.feedback_type == "good"


@pytest.mark.django_db
def test_feedback_stores_edited_response(tenant, conversation):
    from apps.conversations.models import BotFeedback
    msg = conversation.messages.create(
        conversation=conversation,
        role="assistant",
        content="Original reply",
        prompt_version="v2.0",
    )
    feedback = BotFeedback.objects.create(
        conversation=conversation,
        message=msg,
        tenant=tenant,
        feedback_type=BotFeedback.FEEDBACK_EDITED,
        edited_response="Edited reply by owner",
        prompt_version="v2.0",
    )
    assert feedback.edited_response == "Edited reply by owner"


# ---------------------------------------------------------------------------
# Post-purchase follow-ups
# ---------------------------------------------------------------------------

@pytest.mark.django_db
def test_follow_up_created_on_sale(tenant, conversation):
    from apps.payments.models import PaymentLink, Sale, PostSaleFollowUp
    link = PaymentLink.objects.create(
        conversation=conversation, tenant=tenant,
        amount="1000.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_test_fu",
        payment_url="https://paystack.com/pay/test",
    )
    sale = Sale.objects.create(
        payment_link=link, tenant=tenant, conversation=conversation,
        customer_wa_id=conversation.customer_wa_id,
        amount_paid="1000.00", items_snapshot=[],
        gateway_payload={},
    )
    from apps.payments.tasks import schedule_post_sale_follow_ups
    tenant.follow_up_enabled = True
    tenant.save()
    schedule_post_sale_follow_ups(tenant, conversation, sale)
    follow_ups = PostSaleFollowUp.objects.filter(sale=sale)
    assert follow_ups.count() == 4


@pytest.mark.django_db
def test_follow_up_not_created_when_disabled(tenant, conversation):
    from apps.payments.models import PaymentLink, Sale, PostSaleFollowUp
    link = PaymentLink.objects.create(
        conversation=conversation, tenant=tenant,
        amount="1000.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_test_fu2",
        payment_url="https://paystack.com/pay/test",
    )
    sale = Sale.objects.create(
        payment_link=link, tenant=tenant, conversation=conversation,
        customer_wa_id=conversation.customer_wa_id,
        amount_paid="1000.00", items_snapshot=[],
        gateway_payload={},
    )
    from apps.payments.tasks import schedule_post_sale_follow_ups
    tenant.follow_up_enabled = False
    tenant.save()
    schedule_post_sale_follow_ups(tenant, conversation, sale)
    follow_ups = PostSaleFollowUp.objects.filter(sale=sale)
    assert follow_ups.count() == 0


@pytest.mark.django_db
def test_cart_follow_ups_cancelled_on_payment(tenant, conversation):
    from apps.payments.models import PaymentLink, Sale, PostSaleFollowUp
    from django.utils import timezone
    from datetime import timedelta
    link = PaymentLink.objects.create(
        conversation=conversation, tenant=tenant,
        amount="1000.00", currency="NGN",
        gateway="paystack", gateway_reference="ref_test_fu3",
        payment_url="https://paystack.com/pay/test",
    )
    PostSaleFollowUp.objects.create(
        payment_link=link, tenant=tenant, conversation=conversation,
        schedule_type=PostSaleFollowUp.SCHEDULE_CART_2H,
        scheduled_at=timezone.now() + timedelta(hours=2),
    )
    PostSaleFollowUp.objects.filter(
        payment_link=link,
        status=PostSaleFollowUp.STATUS_PENDING,
    ).update(status=PostSaleFollowUp.STATUS_CANCELLED)
    assert PostSaleFollowUp.objects.filter(payment_link=link, status="cancelled").count() == 1

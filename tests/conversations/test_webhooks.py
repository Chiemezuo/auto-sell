import json
import pytest
from unittest.mock import patch
from tests.conftest import build_wa_payload, sign_wa_request
from apps.conversations.models import Message


@pytest.mark.django_db
def test_verify_webhook_returns_challenge(client, tenant):
    url = (
        f"/api/webhooks/whatsapp/{tenant.slug}/"
        f"?hub.mode=subscribe"
        f"&hub.verify_token={tenant.wa_webhook_verify_token}"
        f"&hub.challenge=mychallenge"
    )
    response = client.get(url)
    assert response.status_code == 200
    assert response.content == b"mychallenge"


@pytest.mark.django_db
def test_verify_webhook_wrong_token_returns_403(client, tenant):
    url = (
        f"/api/webhooks/whatsapp/{tenant.slug}/"
        f"?hub.mode=subscribe&hub.verify_token=wrong-token&hub.challenge=mychallenge"
    )
    response = client.get(url)
    assert response.status_code == 403


@pytest.mark.django_db
def test_receive_message_enqueues_task(client, tenant):
    body = json.dumps(
        build_wa_payload(tenant.wa_phone_number_id, "2348099999999", text_body="Hi there")
    ).encode()
    with patch("apps.conversations.tasks.process_message.delay") as mock_delay:
        response = client.post(
            f"/api/webhooks/whatsapp/{tenant.slug}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=sign_wa_request(tenant.wa_app_secret, body),
        )
    assert response.status_code == 200
    mock_delay.assert_called_once()


@pytest.mark.django_db
def test_receive_message_deduplicates_by_wa_message_id(client, tenant, conversation):
    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_USER,
        content="Hi",
        wa_message_id="dup_msg_1",
    )
    body = json.dumps(
        build_wa_payload(
            tenant.wa_phone_number_id,
            conversation.customer_wa_id,
            text_body="Hi again",
            message_id="dup_msg_1",
        )
    ).encode()
    with patch("apps.conversations.tasks.process_message.delay") as mock_delay:
        response = client.post(
            f"/api/webhooks/whatsapp/{tenant.slug}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=sign_wa_request(tenant.wa_app_secret, body),
        )
    assert response.status_code == 200
    mock_delay.assert_not_called()


@pytest.mark.django_db
def test_receive_message_invalid_signature_returns_403(client, tenant):
    body = json.dumps(
        build_wa_payload(tenant.wa_phone_number_id, "2348099999999", text_body="Hi")
    ).encode()
    response = client.post(
        f"/api/webhooks/whatsapp/{tenant.slug}/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=invalidsignature",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_non_text_message_enqueues_reply_unsupported(client, tenant):
    body = json.dumps(
        build_wa_payload(
            tenant.wa_phone_number_id,
            "2348099999999",
            message_type="image",
            message_id="img_msg_1",
        )
    ).encode()
    with patch("apps.conversations.tasks.reply_unsupported_message.delay") as mock_delay:
        response = client.post(
            f"/api/webhooks/whatsapp/{tenant.slug}/",
            data=body,
            content_type="application/json",
            HTTP_X_HUB_SIGNATURE_256=sign_wa_request(tenant.wa_app_secret, body),
        )
    assert response.status_code == 200
    mock_delay.assert_called_once_with(str(tenant.id), "2348099999999")

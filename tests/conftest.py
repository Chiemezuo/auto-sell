import json
import hmac
import hashlib
import pytest
import fakeredis
from unittest.mock import MagicMock
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant
from apps.catalog.models import Product
from apps.conversations.models import Conversation

User = get_user_model()


def build_wa_payload(
    phone_number_id, sender_wa_id, message_type="text",
    text_body=None, message_id="msg_test_1"
):
    message = {"id": message_id, "from": sender_wa_id, "type": message_type}
    if message_type == "text":
        message["text"] = {"body": text_body or "Hello"}
    return {
        "entry": [{
            "changes": [{
                "value": {
                    "metadata": {"phone_number_id": phone_number_id},
                    "messages": [message],
                }
            }]
        }]
    }


def sign_wa_request(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(
        name="Test Shop",
        slug="test-shop",
        wa_phone_number_id="1234567890",
        wa_business_account_id="0987654321",
        wa_access_token="test-wa-token",
        wa_app_secret="test-app-secret",
        wa_webhook_verify_token="test-verify-token",
        owner_phone="2348012345678",
        owner_email="owner@testshop.com",
    )


@pytest.fixture
def product(db, tenant):
    return Product.objects.create(
        tenant=tenant,
        name="Test Product",
        description="A great test product",
        price_min="1000.00",
        price_max="2000.00",
        currency="NGN",
    )


@pytest.fixture
def conversation(db, tenant):
    return Conversation.objects.create(
        tenant=tenant,
        customer_wa_id="2348099999999",
        state=Conversation.STATE_ACTIVE,
    )


@pytest.fixture
def fake_redis(monkeypatch):
    r = fakeredis.FakeRedis()
    monkeypatch.setattr("apps.conversations.tasks._redis", lambda: r)
    return r


@pytest.fixture
def mock_chat(monkeypatch):
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "How can I help you today?"
    mock_response.choices[0].message.tool_calls = None
    mock = MagicMock(return_value=mock_response)
    monkeypatch.setattr("apps.conversations.tasks.chat", mock)
    return mock


@pytest.fixture
def mock_whatsapp(monkeypatch):
    mock_client = MagicMock()
    monkeypatch.setattr("apps.conversations.tasks.WhatsAppClient", lambda tenant: mock_client)
    return mock_client

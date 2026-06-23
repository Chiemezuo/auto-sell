# Testing

How to run the test suite, what it covers, and patterns for writing new tests.

---

## Running Tests

```bash
# Ensure postgres and redis are running first
docker compose up -d

# Activate your virtual environment
source .venv/bin/activate

# Run all tests
pytest tests/ apps/ -v

# Run a specific module
pytest tests/conversations/ -v
pytest tests/payments/ -v

# Run with coverage report
pytest tests/ apps/ --cov=apps --cov-report=term-missing

# Run with HTML coverage report (opens htmlcov/index.html)
pytest tests/ apps/ --cov=apps --cov-report=html
```

`pytest` is configured in `pyproject.toml`:
```toml
[tool.pytest.ini_options]
DJANGO_SETTINGS_MODULE = "auto_sell.settings.local"
python_files = ["tests.py", "test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
testpaths = ["tests", "apps"]
```

Tests live in `tests/` (project-level, organised by app) and any `tests.py` / `test_*.py` inside `apps/`.

---

## Current Test Suite

41 tests across five modules, all passing (requires Postgres for catalog and payment task tests).

### `tests/conversations/test_webhooks.py` — 6 tests

These test the Django Ninja endpoint at `POST /api/webhooks/whatsapp/{tenant_slug}/` end-to-end through the HTTP layer.

| Test | What it checks |
|---|---|
| `test_verify_webhook_returns_challenge` | `GET` verification returns the `hub.challenge` string when the verify token matches |
| `test_verify_webhook_wrong_token_returns_403` | Wrong verify token returns 403 |
| `test_receive_message_enqueues_task` | A valid signed POST enqueues `process_message.delay` exactly once |
| `test_receive_message_deduplicates_by_wa_message_id` | A `wa_message_id` that already exists in `Message` does not re-enqueue the task |
| `test_receive_message_invalid_signature_returns_403` | A tampered `X-Hub-Signature-256` is rejected |
| `test_non_text_message_enqueues_reply_unsupported` | An image/audio message dispatches `reply_unsupported_message.delay` with the right arguments |

### `tests/conversations/test_tasks.py` — 20 tests

These call `process_message.apply()`, `reply_unsupported_message.apply()`, and `sweep_abandoned_conversations.apply()` synchronously (no broker needed), with Redis replaced by `fakeredis` and external calls mocked.

| Test | What it checks |
|---|---|
| `test_process_message_lock_prevents_double_processing` | A pre-set Redis lock causes the task to exit before calling the LLM |
| `test_returning_customer_resets_completed_conversation` | A `STATE_COMPLETED` conversation is reset to `active` and the LLM is called |
| `test_returning_customer_resets_abandoned_conversation` | Same reset for `STATE_ABANDONED` |
| `test_awaiting_payment_sends_reminder_when_link_pending` | `STATE_AWAITING_PAYMENT` + a `STATUS_PENDING` link → sends a reminder; LLM not called |
| `test_awaiting_payment_resets_when_link_expired` | `STATE_AWAITING_PAYMENT` + a `STATUS_EXPIRED` link → resets to `active`; LLM is called |
| `test_awaiting_payment_resets_when_link_failed` | `STATE_AWAITING_PAYMENT` + a `STATUS_FAILED` link → resets to `active`; LLM is called |
| `test_awaiting_payment_resets_when_no_link` | `STATE_AWAITING_PAYMENT` + no link → resets to `active`; LLM is called |
| `test_reply_unsupported_message_sends_text` | `reply_unsupported_message` sends a text that mentions "text" |
| `test_rate_limit_under_threshold_passes_through` | A customer at 9/10 messages is not blocked; LLM is called normally |
| `test_rate_limit_over_threshold_blocks_llm_and_sends_reply` | A customer at 10/10 messages is blocked; LLM not called; "slow down" reply sent |
| `test_rate_limit_ttl_set_on_first_hit` | The rate key has a positive TTL after the first message (window started) |
| `test_unsupported_message_rate_limited_returns_silently` | `reply_unsupported_message` drops silently when over the rate limit (no WA send) |
| `test_sweep_active_over_24h_becomes_abandoned` | An `active` conversation idle for 25h is marked `abandoned` by the sweep |
| `test_sweep_active_within_24h_untouched` | An `active` conversation idle for less than 24h is not touched |
| `test_sweep_awaiting_payment_over_48h_becomes_abandoned` | An `awaiting_payment` conversation idle for 49h is marked `abandoned` |
| `test_sweep_awaiting_payment_within_48h_untouched` | An `awaiting_payment` conversation idle for 25h is not touched |
| `test_sweep_completed_conversations_not_touched` | A `completed` conversation is never touched regardless of age |
| `test_escalated_conversation_is_silent` | A message on an `escalated` conversation produces no LLM call and no WhatsApp reply |
| `test_escalation_tool_sets_state_and_notifies_owner` | LLM calling `escalate_to_human` sets state to `escalated` and enqueues `notify_owner_escalation` with the reason |
| `test_notify_owner_escalation_sends_whatsapp` | `notify_owner_escalation` sends a WhatsApp message to `owner_phone` containing the customer ID and reason |

### `tests/payments/test_tasks.py` — 5 tests

These call `create_payment_link.apply()` synchronously with `PaystackGateway` and `WhatsAppClient` mocked.

| Test | What it checks |
|---|---|
| `test_create_payment_link_calls_paystack` | `initialize_transaction` called with correct amount and placeholder email |
| `test_create_payment_link_creates_db_record` | `PaymentLink` row created with correct reference, URL, amount, and `STATUS_PENDING` |
| `test_create_payment_link_sets_awaiting_payment_state` | Conversation transitions to `STATE_AWAITING_PAYMENT` |
| `test_create_payment_link_sends_whatsapp_with_url` | WhatsApp message sent to customer containing the payment URL |
| `test_create_payment_link_nonexistent_conversation` | Graceful no-op when `conversation_id` doesn't exist |

### `tests/catalog/test_search.py` — 5 tests

These test `get_relevant_products()` end-to-end against a real PostgreSQL database with the `search_vector` populated by the `post_save` signal.

| Test | What it checks |
|---|---|
| `test_search_returns_matching_product` | A product whose name/description match the query is returned |
| `test_search_filters_by_tenant` | A product belonging to a different tenant is not returned |
| `test_search_excludes_unavailable_products` | Products with `is_available=False` are excluded |
| `test_search_returns_empty_for_no_match` | A query with no matching terms returns an empty list |
| `test_search_respects_limit` | The `limit` parameter caps the number of results |

### `tests/payments/test_webhook.py` — 5 tests

These test the Paystack webhook endpoint at `POST /api/payments/paystack/webhook/`.

| Test | What it checks |
|---|---|
| `test_paystack_webhook_creates_sale_and_transitions_state` | `charge.success` creates a `Sale`, marks `PaymentLink` as paid, sets conversation → `completed` |
| `test_paystack_webhook_idempotency` | Posting the same reference twice creates exactly one `Sale` |
| `test_paystack_webhook_invalid_signature_returns_403` | Invalid HMAC-SHA512 is rejected |
| `test_paystack_webhook_ignores_unrecognised_events` | Unrecognised events (e.g. `transfer.success`) return `{"status": "ignored"}` with no side effects |
| `test_paystack_charge_failed_marks_link_failed_and_resets_conversation` | `charge.failed` sets `PaymentLink → STATUS_FAILED` and resets conversation to `active` |

---

## Fixtures

All shared fixtures live in `tests/conftest.py`. The project-root `conftest.py` provides only the `user` fixture.

### Object fixtures

```python
@pytest.fixture
def tenant(db):
    # Creates a Tenant with known WhatsApp credentials and app secret

@pytest.fixture
def product(db, tenant):
    # Creates a Product with price_min=1000 / price_max=2000 NGN

@pytest.fixture
def conversation(db, tenant):
    # Creates a Conversation in STATE_ACTIVE for customer 2348099999999
```

### Infrastructure fixtures

```python
@pytest.fixture
def fake_redis(monkeypatch):
    # Replaces apps.conversations.tasks._redis with fakeredis.FakeRedis()
    # Returns the FakeRedis instance so tests can pre-seed keys

@pytest.fixture
def mock_chat(monkeypatch):
    # Replaces apps.conversations.tasks.chat with a MagicMock
    # Returns a canned response: content="How can I help?", tool_calls=None
    # Returns the MagicMock so tests can assert call count / args

@pytest.fixture
def mock_whatsapp(monkeypatch):
    # Replaces apps.conversations.tasks.WhatsAppClient with lambda tenant: mock_client
    # Returns mock_client so tests can assert on send_text / send_media calls
```

### Webhook helpers

```python
def build_wa_payload(phone_number_id, sender_wa_id, message_type="text", text_body=None, message_id="msg_test_1"):
    # Constructs a WhatsApp Cloud API webhook body

def sign_wa_request(secret: str, body: bytes) -> str:
    # Returns the X-Hub-Signature-256 header value for a given body + app secret
```

---

## Writing New Tests

### Database access

```python
@pytest.mark.django_db
def test_something(tenant, conversation):
    # Use the tenant and conversation fixtures — they get a real test DB row
    ...
```

### Testing a Celery task directly

Call `.apply(kwargs={...})` to run synchronously without a broker:

```python
from apps.conversations.tasks import process_message

@pytest.mark.django_db
def test_my_task(tenant, conversation, fake_redis, mock_chat, mock_whatsapp):
    process_message.apply(kwargs={
        "tenant_id": str(tenant.id),
        "customer_wa_id": conversation.customer_wa_id,
        "message_text": "Hello",
        "wa_message_id": "msg_unique_1",
    })
    mock_chat.assert_called_once()
```

### Testing a webhook endpoint

Use pytest-django's `client` fixture with manually-signed bodies:

```python
from tests.conftest import build_wa_payload, sign_wa_request

@pytest.mark.django_db
def test_my_webhook(client, tenant):
    body = json.dumps(build_wa_payload(tenant.wa_phone_number_id, "234800000000")).encode()
    response = client.post(
        f"/api/webhooks/whatsapp/{tenant.slug}/",
        data=body,
        content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256=sign_wa_request(tenant.wa_app_secret, body),
    )
    assert response.status_code == 200
```

### Overriding settings in a test

Use pytest-django's `settings` fixture:

```python
def test_paystack_something(client, settings):
    settings.PAYSTACK_SECRET_KEY = "test-key"
    # ... rest of test
```

---

## Gaps (not yet covered)

- `apps/catalog/` — FTS search (`get_relevant_products`), `search_vector` signal, media upload endpoint
- `apps/tenants/` — slug uniqueness, `TenantUser` linking, admin site access control
- `apps/conversations/` — `_dispatch_tool` branch for `send_product_media` and `escalate_to_human`; full `process_message` happy-path with tool calls
- `apps/notifications/` — `alert_owner` retry exhaustion logging, `send_confirmation`
- `apps/payments/` — `create_payment_link` task (price validation, Paystack API call, state transition to `awaiting_payment`)

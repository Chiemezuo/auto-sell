# Testing

How to run the test suite, what can be tested right now, and patterns for writing new tests.

---

## Running Tests

```bash
# Ensure postgres is running first
docker compose up -d

# Activate your virtual environment
source .venv/bin/activate

# Run all tests
pytest apps/ -v

# Run a single app
pytest apps/catalog/ -v

# Run a single file
pytest apps/tenants/tests.py -v

# Run with coverage report
pytest apps/ --cov=apps --cov-report=term-missing

# Run with HTML coverage report (opens htmlcov/index.html)
pytest apps/ --cov=apps --cov-report=html
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

Tests are found in two places: `tests/` (project-level) and any `tests.py` or `test_*.py` file inside `apps/`.

---

## What Can Be Tested Right Now

The following checks verify the current scaffold is correctly wired:

```bash
# 1. Verify Django configuration (settings, models, admin, signals, URLs)
python manage.py check

# 2. Verify no unapplied migrations exist
python manage.py migrate --check

# 3. Run the test suite (minimal, but should all pass)
pytest apps/ -v
```

**What these verify:**
- All five apps are correctly registered in `INSTALLED_APPS`
- All models are valid (field types, FKs, constraints)
- All admin classes reference models that exist
- The `post_save` signal on `Product` is connected
- No circular imports
- No missing migrations
- The `conftest.py` user fixture works (touches the database)

---

## Current Test Fixtures

**`conftest.py`** (project root) — available to all tests:

```python
@pytest.fixture
def user(db):
    return User.objects.create_user(
        username="testuser",
        email="test@example.com",
        password="testpass"
    )
```

The `db` fixture (from `pytest-django`) enables database access for this fixture and any test that uses it. Without `db`, a test that touches the database will raise a `PytestUnraisableExceptionWarning`.

---

## Writing New Tests

### Test file location
Place tests in a `tests.py` file inside the app directory, or create a `tests/` subdirectory:

```
apps/
└── catalog/
    ├── tests.py           ← simple
    └── tests/             ← for larger apps
        ├── __init__.py
        ├── test_models.py
        ├── test_search.py
        └── test_api.py
```

### Basic test structure
```python
import pytest
from faker import Faker

fake = Faker()

@pytest.mark.django_db
def test_something():
    # Arrange
    ...
    # Act
    ...
    # Assert
    ...
```

`@pytest.mark.django_db` grants database access for that specific test. Alternatively, use the `db` fixture in the function signature:

```python
def test_something(db):
    ...
```

### Common fixtures to write

Add these to `conftest.py` or a per-app `conftest.py` as you build features:

```python
@pytest.fixture
def tenant(db):
    from apps.tenants.models import Tenant
    return Tenant.objects.create(
        name="Test Boutique",
        slug="test-boutique",
        wa_phone_number_id="123456789",
        wa_business_account_id="987654321",
        wa_access_token="test-token",
        wa_webhook_verify_token="verify-me",
        owner_phone="2348012345678",
        owner_email="owner@testboutique.com",
    )

@pytest.fixture
def product(db, tenant):
    from apps.catalog.models import Product
    return Product.objects.create(
        tenant=tenant,
        name="Nike Air Max 90",
        description="Classic running shoe in white/grey",
        price_min="45000.00",
        price_max="55000.00",
        currency="NGN",
    )

@pytest.fixture
def conversation(db, tenant):
    from apps.conversations.models import Conversation
    return Conversation.objects.create(
        tenant=tenant,
        customer_wa_id="2348099887766",
    )
```

---

## Test Patterns by App

### `apps/tenants` — models

```python
@pytest.mark.django_db
def test_tenant_slug_is_unique(tenant):
    from apps.tenants.models import Tenant
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        Tenant.objects.create(
            name="Another Boutique",
            slug=tenant.slug,   # duplicate slug
            wa_phone_number_id="999",
            wa_business_account_id="888",
            wa_access_token="token",
            wa_webhook_verify_token="verify",
            owner_phone="2348000000000",
            owner_email="other@example.com",
        )

@pytest.mark.django_db
def test_tenant_user_links_user_to_tenant(user, tenant):
    from apps.tenants.models import TenantUser
    tu = TenantUser.objects.create(tenant=tenant, user=user)
    assert tu.user.tenant_profile.tenant == tenant
```

### `apps/catalog` — search vector

```python
@pytest.mark.django_db
def test_search_vector_populated_on_save(product):
    product.refresh_from_db()
    assert product.search_vector is not None

@pytest.mark.django_db
def test_product_fts_finds_by_name(product):
    from django.contrib.postgres.search import SearchQuery
    from apps.catalog.models import Product
    results = Product.objects.filter(search_vector=SearchQuery("Nike"))
    assert product in results

@pytest.mark.django_db
def test_product_fts_finds_by_description(product):
    from django.contrib.postgres.search import SearchQuery
    from apps.catalog.models import Product
    results = Product.objects.filter(search_vector=SearchQuery("running shoe"))
    assert product in results

@pytest.mark.django_db
def test_unavailable_products_excluded(tenant):
    from apps.catalog.models import Product
    p = Product.objects.create(
        tenant=tenant, name="Hidden Item", description="...",
        price_min=1000, price_max=2000, is_available=False
    )
    from django.contrib.postgres.search import SearchQuery
    results = Product.objects.filter(
        search_vector=SearchQuery("Hidden"), is_available=True
    )
    assert p not in results
```

### `apps/conversations` — constraints

```python
@pytest.mark.django_db
def test_one_conversation_per_customer_per_tenant(conversation, tenant):
    from apps.conversations.models import Conversation
    from django.db import IntegrityError
    with pytest.raises(IntegrityError):
        Conversation.objects.create(
            tenant=tenant,
            customer_wa_id=conversation.customer_wa_id,  # duplicate
        )

@pytest.mark.django_db
def test_conversation_default_state_is_active(conversation):
    assert conversation.state == "active"
```

### `apps/payments` — status transitions

```python
@pytest.mark.django_db
def test_payment_link_default_status_is_pending(db, tenant, conversation):
    from apps.payments.models import PaymentLink
    link = PaymentLink.objects.create(
        conversation=conversation,
        tenant=tenant,
        amount="50000.00",
        gateway_reference="PAY-TEST-001",
        payment_url="https://paystack.com/pay/test",
    )
    assert link.status == "pending"
    assert link.paid_at is None
```

---

## What to Test Next (as features are built)

### Phase 3 — Catalog service
After `apps/catalog/search.py` is written:
```python
def test_get_relevant_products_returns_ranked_results(tenant, product):
    from apps.catalog.search import get_relevant_products
    results = get_relevant_products(tenant.id, "Nike running")
    assert len(results) >= 1
    assert results[0].name == "Nike Air Max 90"
```

### Phase 4 — WhatsApp webhook
After the webhook endpoint and `process_message` task are written:
```python
def test_webhook_returns_200_immediately(client, tenant):
    # The endpoint must respond in < 5 seconds regardless of LLM processing time
    payload = {...}  # valid Meta webhook payload
    response = client.post(
        f"/api/webhooks/whatsapp/{tenant.slug}/",
        data=payload, content_type="application/json",
        HTTP_X_HUB_SIGNATURE_256="sha256=...",
    )
    assert response.status_code == 200

def test_duplicate_message_is_ignored(client, tenant, conversation):
    # Same wa_message_id should not trigger a second Celery task
    ...
```

For the LLM and WhatsApp outbound calls, use `unittest.mock.patch` to avoid real API calls in tests:
```python
from unittest.mock import patch, AsyncMock

@pytest.mark.django_db
async def test_process_message_sends_reply(tenant, conversation):
    with patch("apps.conversations.tasks.WhatsAppClient") as mock_wa, \
         patch("apps.conversations.tasks.deepseek_client") as mock_llm:
        mock_llm.chat.completions.create = AsyncMock(return_value=...)
        mock_wa.return_value.send_text = AsyncMock()
        # call the task
        ...
```

### Phase 5 — Paystack
```python
def test_paystack_webhook_rejects_invalid_signature():
    response = client.post(
        "/api/payments/paystack/webhook/",
        data={}, content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE="invalid",
    )
    assert response.status_code == 400

def test_agreed_price_outside_range_raises_error(product):
    from apps.payments.tasks import validate_price
    with pytest.raises(ValueError):
        validate_price(product, agreed_price=99999)  # above price_max
```

---

## Verifying the Test Suite Passes

```bash
# This should output something like:
# apps/tenants/tests.py::... PASSED
# apps/catalog/tests.py::... PASSED
# ...
# N passed in X.XXs

pytest apps/ -v
```

If any test fails with `django.test.utils.DatabaseBlockedBySetupError`, you forgot `@pytest.mark.django_db` or the `db` fixture on that test.

If any test fails with `connection refused` errors, Postgres is not running — run `docker compose up -d` first.

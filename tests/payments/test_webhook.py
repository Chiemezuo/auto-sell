import json
import hmac
import hashlib
import pytest
from unittest.mock import patch
from apps.catalog.models import Product
from apps.conversations.models import Conversation
from apps.payments.models import PaymentLink, Sale


def _paystack_sig(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha512).hexdigest()


def _charge_success(reference: str, items_snapshot=None):
    return {
        "event": "charge.success",
        "data": {
            "reference": reference,
            "amount": 150000,
            "metadata": {
                "items_snapshot": items_snapshot or [{"name": "Test Product", "qty": 1}]
            },
        },
    }


@pytest.fixture
def payment_link(db, tenant, conversation):
    return PaymentLink.objects.create(
        conversation=conversation,
        tenant=tenant,
        amount="1500.00",
        currency="NGN",
        gateway="paystack",
        gateway_reference="ref_test_001",
        payment_url="https://paystack.com/pay/ref_test_001",
        status=PaymentLink.STATUS_PENDING,
    )


@pytest.mark.django_db
def test_paystack_webhook_creates_sale_and_transitions_state(
    client, tenant, conversation, payment_link, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_charge_success(payment_link.gateway_reference)).encode()

    with patch("apps.notifications.tasks.alert_owner.delay"), \
         patch("apps.notifications.tasks.send_confirmation.delay"):
        response = client.post(
            "/api/payments/paystack/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=_paystack_sig("test-paystack-secret", body),
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert Sale.objects.filter(payment_link=payment_link).count() == 1
    payment_link.refresh_from_db()
    assert payment_link.status == PaymentLink.STATUS_PAID
    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_COMPLETED


@pytest.mark.django_db
def test_paystack_webhook_idempotency(
    client, tenant, conversation, payment_link, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_charge_success(payment_link.gateway_reference)).encode()
    sig = _paystack_sig("test-paystack-secret", body)

    with patch("apps.notifications.tasks.alert_owner.delay"), \
         patch("apps.notifications.tasks.send_confirmation.delay"):
        client.post(
            "/api/payments/paystack/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=sig,
        )
        response = client.post(
            "/api/payments/paystack/webhook/",
            data=body,
            content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=sig,
        )

    assert response.json() == {"status": "already_processed"}
    assert Sale.objects.filter(payment_link=payment_link).count() == 1


@pytest.mark.django_db
def test_paystack_webhook_invalid_signature_returns_403(
    client, tenant, conversation, payment_link, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_charge_success(payment_link.gateway_reference)).encode()

    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE="invalidsignature",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_paystack_webhook_ignores_unrecognised_events(
    client, tenant, conversation, payment_link, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    payload = {"event": "transfer.success", "data": {"reference": payment_link.gateway_reference}}
    body = json.dumps(payload).encode()

    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=_paystack_sig("test-paystack-secret", body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ignored"}
    assert not Sale.objects.filter(payment_link=payment_link).exists()


@pytest.mark.django_db
def test_paystack_charge_failed_marks_link_failed_and_resets_conversation(
    client, tenant, conversation, payment_link, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    payload = {"event": "charge.failed", "data": {"reference": payment_link.gateway_reference}}
    body = json.dumps(payload).encode()

    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=_paystack_sig("test-paystack-secret", body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    payment_link.refresh_from_db()
    assert payment_link.status == PaymentLink.STATUS_FAILED
    conversation.refresh_from_db()
    assert conversation.state == Conversation.STATE_ACTIVE


# ---------------------------------------------------------------------------
# refund.processed
# ---------------------------------------------------------------------------

def _refund_payload(reference: str):
    return {"event": "refund.processed", "data": {"transaction_reference": reference}}


@pytest.fixture
def tracked_product(db, tenant):
    return Product.objects.create(
        tenant=tenant, name="Tracked Item", description="desc",
        price_min="500", price_max="1000", currency="NGN",
        is_available=False, stock_quantity=0,
    )


@pytest.fixture
def paid_payment_link(db, tenant, conversation):
    return PaymentLink.objects.create(
        conversation=conversation,
        tenant=tenant,
        amount="2000.00",
        currency="NGN",
        gateway="paystack",
        gateway_reference="ref_refund_001",
        payment_url="https://paystack.com/pay/ref_refund_001",
        status=PaymentLink.STATUS_PAID,
    )


@pytest.fixture
def refund_sale(db, tenant, conversation, paid_payment_link, tracked_product):
    return Sale.objects.create(
        payment_link=paid_payment_link,
        tenant=tenant,
        conversation=conversation,
        customer_wa_id=conversation.customer_wa_id,
        amount_paid="2000.00",
        items_snapshot=[{"product_id": str(tracked_product.id), "name": tracked_product.name, "qty": 2}],
        gateway_payload={"reference": "ref_refund_001"},
    )


@pytest.mark.django_db
def test_refund_marks_link_refunded_and_restores_stock(
    client, tenant, paid_payment_link, refund_sale, tracked_product, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_refund_payload(paid_payment_link.gateway_reference)).encode()

    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=_paystack_sig("test-paystack-secret", body),
    )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    paid_payment_link.refresh_from_db()
    assert paid_payment_link.status == PaymentLink.STATUS_REFUNDED
    tracked_product.refresh_from_db()
    assert tracked_product.stock_quantity == 2
    assert tracked_product.is_available is True


@pytest.mark.django_db
def test_refund_second_call_returns_not_found(
    client, tenant, paid_payment_link, refund_sale, settings
):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_refund_payload(paid_payment_link.gateway_reference)).encode()
    sig = _paystack_sig("test-paystack-secret", body)

    client.post(
        "/api/payments/paystack/webhook/",
        data=body, content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=sig,
    )
    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body, content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=sig,
    )
    # Link is now REFUNDED; the query filters on STATUS_PAID → DoesNotExist → not_found
    assert response.json() == {"status": "not_found"}


@pytest.mark.django_db
def test_refund_unknown_reference_returns_not_found(client, tenant, settings):
    settings.PAYSTACK_SECRET_KEY = "test-paystack-secret"
    body = json.dumps(_refund_payload("ref_does_not_exist")).encode()

    response = client.post(
        "/api/payments/paystack/webhook/",
        data=body,
        content_type="application/json",
        HTTP_X_PAYSTACK_SIGNATURE=_paystack_sig("test-paystack-secret", body),
    )
    assert response.json() == {"status": "not_found"}

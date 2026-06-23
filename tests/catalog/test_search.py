import pytest
from apps.catalog.models import Product
from apps.catalog.search import get_relevant_products


@pytest.mark.django_db
def test_search_returns_matching_product(tenant, product):
    # product fixture: name="Test Product", description="A great test product"
    results = list(get_relevant_products(tenant.id, "test product"))
    assert product in results


@pytest.mark.django_db
def test_search_filters_by_tenant(tenant, product, db):
    from apps.tenants.models import Tenant
    other_tenant = Tenant.objects.create(
        name="Other Shop",
        slug="other-shop",
        wa_phone_number_id="9999999999",
        wa_business_account_id="8888888888",
        wa_access_token="other-token",
        wa_app_secret="other-secret",
        wa_webhook_verify_token="other-verify",
        owner_phone="2348011111111",
        owner_email="other@shop.com",
    )
    results = list(get_relevant_products(other_tenant.id, "test product"))
    assert product not in results


@pytest.mark.django_db
def test_search_excludes_unavailable_products(tenant, product):
    product.is_available = False
    product.save()
    results = list(get_relevant_products(tenant.id, "test product"))
    assert product not in results


@pytest.mark.django_db
def test_search_returns_empty_for_no_match(tenant, product):
    results = list(get_relevant_products(tenant.id, "xyzzy_no_match_at_all"))
    assert len(results) == 0


@pytest.mark.django_db
def test_search_respects_limit(tenant):
    for i in range(7):
        Product.objects.create(
            tenant=tenant,
            name=f"Widget {i}",
            description="A great widget for testing",
            price_min="100.00",
            price_max="200.00",
            currency="NGN",
        )
    results = list(get_relevant_products(tenant.id, "widget", limit=3))
    assert len(results) <= 3

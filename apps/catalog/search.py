from django.contrib.postgres.search import SearchQuery, SearchRank
from .models import Product


def get_relevant_products(tenant_id, query_text: str, limit: int = 5):
    query = SearchQuery(query_text)
    return (
        Product.objects.filter(tenant_id=tenant_id, is_available=True)
        .annotate(rank=SearchRank("search_vector", query))
        .filter(rank__gt=0)
        .order_by("-rank")[:limit]
    )

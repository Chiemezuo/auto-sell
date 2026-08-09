from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models.expressions import RawSQL
from .models import Product


def get_relevant_products(tenant_id, query_text: str, limit: int = 5):
    query = SearchQuery(query_text)
    return (
        Product.objects.filter(tenant_id=tenant_id, is_available=True)
        .annotate(rank=SearchRank("search_vector", query))
        .filter(rank__gt=0.001)
        .order_by("-rank")[:limit]
    )


def semantic_search(tenant_id, query_text: str, limit: int = 10):
    from apps.conversations.llm import get_embedding_provider
    try:
        provider = get_embedding_provider()
        query_embedding = provider.embed(query_text)
    except Exception:
        return Product.objects.none()
    return (
        Product.objects.filter(tenant_id=tenant_id, is_available=True, embedding__isnull=False)
        .annotate(similarity=RawSQL("1 - (embedding <=> %s::vector)", (query_embedding,)))
        .filter(similarity__gt=0.7)
        .order_by("-similarity")[:limit]
    )


def hybrid_search(tenant_id, query_text: str, limit: int = 10):
    fts_results = list(get_relevant_products(tenant_id, query_text, limit=limit))
    semantic_results = list(semantic_search(tenant_id, query_text, limit=limit))

    fts_ids = {p.id for p in fts_results}
    merged = list(fts_results)

    for p in semantic_results:
        if p.id not in fts_ids:
            merged.append(p)

    return merged[:limit]

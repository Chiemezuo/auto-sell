import logging
from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


@shared_task
def generate_product_embedding(product_id: str):
    from .models import Product
    from apps.conversations.llm import get_embedding_provider

    try:
        product = Product.objects.get(id=product_id)
    except Product.DoesNotExist:
        return

    text = f"{product.name} {product.description}"
    try:
        provider = get_embedding_provider()
        embedding = provider.embed(text)
        Product.objects.filter(pk=product.pk).update(embedding=embedding)
        logger.info("Embedding generated for product %s", product_id)
    except Exception:
        logger.exception("Failed to generate embedding for product %s", product_id)

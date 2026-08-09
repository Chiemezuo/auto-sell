from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from .models import Product


@receiver(post_save, sender=Product)
def update_search_vector(sender, instance, **kwargs):
    Product.objects.filter(pk=instance.pk).update(
        search_vector=SearchVector("name", weight="A") + SearchVector("description", weight="B")
    )


@receiver(post_save, sender=Product)
def schedule_embedding_generation(sender, instance, created, **kwargs):
    if created or kwargs.get("update_fields") is None or "embedding" not in kwargs.get("update_fields", ()):
        from .tasks import generate_product_embedding
        generate_product_embedding.delay(str(instance.id))

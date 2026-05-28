from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.postgres.search import SearchVector
from .models import Product


@receiver(post_save, sender=Product)
def update_search_vector(sender, instance, **kwargs):
    Product.objects.filter(pk=instance.pk).update(
        search_vector=SearchVector("name", weight="A") + SearchVector("description", weight="B")
    )

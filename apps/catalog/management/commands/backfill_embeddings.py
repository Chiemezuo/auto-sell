from django.core.management.base import BaseCommand
from apps.catalog.models import Product
from apps.catalog.tasks import generate_product_embedding


class Command(BaseCommand):
    help = "Generate embeddings for all products that don't have one yet"

    def handle(self, **options):
        products = Product.objects.filter(embedding__isnull=True)
        total = products.count()
        self.stdout.write(f"Backfilling embeddings for {total} products...")
        for i, product in enumerate(products, 1):
            generate_product_embedding.delay(str(product.id))
            if i % 50 == 0:
                self.stdout.write(f"  Enqueued {i}/{total}...")
        self.stdout.write(self.style.SUCCESS(f"Enqueued {total} embedding tasks"))

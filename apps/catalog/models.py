from uuid import uuid4
from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from apps.tenants.models import Tenant


class Product(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="products")
    name = models.CharField(max_length=255)
    description = models.TextField()
    price_min = models.DecimalField(max_digits=12, decimal_places=2)
    price_max = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="NGN")
    is_available = models.BooleanField(default=True)
    search_vector = SearchVectorField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        indexes = [GinIndex(fields=["search_vector"])]

    def __str__(self):
        return f"{self.name} ({self.tenant.name})"


class ProductMedia(models.Model):
    MEDIA_TYPES = [("image", "Image"), ("video", "Video"), ("document", "Document")]

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="media")
    media_type = models.CharField(max_length=16, choices=MEDIA_TYPES, default="image")
    s3_key = models.CharField(max_length=512, help_text="Path within the R2/S3 bucket")
    cdn_url = models.URLField(max_length=1024)
    wa_media_id = models.CharField(max_length=128, blank=True, help_text="Cached after first WhatsApp upload")
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order"]

    def __str__(self):
        return f"{self.media_type} for {self.product.name}"

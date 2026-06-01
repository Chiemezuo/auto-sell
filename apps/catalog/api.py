import uuid
from ninja import Router, File, Form, Schema
from ninja.files import UploadedFile
from ninja.security import django_auth
from django.shortcuts import get_object_or_404
from .models import Product, ProductMedia
from .storage import upload_product_media

router = Router(tags=["Catalog"])

_ALLOWED_MEDIA_TYPES = {"image", "video", "document"}


class UploadMediaIn(Schema):
    media_type: str = "image"
    sort_order: int = 0


class ProductMediaOut(Schema):
    id: int
    media_type: str
    s3_key: str
    cdn_url: str
    sort_order: int


@router.post("/products/{product_id}/media/", response=ProductMediaOut, auth=django_auth)
def upload_media(
    request,
    product_id: uuid.UUID,
    data: Form[UploadMediaIn],
    file: UploadedFile = File(...),
):
    if data.media_type not in _ALLOWED_MEDIA_TYPES:
        raise ValueError(f"media_type must be one of {_ALLOWED_MEDIA_TYPES}")

    tenant = request.user.tenant_profile.tenant
    product = get_object_or_404(Product, id=product_id, tenant=tenant)

    ext = file.name.rsplit(".", 1)[-1].lower() if "." in file.name else "bin"
    s3_key = f"tenants/{tenant.id}/products/{product.id}/{uuid.uuid4()}.{ext}"
    cdn_url = upload_product_media(file, s3_key, file.content_type)

    media = ProductMedia.objects.create(
        product=product,
        media_type=data.media_type,
        s3_key=s3_key,
        cdn_url=cdn_url,
        sort_order=data.sort_order,
    )
    return media

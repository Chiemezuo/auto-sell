import boto3
from django.conf import settings


def _client():
    kwargs = {
        "aws_access_key_id": settings.S3_ACCESS_KEY,
        "aws_secret_access_key": settings.S3_SECRET_KEY,
        "region_name": settings.S3_REGION,
    }
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    return boto3.client("s3", **kwargs)


def _cdn_base() -> str:
    if settings.S3_CDN_BASE_URL:
        return settings.S3_CDN_BASE_URL.rstrip("/")
    if settings.S3_ENDPOINT_URL:
        return f"{settings.S3_ENDPOINT_URL.rstrip('/')}/{settings.S3_BUCKET_NAME}"
    region = settings.S3_REGION or "us-east-1"
    return f"https://{settings.S3_BUCKET_NAME}.s3.{region}.amazonaws.com"


def upload_product_media(file_obj, s3_key: str, content_type: str) -> str:
    _client().upload_fileobj(
        file_obj,
        settings.S3_BUCKET_NAME,
        s3_key,
        ExtraArgs={"ContentType": content_type},
    )
    return f"{_cdn_base()}/{s3_key}"


def generate_presigned_url(s3_key: str, expires_in: int = 3600) -> str:
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key},
        ExpiresIn=expires_in,
    )

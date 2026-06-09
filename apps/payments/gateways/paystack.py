import hashlib
import hmac
import httpx
from django.conf import settings
from .base import PaymentGateway

_API_BASE = "https://api.paystack.co"


class PaystackGateway(PaymentGateway):
    def initialize_transaction(self, amount: float, email: str, metadata: dict) -> dict:
        resp = httpx.post(
            f"{_API_BASE}/transaction/initialize",
            headers={
                "Authorization": f"Bearer {settings.PAYSTACK_SECRET_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "amount": int(amount * 100),  # Paystack expects kobo (smallest currency unit)
                "email": email,
                "metadata": metadata,
            },
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return {"authorization_url": data["authorization_url"], "reference": data["reference"]}

    def verify_webhook_signature(self, body: bytes, signature: str) -> bool:
        expected = hmac.new(
            settings.PAYSTACK_SECRET_KEY.encode(),
            body,
            hashlib.sha512,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

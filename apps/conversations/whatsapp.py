import httpx
from django.conf import settings


class WhatsAppClient:
    def __init__(self, tenant):
        self.phone_number_id = tenant.wa_phone_number_id
        self._headers = {"Authorization": f"Bearer {tenant.wa_access_token}"}

    def send_text(self, to: str, body: str) -> dict:
        return self._post("/messages", {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        })

    def send_media(self, to: str, media_type: str, media_id: str, caption: str = None) -> dict:
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": media_type,
            media_type: {"id": media_id},
        }
        if caption:
            payload[media_type]["caption"] = caption
        return self._post("/messages", payload)

    def upload_media(self, file_obj, content_type: str) -> str:
        url = f"{settings.WA_API_BASE}/{self.phone_number_id}/media"
        resp = httpx.post(
            url,
            headers={"Authorization": self._headers["Authorization"]},
            data={"messaging_product": "whatsapp", "type": content_type},
            files={"file": (None, file_obj, content_type)},
        )
        resp.raise_for_status()
        return resp.json()["id"]

    def _post(self, path: str, payload: dict) -> dict:
        url = f"{settings.WA_API_BASE}/{self.phone_number_id}{path}"
        resp = httpx.post(
            url,
            headers={**self._headers, "Content-Type": "application/json"},
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

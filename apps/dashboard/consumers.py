import json
import logging
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from apps.tenants.models import TenantUser

logger = logging.getLogger(__name__)


class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get("user")
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return

        try:
            tenant_profile = user.tenant_profile
        except (AttributeError, TenantUser.DoesNotExist):
            await self.close(code=4003)
            return

        self.tenant_id = str(tenant_profile.tenant_id)
        self.group_name = f"dashboard_{self.tenant_id}"

        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        logger.info("Dashboard WebSocket connected for tenant %s user %s", self.tenant_id, user.email)

    async def disconnect(self, close_code):
        if hasattr(self, "group_name"):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def conversation_update(self, event):
        await self.send_json({
            "type": "conversation_update",
            "conversation_id": event["conversation_id"],
            "customer_wa_id": event["customer_wa_id"],
            "state": event["state"],
            "last_message_at": event.get("last_message_at"),
        })

    async def new_message(self, event):
        await self.send_json({
            "type": "new_message",
            "conversation_id": event["conversation_id"],
            "message": {
                "role": event["role"],
                "content": event["content"],
                "created_at": event.get("created_at"),
                "message_id": event.get("message_id"),
            },
        })

    async def draft_ready(self, event):
        await self.send_json({
            "type": "draft_ready",
            "conversation_id": event["conversation_id"],
            "draft": event["draft"],
            "message_id": event.get("message_id"),
        })

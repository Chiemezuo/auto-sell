from ninja import Router
from ninja.errors import HttpError
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from apps.conversations.models import Conversation, Message, BotFeedback
from apps.conversations.whatsapp import WhatsAppClient
from apps.tenants.models import TenantUser

router = Router(tags=["Dashboard"])


def _get_tenant(request: HttpRequest):
    try:
        return request.user.tenant_profile.tenant
    except (AttributeError, TenantUser.DoesNotExist):
        raise HttpError(403, "Not a tenant user")


@router.get("/conversations/")
def list_conversations(request: HttpRequest):
    tenant = _get_tenant(request)
    conversations = Conversation.objects.filter(tenant=tenant).select_related("tenant").order_by("-last_message_at")[:50]
    return [
        {
            "id": str(c.id),
            "customer_wa_id": c.customer_wa_id,
            "state": c.state,
            "phase": c.phase,
            "co_pilot_mode": c.co_pilot_mode,
            "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None,
        }
        for c in conversations
    ]


@router.get("/conversations/{conversation_id}/messages/")
def get_messages(request: HttpRequest, conversation_id: str):
    tenant = _get_tenant(request)
    conversation = get_object_or_404(Conversation, id=conversation_id, tenant=tenant)
    messages = Message.objects.filter(conversation=conversation).order_by("created_at")[:100]
    return [
        {
            "id": str(m.id),
            "role": m.role,
            "content": m.content,
            "sent_by_owner": m.sent_by_owner,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.post("/conversations/{conversation_id}/take-over/")
def take_over(request: HttpRequest, conversation_id: str):
    tenant = _get_tenant(request)
    conversation = get_object_or_404(Conversation, id=conversation_id, tenant=tenant)
    conversation.state = Conversation.STATE_OWNER_HANDLING
    conversation.save(update_fields=["state"])
    return {"status": "ok", "state": conversation.state}


@router.post("/conversations/{conversation_id}/hand-back/")
def hand_back(request: HttpRequest, conversation_id: str):
    tenant = _get_tenant(request)
    conversation = get_object_or_404(Conversation, id=conversation_id, tenant=tenant)
    conversation.state = Conversation.STATE_ACTIVE
    conversation.save(update_fields=["state"])
    return {"status": "ok", "state": conversation.state}


@router.post("/conversations/{conversation_id}/reply/")
def owner_reply(request: HttpRequest, conversation_id: str, body: dict):
    tenant = _get_tenant(request)
    conversation = get_object_or_404(Conversation, id=conversation_id, tenant=tenant)
    content = body.get("content", "").strip()
    if not content:
        raise HttpError(400, "Message content is required")
    wa_client = WhatsAppClient(tenant)
    wa_client.send_text(conversation.customer_wa_id, content)
    Message.objects.create(
        conversation=conversation,
        role=Message.ROLE_ASSISTANT,
        content=content,
        sent_by_owner=True,
    )
    return {"status": "ok"}


@router.post("/messages/{message_id}/feedback/")
def create_feedback(request: HttpRequest, message_id: str, body: dict):
    tenant = _get_tenant(request)
    message = get_object_or_404(Message, id=message_id, conversation__tenant=tenant)
    feedback_type = body.get("type", "")
    if feedback_type not in ("good", "bad", "edited"):
        raise HttpError(400, "Invalid feedback type")

    feedback, _ = BotFeedback.objects.update_or_create(
        message=message,
        defaults={
            "conversation": message.conversation,
            "tenant": tenant,
            "feedback_type": feedback_type,
            "owner_note": body.get("note", ""),
            "edited_response": body.get("edited_response", ""),
            "context_snapshot": body.get("context_snapshot", []),
            "prompt_version": message.prompt_version or "",
        },
    )
    return {"status": "ok", "feedback_id": str(feedback.id)}

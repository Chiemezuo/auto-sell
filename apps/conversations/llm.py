from openai import OpenAI
from django.conf import settings

_client = OpenAI(api_key=settings.DEEPSEEK_API_KEY, base_url=settings.DEEPSEEK_BASE_URL)


def chat(messages: list, tools: list | None = None):
    kwargs = {"model": settings.DEEPSEEK_MODEL, "messages": messages}
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    return _client.chat.completions.create(**kwargs)

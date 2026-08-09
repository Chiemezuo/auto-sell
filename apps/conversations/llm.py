from abc import ABC, abstractmethod
from openai import OpenAI
from django.conf import settings


class LLMProvider(ABC):
    @abstractmethod
    def chat(self, messages: list, tools: list | None = None, model: str | None = None):
        ...

    @abstractmethod
    def classify(self, text: str, labels: list[str], model: str | None = None) -> str:
        ...

    @abstractmethod
    def embed(self, text: str, model: str | None = None) -> list[float]:
        ...


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, api_key: str, base_url: str, default_model: str,
                 classification_model: str | None = None, embedding_model: str | None = None):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.default_model = default_model
        self.classification_model = classification_model or default_model
        self.embedding_model = embedding_model or "text-embedding-3-small"

    def chat(self, messages: list, tools: list | None = None, model: str | None = None):
        kwargs = {"model": model or self.default_model, "messages": messages}
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"
        return self._client.chat.completions.create(**kwargs)

    def classify(self, text: str, labels: list[str], model: str | None = None) -> str:
        label_list = "\n".join(f"- {label}" for label in labels)
        messages = [
            {"role": "system", "content": f"Classify the user message into exactly one of these categories. Reply with only the category name, nothing else.\n\nCategories:\n{label_list}"},
            {"role": "user", "content": text},
        ]
        response = self.chat(messages, model=model or self.classification_model)
        result = response.choices[0].message.content.strip().lower()
        for label in labels:
            if label.lower() in result:
                return label
        return labels[0]

    def embed(self, text: str, model: str | None = None) -> list[float]:
        resp = self._client.embeddings.create(
            model=model or self.embedding_model,
            input=text,
        )
        return resp.data[0].embedding


class DeepSeekProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str | None = None):
        super().__init__(
            api_key=api_key or settings.DEEPSEEK_API_KEY,
            base_url=settings.DEEPSEEK_BASE_URL,
            default_model=settings.DEEPSEEK_MODEL,
            classification_model=getattr(settings, "DEEPSEEK_CLASSIFICATION_MODEL", settings.DEEPSEEK_MODEL),
        )


class OpenAIProvider(OpenAICompatibleProvider):
    def __init__(self, api_key: str):
        super().__init__(
            api_key=api_key,
            base_url="https://api.openai.com/v1",
            default_model="gpt-4o",
            classification_model="gpt-4o-mini",
            embedding_model="text-embedding-3-small",
        )


class AnthropicProvider(LLMProvider):
    def __init__(self, api_key: str):
        try:
            import anthropic
        except ImportError:
            raise ImportError("anthropic package is required for AnthropicProvider. Install with: pip install anthropic")
        self._client = anthropic.Anthropic(api_key=api_key)
        self.default_model = "claude-sonnet-4-20250514"
        self.classification_model = "claude-haiku-4-20250514"

    def chat(self, messages: list, tools: list | None = None, model: str | None = None):
        system = None
        api_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                api_messages.append(msg)
        kwargs = {"model": model or self.default_model, "messages": api_messages}
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools
        response = self._client.messages.create(**kwargs)
        return _AnthropicResponseAdapter(response)

    def classify(self, text: str, labels: list[str], model: str | None = None) -> str:
        label_list = "\n".join(f"- {label}" for label in labels)
        messages = [{"role": "user", "content": text}]
        response = self.chat(
            [
                {"role": "system", "content": f"Classify the user message into exactly one of these categories. Reply with only the category name, nothing else.\n\nCategories:\n{label_list}"},
                {"role": "user", "content": text},
            ],
            model=model or self.classification_model,
        )
        result = response.choices[0].message.content.strip().lower()
        for label in labels:
            if label.lower() in result:
                return label
        return labels[0]

    def embed(self, text: str, model: str | None = None) -> list[float]:
        raise NotImplementedError("Anthropic does not provide embeddings. Use OpenAI or another provider for embeddings.")


class _AnthropicResponseAdapter:
    def __init__(self, anthropic_response):
        self._raw = anthropic_response

    @property
    def choices(self):
        return [self]

    @property
    def message(self):
        return _AnthropicMessageAdapter(self._raw)

    def __getitem__(self, index):
        return self


class _AnthropicMessageAdapter:
    def __init__(self, raw):
        self._raw = raw

    @property
    def content(self):
        for block in self._raw.content:
            if block.type == "text":
                return block.text
        return ""

    @property
    def tool_calls(self):
        result = []
        for block in self._raw.content:
            if block.type == "tool_use":
                result.append(_AnthropicToolCall(block))
        return result or None


class _AnthropicToolCall:
    def __init__(self, block):
        self._block = block
        self.id = block.id
        self.function = _AnthropicFunction(block)


class _AnthropicFunction:
    def __init__(self, block):
        self.name = block.name
        self.arguments = __import__("json").dumps(block.input)


def get_provider(tenant, tier: str = "primary") -> LLMProvider:
    provider_key = getattr(tenant, f"{tier}_llm_provider", None) or "deepseek"

    if provider_key == "openai":
        return OpenAIProvider(api_key=getattr(settings, "OPENAI_API_KEY", ""))
    elif provider_key == "anthropic":
        return AnthropicProvider(api_key=getattr(settings, "ANTHROPIC_API_KEY", ""))
    else:
        return DeepSeekProvider()


def get_embedding_provider() -> LLMProvider:
    key = getattr(settings, "OPENAI_API_KEY", "")
    if key:
        return OpenAIProvider(api_key=key)
    return DeepSeekProvider()


def chat(messages: list, tools: list | None = None):
    provider = DeepSeekProvider()
    return provider.chat(messages, tools=tools)

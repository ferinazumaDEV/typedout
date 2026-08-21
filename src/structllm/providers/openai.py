"""OpenAI provider.

The ``openai`` SDK is imported lazily — install ``structllm[openai]`` to use
this. A pre-built ``client`` can be injected for testing the mapping offline.
"""

from __future__ import annotations

from typing import Any, List, Optional

from .base import Completion, Message, Provider, RawUsage


class OpenAIProvider(Provider):
    """Wraps ``openai.OpenAI`` behind the structllm :class:`Provider` interface."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        *,
        client: Any = None,
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
        json_mode: bool = True,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self._api_key = api_key
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - depends on env
                raise ImportError(
                    "OpenAIProvider needs the 'openai' package "
                    "(pip install structllm[openai])"
                ) from exc
            self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def complete(
        self,
        messages: List[Message],
        *,
        schema=None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Completion:
        kwargs: dict[str, Any] = {
            "model": model or self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if self.json_mode:
            # Nudges the model to emit a JSON object; repair still guards the result.
            kwargs["response_format"] = {"type": "json_object"}
        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        text = choice.message.content or ""
        usage = RawUsage(
            input_tokens=getattr(response.usage, "prompt_tokens", 0),
            output_tokens=getattr(response.usage, "completion_tokens", 0),
        )
        return Completion(text=text, model=getattr(response, "model", model or self.model), usage=usage)

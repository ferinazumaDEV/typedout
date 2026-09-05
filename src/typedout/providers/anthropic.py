"""Anthropic (Claude) provider.

The ``anthropic`` SDK is imported lazily, so typedout has no hard dependency on
it — install the ``anthropic`` package to use this. A pre-built ``client`` can be
injected (used by the test-suite to exercise the mapping without a network call
or an API key).
"""

from __future__ import annotations

from typing import Any, List, Optional

from .base import Completion, Message, Provider, RawUsage


class AnthropicProvider(Provider):
    """Wraps ``anthropic.Anthropic`` behind the typedout :class:`Provider` interface.

    The engine's ``temperature`` argument is accepted for interface compatibility
    but is **not** sent to Anthropic: ``anthropic`` SDK 1.x removed it from
    ``messages.create`` (passing it raises ``TypeError`` before any request), and
    current models reject it server-side. Requests therefore use the API default.
    """

    def __init__(
        self,
        model: str = "claude-opus-5",
        *,
        client: Any = None,
        api_key: Optional[str] = None,
        max_tokens: int = 1024,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client = client

    @property
    def client(self) -> Any:
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - depends on env
                raise ImportError(
                    "AnthropicProvider needs the 'anthropic' package "
                    "(pip install anthropic)"
                ) from exc
            self._client = anthropic.Anthropic(api_key=self._api_key)
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
        system, chat = _split_system(messages)
        response = self.client.messages.create(
            model=model or self.model,
            system=system or None,
            messages=[{"role": m.role, "content": m.content} for m in chat],
            max_tokens=max_tokens or self.max_tokens,
        )
        text = "".join(
            getattr(block, "text", "")
            for block in response.content
            if getattr(block, "type", "text") == "text"
        )
        usage = RawUsage(
            input_tokens=getattr(response.usage, "input_tokens", 0),
            output_tokens=getattr(response.usage, "output_tokens", 0),
        )
        return Completion(text=text, model=getattr(response, "model", model or self.model), usage=usage)


def _split_system(messages: List[Message]) -> tuple[str, List[Message]]:
    """Anthropic takes the system prompt as a top-level arg, not a message."""
    system_parts = [m.content for m in messages if m.role == "system"]
    chat = [m for m in messages if m.role != "system"]
    return "\n\n".join(system_parts), chat

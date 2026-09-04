"""Providers: the boundary between typedout and a concrete LLM backend."""

from .base import Completion, Message, Provider, RawUsage
from .mock import MockProvider

__all__ = [
    "Provider",
    "Message",
    "Completion",
    "RawUsage",
    "MockProvider",
    "AnthropicProvider",
    "OpenAIProvider",
]


def __getattr__(name: str):
    # Lazy so importing typedout never requires the anthropic/openai SDKs.
    if name == "AnthropicProvider":
        from .anthropic import AnthropicProvider

        return AnthropicProvider
    if name == "OpenAIProvider":
        from .openai import OpenAIProvider

        return OpenAIProvider
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

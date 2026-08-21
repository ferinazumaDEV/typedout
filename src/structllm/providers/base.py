"""Provider interface and the small value objects that cross it.

A provider is the only place structllm talks to a model. Keep it tiny: turn a
list of :class:`Message` into a :class:`Completion`, and (optionally) stream the
text back in chunks. Everything else — prompting, repair, validation, retries,
cost — lives in the engine and is provider-independent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator, List, Optional


@dataclass
class Message:
    """A single chat message. ``role`` is ``"system"``, ``"user"`` or ``"assistant"``."""

    role: str
    content: str


@dataclass
class RawUsage:
    """Token counts reported by a provider for one completion."""

    input_tokens: int = 0
    output_tokens: int = 0


@dataclass
class Completion:
    """The result of a single provider call."""

    text: str
    model: str
    usage: RawUsage


class Provider(ABC):
    """Base class for all providers.

    Subclasses must implement :meth:`complete`. Implementing :meth:`stream` is
    optional; providers that cannot stream inherit a fallback that yields the
    whole completion as one chunk, so streaming code still works.
    """

    #: Default model id, used when the engine does not override it.
    model: str = "unknown"

    @abstractmethod
    def complete(
        self,
        messages: List[Message],
        *,
        schema=None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Completion:
        """Return a completion for *messages*."""
        raise NotImplementedError

    def stream(
        self,
        messages: List[Message],
        *,
        schema=None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        """Yield the completion text in chunks. Default: one chunk."""
        completion = self.complete(
            messages,
            schema=schema,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        yield completion.text

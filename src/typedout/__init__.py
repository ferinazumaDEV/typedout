"""typedout — reliable structured output from OpenAI and Anthropic, with a provider interface for others.

Define a schema (pydantic model or JSON Schema), and typedout forces the model
to return a valid instance: tolerant JSON repair, schema validation, and
error-aware retries, behind one provider-agnostic interface.

    from pydantic import BaseModel
    from typedout import TypedOut, MockProvider

    class Person(BaseModel):
        name: str
        age: int
        email: str

    llm = TypedOut(MockProvider(script=["invalid", "valid"]))
    person = llm.extract(Person, "Ada Lovelace, 36, ada@example.com")
    print(person, llm.last_usage)
"""

from __future__ import annotations

from .decorator import extract
from .engine import TypedOut
from .errors import (
    ExtractionError,
    ProviderError,
    RepairError,
    SchemaValidationError,
    TypedOutError,
)
from .providers import (
    Completion,
    Message,
    MockProvider,
    Provider,
    RawUsage,
)
from .repair import loads_repaired, repair_json
from .schema import Schema
from .streaming import iter_partial
from .usage import Usage, cost_of, price_for, register_price

__version__ = "0.1.1"

__all__ = [
    "TypedOut",
    "extract",
    "Schema",
    # providers
    "Provider",
    "MockProvider",
    "Message",
    "Completion",
    "RawUsage",
    # repair / streaming
    "repair_json",
    "loads_repaired",
    "iter_partial",
    # usage
    "Usage",
    "cost_of",
    "price_for",
    "register_price",
    # errors
    "TypedOutError",
    "RepairError",
    "SchemaValidationError",
    "ExtractionError",
    "ProviderError",
    "__version__",
]


def __getattr__(name: str):
    # Lazy provider access so `from typedout import AnthropicProvider` works
    # without importing the optional SDKs at package import time.
    if name in ("AnthropicProvider", "OpenAIProvider"):
        from . import providers

        return getattr(providers, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

"""The ``@extract`` decorator: turn a prompt-building function into a typed extractor.

The decorated function returns the *prompt string* (it can format arguments,
inject context, whatever); the decorator runs it through a :class:`TypedOut`
engine and returns the validated object of the declared schema::

    @extract(Person, provider=MockProvider(script=["valid"]))
    def parse_person(text: str) -> Person:
        return f"Extract the person described here:\\n{text}"

    person = parse_person("Ada Lovelace, 36, ada@example.com")  # -> Person
"""

from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional, Union

from .engine import TypedOut
from .providers.base import Provider
from .schema import Schema, SchemaSpec


def extract(
    schema: Union[Schema, SchemaSpec],
    *,
    provider: Optional[Provider] = None,
    engine: Optional[TypedOut] = None,
    system: Optional[str] = None,
    **engine_kwargs: Any,
) -> Callable[[Callable[..., str]], Callable[..., Any]]:
    """Decorate a function returning a prompt so calling it returns a typed object.

    Provide either a ready ``engine`` or a ``provider`` (plus optional engine
    kwargs like ``max_retries``). The decorated function's per-call ``system``
    override still wins if you set it here.
    """
    if engine is None and provider is None:
        raise ValueError("extract() needs either a provider or an engine")

    def decorator(fn: Callable[..., str]) -> Callable[..., Any]:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            prompt = fn(*args, **kwargs)
            if not isinstance(prompt, str):
                raise TypeError(
                    f"@extract function {fn.__name__!r} must return a prompt string, "
                    f"got {type(prompt).__name__}"
                )
            eng = engine or TypedOut(provider, system=system, **engine_kwargs)  # type: ignore[arg-type]
            return eng.extract(schema, prompt, system=system)

        wrapper.schema = schema  # type: ignore[attr-defined]
        return wrapper

    return decorator

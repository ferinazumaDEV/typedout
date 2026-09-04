"""The extraction engine: prompt → complete → repair → validate → (retry) → typed object.

``TypedOut`` is provider-agnostic. It builds a schema-aware prompt, parses the
model's reply through the tolerant repairer, validates it, and — if validation
fails — feeds the concrete errors back to the model and tries again, up to
``max_retries`` times. Token usage and cost accumulate on the engine.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from typing import Any, Iterator, List, Optional, Union

from pydantic import ValidationError as PydanticValidationError

from .errors import (
    ExtractionError,
    ProviderError,
    RepairError,
    SchemaValidationError,
    TypedOutError,
)
from .providers.base import Message, Provider
from .repair import loads_repaired
from .schema import Schema, SchemaSpec, ensure_schema
from .streaming import iter_partial
from .usage import Usage, cost_of

_DEFAULT_SYSTEM = (
    "You are a precise data-extraction engine. Read the user's content and "
    "respond with a SINGLE JSON object that conforms exactly to the provided "
    "JSON Schema. Do not include explanations, markdown fences, or any text "
    "outside the JSON object."
)


class TypedOut:
    """Reliable structured extraction on top of any :class:`Provider`.

    Args:
        provider: the backend to call (e.g. ``MockProvider``, ``AnthropicProvider``).
        max_retries: extra attempts after the first when parsing/validation fails.
        repair: run the tolerant JSON repairer before parsing.
        model: model id override passed to the provider (defaults to the provider's).
        temperature / max_tokens: forwarded to the provider.
        system: override the default system prompt.
    """

    def __init__(
        self,
        provider: Provider,
        *,
        max_retries: int = 2,
        repair: bool = True,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
        system: Optional[str] = None,
    ):
        self.provider = provider
        self.max_retries = max_retries
        self.repair = repair
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.system = system

        self.total_usage = Usage()
        #: Usage of the most recent extract (summed across its retries).
        self.last_usage = Usage()
        #: How many attempts the last extract took (1 == first try).
        self.last_attempts = 0
        #: Raw text of the final provider reply from the last extract.
        self.last_raw: Optional[str] = None
        #: Validated result of the last stream() run.
        self.last_result: Any = None

    # -- public API ------------------------------------------------------------

    def extract(
        self,
        schema: Union[Schema, SchemaSpec],
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> Any:
        """Extract a validated object of *schema* from *prompt*.

        Returns a pydantic instance (model schemas) or a ``dict`` (JSON Schema
        dicts). Raises :class:`ExtractionError` if every attempt fails and
        :class:`ProviderError` if the provider call itself fails.
        """
        sch = ensure_schema(schema)
        messages = self._build_messages(sch, prompt, system)
        run_usage = Usage()
        attempt_errors: List[str] = []

        for attempt in range(self.max_retries + 1):
            with _provider_errors():
                completion = self.provider.complete(
                    messages,
                    schema=sch,
                    model=self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                )
            run_usage += self._account(completion)
            self.last_raw = completion.text

            try:
                data = self._parse(completion.text)
            except RepairError as exc:
                attempt_errors.append(f"attempt {attempt + 1}: unparseable JSON ({exc})")
                messages = self._with_correction(
                    messages,
                    completion.text,
                    f"That was not valid JSON ({exc}). Reply with ONLY the JSON object.",
                )
                continue

            try:
                result = sch.validate(data)
            except (PydanticValidationError, SchemaValidationError) as exc:
                detail = _format_validation_error(exc)
                attempt_errors.append(f"attempt {attempt + 1}: schema mismatch ({detail})")
                messages = self._with_correction(
                    messages,
                    completion.text,
                    f"Your JSON did not match the schema: {detail}. "
                    "Fix those fields and reply with ONLY the corrected JSON.",
                )
                continue

            self.last_usage = run_usage
            self.last_attempts = attempt + 1
            return result

        self.last_usage = run_usage
        self.last_attempts = self.max_retries + 1
        raise ExtractionError(
            f"failed to extract {sch.name} after {self.max_retries + 1} attempt(s)",
            attempts=attempt_errors,
            last_raw=self.last_raw,
        )

    def stream(
        self,
        schema: Union[Schema, SchemaSpec],
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> Iterator[Any]:
        """Yield progressively completer partial objects as the model streams.

        Each yielded value is the best-effort parse of everything received so far
        (a ``dict``/``list`` built by closing the partial JSON). After the
        generator is exhausted, the fully validated object is on ``last_result``.

        Raises :class:`ProviderError` if the provider fails while streaming and
        :class:`ExtractionError` if the completed stream does not validate.
        """
        sch = ensure_schema(schema)
        messages = self._build_messages(sch, prompt, system)
        self.last_result = None

        with _provider_errors():
            chunks = self.provider.stream(
                messages,
                schema=sch,
                model=self.model,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )

        final: Any = None
        partials = iter_partial(chunks)
        while True:
            # Providers stream lazily, so SDK/network failures surface here, not
            # at the call above; convert them the same way.
            with _provider_errors():
                partial = next(partials, _DONE)
            if partial is _DONE:
                break
            final = partial
            yield partial

        if final is None:
            raise ExtractionError(f"stream produced no parseable JSON for {sch.name}")
        try:
            self.last_result = sch.validate(final)
        except (PydanticValidationError, SchemaValidationError) as exc:
            raise ExtractionError(
                f"streamed {sch.name} failed validation: {_format_validation_error(exc)}",
                last_raw=json.dumps(final),
            ) from exc

    def collect(
        self,
        schema: Union[Schema, SchemaSpec],
        prompt: str,
        *,
        system: Optional[str] = None,
    ) -> Any:
        """Consume :meth:`stream` fully and return the validated final object."""
        for _ in self.stream(schema, prompt, system=system):
            pass
        return self.last_result

    # -- internals -------------------------------------------------------------

    def _build_messages(self, sch: Schema, prompt: str, system: Optional[str]) -> List[Message]:
        base = system or self.system or _DEFAULT_SYSTEM
        schema_block = json.dumps(sch.json_schema, indent=2)
        system_full = f"{base}\n\nJSON Schema for `{sch.name}`:\n{schema_block}"
        return [Message("system", system_full), Message("user", prompt)]

    def _parse(self, text: str) -> Any:
        if self.repair:
            return loads_repaired(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RepairError(str(exc)) from exc

    def _with_correction(self, messages: List[Message], raw: str, instruction: str) -> List[Message]:
        return messages + [Message("assistant", raw), Message("user", instruction)]

    def _account(self, completion) -> Usage:
        model = self.model or completion.model or getattr(self.provider, "model", "unknown")
        cost = cost_of(model, completion.usage.input_tokens, completion.usage.output_tokens)
        unit = Usage(
            input_tokens=completion.usage.input_tokens,
            output_tokens=completion.usage.output_tokens,
            requests=1,
            cost_usd=cost,
        )
        self.total_usage += unit
        return unit


_DONE = object()


@contextmanager
def _provider_errors():
    """Re-raise whatever a provider throws as :class:`ProviderError`.

    Library errors (``TypedOutError`` subclasses) pass through untouched, so the
    errors.py contract holds: everything ``TypedOut`` raises is a ``TypedOutError``.
    """
    try:
        yield
    except TypedOutError:
        raise
    except Exception as exc:
        raise ProviderError(f"{type(exc).__name__}: {exc}") from exc


def _format_validation_error(exc: Exception) -> str:
    if isinstance(exc, SchemaValidationError):
        return "; ".join(exc.errors)
    if isinstance(exc, PydanticValidationError):
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ())) or "<root>"
            parts.append(f"{loc}: {err.get('msg', 'invalid')}")
        return "; ".join(parts)
    return str(exc)  # pragma: no cover

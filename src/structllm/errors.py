"""Exception hierarchy for structllm.

All errors raised by the library subclass :class:`StructLLMError`, so callers can
catch everything with a single ``except`` while still being able to distinguish
parse failures from validation failures when they care.
"""

from __future__ import annotations

from typing import List, Optional


class StructLLMError(Exception):
    """Base class for every error raised by structllm."""


class RepairError(StructLLMError):
    """Raised when a string could not be coerced into parseable JSON."""


class SchemaValidationError(StructLLMError):
    """Raised when parsed JSON does not satisfy a raw JSON Schema.

    Pydantic models raise ``pydantic.ValidationError`` instead; the engine treats
    both as a validation failure and folds the details into a retry prompt.
    """

    def __init__(self, errors: List[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors) if self.errors else "schema validation failed")


class ProviderError(StructLLMError):
    """Raised when an underlying LLM provider call fails."""


class ExtractionError(StructLLMError):
    """Raised when extraction fails after exhausting all repair/retry attempts.

    The full trail of attempt-by-attempt errors is preserved on ``attempts`` and
    the last raw model output on ``last_raw`` for debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        attempts: Optional[List[str]] = None,
        last_raw: Optional[str] = None,
    ):
        self.attempts = list(attempts or [])
        self.last_raw = last_raw
        detail = message
        if self.attempts:
            detail += "\n  - " + "\n  - ".join(self.attempts)
        super().__init__(detail)

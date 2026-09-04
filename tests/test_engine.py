"""Tests for the TypedOut engine: repair, validation, retries, usage."""

from __future__ import annotations

import pytest

from typedout import (
    AnthropicProvider,
    ExtractionError,
    MockProvider,
    ProviderError,
    TypedOut,
    TypedOutError,
)


class _FailingMessages:
    def create(self, **kwargs):
        raise RuntimeError("boom")


class _FailingAnthropicClient:
    """Fake SDK client whose only call blows up, like a network/SDK failure."""

    messages = _FailingMessages()


def test_valid_first_try(person_cls):
    llm = TypedOut(MockProvider(script=["valid"]))
    person = llm.extract(person_cls, "Ada Lovelace, 36, ada@example.com")
    assert isinstance(person, person_cls)
    assert llm.last_attempts == 1
    assert llm.last_usage.requests == 1


def test_repairs_fenced_output_without_retry(person_cls):
    provider = MockProvider(script=["fenced"])
    llm = TypedOut(provider)
    person = llm.extract(person_cls, "...")
    assert person.name
    assert llm.last_attempts == 1  # repair, not a re-prompt
    assert len(provider.calls) == 1


def test_repairs_loose_python_literals(person_cls):
    llm = TypedOut(MockProvider(script=["loose"]))
    person = llm.extract(person_cls, "...")
    assert person.email


def test_retries_after_schema_violation(person_cls):
    provider = MockProvider(script=["invalid", "valid"])
    llm = TypedOut(provider)
    person = llm.extract(person_cls, "...")
    assert isinstance(person, person_cls)
    assert llm.last_attempts == 2
    assert len(provider.calls) == 2
    # The retry prompt must include the assistant's bad answer + a correction.
    retry_roles = [m.role for m in provider.calls[1]]
    assert retry_roles == ["system", "user", "assistant", "user"]


def test_retries_after_unparseable_then_succeeds(person_cls):
    provider = MockProvider(script=["garbage", "valid"])
    llm = TypedOut(provider)
    person = llm.extract(person_cls, "...")
    assert person.name
    assert llm.last_attempts == 2


def test_raises_after_exhausting_retries(person_cls):
    provider = MockProvider(script=["invalid", "invalid", "invalid"])
    llm = TypedOut(provider, max_retries=2)
    with pytest.raises(ExtractionError) as exc:
        llm.extract(person_cls, "...")
    assert len(provider.calls) == 3
    assert len(exc.value.attempts) == 3
    assert exc.value.last_raw is not None


def test_truncated_output_is_repaired(person_cls):
    llm = TypedOut(MockProvider(script=["truncated"]))
    person = llm.extract(person_cls, "...")
    assert person.name  # closed + validated


def test_usage_accumulates_across_extracts(person_cls):
    llm = TypedOut(MockProvider(script=["valid"]))
    llm.extract(person_cls, "one")
    llm.extract(person_cls, "two")
    assert llm.total_usage.requests == 2
    assert llm.total_usage.input_tokens > 0


def test_usage_counts_every_attempt(person_cls):
    llm = TypedOut(MockProvider(script=["invalid", "valid"]))
    llm.extract(person_cls, "...")
    assert llm.last_usage.requests == 2  # both the failed and the good call


def test_cost_is_computed_for_known_model(person_cls):
    provider = MockProvider(script=["valid"], model="gpt-4o-mini")
    llm = TypedOut(provider, model="gpt-4o-mini")
    llm.extract(person_cls, "...")
    assert llm.last_usage.cost_usd > 0


def test_raw_dict_schema_extraction():
    spec = {
        "title": "Ticket",
        "type": "object",
        "properties": {
            "id": {"type": "integer"},
            "title": {"type": "string"},
            "priority": {"enum": ["low", "high"]},
        },
        "required": ["id", "title"],
    }
    provider = MockProvider(
        responses=['{"id": 7, "title": "Fix login", priority: high,}']
    )
    llm = TypedOut(provider)
    result = llm.extract(spec, "...")
    assert result == {"id": 7, "title": "Fix login", "priority": "high"}


def test_repair_can_be_disabled(person_cls):
    # With repair off, fenced output is unparseable and (with no retry budget) fails.
    llm = TypedOut(MockProvider(script=["fenced"]), repair=False, max_retries=0)
    with pytest.raises(ExtractionError):
        llm.extract(person_cls, "...")


def test_provider_failure_is_wrapped_in_provider_error(person_cls):
    llm = TypedOut(AnthropicProvider(client=_FailingAnthropicClient()), max_retries=0)
    with pytest.raises(ProviderError) as exc:
        llm.extract(person_cls, "x")
    # One `except TypedOutError` catches it, and the original cause is preserved.
    assert isinstance(exc.value, TypedOutError)
    assert isinstance(exc.value.__cause__, RuntimeError)
    assert "RuntimeError: boom" in str(exc.value)


def test_stream_provider_failure_is_wrapped_in_provider_error(person_cls):
    # The base-class stream() calls complete() lazily, so the failure happens
    # while iterating, not when stream() is called.
    llm = TypedOut(AnthropicProvider(client=_FailingAnthropicClient()))
    with pytest.raises(ProviderError):
        list(llm.stream(person_cls, "x"))

"""Tests for the @extract decorator."""

from __future__ import annotations

import pytest

from typedout import MockProvider, TypedOut, extract


def test_decorator_returns_typed_object(person_cls):
    @extract(person_cls, provider=MockProvider(script=["valid"]))
    def parse_person(text: str) -> "person_cls":  # noqa: F821
        return f"Extract the person from: {text}"

    person = parse_person("Ada Lovelace, 36")
    assert isinstance(person, person_cls)
    assert person.name


def test_decorator_forwards_arguments(person_cls):
    provider = MockProvider(script=["valid"])

    @extract(person_cls, provider=provider)
    def parse_person(name: str, note: str = "") -> "person_cls":  # noqa: F821
        return f"name={name} note={note}"

    parse_person("Ada", note="famous")
    prompt = provider.calls[0][1].content
    assert "name=Ada" in prompt and "note=famous" in prompt


def test_decorator_with_shared_engine(person_cls):
    engine = TypedOut(MockProvider(script=["valid", "valid"]))

    @extract(person_cls, engine=engine)
    def parse_person(text: str) -> "person_cls":  # noqa: F821
        return text

    parse_person("one")
    parse_person("two")
    assert engine.total_usage.requests == 2


def test_decorator_exposes_schema(person_cls):
    @extract(person_cls, provider=MockProvider(script=["valid"]))
    def parse_person(text: str) -> "person_cls":  # noqa: F821
        return text

    assert parse_person.schema is person_cls


def test_decorator_rejects_non_string_prompt(person_cls):
    @extract(person_cls, provider=MockProvider(script=["valid"]))
    def bad() -> "person_cls":  # noqa: F821
        return 123  # type: ignore[return-value]

    with pytest.raises(TypeError):
        bad()


def test_decorator_requires_provider_or_engine(person_cls):
    with pytest.raises(ValueError):
        extract(person_cls)

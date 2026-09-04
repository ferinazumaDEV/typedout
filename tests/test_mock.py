"""Tests for MockProvider synthesis and behaviours."""

from __future__ import annotations

import json
from datetime import date, datetime, time
from uuid import UUID

import pytest
from pydantic import BaseModel, Field, HttpUrl

from typedout import MockProvider, Schema, TypedOut
from typedout.providers.base import Message
from typedout.repair import loads_repaired


def _msgs():
    return [Message("system", "sys"), Message("user", "extract")]


def test_valid_behaviour_matches_schema(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["valid"])
    text = provider.complete(_msgs(), schema=sch).text
    data = json.loads(text)
    person = sch.validate(data)  # should not raise
    assert person.name and person.email


def test_fenced_behaviour_is_repairable(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["fenced"])
    text = provider.complete(_msgs(), schema=sch).text
    assert "```" in text
    sch.validate(loads_repaired(text))  # repair + validate must succeed


def test_loose_behaviour_is_python_literals(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["loose"])
    text = provider.complete(_msgs(), schema=sch).text
    assert "'" in text  # single quotes
    sch.validate(loads_repaired(text))


def test_truncated_behaviour_needs_repair(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["truncated"])
    text = provider.complete(_msgs(), schema=sch).text
    with pytest.raises(Exception):
        json.loads(text)  # not valid on its own
    loads_repaired(text)  # but repairable


def test_invalid_behaviour_fails_validation(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["invalid"])
    text = provider.complete(_msgs(), schema=sch).text
    data = json.loads(text)  # syntactically valid JSON
    with pytest.raises(Exception):
        sch.validate(data)  # but violates the schema


def test_nested_schema_synthesis(company_cls):
    sch = Schema(company_cls)
    provider = MockProvider(script=["valid"])
    company = sch.validate(json.loads(provider.complete(_msgs(), schema=sch).text))
    assert company.hq.city  # nested model populated
    assert isinstance(company.tags, list)


def test_canned_responses_returned_in_order():
    provider = MockProvider(responses=['{"a": 1}', '{"a": 2}'])
    assert provider.complete(_msgs()).text == '{"a": 1}'
    assert provider.complete(_msgs()).text == '{"a": 2}'
    assert provider.complete(_msgs()).text == '{"a": 2}'  # last repeats


def test_calls_are_recorded():
    provider = MockProvider(responses=['{"a": 1}'])
    provider.complete(_msgs())
    assert len(provider.calls) == 1
    assert provider.calls[0][0].role == "system"


def test_stream_yields_chunks(person_cls):
    sch = Schema(person_cls)
    provider = MockProvider(script=["valid"], chunk_size=4)
    chunks = list(provider.stream(_msgs(), schema=sch))
    assert len(chunks) > 1
    assert loads_repaired("".join(chunks))


def test_rejects_both_responses_and_script():
    with pytest.raises(ValueError):
        MockProvider(responses=["x"], script=["valid"])


def test_rejects_unknown_behaviour():
    with pytest.raises(ValueError):
        MockProvider(script=["nonsense"])


# -- "valid" must honour the constraints ordinary pydantic models carry ---------


class _ExclusiveMin(BaseModel):
    n: int = Field(gt=0)  # pydantic emits exclusiveMinimum


class _ClampedHint(BaseModel):
    age: int = Field(ge=40, le=50)  # the name hint (36) must be raised into range


class _ExclusiveMax(BaseModel):
    n: int = Field(lt=0)


class _OpenInterval(BaseModel):
    ratio: float = Field(gt=0, lt=1)


class _Formats(BaseModel):
    when: datetime
    day: date
    at: time
    ident: UUID
    homepage: HttpUrl


class _MinLength(BaseModel):
    s: str = Field(min_length=10)


class _MaxLength(BaseModel):
    name: str = Field(max_length=5)  # the name hint ("Ada Lovelace") must be cut


@pytest.mark.parametrize(
    "model",
    [
        _ExclusiveMin,
        _ClampedHint,
        _ExclusiveMax,
        _OpenInterval,
        _Formats,
        _MinLength,
        _MaxLength,
    ],
)
def test_valid_behaviour_honours_constraints(model):
    llm = TypedOut(MockProvider(script=["valid"]), max_retries=0)
    assert isinstance(llm.extract(model, "..."), model)


def test_valid_behaviour_honours_string_format_in_dict_schema():
    sch = Schema(
        {
            "type": "object",
            "properties": {"contact": {"type": "string", "format": "email"}},
            "required": ["contact"],
        }
    )
    text = MockProvider(script=["valid"]).complete(_msgs(), schema=sch).text
    assert json.loads(text) == {"contact": "ada@example.com"}

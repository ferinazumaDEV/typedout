"""Tests for the Schema adapter (pydantic + raw JSON Schema dict)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from structllm import Schema
from structllm.errors import SchemaValidationError


def test_pydantic_schema_validates_to_instance(person_cls):
    sch = Schema(person_cls)
    assert sch.name == "Person"
    assert sch.is_model is True
    person = sch.validate({"name": "Ada", "age": 36, "email": "ada@x.com"})
    assert isinstance(person, person_cls)
    assert person.age == 36


def test_pydantic_schema_raises_on_bad_data(person_cls):
    sch = Schema(person_cls)
    with pytest.raises(ValidationError):
        sch.validate({"name": "Ada", "age": "old", "email": "ada@x.com"})


def test_dict_schema_returns_dict():
    spec = {
        "title": "Point",
        "type": "object",
        "properties": {"x": {"type": "integer"}, "y": {"type": "integer"}},
        "required": ["x", "y"],
    }
    sch = Schema(spec)
    assert sch.name == "Point"
    assert sch.is_model is False
    assert sch.validate({"x": 1, "y": 2}) == {"x": 1, "y": 2}


def test_dict_schema_raises_on_bad_data():
    spec = {"type": "object", "properties": {"x": {"type": "integer"}}, "required": ["x"]}
    with pytest.raises(SchemaValidationError):
        Schema(spec).validate({})


def test_invalid_spec_type():
    with pytest.raises(TypeError):
        Schema(42)  # type: ignore[arg-type]

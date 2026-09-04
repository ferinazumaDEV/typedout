"""Tests for the built-in lite JSON Schema validator."""

from __future__ import annotations

from typedout import jsonschema_lite as js

PERSON = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "minLength": 1},
        "age": {"type": "integer", "minimum": 0, "maximum": 130},
        "email": {"type": "string", "pattern": r"^[^@]+@[^@]+$"},
        "role": {"enum": ["admin", "user", "guest"]},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}


def test_valid_instance_has_no_errors():
    assert js.validate({"name": "Ada", "age": 36}, PERSON) == []


def test_missing_required_field():
    errors = js.validate({"name": "Ada"}, PERSON)
    assert any("missing required property 'age'" in e for e in errors)


def test_wrong_type():
    errors = js.validate({"name": "Ada", "age": "old"}, PERSON)
    assert any("age" in e and "expected type integer" in e for e in errors)


def test_boolean_is_not_integer():
    errors = js.validate({"name": "Ada", "age": True}, PERSON)
    assert any("age" in e for e in errors)


def test_numeric_bounds():
    assert any("maximum" in e for e in js.validate({"name": "Ada", "age": 999}, PERSON))
    assert any("minimum" in e for e in js.validate({"name": "Ada", "age": -1}, PERSON))


def test_enum_violation():
    errors = js.validate({"name": "Ada", "age": 1, "role": "wizard"}, PERSON)
    assert any("role" in e and "not one of" in e for e in errors)


def test_pattern_violation():
    errors = js.validate({"name": "Ada", "age": 1, "email": "nope"}, PERSON)
    assert any("email" in e and "pattern" in e for e in errors)


def test_additional_properties_forbidden():
    errors = js.validate({"name": "Ada", "age": 1, "extra": 1}, PERSON)
    assert any("additional property" in e for e in errors)


def test_nested_array_items():
    schema = {
        "type": "object",
        "properties": {"nums": {"type": "array", "items": {"type": "integer"}, "minItems": 2}},
        "required": ["nums"],
    }
    assert js.validate({"nums": [1, 2, 3]}, schema) == []
    assert any("minItems" in e for e in js.validate({"nums": [1]}, schema))
    assert any("[1]" in e for e in js.validate({"nums": [1, "two"]}, schema))


def test_anyof_optional_field():
    schema = {
        "type": "object",
        "properties": {"note": {"anyOf": [{"type": "string"}, {"type": "null"}]}},
    }
    assert js.validate({"note": None}, schema) == []
    assert js.validate({"note": "hi"}, schema) == []
    assert js.validate({"note": 5}, schema) != []


def test_ref_resolution():
    schema = {
        "type": "object",
        "properties": {"hq": {"$ref": "#/$defs/Address"}},
        "required": ["hq"],
        "$defs": {
            "Address": {
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            }
        },
    }
    assert js.validate({"hq": {"city": "London"}}, schema) == []
    assert any("city" in e for e in js.validate({"hq": {}}, schema))

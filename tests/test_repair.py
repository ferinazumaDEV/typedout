"""Tests for the tolerant JSON repairer — the heart of structllm."""

from __future__ import annotations

import json

import pytest

from structllm import loads_repaired, repair_json
from structllm.errors import RepairError


def _roundtrip(text):
    return json.loads(repair_json(text))


def test_valid_json_is_untouched():
    src = '{"a": 1, "b": [2, 3], "c": null}'
    assert repair_json(src) == src


def test_strips_markdown_fences():
    src = '```json\n{"ok": true}\n```'
    assert _roundtrip(src) == {"ok": True}


def test_strips_surrounding_prose():
    src = 'Sure! Here is the data:\n{"name": "Ada", "age": 36}\nHope that helps!'
    assert _roundtrip(src) == {"name": "Ada", "age": 36}


def test_trailing_commas_object_and_array():
    src = '{"items": [1, 2, 3,], "done": true,}'
    assert _roundtrip(src) == {"items": [1, 2, 3], "done": True}


def test_single_quotes_and_python_literals():
    src = "{'name': 'Ada', 'active': True, 'manager': None, 'flag': False}"
    assert _roundtrip(src) == {
        "name": "Ada",
        "active": True,
        "manager": None,
        "flag": False,
    }


def test_unquoted_keys():
    src = "{name: 'Ada', age: 36, city: London}"
    assert _roundtrip(src) == {"name": "Ada", "age": 36, "city": "London"}


def test_line_and_block_comments():
    src = """
    {
      // the subject's name
      "name": "Ada",
      "age": 36 /* years */
    }
    """
    assert _roundtrip(src) == {"name": "Ada", "age": 36}


def test_truncated_object_is_closed():
    src = '{"name": "Ada", "age": 36, "email": "ada@exampl'
    out = _roundtrip(src)
    assert out["name"] == "Ada" and out["age"] == 36
    assert out["email"].startswith("ada@exampl")


def test_truncated_nested_structures_are_closed():
    src = '{"a": [1, 2, {"b": [3, 4'
    out = _roundtrip(src)
    assert out == {"a": [1, 2, {"b": [3, 4]}]}


def test_truncated_after_key_gets_null():
    src = '{"a": 1, "b"'
    assert _roundtrip(src) == {"a": 1, "b": None}


def test_dangling_colon_gets_null():
    src = '{"a": 1, "b":}'
    assert _roundtrip(src) == {"a": 1, "b": None}


def test_number_normalisation():
    src = '{"x": .5, "y": 5., "z": +3, "w": 1e3}'
    out = _roundtrip(src)
    assert out["x"] == 0.5
    assert out["y"] == 5.0
    assert out["z"] == 3
    assert out["w"] == 1000.0


def test_apostrophe_inside_double_quoted_string_survives():
    src = '{"note": "it\'s fine"}'
    assert _roundtrip(src) == {"note": "it's fine"}


def test_escaped_quote_inside_single_quoted_string():
    src = r"{'note': 'they said \'hi\''}"
    assert _roundtrip(src) == {"note": "they said 'hi'"}


def test_unicode_escape_is_decoded():
    src = '{"greeting": "caf\\u00e9"}'
    assert _roundtrip(src) == {"greeting": "café"}


def test_top_level_array():
    src = "```\n[{'a': 1,}, {'a': 2,},]\n```"
    assert _roundtrip(src) == [{"a": 1}, {"a": 2}]


def test_bare_scalar_python_literal():
    assert loads_repaired("True") is True
    assert loads_repaired("None") is None


def test_nested_mixed_mess():
    src = """```json
    {
        name: 'Widget',       // product name
        'price': 9.99,
        tags: ['a', 'b',],
        meta: {stock: True, sku: WGT-1,}
    }
    ```"""
    assert _roundtrip(src) == {
        "name": "Widget",
        "price": 9.99,
        "tags": ["a", "b"],
        "meta": {"stock": True, "sku": "WGT-1"},
    }


def test_unrepairable_raises():
    with pytest.raises(RepairError):
        repair_json("this is just prose with no json at all")


def test_non_string_input_raises():
    with pytest.raises(RepairError):
        repair_json(12345)  # type: ignore[arg-type]

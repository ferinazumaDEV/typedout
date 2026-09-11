"""Tests for the tolerant JSON repairer — the heart of typedout."""

from __future__ import annotations

import json

import pytest

from typedout import loads_repaired, repair_json
from typedout.errors import RepairError


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


# --- Regressions for the external audit findings F01 and F02 (2026-09-11) --- #
#
# F01: repair_json stripped Markdown fences BEFORE checking whether the input
# was already valid JSON, and the fence pattern matched anywhere in the text --
# including inside a JSON string literal. A valid object whose string value
# contained ```json ... ``` was replaced by whatever sat between the backticks;
# one containing ```python ... ``` raised instead. Both destroyed an input that
# needed no repair at all.
#
# F02: the validity checks used plain json.loads, which accepts NaN, Infinity
# and -Infinity. RFC 8259 has no syntax for them, so returning them unchanged
# broke the documented promise of "a strictly valid JSON string".

FENCED_INSIDE_A_STRING = [
    {"message": "literal ```json 123 ``` kept"},
    {"texto": "look at ```python print(1) ``` here", "n": 7},
    {"a": {"b": "nested ```json {\"x\": 1} ``` value"}, "list": [1, 2, 3]},
    {"code": "inline `print()` is fine"},
    {"empty_fence": "``` ```"},
    {"unclosed": "an unclosed ```json fence"},
]


@pytest.mark.parametrize("obj", FENCED_INSIDE_A_STRING)
def test_valid_json_survives_fences_inside_strings(obj):
    """Valid JSON in, the same value out. No exception, no substitution."""
    assert json.loads(repair_json(json.dumps(obj))) == obj


def test_a_real_outer_fence_is_still_stripped():
    """The reordering must not cost us the feature the library exists for."""
    assert json.loads(repair_json('```json\n{"a": 1}\n```')) == {"a": 1}
    assert json.loads(repair_json('Sure!\n```json\n{"a": 1}\n```\nHope that helps!')) == {"a": 1}


def test_repair_is_idempotent_on_valid_json():
    for obj in FENCED_INSIDE_A_STRING:
        once = repair_json(json.dumps(obj))
        assert repair_json(once) == once


@pytest.mark.parametrize("literal", ['{"x": NaN}', '{"x": Infinity}', '{"x": -Infinity}'])
def test_non_finite_numbers_never_survive(literal):
    """RFC 8259 has no NaN or Infinity; the output must not contain them."""
    out = repair_json(literal)

    def reject(name):
        raise AssertionError(f"{name} survived into the output: {out!r}")

    json.loads(out, parse_constant=reject)


def test_infinity_does_not_become_a_string():
    """It used to come back as "Infinity" -- a number quietly turned into text."""
    assert json.loads(repair_json('{"x": Infinity}')) == {"x": None}
    assert json.loads(repair_json('{"x": -Infinity}')) == {"x": None}


# --- Property test: valid JSON in, the same value out ---------------------- #
#
# The bug above was not a corner case. Against the code as it stood before the
# fix, this generator corrupted or crashed on 857 of 4000 randomly generated
# valid JSON documents -- better than one in five -- while every example-based
# test in this file passed. That is why this one is here: examples only check
# the cases somebody thought of.

_FRAGMENTS = [
    "```json", "```", "```python", "`", "``", "{", "}", "[", "]", '"', "\\",
    "true", "null", "NaN", "Infinity", ",", ":", "\n", "// comment", "/*", "*/",
    "áé", "😀", "  ", "0", "-1e5",
]


def _messy_string(rng):
    import string as _string
    noise = "".join(rng.choice(_FRAGMENTS) for _ in range(rng.randint(0, 6)))
    tail = "".join(rng.choice(_string.printable[:80]) for _ in range(rng.randint(0, 8)))
    return noise + tail


def _random_value(rng, depth=0):
    kind = rng.randint(0, 6 if depth < 3 else 4)
    if kind in (0, 4):
        return _messy_string(rng)
    if kind == 1:
        return rng.randint(-10**6, 10**6)
    if kind == 2:
        return round(rng.uniform(-1e3, 1e3), 4)
    if kind == 3:
        return rng.choice([True, False, None])
    if kind == 5:
        return [_random_value(rng, depth + 1) for _ in range(rng.randint(0, 4))]
    return {(_messy_string(rng) or "k"): _random_value(rng, depth + 1)
            for _ in range(rng.randint(0, 4))}


def test_repair_preserves_every_valid_json_document():
    import random
    rng = random.Random(20260911)      # fixed seed: a failure is reproducible
    for _ in range(400):
        obj = _random_value(rng)
        source = json.dumps(obj)
        assert json.loads(repair_json(source)) == obj, f"corrupted: {source!r}"

"""A deterministic, offline provider for tests, demos and CI.

``MockProvider`` never touches the network. Drive it two ways:

* **Scripted behaviours** — ``MockProvider(script=["invalid", "valid"])`` makes
  the provider return a schema-violating answer first and a clean one second, so
  you can exercise the engine's repair/retry path end to end. Supported
  behaviours: ``valid``, ``fenced``, ``loose``, ``truncated``, ``invalid``,
  ``garbage``.
* **Canned responses** — ``MockProvider(responses=["...raw text..."])`` returns
  the exact strings you give it, in order (the last one repeats).

For scripted behaviours the provider *synthesises* a realistic instance from the
schema, then deforms it, so a ``Person`` schema yields a plausible person rather
than lorem ipsum.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional

from ..schema import Schema
from .base import Completion, Message, Provider, RawUsage

_BEHAVIOURS = {"valid", "fenced", "loose", "truncated", "invalid", "garbage"}

# Name-based hints so synthesised objects read like real data in demos.
_STRING_HINTS = {
    "name": "Ada Lovelace",
    "first_name": "Ada",
    "last_name": "Lovelace",
    "full_name": "Ada Lovelace",
    "email": "ada@example.com",
    "phone": "+44 20 7946 0958",
    "city": "London",
    "country": "United Kingdom",
    "company": "Analytical Engines Ltd",
    "title": "Countess of Lovelace",
    "role": "Mathematician",
    "summary": "A concise, faithful summary of the source text.",
    "sentiment": "positive",
    "status": "active",
    "currency": "USD",
    "url": "https://example.com",
}
_INT_HINTS = {"age": 36, "year": 1843, "count": 3, "quantity": 3, "priority": 1, "id": 1}


class MockProvider(Provider):
    """Offline provider driven by a ``script`` of behaviours or canned ``responses``."""

    def __init__(
        self,
        responses: Optional[List[str]] = None,
        *,
        script: Optional[List[str]] = None,
        model: str = "mock-echo-1",
        chunk_size: int = 6,
    ):
        if responses is not None and script is not None:
            raise ValueError("pass either responses or script, not both")
        if script is not None:
            unknown = set(script) - _BEHAVIOURS
            if unknown:
                raise ValueError(f"unknown behaviours: {sorted(unknown)}")
        self._responses = list(responses) if responses is not None else None
        self._script = list(script) if script is not None else None
        self.model = model
        self.chunk_size = max(1, chunk_size)
        self._idx = 0
        #: Every messages list the engine sent, in order — handy for assertions.
        self.calls: List[List[Message]] = []

    def complete(
        self,
        messages: List[Message],
        *,
        schema: Optional[Schema] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Completion:
        self.calls.append(list(messages))
        text = self._next_text(schema)
        usage = RawUsage(
            input_tokens=_approx_tokens("".join(m.content for m in messages)),
            output_tokens=_approx_tokens(text),
        )
        return Completion(text=text, model=model or self.model, usage=usage)

    def stream(
        self,
        messages: List[Message],
        *,
        schema: Optional[Schema] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> Iterator[str]:
        self.calls.append(list(messages))
        text = self._next_text(schema)
        for start in range(0, len(text), self.chunk_size):
            yield text[start : start + self.chunk_size]

    # -- response selection ----------------------------------------------------

    def _next_text(self, schema: Optional[Schema]) -> str:
        if self._responses is not None:
            idx = min(self._idx, len(self._responses) - 1)
            self._idx += 1
            return self._responses[idx]
        behaviour = "valid"
        if self._script is not None:
            behaviour = self._script[min(self._idx, len(self._script) - 1)]
        self._idx += 1
        return self._render(behaviour, schema)

    def _render(self, behaviour: str, schema: Optional[Schema]) -> str:
        if schema is None:
            raise ValueError("scripted MockProvider requires a schema to synthesise from")
        sample = _synthesize(schema.json_schema, schema.json_schema)
        pretty = json.dumps(sample, indent=2)

        if behaviour == "valid":
            return pretty
        if behaviour == "fenced":
            body = pretty.rstrip("\n}") + ",\n}"  # add a trailing comma to repair
            return (
                "Sure! Here is the structured data you asked for:\n\n"
                f"```json\n{body}\n```\n\nLet me know if you'd like anything changed."
            )
        if behaviour == "loose":
            return _python_literal_dump(sample)
        if behaviour == "truncated":
            # Cut inside the last value so every field is still present (just the
            # tail is missing) — this exercises the repairer's brace-closing, not
            # a genuinely-missing-required-field case.
            compact = json.dumps(sample)
            last_colon = compact.rfind(":")
            cut = max(int(len(compact) * 0.8), last_colon + 3)
            cut = min(cut, len(compact) - 1)
            return compact[:cut]
        if behaviour == "invalid":
            return json.dumps(_corrupt(sample, schema.json_schema))
        if behaviour == "garbage":
            return "I'm sorry, I can't help with that request."
        raise ValueError(f"unknown behaviour: {behaviour}")  # pragma: no cover


# -- schema synthesis ----------------------------------------------------------


def _synthesize(schema: Dict[str, Any], root: Dict[str, Any], key: str = "") -> Any:
    if "$ref" in schema:
        target = _deref(root, schema["$ref"])
        if target is not None:
            return _synthesize(target, root, key)
    for literal in ("example", "default", "const"):
        if literal in schema:
            return schema[literal]
    if schema.get("examples"):
        return schema["examples"][0]
    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]
    if "anyOf" in schema:
        for sub in schema["anyOf"]:
            if sub.get("type") != "null":
                return _synthesize(sub, root, key)
    if "allOf" in schema and schema["allOf"]:
        merged: Dict[str, Any] = {}
        for sub in schema["allOf"]:
            resolved = _deref(root, sub["$ref"]) if "$ref" in sub else sub
            merged.update(resolved or {})
        return _synthesize(merged, root, key)

    typ = schema.get("type")
    if isinstance(typ, list):
        typ = next((t for t in typ if t != "null"), typ[0])

    if typ == "object" or "properties" in schema:
        obj: Dict[str, Any] = {}
        for name, sub in schema.get("properties", {}).items():
            obj[name] = _synthesize(sub, root, name)
        return obj
    if typ == "array":
        items = schema.get("items", {"type": "string"})
        return [_synthesize(items, root, key)]
    if typ == "boolean":
        return True
    if typ == "integer":
        return _INT_HINTS.get(key.lower(), int(schema.get("minimum", 0)) or 0)
    if typ == "number":
        return float(schema.get("minimum", 0.0)) or 1.5
    if typ == "null":
        return None
    # default: string
    return _STRING_HINTS.get(key.lower(), "example")


def _corrupt(sample: Any, schema: Dict[str, Any]) -> Any:
    """Return a syntactically valid but schema-violating variant of *sample*."""
    if isinstance(sample, dict):
        required = schema.get("required", [])
        if required:
            return {k: v for k, v in sample.items() if k not in required} or {"_": "x"}
        props = schema.get("properties", {})
        if props:
            corrupted = dict(sample)
            first = next(iter(props))
            expected = props[first].get("type")
            corrupted[first] = 424242 if expected in ("string", "object", "array") else "not-a-number"
            return corrupted
    return {"unexpected": "shape"}


def _deref(root: Dict[str, Any], ref: str) -> Optional[Dict[str, Any]]:
    if not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, dict) else None


def _python_literal_dump(value: Any) -> str:
    """Dump *value* like a Python ``repr`` (single quotes, ``True``/``None``) plus a
    trailing comma — a common 'looks like JSON but isn't' failure the repairer fixes."""
    if isinstance(value, dict):
        inner = ", ".join(f"'{k}': {_python_literal_dump(v)}" for k, v in value.items())
        return "{" + inner + ",}"
    if isinstance(value, list):
        return "[" + ", ".join(_python_literal_dump(v) for v in value) + ",]"
    if isinstance(value, bool):
        return "True" if value else "False"
    if value is None:
        return "None"
    if isinstance(value, str):
        return "'" + value.replace("'", "\\'") + "'"
    return repr(value)


def _approx_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) — enough for cost demos, not billing."""
    return max(1, len(text) // 4)

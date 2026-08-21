"""A compact, dependency-free JSON Schema validator.

Only used when a caller hands structllm a raw JSON Schema ``dict`` instead of a
pydantic model — pydantic validates itself. It covers the keywords that actually
show up in LLM extraction schemas (types, ``required``, ``properties``,
``items``, ``enum``, numeric/length/pattern bounds, ``anyOf``/``allOf`` and
``$ref`` into ``$defs``) and returns a flat list of human-readable errors with
JSON-path locations, which is exactly what the retry prompt needs.

It is intentionally *not* a complete draft implementation — no ``if/then/else``,
no ``dependentSchemas``. For those, install ``jsonschema`` and validate yourself.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

Number = (int, float)

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, Number) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """Validate *instance* against *schema*; return a list of error strings (empty = valid)."""
    errors: List[str] = []
    _validate(instance, schema, schema, "$", errors)
    return errors


def _validate(
    value: Any,
    schema: Dict[str, Any],
    root: Dict[str, Any],
    path: str,
    errors: List[str],
) -> None:
    if not isinstance(schema, dict):
        return
    if "$ref" in schema:
        resolved = _resolve_ref(root, schema["$ref"])
        if resolved is None:
            errors.append(f"{path}: unresolved $ref '{schema['$ref']}'")
            return
        _validate(value, resolved, root, path, errors)
        return

    if "allOf" in schema:
        for sub in schema["allOf"]:
            _validate(value, sub, root, path, errors)
    if "anyOf" in schema:
        if not _matches_any(value, schema["anyOf"], root):
            errors.append(f"{path}: does not match any of the allowed schemas")
    if "oneOf" in schema:
        matches = sum(1 for sub in schema["oneOf"] if not _sub_errors(value, sub, root))
        if matches != 1:
            errors.append(f"{path}: must match exactly one schema (matched {matches})")

    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: must equal {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} is not one of {schema['enum']!r}")

    types = schema.get("type")
    if types is not None:
        if isinstance(types, str):
            types = [types]
        if not any(_TYPE_CHECKS.get(t, lambda v: True)(value) for t in types):
            got = "null" if value is None else type(value).__name__
            errors.append(f"{path}: expected type {'/'.join(types)}, got {got}")
            return  # further keyword checks would be noise once the type is wrong

    if isinstance(value, dict):
        _validate_object(value, schema, root, path, errors)
    elif isinstance(value, list):
        _validate_array(value, schema, root, path, errors)
    elif isinstance(value, str):
        _validate_string(value, schema, path, errors)
    elif isinstance(value, Number) and not isinstance(value, bool):
        _validate_number(value, schema, path, errors)


def _validate_object(value, schema, root, path, errors) -> None:
    props: Dict[str, Any] = schema.get("properties", {})
    for name in schema.get("required", []):
        if name not in value:
            errors.append(f"{path}: missing required property '{name}'")
    for key, sub_value in value.items():
        child = f"{path}.{key}"
        if key in props:
            _validate(sub_value, props[key], root, child, errors)
        else:
            additional = schema.get("additionalProperties", True)
            if additional is False:
                errors.append(f"{child}: additional property not allowed")
            elif isinstance(additional, dict):
                _validate(sub_value, additional, root, child, errors)


def _validate_array(value, schema, root, path, errors) -> None:
    items = schema.get("items")
    if isinstance(items, dict):
        for idx, item in enumerate(value):
            _validate(item, items, root, f"{path}[{idx}]", errors)
    if "minItems" in schema and len(value) < schema["minItems"]:
        errors.append(f"{path}: has {len(value)} items, fewer than minItems {schema['minItems']}")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        errors.append(f"{path}: has {len(value)} items, more than maxItems {schema['maxItems']}")


def _validate_string(value: str, schema, path, errors) -> None:
    if "minLength" in schema and len(value) < schema["minLength"]:
        errors.append(f"{path}: shorter than minLength {schema['minLength']}")
    if "maxLength" in schema and len(value) > schema["maxLength"]:
        errors.append(f"{path}: longer than maxLength {schema['maxLength']}")
    pattern = schema.get("pattern")
    if pattern and re.search(pattern, value) is None:
        errors.append(f"{path}: does not match pattern /{pattern}/")


def _validate_number(value, schema, path, errors) -> None:
    if "minimum" in schema and value < schema["minimum"]:
        errors.append(f"{path}: {value} < minimum {schema['minimum']}")
    if "maximum" in schema and value > schema["maximum"]:
        errors.append(f"{path}: {value} > maximum {schema['maximum']}")
    if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
        errors.append(f"{path}: {value} <= exclusiveMinimum {schema['exclusiveMinimum']}")
    if "exclusiveMaximum" in schema and value >= schema["exclusiveMaximum"]:
        errors.append(f"{path}: {value} >= exclusiveMaximum {schema['exclusiveMaximum']}")
    if "multipleOf" in schema and schema["multipleOf"]:
        ratio = value / schema["multipleOf"]
        if abs(ratio - round(ratio)) > 1e-9:
            errors.append(f"{path}: {value} is not a multiple of {schema['multipleOf']}")


def _matches_any(value, subs, root) -> bool:
    return any(not _sub_errors(value, sub, root) for sub in subs)


def _sub_errors(value, sub, root) -> List[str]:
    local: List[str] = []
    _validate(value, sub, root, "$", local)
    return local


def _resolve_ref(root: Dict[str, Any], ref: str) -> Optional[Dict[str, Any]]:
    if not ref.startswith("#/"):
        return None
    node: Any = root
    for part in ref[2:].split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            return None
    return node if isinstance(node, dict) else None

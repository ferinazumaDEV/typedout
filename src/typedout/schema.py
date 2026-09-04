"""A thin adapter that lets the engine treat pydantic models and raw JSON Schema
dicts uniformly: both expose a JSON Schema (to put in the prompt) and a
``validate`` method (to check the model's answer)."""

from __future__ import annotations

from typing import Any, Dict, Type, Union

from pydantic import BaseModel

from . import jsonschema_lite
from .errors import SchemaValidationError

SchemaSpec = Union[Type[BaseModel], Dict[str, Any]]


class Schema:
    """Normalises a schema *spec* into ``json_schema`` + ``validate``.

    Accepts a ``pydantic.BaseModel`` subclass (validation returns a typed model
    instance) or a JSON Schema ``dict`` (validation returns the plain ``dict``,
    checked by :mod:`typedout.jsonschema_lite`).
    """

    def __init__(self, spec: SchemaSpec):
        if isinstance(spec, type) and issubclass(spec, BaseModel):
            self._model: Type[BaseModel] | None = spec
            self._json_schema = spec.model_json_schema()
            self._name = spec.__name__
        elif isinstance(spec, dict):
            self._model = None
            self._json_schema = spec
            self._name = str(spec.get("title", "Object"))
        else:
            raise TypeError(
                "schema must be a pydantic BaseModel subclass or a JSON Schema dict, "
                f"got {type(spec).__name__}"
            )

    @property
    def name(self) -> str:
        return self._name

    @property
    def json_schema(self) -> Dict[str, Any]:
        return self._json_schema

    @property
    def is_model(self) -> bool:
        return self._model is not None

    def validate(self, data: Any) -> Any:
        """Validate parsed *data*.

        Returns a pydantic instance (model specs) or the ``dict`` (JSON Schema
        specs). Raises ``pydantic.ValidationError`` or
        :class:`typedout.errors.SchemaValidationError` on failure.
        """
        if self._model is not None:
            return self._model.model_validate(data)
        errors = jsonschema_lite.validate(data, self._json_schema)
        if errors:
            raise SchemaValidationError(errors)
        return data


def ensure_schema(spec: Union[Schema, SchemaSpec]) -> Schema:
    """Return *spec* as a :class:`Schema`, wrapping it if necessary."""
    return spec if isinstance(spec, Schema) else Schema(spec)

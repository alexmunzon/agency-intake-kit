"""Canonical schema, enums, lineage, format helpers, and the ExceptionRecord model."""

from typing import Any

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from agency_schema.exceptions import ExceptionRecord
from agency_schema.lineage import Lineage
from agency_schema.models import TABLE_MODELS

__version__ = "0.0.0"

__all__ = ["ExceptionRecord", "Lineage", "TABLE_MODELS", "json_schema"]


def json_schema() -> dict[str, Any]:
    """JSON Schema for the six tables and ExceptionRecord, sharing one $defs block."""
    models: list[type[BaseModel]] = [*TABLE_MODELS.values(), ExceptionRecord]
    _, schema = models_json_schema(
        [(m, "validation") for m in models], title="agency-intake-kit canonical schema"
    )
    return schema

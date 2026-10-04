"""Canonical schema, enums, lineage, format helpers, and the ExceptionRecord model."""

from typing import Any, Literal

from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

from agency_schema.exceptions import ExceptionRecord
from agency_schema.lineage import Lineage
from agency_schema.models import TABLE_MODELS
from agency_schema.outputs import RUN_FILE_MODELS

__version__ = "0.0.0"

__all__ = ["ExceptionRecord", "Lineage", "RUN_FILE_MODELS", "TABLE_MODELS", "json_schema"]


def json_schema(mode: Literal["validation", "serialization"] = "validation") -> dict[str, Any]:
    """JSON Schema for the six tables, ExceptionRecord, and the run output files.

    "serialization" describes files as written (money is text); "validation" also shows
    what the models accept when reading (money as text or number).
    """
    models: list[type[BaseModel]] = [
        *TABLE_MODELS.values(),
        ExceptionRecord,
        *dict.fromkeys(RUN_FILE_MODELS.values()),
    ]
    _, schema = models_json_schema(
        [(m, mode) for m in models], title="agency-intake-kit canonical schema"
    )
    return schema

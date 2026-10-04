"""Lineage: where every value came from. Required on every table row."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictInt

NonEmpty = Annotated[str, Field(min_length=1)]
# Blank means None. An empty string is refused, so there is only one kind of missing.
OptionalText = NonEmpty | None
RowNumber = Annotated[StrictInt, Field(ge=1)]
Sha256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class StrictModel(BaseModel):
    """Base for every schema model: unknown fields are refused and rows never change.

    Whole numbers and yes/no fields are strict (StrictInt, StrictBool): "yes" or "2026" as
    text is refused, because turning messy words into values is the mapping step's job.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class Lineage(StrictModel):
    source_file: NonEmpty
    sheet: OptionalText  # None for CSV files
    row_number: RowNumber  # 1-based row in the source file
    raw_hash: Sha256  # sha256 of the raw row
    run_id: NonEmpty
    mapping_version: NonEmpty

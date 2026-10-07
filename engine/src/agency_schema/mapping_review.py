"""mapping_review.json and the reviewer's decisions file.

The review file lists every column header that the synonym table and saved decisions did not
settle, with the evidence a person needs to approve, correct or ignore it. The decisions file
is what the dashboard downloads; `intake mapping apply` reads it. It is a reviewer's note, not
an authenticated approval, and it can never clear a blocker or approve a package.
"""

from typing import Annotated, Literal, Self

from pydantic import Field, StrictBool, StrictInt, model_validator

from agency_schema.enums import JevMode
from agency_schema.lineage import NonEmpty, OptionalText, StrictModel

Count = Annotated[StrictInt, Field(ge=0)]
Fingerprint = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
ItemId = Annotated[str, Field(pattern=r"^mr-[0-9a-f]{12}$")]
FieldRef = Annotated[str, Field(pattern=r"^([a-z_]+\.[a-z0-9_]+|none)$")]  # "table.field" or "none"

Origin = Literal["jev_replay", "jev_live", "jev_record", "none"]
Route = Literal["auto", "suggest", "unmapped", "person"]
Action = Literal["approve", "correct", "ignore"]
DECISIONS_NOTE: Literal["a reviewer's note, not an authenticated approval"] = (
    "a reviewer's note, not an authenticated approval"
)
MAX_SAMPLES = 5


class MappingReviewItem(StrictModel):
    item_id: ItemId
    source: NonEmpty
    file_name: NonEmpty
    header: NonEmpty
    format_fingerprint: Fingerprint
    samples: tuple[NonEmpty, ...]
    samples_withheld: StrictBool
    allowed_fields: tuple[FieldRef, ...]
    proposed_field: FieldRef | None
    origin: Origin
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] | None  # the model's own number
    route: Route
    reason: OptionalText
    rows_with_value: Count
    exception_ids: tuple[NonEmpty, ...]
    explanation: NonEmpty  # built from the fields above, never model prose

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if len(self.samples) > MAX_SAMPLES:
            raise ValueError(f"{self.item_id}: at most {MAX_SAMPLES} samples")
        if self.samples_withheld and self.samples:
            raise ValueError(f"{self.item_id}: withheld samples must be empty")
        if self.proposed_field is not None and self.proposed_field not in self.allowed_fields:
            raise ValueError(f"{self.item_id}: proposed field is not an allowed option")
        if self.origin == "none" and self.confidence is not None:
            raise ValueError(f"{self.item_id}: no model answer, so no confidence")
        return self


class MappingReview(StrictModel):
    run_id: NonEmpty
    mapping_version: NonEmpty
    jev_mode: JevMode
    items: tuple[MappingReviewItem, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [item.item_id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("each header appears exactly once")
        return self


class MappingDecision(StrictModel):
    item_id: ItemId
    source: NonEmpty
    header: NonEmpty
    format_fingerprint: Fingerprint
    action: Action
    field: FieldRef | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.action == "ignore" and self.field is not None:
            raise ValueError(f"{self.item_id}: ignore takes no field")
        if self.action != "ignore" and self.field in (None, "none"):
            raise ValueError(f"{self.item_id}: {self.action} needs a field")
        return self


class MappingDecisions(StrictModel):
    run_id: NonEmpty
    mapping_version: NonEmpty
    reviewer: NonEmpty
    decided_at: NonEmpty  # ISO 8601
    note: Literal["a reviewer's note, not an authenticated approval"]
    decisions: tuple[MappingDecision, ...]

    @model_validator(mode="after")
    def _unique(self) -> Self:
        ids = [d.item_id for d in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError("one decision per item")
        return self

"""ExceptionRecord: how every stage reports a problem. Never name a class Exception."""

import re
from typing import Annotated, Self

from pydantic import Field, StrictBool, model_validator

from agency_schema.enums import Family, Lane, Severity
from agency_schema.lineage import NonEmpty, OptionalText, RowNumber, Sha256, StrictModel

# The only rules allowed to stop a run. Fixed by the spec, not tunable.
BLOCKER_RULE_IDS = frozenset({"MAP-003", "CMP-001", "SSN-001"})

RULE_ID_PATTERN = r"^[A-Z]{3}-\d{3}$"

MASK_KEEP_CHARS = 2  # leading characters left readable, at most a third of the value
MASK_MAX_CHARS = 32  # longer values are cut and end with "..."

Probability = Annotated[float, Field(ge=0.0, le=1.0)]


def minimize_value(value: str | None) -> str | None:
    """Mask a raw value for display: keep up to two leading characters and the punctuation.

    "1958-03-12" becomes "19**-**-**" and "TX" becomes "**". Empty becomes None.
    Every stage must use this for value_minimized.
    """
    if not value:
        return None
    keep = min(MASK_KEEP_CHARS, len(value) // 3)
    masked = value[:keep] + "".join("*" if ch.isalnum() else ch for ch in value[keep:])
    if len(masked) > MASK_MAX_CHARS:
        return masked[:MASK_MAX_CHARS] + "..."
    return masked


def _looks_minimized(value: str) -> bool:
    """True when value has the shape minimize_value produces."""
    body = value.removesuffix("...")
    if len(body) > MASK_MAX_CHARS:
        return False
    return not any(ch.isalnum() for ch in body[MASK_KEEP_CHARS:])


SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def check_rule_identity(rule_id: str, family: Family, severity: Severity, blocks: bool) -> None:
    """Raise ValueError unless the rule id, family, severity, and blocking flag agree."""
    if not re.fullmatch(RULE_ID_PATTERN, rule_id):
        raise ValueError(f"bad rule id {rule_id!r}, expected a form like DOB-001")
    if rule_id[:3] != family:
        raise ValueError(f"rule id {rule_id} does not belong to family {family}")
    if (severity == Severity.BLOCKER) != (rule_id in BLOCKER_RULE_IDS):
        raise ValueError(f"{rule_id}: only {sorted(BLOCKER_RULE_IDS)} are blocker rules")
    if blocks != (severity == Severity.BLOCKER):
        raise ValueError(f"{rule_id}: blocks_load must be true exactly for blocker rules")


class JevScores(StrictModel):
    """Jev's triage answers. They order the queue; they never change severity or blocking."""

    entry_error_probability: Probability | None
    impact_score: float | None
    pii_probability: Probability | None


class ExceptionRecord(StrictModel):
    id: NonEmpty
    rule_id: Annotated[str, Field(pattern=RULE_ID_PATTERN)]
    severity: Severity
    family: Family
    source: NonEmpty  # which source in the drop, for example "crm"
    row_number: RowNumber | None  # None for file-level problems
    raw_hash: Sha256 | None
    field: OptionalText
    value_minimized: OptionalText  # output of minimize_value, never a raw value
    message: NonEmpty  # plain language; never embed a raw value, use value_minimized
    suggested_fix: OptionalText
    blocks_load: StrictBool
    lane: Lane
    jev: JevScores | None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        check_rule_identity(self.rule_id, self.family, self.severity, self.blocks_load)
        if self.value_minimized is not None and not _looks_minimized(self.value_minimized):
            raise ValueError("value_minimized looks raw; pass the value through minimize_value")
        for text in (self.message, self.suggested_fix):
            if text is not None and SSN_PATTERN.search(text):
                raise ValueError("message or suggested_fix contains an SSN-shaped value")
        return self

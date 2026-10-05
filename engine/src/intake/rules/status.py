"""STA rule: status words that are not a known policy status."""

import polars as pl

from agency_schema.enums import Family, PolicyStatus, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import rule
from intake.rules.frames import hit, norm, policy_rows, raw, shown


@rule("STA-001", Severity.WARNING, Family.STA, "Status value not recognized")
def status_unknown(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """Judged on the status as written, even when the word table or Jev normalized it."""
    return [
        hit(
            "STA-001",
            r,
            "status",
            raw(r, "status"),
            f'"{shown(raw(r, "status"))}" is not a known status',
            "Mapped to UNKNOWN; confirm",
        )
        for r in policy_rows(frame)
        if raw(r, "status") and norm(raw(r, "status")) not in set(PolicyStatus)
    ]

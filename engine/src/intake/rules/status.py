"""STA rule: status words that are not a known policy status."""

import polars as pl

from agency_schema.enums import Family, PolicyStatus, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import rule
from intake.rules.frames import hit, norm, policy_rows, shown


@rule("STA-001", Severity.WARNING, Family.STA, "Status value not recognized")
def status_unknown(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return [
        hit(
            "STA-001",
            r,
            "status",
            r["status"],
            f'"{shown(r["status"])}" is not a known status',
            "Mapped to UNKNOWN; confirm",
        )
        for r in policy_rows(frame)
        if r["status"] and norm(r["status"]) not in set(PolicyStatus)
    ]

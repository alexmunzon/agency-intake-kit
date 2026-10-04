"""LIC rules: policies sold in a state the writing agent is not licensed in."""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import rule
from intake.checks._records import record


@rule(
    "LIC-001",
    Severity.ERROR,
    Family.LIC,
    "Agent license states do not include the policy state (client address state when the "
    "policy has none)",
)
def license_gaps(view: pl.DataFrame) -> list[ExceptionRecord]:
    """Reads the policy view. Agents missing from the roster are NPN-002's job, so skipped."""
    hits = view.filter(
        pl.col("_agent_known") & pl.col("_state").is_not_null() & ~pl.col("_licensed")
    )
    return [
        record(
            "LIC-001",
            Severity.ERROR,
            row,
            f"The writing agent is not licensed in {row['_state']}",
            "Verify license",
            field="writing_agent_npn",
        )
        for row in hits.sort("_row").iter_rows(named=True)
    ]

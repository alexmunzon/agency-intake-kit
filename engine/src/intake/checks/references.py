"""REF rules: policies pointing at a client the book does not have.

Orphan commission lines are TIE-002 (PR 10) and unknown writing agents are NPN-002 (PR 8), so
REF-001 is the only reference rule here.
"""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import rule
from intake.checks._records import record


@rule("REF-001", Severity.ERROR, Family.REF, "Policy references unknown client")
def orphan_policies(view: pl.DataFrame) -> list[ExceptionRecord]:
    """Anti-join of policies to clients, on the trimmed client id. Reads the policy view."""
    return [
        record(
            "REF-001",
            Severity.ERROR,
            row,
            f"{row['_pid'] or 'A policy'} has no client",
            "Add client or fix client_id",
            field="client_id",
        )
        for row in view.filter(~pl.col("_client_found"))
        .with_columns(pl.col("policy_id").str.strip_chars().alias("_pid"))
        .sort("_rec")
        .iter_rows(named=True)
    ]

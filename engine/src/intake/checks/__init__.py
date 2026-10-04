"""Cross-record checks (PR 9): duplicates, references, RTS, and licenses.

These rules need several tables at once, so run_cross_record_checks builds the frame each rule
reads and calls the rules directly instead of through registry.run_rules. The rules still
register with @rule so the catalog and docs/rules.md list them.
"""

from dataclasses import dataclass

import polars as pl

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import RtsCoverage
from intake.checks import duplicates, licenses, references, rts
from intake.checks._policy_view import policy_view


@dataclass(frozen=True)
class CrossRecordResult:
    records: list[ExceptionRecord]
    coverage: RtsCoverage


def run_cross_record_checks(tables: dict[str, pl.DataFrame]) -> CrossRecordResult:
    """Run DUP, REF, RTS, and LIC rules on canonical tables and build rts_coverage.json."""
    records: list[ExceptionRecord] = []
    for frame in tables.values():
        records += duplicates.exact_duplicate_rows(frame)
    if "clients" in tables:
        records += duplicates.name_dob_collisions(tables["clients"])
    if "policies" not in tables:
        return CrossRecordResult(records, RtsCoverage(cells=()))
    view = policy_view(tables)
    records += duplicates.duplicate_policy_ids(tables["policies"])
    records += references.orphan_policies(view)
    gaps = rts.rts_gaps(view)
    records += gaps + rts.rts_expired(view) + licenses.license_gaps(view)
    coverage = rts.build_rts_coverage(view, tables.get("rts"), gaps)
    return CrossRecordResult(records, coverage)

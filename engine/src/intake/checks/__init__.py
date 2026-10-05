"""Cross-record checks (PR 9): duplicates, references, RTS, and licenses.

These rules need several tables at once, so run_cross_record_checks builds the frame each rule
reads and calls the rules directly instead of through registry.run_rules. The rules still
register with @rule so the catalog and docs/rules.md list them.
"""

import logging
from dataclasses import dataclass, field

import polars as pl

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import RtsCoverage
from intake.checks import duplicates, licenses, references, rts
from intake.checks._policy_view import policy_view
from intake.checks._records import with_lineage
from intake.normalize import unreadable_dates

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossRecordResult:
    records: list[ExceptionRecord]
    coverage: RtsCoverage
    # Rows a check could not evaluate, by "table.field". The row's own problem is reported once,
    # by its row rule (DAT-001 for a policy date); this count makes the gap visible here too.
    skipped: dict[str, int] = field(default_factory=dict)


def _skipped(tables: dict[str, pl.DataFrame], view: pl.DataFrame) -> dict[str, int]:
    """Policies RTS could not check for want of an effective date, and unreadable RTS end dates."""
    counts = {
        "policies.effective_date": view.filter(
            pl.col("_agent_known") & pl.col("_eff").is_null()
        ).height,
        "rts.end_date": unreadable_dates(tables["rts"], "end_date") if "rts" in tables else 0,
    }
    for where, n in counts.items():
        if n:
            log.warning("Cross-record checks skipped %d rows: %s has no readable date", n, where)
    return {where: n for where, n in counts.items() if n}


def run_cross_record_checks(tables: dict[str, pl.DataFrame]) -> CrossRecordResult:
    """Run DUP, REF, RTS, and LIC rules and build rts_coverage.json.

    Takes reader frames (a `lineage` struct column) or the stopgap loader's flat columns.
    """
    tables = {name: with_lineage(name, frame) for name, frame in tables.items()}
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
    return CrossRecordResult(records, coverage, _skipped(tables, view))

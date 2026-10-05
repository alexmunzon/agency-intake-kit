"""RTS rules (missing or ended ready-to-sell) and the rts_coverage.json builder.

A policy needs an appointed and certified RTS row for its writing agent, carrier, state (policy
state, else the client's address state), plan year (the effective year), and line of business.
No matching row is RTS-001. A matching row that ended before the effective date is RTS-002,
never RTS-001. Agents missing from the roster are left to NPN-001 and NPN-002.
"""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import RtsCell, RtsCellState, RtsCoverage
from agency_schema.registry import rule
from intake.checks._policy_view import held_rts
from intake.checks._records import record, record_id

CELL = ["_npn", "_carrier", "_state", "_plan_year"]


@rule(
    "RTS-001",
    Severity.ERROR,
    Family.RTS,
    "Writing agent not RTS for carrier, policy state, plan year, line of business",
)
def rts_gaps(view: pl.DataFrame) -> list[ExceptionRecord]:
    """Reads the policy view."""
    return [
        record(
            "RTS-001",
            Severity.ERROR,
            row,
            f"The writing agent is not ready to sell {row['carrier'].strip()} in {row['_state']} "
            f"for {row['_plan_year']}",
            "Obtain RTS or reassign writing agent",
            field="writing_agent_npn",
        )
        for row in view.filter(pl.col("_rts") == "MISSING").sort("_rec").iter_rows(named=True)
    ]


@rule("RTS-002", Severity.WARNING, Family.RTS, "RTS record end_date before policy effective date")
def rts_expired(view: pl.DataFrame) -> list[ExceptionRecord]:
    """Reads the policy view."""
    return [
        record(
            "RTS-002",
            Severity.WARNING,
            row,
            f"RTS ended {row['_ended'].isoformat()}",
            "Renew RTS",
            field="writing_agent_npn",
        )
        for row in view.filter(pl.col("_rts") == "EXPIRED").sort("_rec").iter_rows(named=True)
    ]


def build_rts_coverage(
    view: pl.DataFrame, rts: pl.DataFrame | None, gaps: list[ExceptionRecord]
) -> RtsCoverage:
    """One cell per agent, carrier, state, and plan year, across lines of business.

    Held cells come from appointed and certified RTS rows (ended rows included: the record is
    held, and RTS-002 flags the lapse). A cell with any RTS-001 policy is USED_WITHOUT_RTS and
    its policy_count is the uncovered policies only, one exception id each.
    """
    gap_ids = {r.id for r in gaps}
    labels: dict[str, str] = {}  # normalized carrier -> carrier as first written
    held: set[tuple[str, str, str, int]] = set()
    if rts is not None:
        for name in rts["carrier"].drop_nulls().str.strip_chars():
            labels.setdefault(name.lower(), name)
        held = set(held_rts(rts).drop_nulls(CELL).select(CELL).iter_rows())
    used: dict[tuple[str, str, str, int], int] = dict.fromkeys(held, 0)
    gap: dict[tuple[str, str, str, int], list[str]] = {}
    for row in view.filter(pl.col("_rts").is_not_null()).sort("_rec").iter_rows(named=True):
        key = (row["_npn"], row["_carrier"], row["_state"], row["_plan_year"])
        labels.setdefault(row["_carrier"], row["carrier"].strip())
        ex_id = record_id("RTS-001", row)
        if ex_id not in gap_ids:
            used[key] = used.get(key, 0) + 1
        else:
            gap.setdefault(key, []).append(ex_id)
    cells = []
    for key in sorted(used.keys() | gap.keys()):
        npn, carrier, state, year = key
        if key in gap:
            coverage, count, ids = RtsCellState.USED_WITHOUT_RTS, len(gap[key]), tuple(gap[key])
        elif used[key]:
            coverage, count, ids = RtsCellState.HELD_AND_USED, used[key], ()
        else:
            coverage, count, ids = RtsCellState.HELD_UNUSED, 0, ()
        cells.append(
            RtsCell(
                npn=npn,
                carrier=labels[carrier],
                state=state,
                plan_year=year,
                coverage=coverage,
                policy_count=count,
                exception_ids=ids,
            )
        )
    return RtsCoverage(cells=tuple(cells))

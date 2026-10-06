"""Turn the tie-out views into the six tie_out/*.json models and their TIE ExceptionRecords."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.lineage import Lineage, StrictModel
from agency_schema.outputs import (
    RULE_LEG,
    LegResult,
    LegStatus,
    TieOutLeg,
    TotalRow,
    Totals,
    Variance,
    VarianceReport,
)
from intake import config
from intake.tieout.link_evidence import LinkEvidence, collect_links
from intake.tieout.load import connect
from intake.tieout.prepare import prepare
from intake.tieout.views import create_views, rows
from synth_agency_data.rates import MONTHLY_RATES, NEW_BUSINESS_MONTHS

CENT = Decimal("0.01")
# The fixtures rate table: illustrative, made-up amounts for the synthetic world.
DEFAULT_RATES = {(lob.value, kind.value): amount for (lob, kind), amount in MONTHLY_RATES.items()}
TOTAL_PCT = f"{(config.TIE_TOTAL_TOLERANCE_PCT * 100).normalize()} percent"

# rule_id: (severity, suggested fix). Messages never repeat a raw value.
RULES = {
    "TIE-001": (Severity.WARNING, "Check carrier statement or policy status"),
    "TIE-002": (Severity.ERROR, "Add policy or investigate"),
    "TIE-003": (Severity.WARNING, "Check commission type or rate"),
    "TIE-004": (Severity.WARNING, "Update CRM"),
    "TIE-005": (Severity.ERROR, "Investigate legs A and B"),
    "MISSING_STATEMENT": (Severity.ERROR, "Get the missing carrier statement and rerun"),
    "TIE-006": (Severity.INFO, "Add carrier_member_id to CRM"),
}


def _message(f: Mapping[str, Any]) -> str:
    match f["rule_id"]:
        case "TIE-001":
            return f"An active policy has no confirmed commission link in {f['statement_period']}"
        case "TIE-002" if f["reason_code"] == "UNRESOLVED_LINK":
            return "Commission policy attribution is unresolved; review the candidate evidence"
        case "TIE-002":
            return f"{f['carrier']} paid a commission for a member who is not in the book"
        case "TIE-003" if f["reason_code"] == "AMOUNT_BLANK":
            return f"Line {f['line_no'] or '(no number)'} has a blank amount"
        case "TIE-003" if f["reason_code"] == "AMOUNT_NOT_A_NUMBER":
            return f"Line {f['line_no'] or '(no number)'} has an amount that is not a number"
        case "TIE-003":
            return "The commission amount is off the rate schedule beyond the tolerance"
        case "TIE-004":
            return "The CRM status disagrees with the carrier statement"
        case "TIE-005" if f["reason_code"] == "MISSING_STATEMENT":
            return (
                f"No {f['carrier']} statement was received for {f['statement_period']}, so "
                "its policies for that period were not tied out"
            )
        case "TIE-005":
            who = f["carrier"] or "An agent"
            return f"{who}: the statement total is off the book by more than {TOTAL_PCT}"
        case _:
            return f"Line {f['line_no']} matched a policy on name and date of birth only"


@dataclass(frozen=True)
class TieOutResult:
    legs: tuple[LegResult, ...]  # in leg order: A, B, C
    variances: VarianceReport
    totals_by_carrier: Totals
    totals_by_agent: Totals
    exceptions: tuple[ExceptionRecord, ...]
    # Non-blank values that could not be read, by "table.field" (each also logged). A policy
    # date is reported once, by DAT-001; a bad amount is also its own TIE-003.
    skipped: Mapping[str, int] = field(default_factory=dict)
    links: tuple[LinkEvidence, ...] = ()


def _cents(value: Decimal | None) -> Decimal | None:
    return None if value is None else value.quantize(CENT)


def _record(ex_id: str, f: Mapping[str, Any], lineage: Lineage | None) -> ExceptionRecord:
    """lineage is the row's own, exactly as the reader attached it (None for a total)."""
    severity, fix = RULES[f["reason_code"] if f["reason_code"] in RULES else f["rule_id"]]
    row = lineage.row_number if lineage else None
    return ExceptionRecord(
        id=ex_id, rule_id=f["rule_id"], severity=severity, family=Family.TIE,
        source=f["source"], row_number=row, raw_hash=lineage.raw_hash if lineage else None,
        field=f["field"],
        value_minimized=minimize_value(f["raw_value"]), message=_message(f), suggested_fix=fix,
        blocks_load=False, lane=Lane.UNREVIEWED, jev=None, lineage=lineage,
    )  # fmt: skip


def _variance(ex_id: str, f: Mapping[str, Any]) -> Variance:
    paid, expected = _cents(f["paid"]), _cents(f["expected"])
    return Variance(
        rule_id=f["rule_id"], exception_id=ex_id, leg=RULE_LEG[f["rule_id"]],
        carrier=f["carrier"], statement_period=f["statement_period"], line_no=f["line_no"],
        policy_id=f["policy_id"], carrier_member_id=f["carrier_member_id"],
        agent_npn=f["agent_npn"], paid=paid, expected=expected,
        difference=(paid or Decimal("0.00")) - (expected or Decimal("0.00")),
    )  # fmt: skip


def _totals_finding(group_by: str, row: TotalRow) -> dict[str, Any]:
    by_carrier = group_by == "carrier"
    return {
        "rule_id": "TIE-005", "reason_code": "TOTAL_OFF", "_rec": None,
        "carrier": row.key if by_carrier else None,
        "agent_npn": None if by_carrier else row.key, "statement_period": None,
        "line_no": None, "policy_id": None, "carrier_member_id": None,
        "paid": row.statement_paid, "expected": row.book_expected, "source": "commission_lines",
        "field": "carrier" if by_carrier else "agent_npn", "raw_value": row.key,
    }  # fmt: skip


def _not_run(reason: str) -> TieOutResult:
    legs = tuple(
        LegResult(
            leg=leg,
            status=LegStatus.NOT_RUN,
            not_run_reason=reason,
            matched=None,
            unmatched=None,
            weak_matched=None,
            variance_count=None,
            variance_dollars=None,
            variances=(),
        )  # fmt: skip
        for leg in TieOutLeg
    )
    by_carrier, by_agent = (
        Totals(group_by=g, status=LegStatus.NOT_RUN, not_run_reason=reason, rows=())
        for g in ("carrier", "agent")
    )
    return TieOutResult(legs, VarianceReport(variances=()), by_carrier, by_agent, exceptions=())


def run_tieout(
    tables: Mapping[str, pl.DataFrame | None],
    *,
    run_id: str,
    rates: Mapping[tuple[str, str], Decimal] = DEFAULT_RATES,
) -> TieOutResult:
    """Run legs A, B, C, the dollar checks, and the totals. Missing book or statements: NOT_RUN."""
    if tables.get("commission_lines") is None:
        return _not_run("No commission statements were received, so there is nothing to tie out")
    if tables.get("policies") is None:
        return _not_run("No policy book was received, so statements cannot be tied out")
    prepared = prepare(tables, run_id)
    con = connect(prepared.frames, rates, NEW_BUSINESS_MONTHS)
    create_views(con)
    totals = {g: [] for g in ("carrier", "agent")}  # type: dict[str, list[TotalRow]]
    for row in rows(con, "totals"):
        totals[str(row.pop("group_by"))].append(TotalRow.model_validate(row))
    findings = rows(con, "variances") + [
        _totals_finding(g, r) for g, group in totals.items() for r in group
        if not r.within_tolerance
    ]  # fmt: skip
    findings.sort(key=lambda f: f["rule_id"])  # stable: keeps the SQL order inside a rule
    exceptions, variances = [], []
    for n, f in enumerate(findings, start=1):
        ex_id = f"EX-TIE-{n:06d}"
        rec = f["_rec"]
        lineage = None if rec is None else prepared.lineage[f["source"]][rec]
        exceptions.append(_record(ex_id, f, lineage))
        if f["rule_id"] in RULE_LEG:  # TIE-006 is an exception only
            variances.append(_variance(ex_id, f))
    counts = {c["leg"]: c for c in rows(con, "leg_counts")}
    legs = []
    for leg in TieOutLeg:
        own = tuple(v for v in variances if v.leg == leg)
        c = counts[leg.value]
        legs.append(
            LegResult(
                leg=leg,
                status=LegStatus.RAN,
                not_run_reason=None,
                matched=c["matched"],
                unmatched=c["unmatched"],
                weak_matched=c["weak_matched"],
                variance_count=len(own),
                variance_dollars=sum((abs(v.difference) for v in own), Decimal("0.00")),
                variances=own,
            )  # fmt: skip
        )
    return TieOutResult(
        legs=tuple(legs),
        variances=VarianceReport(variances=tuple(variances)),
        totals_by_carrier=Totals(group_by="carrier", status=LegStatus.RAN, not_run_reason=None,
                                 rows=tuple(totals["carrier"])),
        totals_by_agent=Totals(group_by="agent", status=LegStatus.RAN, not_run_reason=None,
                               rows=tuple(totals["agent"])),
        exceptions=tuple(exceptions),
        skipped=prepared.skipped,
        links=collect_links(con, prepared),
    )  # fmt: skip


def write_tieout(result: TieOutResult, run_dir: Path) -> None:
    """Write the six tie_out/*.json files exactly as the models serialize them."""
    out = run_dir / "tie_out"
    out.mkdir(parents=True, exist_ok=True)
    files: dict[str, StrictModel] = {
        f"leg_{leg.leg.value.lower()}.json": leg for leg in result.legs
    }
    files |= {
        "variances.json": result.variances,
        "totals_by_carrier.json": result.totals_by_carrier,
        "totals_by_agent.json": result.totals_by_agent,
    }
    for name, model in files.items():
        (out / name).write_text(model.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (out / "links.jsonl").write_text(
        "".join(link.model_dump_json() + "\n" for link in result.links), encoding="utf-8"
    )

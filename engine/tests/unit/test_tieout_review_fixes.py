"""Review fixes for the tie-out: line keys (#53), dates (#44), amounts (#45), chargebacks (#47),
missing statements (#48), and lineage (#49). Frames here are built the way PR 4 readers build
them: every cell text, one `lineage` struct column, row numbers restarting in each file."""

from collections import Counter
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest

from intake.readers import build_frame
from intake.run.pipeline import canonical_from_drop
from intake.tieout import TieOutResult, run_tieout
from synth_agency_data.canonical_writer import load_ground_truth

AGENCY_A = Path(__file__).parents[3] / "fixtures" / "agency-a"
RATES = {("MA", "NEW"): Decimal("52.50"), ("MA", "RENEWAL"): Decimal("26.25")}
POLICY = "policy_id client_id carrier carrier_member_id line_of_business effective_date "
POLICY += "termination_date status writing_agent_npn"
LINE = "carrier statement_period line_no carrier_member_id member_name member_dob policy_ref "
LINE += "agent_npn amount commission_type"
Cells = list[str | None]


def reader_frame(header: str, rows: list[Cells], file: str, sheet: str | None = None,
                 first_row: int = 2, version: str = "v2") -> pl.DataFrame:  # fmt: skip
    return build_frame(
        header.split(),
        [(first_row + i, r) for i, r in enumerate(rows)],
        source_file=file,
        sheet=sheet,
        run_id="run-7",
        mapping_version=version,
    )


def policy(pid: str, carrier: str = "Bluepeak", eff: str = "2020-01-01",
           status: str = "ACTIVE", term: str | None = None) -> Cells:  # fmt: skip
    return [pid, "C-1", carrier, f"M-{pid}", "MA", eff, term, status, "1234567"]


def line(no: int, pid: str | None, amount: str | None, carrier: str = "Bluepeak",
         kind: str = "RENEWAL", dob: str | None = None) -> Cells:  # fmt: skip
    member = f"M-{pid}" if pid else None
    name = "Ann Lee" if dob else None
    return [carrier, "2026-06", str(no), member, name, dob, None, "1234567", amount, kind]


def tie(policies: list[Cells], lines: list[Cells], dob: str = "1950-01-02") -> TieOutResult:
    tables = {
        "policies": reader_frame(POLICY, policies, "crm.csv"),
        "commission_lines": reader_frame(LINE, lines, "bluepeak.xlsx", "Statement", 4),
        "clients": reader_frame("client_id first_name last_name dob", [["C-1", "Ann", "Lee", dob]],
                                "crm_clients.csv"),
    }  # fmt: skip
    return run_tieout(tables, run_id="run-7", rates=RATES)


def rules(result: TieOutResult) -> list[tuple[str, str | None]]:
    return sorted((r.rule_id, r.message) for r in result.exceptions)


def by_rule(result: TieOutResult) -> Counter[str]:
    return Counter(r.rule_id for r in result.exceptions)


def test_overlapping_line_numbers_across_carriers_do_not_cross_match() -> None:
    """#53: two statement files both start at row 4; each line keeps its own carrier's match."""
    tables = {
        "policies": reader_frame(POLICY, [policy("P1"), policy("P2", "Harborline")], "crm.csv"),
        "commission_lines": pl.concat(
            [
                reader_frame(LINE, [line(1, "P1", "26.25")], "bluepeak.xlsx", "Statement", 4),
                reader_frame(
                    LINE, [line(1, None, "61.05", "Harborline")], "harbor.xlsx", "Statement", 4
                ),
            ]
        ),  # fmt: skip
    }
    result = run_tieout(tables, run_id="run-7", rates=RATES)
    found = {(v.rule_id, v.carrier, v.policy_id) for v in result.variances.variances}
    assert ("TIE-002", "Harborline", None) in found
    assert ("TIE-001", "Harborline", "P2") in found
    assert not [v for v in found if v[0] == "TIE-003"]


def _key(rule_id: str, v: dict[str, object]) -> tuple[object, ...]:
    """The ground truth's record key for each rule, as tests/unit/test_tieout.py reads it."""
    if rule_id == "TIE-005":  # a total: by carrier, or by agent
        return (v.get("carrier"), v.get("agent_npn"))
    if rule_id in ("TIE-001", "TIE-004"):
        return (v["policy_id"],)
    return (v["carrier"], v["statement_period"], v["line_no"])


def test_six_statement_files_find_exactly_the_ground_truth() -> None:
    """#53: the real drop has one statement file per carrier, rows numbered from 4 in each."""
    tables = canonical_from_drop(AGENCY_A / "drop").tables
    lines = tables["commission_lines"]
    files = lines["lineage"].struct.field("source_file").unique()
    assert files.len() == 6, "the real drop has one statement file per carrier"
    result = run_tieout(tables, run_id="test-run")
    truth = load_ground_truth(AGENCY_A / "ground_truth.json")["defects"]
    for rule_id in ("TIE-001", "TIE-002", "TIE-003", "TIE-004", "TIE-005"):
        planted = Counter(
            _key(rule_id, d["record_key"]) for d in truth if rule_id in d["expected_rule_ids"]
        )
        found = Counter(
            _key(rule_id, v.model_dump())
            for v in result.variances.variances
            if v.rule_id == rule_id
        )
        # The planted REF-001 now leaves the conflicting policy link unresolved.
        if rule_id == "TIE-001":
            planted[("P-01324",)] += 3
        elif rule_id == "TIE-002":
            planted.update(("Meridian Care", f"2026-{m}", 193) for m in ("06", "07", "08"))
        assert planted and found == planted, rule_id
    orphan = [v for v in result.variances.variances if v.carrier_member_id == "HL-998213"]
    assert [(v.rule_id, v.paid) for v in orphan] == [("TIE-002", Decimal("61.05"))]


def test_every_date_style_is_tied_out_and_unreadable_dates_are_counted() -> None:
    """#44: ISO, US, and two-digit-year effective dates are all due; an unreadable one counted."""
    result = tie(
        [policy("P1"), policy("P2", eff="05/01/2020"), policy("P3", eff="05/01/20"),
         policy("P4", eff="someday")],
        [line(1, "P1", "26.25")],
    )  # fmt: skip
    unpaid = sorted(v.policy_id or "" for v in result.variances.variances if v.rule_id == "TIE-001")
    assert unpaid == ["P2", "P3"]
    assert result.skipped == {"policies.effective_date": 1}


def test_name_and_dob_match_reads_a_serial_dob_against_a_us_dob() -> None:
    """#44: CRM DOB as an Excel serial, statement DOB as 01/01/60: still a weak match."""
    result = tie([policy("P1")], [line(1, None, "26.25", dob="01/01/60")], dob="21916")
    assert [r.rule_id for r in result.exceptions] == ["TIE-001", "TIE-002", "TIE-006"]


@pytest.mark.parametrize("amount", ["$26.25", " 26.25 ", "$1,026.25"])
def test_amounts_with_dollar_signs_and_commas_are_read(amount: str) -> None:
    """#45: never a crash; $1,026.25 is read and is off schedule (TIE-003, not an error)."""
    result = tie([policy("P1")], [line(1, "P1", amount)])
    expected = ["TIE-003", "TIE-005"] if "1,0" in amount else []
    assert sorted(by_rule(result)) == expected


@pytest.mark.parametrize(
    ("amount", "says"), [(None, "blank"), ("abc", "not a number")]
)  # fmt: skip
def test_a_blank_or_unreadable_amount_is_one_reported_variance(
    amount: str | None, says: str
) -> None:
    """#45: the bad line is one TIE-003 with lineage; the good line still ties out."""
    result = tie([policy("P1"), policy("P2")], [line(1, "P1", "26.25"), line(2, "P2", amount)])
    bad = [v for v in result.variances.variances if v.rule_id == "TIE-003"]
    assert [(v.line_no, v.paid, v.expected) for v in bad] == [(2, None, Decimal("26.25"))]
    record = next(r for r in result.exceptions if r.id == bad[0].exception_id)
    assert says in record.message and record.row_number == 5
    assert result.skipped == {"commission_lines.amount": 1}


@pytest.mark.parametrize("status", ["CANCELLED", "TERMINATED"])
def test_a_chargeback_on_an_ended_policy_is_expected(status: str) -> None:
    """#47: no TIE-003, no TIE-004, and the totals still tie."""
    result = tie(
        [policy("P1", status=status, term="2026-05-31")],
        [line(1, "P1", "-26.25", kind="CHARGEBACK")],
    )
    assert result.exceptions == ()


def test_a_negative_amount_counts_as_a_chargeback() -> None:
    result = tie([policy("P1", status="CANCELLED")], [line(1, "P1", "(26.25)")])
    assert result.exceptions == ()


def test_a_chargeback_on_an_active_policy_still_raises() -> None:
    result = tie([policy("P1")], [line(1, "P1", "-26.25", kind="CHARGEBACK")])
    assert "TIE-003" in by_rule(result) and "TIE-004" not in by_rule(result)


def test_a_carrier_with_no_statement_is_reported_never_dropped() -> None:
    """#48: Harborline sent nothing for 2026-06; it is a TIE-005 and stays in the totals."""
    result = tie([policy("P1"), policy("P2", "Harborline")], [line(1, "P1", "26.25")])
    missing = [
        v for v in result.variances.variances if v.rule_id == "TIE-005" and v.statement_period
    ]
    assert [(v.carrier, v.statement_period, v.expected) for v in missing] == [
        ("Harborline", "2026-06", Decimal("26.25"))
    ]
    record = next(r for r in result.exceptions if r.id == missing[0].exception_id)
    assert "No Harborline statement was received for 2026-06" in record.message
    harbor = next(r for r in result.totals_by_carrier.rows if r.key == "Harborline")
    assert (harbor.book_expected, harbor.statement_paid) == (Decimal("26.25"), Decimal("0.00"))
    assert not [v for v in result.variances.variances if v.rule_id == "TIE-001"]


def test_exceptions_carry_the_incoming_lineage() -> None:
    """#49: sheet, mapping_version, and run_id come from the row's own lineage."""
    result = tie([policy("P1")], [line(1, "P1", "26.25"), line(2, None, "61.05")])
    orphan = next(r for r in result.exceptions if r.rule_id == "TIE-002")
    assert orphan.lineage is not None
    assert (orphan.lineage.source_file, orphan.lineage.sheet, orphan.lineage.row_number) == (
        "bluepeak.xlsx",
        "Statement",
        5,
    )
    assert (orphan.lineage.mapping_version, orphan.lineage.run_id) == ("v2", "run-7")

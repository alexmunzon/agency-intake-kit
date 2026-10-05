"""PR 10: the three-way tie-out (SPEC, Three-way tie-out definition; example 4)."""

import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import LegStatus, Scorecard, TieOutLeg
from agency_schema.run_dir import check_run_dir
from intake.run.canonicalize import frame_from_rows
from intake.run.pipeline import canonical_from_drop
from intake.tieout import TieOutResult, run_tieout, write_tieout
from synth_agency_data.canonical_writer import load_ground_truth
from synth_agency_data.world import build_world
from synth_agency_data.writers import write_drop

FIXTURES = Path(__file__).parents[3] / "fixtures"
AGENCY_A = FIXTURES / "agency-a"
LEG_RULE = {"TIE-001": "A", "TIE-002": "B", "TIE-003": None, "TIE-004": "C"}


@pytest.fixture(scope="module")
def defected() -> TieOutResult:
    return run_tieout(canonical_from_drop(AGENCY_A / "drop").tables, run_id="test-run")


@pytest.fixture(scope="module")
def clean(tmp_path_factory: pytest.TempPathFactory) -> TieOutResult:
    out = tmp_path_factory.mktemp("clean")
    write_drop(build_world(seed=42, n_clients=2000), [], out / "drop", plant_pii=False)
    return run_tieout(canonical_from_drop(out / "drop").tables, run_id="test-run")


def _key(rule_id: str, v: Any) -> tuple[Any, ...]:
    if rule_id == "TIE-005":  # a total: by carrier, or by agent
        return (v.get("carrier"), v.get("agent_npn"))
    if rule_id in ("TIE-001", "TIE-004"):
        return (v["policy_id"],)
    return (v["carrier"], v["statement_period"], v["line_no"])


@pytest.mark.parametrize("rule_id", ["TIE-001", "TIE-002", "TIE-003", "TIE-004", "TIE-005"])
def test_each_rule_finds_exactly_its_ground_truth_defects(
    defected: TieOutResult, rule_id: str
) -> None:
    truth = load_ground_truth(AGENCY_A / "ground_truth.json")["defects"]
    planted = {_key(rule_id, d["record_key"]) for d in truth if rule_id in d["expected_rule_ids"]}
    found = {
        _key(rule_id, v.model_dump()) for v in defected.variances.variances if v.rule_id == rule_id
    }
    assert planted and found == planted


def test_each_leg_file_holds_its_own_rule(defected: TieOutResult) -> None:
    rules = {leg.leg: {v.rule_id for v in leg.variances} for leg in defected.legs}
    assert rules == {
        TieOutLeg.BOOK_VS_STATEMENT: {"TIE-001"},
        TieOutLeg.STATEMENT_VS_BOOK: {"TIE-002"},
        TieOutLeg.CRM_VS_STATEMENT: {"TIE-004"},
    }
    assert all(leg.status == LegStatus.RAN and leg.weak_matched == 0 for leg in defected.legs)


def test_example_4_orphan_payment_lands_in_leg_b(defected: TieOutResult) -> None:
    leg_b = defected.legs[1]
    hits = [
        v
        for v in leg_b.variances
        if (v.carrier, v.statement_period, v.line_no) == ("Harborline", "2026-08", 212)
    ]
    assert len(hits) == 1
    v = hits[0]
    assert (v.rule_id, v.carrier_member_id, v.paid, v.difference, v.policy_id) == (
        "TIE-002",
        "HL-998213",
        Decimal("61.05"),
        Decimal("61.05"),
        None,
    )
    record = next(r for r in defected.exceptions if r.id == v.exception_id)
    assert (record.rule_id, record.severity, record.row_number) == ("TIE-002", "ERROR", 970)
    assert record.lineage is not None
    assert (record.lineage.source_file, record.lineage.sheet) == (
        "commissions_harborline.xlsx",
        "Statement",
    )
    assert "HL-998213" not in record.message and record.value_minimized == "HL-******"
    harborline = next(r for r in defected.totals_by_carrier.rows if r.key == "Harborline")
    assert harborline.unexplained_revenue >= Decimal("61.05")


def test_totals_fire_tie_005_on_the_defected_world(defected: TieOutResult) -> None:
    out = [r.key for r in defected.totals_by_carrier.rows if not r.within_tolerance]
    tie005 = [v for v in defected.variances.variances if v.rule_id == "TIE-005"]
    assert out and {v.carrier for v in tie005 if v.carrier} == set(out)


def test_clean_world_has_zero_variances_and_totals_tie_to_the_cent(clean: TieOutResult) -> None:
    assert clean.exceptions == () and clean.variances.variances == ()
    for leg in clean.legs:
        assert (leg.status, leg.unmatched, leg.variance_count, leg.variance_dollars) == (
            LegStatus.RAN,
            0,
            0,
            Decimal("0.00"),
        )
        assert leg.matched and leg.matched > 0
    for totals in (clean.totals_by_carrier, clean.totals_by_agent):
        assert totals.rows and all(r.difference == 0 and r.within_tolerance for r in totals.rows)


# A tiny hand-built world for the edges: one client, policies on custom rates.
POLICY_COLS = [
    "policy_id",
    "client_id",
    "carrier",
    "plan_id",
    "line_of_business",
    "state",
    "eligibility_reason",
    "effective_date",
    "termination_date",
    "status",
    "writing_agent_npn",
    "monthly_premium",
    "carrier_member_id",
]
LINE_COLS = [
    "carrier",
    "statement_period",
    "line_no",
    "carrier_member_id",
    "member_name",
    "member_dob",
    "policy_ref",
    "agent_npn",
    "amount",
    "commission_type",
    "paid_date",
]
CLIENT_COLS = ["client_id", "first_name", "last_name", "dob"]
RATES = {("MA", "RENEWAL"): Decimal("26.25"), ("ACA", "RENEWAL"): Decimal("200.00")}


def _policy(pid: str, lob: str, member: str, status: str = "ACTIVE") -> list[str | None]:
    return [
        pid,
        "C-00001",
        "Bluepeak",
        "x",
        lob,
        "GA",
        "AGE",
        "2020-01-01",
        None,
        status,
        "1234567",
        "1.00",
        member,
    ]


def _line(no: int, member: str | None, ref: str | None, amount: str) -> list[str | None]:
    name, dob = ("Ann Lee", "1950-01-02") if ref is None else (None, None)
    return [
        "Bluepeak",
        "2026-06",
        str(no),
        member,
        name,
        dob,
        ref,
        "1234567",
        amount,
        "RENEWAL",
        "2026-07-15",
    ]


def _tiny(lines: list[list[str | None]], policies: list[list[str | None]]) -> TieOutResult:
    tables = {
        "policies": frame_from_rows(
            "policies.csv", [dict(zip(POLICY_COLS, row, strict=True)) for row in policies]
        ),
        "commission_lines": frame_from_rows(
            "commission_lines.csv", [dict(zip(LINE_COLS, row, strict=True)) for row in lines]
        ),
        "clients": frame_from_rows(
            "clients.csv",
            [dict(zip(CLIENT_COLS, ["C-00001", "Ann", "Lee", "1950-01-02"], strict=True))],
        ),
    }
    return run_tieout(tables, run_id="test-run", rates=RATES)


@pytest.mark.parametrize(
    ("lob", "amount", "flagged"),
    [
        ("MA", "27.25", False),  # exactly $1 over (1 percent of 26.25 is less than $1)
        ("MA", "25.25", False),
        ("MA", "27.26", True),  # one cent over
        ("ACA", "202.00", False),  # exactly 1 percent over (more than $1)
        ("ACA", "197.99", True),
    ],
)
def test_line_tolerance_is_the_larger_of_one_dollar_or_one_percent(
    lob: str, amount: str, flagged: bool
) -> None:
    result = _tiny([_line(1, "BP-1", None, amount)], [_policy("P-1", lob, "BP-1")])
    assert [v.rule_id for v in result.variances.variances if v.rule_id == "TIE-003"] == (
        ["TIE-003"] if flagged else []
    )


@pytest.mark.parametrize(("amount", "within"), [("201.00", True), ("201.01", False)])
def test_totals_tolerance_is_half_a_percent(amount: str, within: bool) -> None:
    result = _tiny([_line(1, "BP-1", None, amount)], [_policy("P-1", "ACA", "BP-1")])
    assert [r.within_tolerance for r in result.totals_by_carrier.rows] == [within]
    assert [r.within_tolerance for r in result.totals_by_agent.rows] == [within]
    assert any(v.rule_id == "TIE-005" for v in result.variances.variances) is not within


def test_a_name_and_dob_match_is_weak_and_flagged() -> None:
    result = _tiny([_line(1, None, None, "26.25")], [_policy("P-1", "MA", "BP-1")])
    leg_b = result.legs[1]
    assert (leg_b.matched, leg_b.weak_matched, leg_b.unmatched) == (1, 1, 0)
    assert [r.rule_id for r in result.exceptions] == ["TIE-006"]
    assert result.exceptions[0].severity == "INFO"


def test_status_conflict_and_unpaid_policy() -> None:
    result = _tiny(
        [_line(1, "BP-1", "P-1", "26.25")],
        [_policy("P-1", "MA", "BP-1", "CANCELLED"), _policy("P-2", "MA", "BP-2")],
    )
    rules = sorted((v.rule_id, v.policy_id) for v in result.variances.variances)
    assert rules == [("TIE-001", "P-2"), ("TIE-004", "P-1")]  # totals still tie


@pytest.mark.parametrize("absent", [False, True], ids=["none", "absent"])
@pytest.mark.parametrize("missing", ["commission_lines", "policies"])
def test_a_missing_source_means_not_run_never_zero(missing: str, absent: bool) -> None:
    tables: dict[str, Any] = dict(canonical_from_drop(AGENCY_A / "drop").tables)
    if absent:
        del tables[missing]
    else:
        tables[missing] = None
    result = run_tieout(tables, run_id="test-run")
    for leg in result.legs:
        assert leg.status == LegStatus.NOT_RUN and leg.not_run_reason
        assert (leg.matched, leg.variance_count, leg.variance_dollars) == (None, None, None)
    assert result.totals_by_carrier.status == LegStatus.NOT_RUN
    assert result.exceptions == () and result.variances.variances == ()


def test_written_files_pass_check_run_dir(defected: TieOutResult, tmp_path: Path) -> None:
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "sample-run", run)
    write_tieout(defected, run)
    lines = (run / "exceptions.jsonl").read_text().splitlines()
    kept = [r for r in map(ExceptionRecord.model_validate_json, lines) if r.family != "TIE"]
    records = kept + list(defected.exceptions)
    (run / "exceptions.jsonl").write_text("".join(r.model_dump_json() + "\n" for r in records))
    card = Scorecard.model_validate_json((run / "scorecard.json").read_text()).model_dump()
    by_rule: dict[str, int] = {}
    for r in records:
        by_rule[r.rule_id] = by_rule.get(r.rule_id, 0) + 1
    card["exceptions_by_rule"] = by_rule
    card["exceptions_by_severity"] = {
        s: sum(r.severity.lower() == s for r in records)
        for s in ("blocker", "error", "warning", "info")
    }
    card["tie_out"] = [leg.model_dump(exclude={"variances"}) for leg in defected.legs]
    (run / "scorecard.json").write_text(Scorecard.model_validate(card).model_dump_json(indent=2))
    check_run_dir(run)
    assert (run / "tie_out" / "leg_statement_vs_book.json").read_text().endswith("}\n")

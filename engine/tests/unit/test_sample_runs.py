"""The sample runs are the engine-to-dashboard contract (SPEC, Sample-run contract)."""

import json
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import (
    RUN_FILE_MODELS,
    LegResult,
    LegStatus,
    RtsCellState,
    RtsCoverage,
    TieOutLeg,
    Totals,
)
from agency_schema.run_dir import check_run_dir

FIXTURES = Path(__file__).parents[3] / "fixtures"
SAMPLES = ["sample-run", "sample-run-failed", "sample-run-passed", "sample-run-partial"]


def load(sample: str, name: str) -> Any:
    model = RUN_FILE_MODELS[name]
    return model.model_validate_json((FIXTURES / sample / name).read_text())


def exceptions(sample: str) -> list[ExceptionRecord]:
    lines = (FIXTURES / sample / "exceptions.jsonl").read_text().splitlines()
    return [ExceptionRecord.model_validate_json(line) for line in lines if line]


@pytest.mark.parametrize("sample", SAMPLES)
def test_every_sample_is_a_valid_consistent_run(sample: str) -> None:
    check_run_dir(FIXTURES / sample)
    assert load(sample, "manifest.json").started_at.isoformat() == "2026-10-01T09:00:00+00:00"


@pytest.mark.parametrize("sample", SAMPLES)
@pytest.mark.parametrize("name", sorted(RUN_FILE_MODELS))
def test_samples_are_written_exactly_as_the_models_write(sample: str, name: str) -> None:
    # Catches money written as a JSON number: the dashboard types say it is text.
    text = (FIXTURES / sample / name).read_text()
    assert load(sample, name).model_dump_json(indent=2) + "\n" == text


@pytest.mark.parametrize(
    ("name", "edit"),
    [
        ("scorecard.json", lambda d: {**d, "rts_gaps": d["rts_gaps"] + 1}),
        ("scorecard.json", lambda d: {**d, "exceptions_by_rule": {"DOB-002": 13}}),
        ("tie_out/variances.json", lambda d: {"variances": d["variances"][1:]}),
        ("tie_out/totals_by_carrier.json", lambda d: {**d, "group_by": "agent"}),
    ],
)
def test_check_run_dir_catches_files_that_disagree(tmp_path: Path, name: str, edit: Any) -> None:
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "sample-run", run)
    (run / name).write_text(json.dumps(edit(json.loads((run / name).read_text()))))
    with pytest.raises(ValueError):
        check_run_dir(run)


def test_all_statuses_and_severities_appear() -> None:
    statuses = {load(s, "manifest.json").status for s in SAMPLES}
    assert statuses == {"PASSED", "PASSED_WITH_WARNINGS", "FAILED"}
    severities = {r.severity for s in SAMPLES for r in exceptions(s)}
    assert severities == {"BLOCKER", "ERROR", "WARNING", "INFO"}


def test_failed_sample_stops_at_the_raw_gate() -> None:
    sample = "sample-run-failed"
    records = exceptions(sample)
    assert [r.rule_id for r in records if r.blocks_load] == ["CMP-001"]
    crm = next(f for f in load(sample, "manifest.json").inputs if f.source == "crm")
    assert (crm.rows_expected, crm.rows_received) == (2680, 2574)
    for stem in TieOutLeg.file_stems():
        assert load(sample, f"tie_out/leg_{stem}.json").status == LegStatus.NOT_RUN
    for stem in ("carrier", "agent"):
        totals: Totals = load(sample, f"tie_out/totals_by_{stem}.json")
        assert totals.status == LegStatus.NOT_RUN
    assert load(sample, "rts_coverage.json").cells == ()
    assert not (FIXTURES / sample / "clean").exists()


def test_passed_sample_has_nothing_above_info() -> None:
    assert all(r.severity == "INFO" for r in exceptions("sample-run-passed"))


def test_example_3_rts_gap_is_in_the_sample() -> None:
    rts = [r for r in exceptions("sample-run") if r.rule_id == "RTS-001"]
    assert rts and rts[0].suggested_fix == "Obtain RTS or reassign writing agent"
    cells: RtsCoverage = load("sample-run", "rts_coverage.json")
    cell = next(
        c for c in cells.cells if (c.npn, c.carrier, c.state) == ("1884412", "Harborline", "TX")
    )
    assert (cell.plan_year, cell.coverage) == (2026, RtsCellState.USED_WITHOUT_RTS)
    assert rts[0].id in cell.exception_ids


def test_example_4_orphan_payment_is_in_the_sample() -> None:
    leg: LegResult = load("sample-run", "tie_out/leg_statement_vs_book.json")
    orphan = next(v for v in leg.variances if v.carrier_member_id == "HL-998213")
    assert (orphan.rule_id, orphan.carrier, orphan.statement_period) == (
        "TIE-002",
        "Harborline",
        "2026-08",
    )
    assert (orphan.line_no, orphan.paid) == (212, Decimal("61.05"))
    totals: Totals = load("sample-run", "tie_out/totals_by_carrier.json")
    harborline = next(t for t in totals.rows if t.key == "Harborline")
    assert harborline.unexplained_revenue >= Decimal("61.05")


def test_partial_sample_has_two_legs_ran_and_one_not_run() -> None:
    sample = "sample-run-partial"
    legs = {s: load(sample, f"tie_out/leg_{s}.json") for s in TieOutLeg.file_stems()}
    assert legs["crm_vs_statement"].status == LegStatus.NOT_RUN
    assert legs["crm_vs_statement"].not_run_reason
    assert legs["crm_vs_statement"].variance_dollars is None
    ran = [leg for stem, leg in legs.items() if stem != "crm_vs_statement"]
    assert all(leg.status == LegStatus.RAN for leg in ran)
    assert "TIE-004" not in {r.rule_id for r in exceptions(sample)}

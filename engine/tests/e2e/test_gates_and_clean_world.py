"""SPEC examples 5 and 6 end to end, refusals (#59), and the clean world through the pipeline."""

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import LegStatus, Manifest, RunStatus, Scorecard
from agency_schema.run_dir import check_run_dir
from intake.cli import app
from intake.run.pipeline import RunOptions, RunRefused, RunResult, run

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"


def records(run_dir: Path) -> list[ExceptionRecord]:
    lines = (run_dir / "exceptions.jsonl").read_text().splitlines()
    return [ExceptionRecord.model_validate_json(line) for line in lines]


def assert_stopped_at_the_gates(result: RunResult, rule_id: str) -> list[ExceptionRecord]:
    check_run_dir(result.run_dir)
    found = records(result.run_dir)
    assert [r.rule_id for r in found if r.severity == Severity.BLOCKER] == [rule_id]
    assert {r.rule_id[:3] for r in found} <= {"ING", rule_id[:3]}  # nothing after the gates
    assert result.client.usage.calls == 0 and result.client.misses == {}  # no model call
    assert not (result.run_dir / "clean").exists()
    assert not (result.run_dir / "mapping").exists()
    card = Scorecard.model_validate_json((result.run_dir / "scorecard.json").read_text())
    assert card.status == RunStatus.FAILED and card.rows_mapped == 0 and card.rows_clean == 0
    assert all(leg.status == LegStatus.NOT_RUN and leg.not_run_reason for leg in card.tie_out)
    assert json.loads((result.run_dir / "rts_coverage.json").read_text()) == {"cells": []}
    return found


def test_example_5_truncation_blocks_with_both_counts(truncated: RunResult) -> None:
    found = assert_stopped_at_the_gates(truncated, "CMP-001")
    blocker = next(r for r in found if r.rule_id == "CMP-001")
    assert "expected 2680 rows, received 2574" in blocker.message
    m = Manifest.model_validate_json((truncated.run_dir / "manifest.json").read_text())
    assert m.status_reason is not None and "2680" in m.status_reason and "2574" in m.status_reason
    crm = next(f for f in m.inputs if f.source == "crm")
    assert (crm.rows_expected, crm.rows_received) == (2680, 2574)
    report = (truncated.run_dir / "report.html").read_text()
    assert 'class="banner FAILED"' in report and "2,680" in report and "2,574" in report


def test_example_6_ssn_blocks_and_no_value_appears_anywhere(ssn: RunResult) -> None:
    assert_stopped_at_the_gates(ssn, "SSN-001")
    truth = json.loads((FIXTURES / "agency-a-ssn" / "ground_truth.json").read_text())
    values = next(d for d in truth["defects"] if d["defect_type"] == "ssn_column")
    values = values["injected_values"]["values"]
    assert len(values) == 25
    files = [p for p in ssn.run_dir.rglob("*") if p.is_file()]
    assert len(files) >= 9
    for path in files:
        text = path.read_bytes().decode("utf-8", errors="replace")
        leaked = [v for v in values if v in text or v.replace("-", "") in text]
        assert leaked == [], path


def _copy_drop(tmp: Path, keep: set[str]) -> Path:
    drop = tmp / "drop"
    drop.mkdir()
    shutil.copy(FIXTURES / "agency-a" / "drop" / "manifest.json", drop)
    for name in keep:
        shutil.copy(FIXTURES / "agency-a" / "drop" / name, drop)
    return drop


def test_a_drop_without_a_manifest_gets_a_plain_error(tmp_path: Path) -> None:
    (tmp_path / "drop").mkdir()
    with pytest.raises(RunRefused, match="has no manifest.json"):
        run(RunOptions(drop=tmp_path / "drop", out=tmp_path / "run"))
    result = CliRunner().invoke(
        app, ["run", "--in", str(tmp_path / "drop"), "--out", str(tmp_path / "r")]
    )
    assert result.exit_code == 2 and "has no manifest.json" in result.output
    assert not (tmp_path / "r").exists()


@pytest.mark.parametrize(
    "keep", [set(), {"agent_roster.xlsx", "commissions_harborline.xlsx", "enrollment_export.csv"}]
)
def test_a_drop_without_the_crm_fails_through_map_003(tmp_path: Path, keep: set[str]) -> None:
    """#59: an empty drop or one missing the CRM has no book to load, so it cannot pass."""
    result = run(RunOptions(drop=_copy_drop(tmp_path, keep), out=tmp_path / "run"))
    check_run_dir(result.run_dir)
    found = records(result.run_dir)
    assert result.status == RunStatus.FAILED
    missing = {r.field for r in found if r.rule_id == "MAP-003"}
    assert {"client_id", "policy_id", "dob", "effective_date"} <= missing
    assert any(r.rule_id == "CMP-002" and r.source == "crm" for r in found)
    assert not (result.run_dir / "clean").exists()


def test_cli_run_writes_the_run_and_exits_1_when_failed(tmp_path: Path) -> None:
    drop = str(FIXTURES / "agency-a-truncated" / "drop")
    args = ["run", "--in", drop, "--out", str(tmp_path / "t"), "--jev", "off"]
    first = CliRunner().invoke(app, [*args, "--as-of", "2026-10-01T09:00:00Z"])
    assert first.exit_code == 1 and first.output.startswith("FAILED:")
    again = CliRunner().invoke(app, args)
    assert again.exit_code == 2 and "--overwrite" in again.output
    assert CliRunner().invoke(app, [*args, "--overwrite"]).exit_code == 1
    assert CliRunner().invoke(app, [*args, "--jev", "live"]).exit_code == 2


def test_the_clean_world_gives_zero_exceptions_above_info(clean_world: RunResult) -> None:
    check_run_dir(clean_world.run_dir)
    loud = [(r.rule_id, r.message) for r in clean_world.records if r.severity != Severity.INFO]
    assert loud == []
    assert clean_world.status == RunStatus.PASSED
    assert clean_world.client.misses == {}  # every mapping question has a recording
    card = Scorecard.model_validate_json((clean_world.run_dir / "scorecard.json").read_text())
    assert card.rows_clean == card.rows_mapped


def test_the_spend_cap_switches_jev_off_and_the_run_completes(tmp_path: Path) -> None:
    """A tiny budget trips on the first answer; the rest goes to a person, as the manifest says."""
    from decimal import Decimal

    from agency_schema.outputs import JevMode
    from intake.run.jev import RunJevClient

    client = RunJevClient(mode=JevMode.REPLAY, api_key=None, budget_usd=Decimal("0.000001"))
    drop = FIXTURES / "agency-a" / "drop"
    result = run(RunOptions(drop=drop, out=tmp_path / "capped", client=client))
    check_run_dir(result.run_dir)
    m = Manifest.model_validate_json((result.run_dir / "manifest.json").read_text())
    assert m.budget_tripped is True and m.jev.mode == "replay" and m.jev.calls == 1
    assert result.status == RunStatus.PASSED_WITH_WARNINGS
    assert any(r.rule_id == "MAP-002" and "budget_tripped" in r.message for r in result.records)

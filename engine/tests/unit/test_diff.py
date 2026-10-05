"""`intake diff`: what changed between two runs, in plain language (PR 16)."""

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from intake.cli import app

FIXTURES = Path(__file__).parents[3] / "fixtures"
runner = CliRunner()


def diff(a: Path, b: Path) -> str:
    result = runner.invoke(app, ["diff", str(a), str(b)])
    assert result.exit_code == 0, result.output
    return result.output


def test_a_run_against_itself_changes_nothing() -> None:
    out = diff(FIXTURES / "sample-run", FIXTURES / "sample-run")
    assert "Status: Passed with warnings, unchanged." in out
    assert "New exceptions: none." in out
    assert "Resolved exceptions: none." in out
    assert "Unchanged exceptions: 13." in out
    assert "A. Book vs statement: 1 difference, $24.50, unchanged." in out


def test_partial_run_shows_the_leg_that_stopped_running() -> None:
    out = diff(FIXTURES / "sample-run", FIXTURES / "sample-run-partial")
    assert "Comparing sample-run (before) with sample-run-partial (after)." in out
    assert "Warning: 6 to 5 (down 1)" in out
    assert "Error: 4 to 4" in out
    assert "Resolved exceptions: 1.\n  TIE-004: 1" in out
    assert "New exceptions: none." in out
    assert "C. CRM vs statement: 1 difference, $0.00, now not checked" in out
    assert "no policy status column" in out
    assert "B. Statement vs book: 1 difference, $61.05, unchanged." in out


def test_one_added_exception_is_new(tmp_path: Path) -> None:
    run = tmp_path / "sample-run-plus"
    shutil.copytree(FIXTURES / "sample-run", run)
    lines = (run / "exceptions.jsonl").read_text().splitlines()
    added = json.loads(lines[2])  # DOB-002 on row 118
    added.update(id="EX-000014", row_number=640, raw_hash="ab" * 32)
    added["lineage"].update(row_number=640, raw_hash="ab" * 32)
    (run / "exceptions.jsonl").write_text("\n".join([*lines, json.dumps(added)]) + "\n")
    out = diff(FIXTURES / "sample-run", run)
    assert "New exceptions: 1.\n  DOB-002: 1" in out
    assert "Error: 4 to 5 (up 1)" in out
    assert "Resolved exceptions: none." in out
    assert "Unchanged exceptions: 13." in out


def test_tie_out_dollar_changes_say_up_or_down(tmp_path: Path) -> None:
    run = tmp_path / "run"
    shutil.copytree(FIXTURES / "sample-run", run)
    card = run / "scorecard.json"
    data = json.loads(card.read_text())
    data["tie_out"][0]["variance_dollars"] = "30.00"
    card.write_text(json.dumps(data))
    out = diff(FIXTURES / "sample-run", run)
    assert "A. Book vs statement: 1 difference, $24.50, now 1 difference, $30.00 (up $5.50)." in out


def test_a_folder_that_is_not_a_run_is_refused(tmp_path: Path) -> None:
    result = runner.invoke(app, ["diff", str(FIXTURES / "sample-run"), str(tmp_path)])
    assert result.exit_code == 1
    assert "manifest.json" in result.output

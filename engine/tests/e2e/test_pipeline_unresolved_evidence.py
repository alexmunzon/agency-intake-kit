"""M1: incomplete identity evidence remains reviewable without becoming load-ready."""

import json
from pathlib import Path

import pytest

from agency_schema.outputs import LegStatus, RunStatus, Scorecard
from intake.run.pipeline import RunOptions, run


def _drop(path: Path, crm: str | None) -> Path:
    path.mkdir()
    files = [
        {
            "source": "statement_harborline",
            "file_name": "statement_harborline.csv",
            "sheet": None,
            "rows": 1,
        }
    ]
    (path / "statement_harborline.csv").write_text(
        "Line,Period,Member ID,Member Name,DOB,Policy,Writing Agent,Type,Paid,Commission\n"
        "1,202601,MBR-001,Sample Person,1950-01-01,POL-001,AGT-001,Payment,25.00,5.00\n"
    )
    if crm is not None:
        files.append({"source": "crm", "file_name": "crm_export.csv", "sheet": None, "rows": 3})
        (path / "crm_export.csv").write_text(crm)
    (path / "manifest.json").write_text(json.dumps({"files": files}))
    return path


def _evidence(run_dir: Path) -> list[dict[str, object]]:
    path = run_dir / "unresolved_evidence.jsonl"
    assert path.is_file()
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_absent_crm_keeps_summary_and_all_received_rows_as_lineage_only(tmp_path: Path) -> None:
    drop = _drop(tmp_path / "drop", None)
    result = run(RunOptions(drop=drop, out=tmp_path / "run"))
    cases = _evidence(result.run_dir)
    assert result.status == RunStatus.FAILED and not (result.run_dir / "clean").exists()
    assert [(c["source"], c["reason"], c["lineage"]) for c in cases] == [
        ("crm", "crm_absent", None),
        ("statement_harborline", "crm_absent", cases[1]["lineage"]),
    ]
    assert cases[1]["lineage"]["row_number"] == 2  # type: ignore[index]
    assert all(c["schema_version"] == 1 and c["run_id"] == result.run_dir.name for c in cases)
    artifact = (result.run_dir / "unresolved_evidence.jsonl").read_text()
    assert "MBR-001" not in artifact and "25.00" not in artifact and "5.00" not in artifact
    card = Scorecard.model_validate_json((result.run_dir / "scorecard.json").read_text())
    assert all(leg.status == LegStatus.NOT_RUN for leg in card.tie_out)


@pytest.mark.parametrize(
    ("dob_header", "values", "expected"),
    [
        (
            "",
            ["1950-01-01", "", "bad"],
            [("dob_column_missing", 2), ("dob_column_missing", 3), ("dob_column_missing", 4)],
        ),
        ("Mbr DOB", ["1950-01-01", "", "bad"], [("dob_blank", 3), ("dob_malformed", 4)]),
    ],
)
def test_present_crm_distinguishes_missing_column_blank_and_malformed(
    tmp_path: Path, dob_header: str, values: list[str], expected: list[tuple[str, int]]
) -> None:
    headers = "Client ID,Client Name,Policy #,Eff Date" + (f",{dob_header}" if dob_header else "")
    rows = [
        f"C-00{i},Synthetic Person {i},P-00{i},2026-01-01" + (f",{value}" if dob_header else "")
        for i, value in enumerate(values, 1)
    ]
    crm = "\n".join([headers, *rows, ""])
    result = run(RunOptions(drop=_drop(tmp_path / "drop", crm), out=tmp_path / "run"))
    cases = [case for case in _evidence(result.run_dir) if case["source"] == "crm"]
    assert [(case["reason"], case["lineage"]["row_number"]) for case in cases] == expected  # type: ignore[index]
    assert all("Synthetic Person" not in json.dumps(case) for case in cases)


@pytest.mark.parametrize("fixture_name", ["truncated", "ssn"])
def test_raw_blocker_leaves_unresolved_artifact_empty(request, fixture_name: str) -> None:
    blocked = request.getfixturevalue(fixture_name)
    path = blocked.run_dir / "unresolved_evidence.jsonl"
    assert path.is_file() and path.read_text() == ""

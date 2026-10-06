"""Statement dimensions annotate every received amount without inventing identity."""

import json

import pytest
from pydantic import ValidationError

from agency_schema.outputs import JevMode
from intake.ingest import IngestResult
from intake.readers import table_from_rows
from intake.run.pipeline import RunOptions, run
from intake.run.statement_groups import StatementDimensions, collect_statement_groups
from intake.run.statement_totals import collect_statement_totals


def collect(tmp_path, headers, rows, blocked=False):
    table = table_from_rows(
        [headers, *rows],
        source="statement_harborline",
        source_file="statement.csv",
        sheet=None,
        run_id="run-a",
        mapping_version="unmapped",
    )
    raw = IngestResult((table,), (), True)
    totals = collect_statement_totals(raw, tmp_path / "drop", "run-a", blocked)
    return totals, collect_statement_groups(raw, tmp_path / "drop", totals)


def test_dimensions_keep_every_amount_line_and_exact_lineage(tmp_path):
    totals, groups = collect(
        tmp_path,
        ["Commission", "Carrier Name", "Period"],
        [
            ["25.00", " Harborline ", " 2026-09 "],
            ["-25.00", "Unknown", "2026-10"],
            ["bad", "", "2026-13"],
        ],
    )
    assert [line.lineage for line in groups.lines] == [line.lineage for line in totals.lines]
    assert [(line.carrier, line.statement_period) for line in groups.lines] == [
        ("Harborline", "2026-09"),
        ("Unknown", "2026-10"),
        (None, None),
    ]
    assert totals.total_paid == "0.00" and totals.excluded_line_count == 1
    assert groups.model_dump().keys() == {"schema_version", "run_id", "lines"}


@pytest.mark.parametrize("period", ["", "2026-9", "2026-09-01", "0000-01", "2026-00", "bad"])
def test_missing_and_invalid_dimensions_are_unknown_not_source_inferred(tmp_path, period):
    _, groups = collect(tmp_path, ["Commission", "Period"], [["1.00", period]])
    assert groups.lines[0].carrier is None
    assert groups.lines[0].statement_period is None


def test_ambiguous_and_saved_manual_ignore_suppress_dimension_fallback(tmp_path):
    _, ambiguous = collect(
        tmp_path,
        ["Amount", "Carrier", "Carrier Name", "Period", "Statement Month"],
        [["1", "A", "B", "2026-09", "2026-10"]],
    )
    assert (ambiguous.lines[0].carrier, ambiguous.lines[0].statement_period) == (None, None)
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    (mapping / "statement_harborline.yaml").write_text(
        "source: statement_harborline\nentries:\n"
        + "".join(
            f"- {{header: {header}, table: null, field: null, method: manual, "
            "confidence: null, decided_at: '2026-10-05T00:00:00Z'}\n"
            for header in ("Carrier", "Period")
        )
    )
    _, ignored = collect(tmp_path, ["Amount", "Carrier", "Period"], [["1", "A", "2026-09"]])
    assert (ignored.lines[0].carrier, ignored.lines[0].statement_period) == (None, None)


def test_blocked_and_empty_artifacts_expose_no_dimensions(tmp_path):
    for rows, blocked in [([], False), ([["1", "A"]], True)]:
        _, groups = collect(tmp_path, ["Amount", "Carrier"], rows, blocked)
        assert groups.lines == ()


def test_dimension_model_refuses_noncanonical_claims(tmp_path):
    _, groups = collect(tmp_path, ["Amount"], [["1"]])
    for patch in [{"carrier": " "}, {"carrier": " A "}, {"statement_period": "2026-13"}]:
        with pytest.raises(ValidationError):
            StatementDimensions.model_validate({**groups.lines[0].model_dump(), **patch})


def test_pipeline_emits_companion_without_changing_run_gates(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "statement.csv").write_text("Amount,Carrier,Period\n1.00,Harborline,2026-09\n")
    (drop / "manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "source": "statement_harborline",
                        "file_name": "statement.csv",
                        "sheet": None,
                        "rows": 1,
                    }
                ]
            }
        )
    )
    result = run(RunOptions(drop=drop, out=tmp_path / "run", jev_mode=JevMode.OFF))
    groups = json.loads((result.run_dir / "statement_groups.json").read_text())
    totals = json.loads((result.run_dir / "statement_totals.json").read_text())
    assert groups["lines"][0]["lineage"] == totals["lines"][0]["lineage"]
    assert groups["lines"][0]["carrier"] == "Harborline"
    assert result.status.value == "FAILED" and not (result.run_dir / "clean").exists()
    assert json.loads((result.run_dir / "manifest.json").read_text())["jev"]["calls"] == 0


def test_saved_nonalias_dimension_decisions_are_read_only(tmp_path):
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    path = mapping / "statement_harborline.yaml"
    content = "source: statement_harborline\nentries:\n" + "".join(
        f"- {{header: {header}, table: commission_lines, field: {field}, method: manual, "
        "confidence: null, decided_at: '2026-10-05T00:00:00Z'}\n"
        for header, field in [("Company", "carrier"), ("Month label", "statement_period")]
    )
    path.write_text(content)
    _, groups = collect(tmp_path, ["Amount", "Company", "Month label"], [["1", "A", "2026-09"]])
    assert (groups.lines[0].carrier, groups.lines[0].statement_period) == ("A", "2026-09")
    assert path.read_text() == content


def test_raw_blocker_has_empty_companion_and_crm_present_has_no_companion(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "statement.csv").write_text("Amount,Carrier,Period\n1,A,2026-09\n")
    files = [
        {"source": "statement_harborline", "file_name": "statement.csv", "sheet": None, "rows": 2}
    ]
    (drop / "manifest.json").write_text(json.dumps({"files": files}))
    blocked = run(RunOptions(drop=drop, out=tmp_path / "blocked", jev_mode=JevMode.OFF))
    assert json.loads((blocked.run_dir / "statement_groups.json").read_text())["lines"] == []
    assert (
        json.loads((blocked.run_dir / "statement_totals.json").read_text())["status"] == "BLOCKED"
    )
    (drop / "crm.csv").write_text("First Name,Last Name\n")
    files.append({"source": "crm", "file_name": "crm.csv", "sheet": None, "rows": 0})
    (drop / "manifest.json").write_text(json.dumps({"files": files}))
    present = run(RunOptions(drop=drop, out=tmp_path / "crm-present", jev_mode=JevMode.OFF))
    assert not (present.run_dir / "statement_groups.json").exists()
    assert not (present.run_dir / "statement_totals.json").exists()

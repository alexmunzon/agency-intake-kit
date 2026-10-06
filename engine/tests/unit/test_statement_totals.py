"""Received statement money remains reviewable when the CRM book is absent."""

import json

import pytest
from pydantic import ValidationError

from agency_schema.outputs import JevMode
from intake.ingest import IngestResult
from intake.readers import table_from_rows
from intake.run.pipeline import RunOptions, run
from intake.run.statement_totals import StatementAmount, collect_statement_totals


def statement(headers: list[str], rows: list[list[str]], source_file: str = "statement.csv"):
    return table_from_rows(
        [headers, *rows],
        source="statement_harborline",
        source_file=source_file,
        sheet=None,
        run_id="run-a",
        mapping_version="unmapped",
    )


def collect(tmp_path, *tables, blocked=False):
    return collect_statement_totals(
        IngestResult(tuple(tables), (), True), tmp_path / "drop", "run-a", blocked
    )


def test_signed_rows_count_once_and_preserve_raw_lineage(tmp_path):
    table = statement(
        ["Commission", "Member Name"], [["25.00", "Private A"], ["(5.00)", "Private B"]]
    )
    result = collect(tmp_path, table)
    assert (result.status, result.reason, result.valid_line_count, result.excluded_line_count) == (
        "AVAILABLE",
        None,
        2,
        0,
    )
    assert result.total_paid == "20.00"
    assert [line.amount for line in result.lines] == ["25.00", "-5.00"]
    assert [line.lineage.row_number for line in result.lines] == [2, 3]
    assert all(line.lineage.mapping_version == "unmapped" for line in result.lines)
    assert "Private" not in result.model_dump_json()


def test_partial_and_zero_valid_are_distinct_from_true_zero(tmp_path):
    table = statement(["Commission"], [[""], ["bad"], ["0.001"], ["1e+999999999"]])
    result = collect(tmp_path, table)
    assert (result.status, result.reason, result.total_paid) == ("PARTIAL", "excluded_rows", None)
    assert [line.reason for line in result.lines] == [
        "amount_blank",
        "amount_malformed",
        "amount_malformed",
        "amount_malformed",
    ]
    assert (result.valid_line_count, result.excluded_line_count) == (0, 4)
    zero = collect(tmp_path, statement(["Commission"], [["1.00"], ["-1.00"]]))
    assert (zero.status, zero.total_paid) == ("AVAILABLE", "0.00")


def test_unavailable_and_raw_blocked_do_not_claim_zero(tmp_path):
    missing = collect(tmp_path)
    empty = collect(tmp_path, statement(["Commission"], []))
    blocked = collect(tmp_path, statement(["Commission"], [["25.00"]]), blocked=True)
    assert (missing.status, missing.reason) == ("UNAVAILABLE", "no_statements")
    assert (empty.status, empty.reason) == ("UNAVAILABLE", "no_statement_rows")
    assert (blocked.status, blocked.reason) == ("BLOCKED", "raw_gate_blocked")
    for result in (missing, empty, blocked):
        assert (
            result.lines,
            result.total_paid,
            result.valid_line_count,
            result.excluded_line_count,
        ) == (
            (),
            None,
            0,
            0,
        )


def test_saved_manual_ignore_and_ambiguous_headers_exclude_all_rows(tmp_path):
    ambiguous = collect(tmp_path, statement(["Amount", "Commission"], [["25.00", "5.00"]]))
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    (mapping / "statement_harborline.yaml").write_text(
        "source: statement_harborline\nentries:\n"
        "- {header: Commission, table: null, field: null, method: manual, "
        "confidence: null, decided_at: '2026-10-05T00:00:00Z'}\n"
    )
    ignored = collect(tmp_path, statement(["Commission"], [["25.00"]]))
    assert [line.reason for line in ignored.lines] == ["amount_mapping_unavailable"]
    assert [line.reason for line in ambiguous.lines] == ["amount_mapping_unavailable"]


def test_duplicate_physical_row_is_refused(tmp_path):
    table = statement(["Commission"], [["25.00"]])
    with pytest.raises(ValueError, match="duplicate statement row"):
        collect(tmp_path, table, table)


def test_invalid_claimed_amount_and_malformed_saved_mapping_refuse(tmp_path):
    lineage = statement(["Commission"], [["25.00"]]).frame["lineage"][0]
    for amount in ("bad", "1.001", "10000000000.00"):
        with pytest.raises(ValidationError):
            StatementAmount(
                source="statement_harborline", lineage=lineage, amount=amount, reason="valid"
            )
    with pytest.raises(ValidationError):
        StatementAmount(source="crm", lineage=lineage, amount="25.00", reason="valid")
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    (mapping / "statement_harborline.yaml").write_text("bad: mapping\n")
    with pytest.raises(ValidationError):
        collect(tmp_path, statement(["Commission"], [["25.00"]]))


def test_absent_book_pipeline_writes_separate_totals_without_running_tieout(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "statement.csv").write_text(
        "Commission,Member Name\n25.00,Private A\n(5.00),Private B\n"
    )
    (drop / "manifest.json").write_text(
        json.dumps(
            {
                "files": [
                    {
                        "source": "statement_harborline",
                        "file_name": "statement.csv",
                        "sheet": None,
                        "rows": 2,
                    }
                ]
            }
        )
    )
    result = run(RunOptions(drop=drop, out=tmp_path / "run", jev_mode=JevMode.OFF))
    artifact = json.loads((result.run_dir / "statement_totals.json").read_text())
    assert result.status.value == "FAILED" and not (result.run_dir / "clean").exists()
    assert not (result.run_dir / "mapping").exists()
    assert json.loads((result.run_dir / "manifest.json").read_text())["jev"]["calls"] == 0
    assert (artifact["status"], artifact["total_paid"], artifact["valid_line_count"]) == (
        "AVAILABLE",
        "20.00",
        2,
    )
    assert [line["lineage"]["row_number"] for line in artifact["lines"]] == [2, 3]
    assert "Private" not in json.dumps(artifact)
    card = json.loads((result.run_dir / "scorecard.json").read_text())
    assert all(leg["status"] == "NOT_RUN" for leg in card["tie_out"])
    assert all(
        json.loads((result.run_dir / f"tie_out/totals_by_{group}.json").read_text())["status"]
        == "NOT_RUN"
        for group in ("carrier", "agent")
    )

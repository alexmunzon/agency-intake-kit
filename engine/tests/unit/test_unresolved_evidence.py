"""Small synthetic cases for the separate unresolved-evidence artifact."""

from datetime import UTC, datetime

import pytest

from agency_schema.lineage import Lineage
from intake.ingest import IngestResult
from intake.mapping.headers import map_table
from intake.readers import table_from_rows
from intake.run.canonicalize import MappedSource
from intake.run.unresolved_evidence import (
    UnresolvedEvidence,
    collect_unresolved_evidence,
    serialize_unresolved_evidence,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def source(tmp_path, name: str, header: list[str], rows: list[list[str]]):
    table = table_from_rows(
        [header, *rows],
        source=name,
        source_file=f"{name}.csv",
        sheet=None,
        run_id="run-a",
        mapping_version="raw",
    )
    return table, MappedSource(table, map_table(table, tmp_path, NOW))


def test_absent_crm_keeps_received_row_refs_and_summary(tmp_path):
    table, _ = source(tmp_path, "statement_x", ["Line"], [["1"], ["2"]])
    cases = collect_unresolved_evidence(IngestResult((table,), (), True), (), "run-a", False)
    assert [(c.source, c.reason, c.lineage.row_number if c.lineage else None) for c in cases] == [
        ("crm", "crm_absent", None),
        ("statement_x", "crm_absent", 2),
        ("statement_x", "crm_absent", 3),
    ]
    assert "Line" not in serialize_unresolved_evidence(cases, "run-a")


def test_dob_reasons_keep_exact_row_and_mapping_lineage(tmp_path):
    table, mapped = source(tmp_path, "crm", ["Mbr DOB"], [[""], ["not-a-date"], ["01/02/1950"]])
    assert (mapped.targets()["Mbr DOB"].table, mapped.targets()["Mbr DOB"].field) == (
        "clients",
        "dob",
    )
    cases = collect_unresolved_evidence(IngestResult((table,), (), True), (mapped,), "run-a", False)
    assert [c.reason for c in cases] == ["dob_blank", "dob_malformed"]
    assert [c.lineage.row_number for c in cases if c.lineage] == [2, 3]
    assert cases[0].lineage.raw_hash == table.frame["lineage"][0]["raw_hash"]
    assert cases[0].lineage.mapping_version == mapped.result.version
    assert "not-a-date" not in serialize_unresolved_evidence(cases, "run-a")


def test_missing_dob_column_marks_each_row_even_when_mapping_blocks(tmp_path):
    table, mapped = source(tmp_path, "crm", ["Name"], [["A"], ["B"]])
    cases = collect_unresolved_evidence(IngestResult((table,), (), True), (mapped,), "run-a", False)
    assert [c.reason for c in cases] == ["dob_column_missing"] * 2
    assert [c.lineage.row_number for c in cases if c.lineage] == [2, 3]


def test_raw_blocker_returns_no_case(tmp_path):
    table, mapped = source(tmp_path, "crm", ["Mbr DOB"], [["bad"]])
    raw = IngestResult((table,), (), True)
    assert collect_unresolved_evidence(raw, (mapped,), "run-a", True) == ()


def test_serializer_deterministic_and_rejects_duplicate_or_wrong_run():
    summary = UnresolvedEvidence(run_id="run-a", source="crm", reason="crm_absent", lineage=None)
    row = Lineage(
        source_file="x.csv",
        sheet=None,
        row_number=10,
        raw_hash="0" * 64,
        run_id="run-a",
        mapping_version="raw",
    )
    other = UnresolvedEvidence(run_id="run-a", source="x", reason="crm_absent", lineage=row)
    assert serialize_unresolved_evidence(
        (other, summary), "run-a"
    ) == serialize_unresolved_evidence((summary, other), "run-a")
    with pytest.raises(ValueError, match="duplicate"):
        serialize_unresolved_evidence((summary, summary), "run-a")
    with pytest.raises(ValueError, match="run_id"):
        serialize_unresolved_evidence((summary,), "run-b")
    with pytest.raises(ValueError, match="CRM absence"):
        UnresolvedEvidence(run_id="run-a", source="x", reason="crm_absent", lineage=None)

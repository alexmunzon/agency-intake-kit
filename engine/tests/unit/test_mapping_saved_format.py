"""Saved review fields and the reuse rule: a saved decision is reused only for the same format."""

from datetime import UTC, datetime
from pathlib import Path

import polars as pl

from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.headers import format_changes, map_headers
from intake.mapping.store import (
    MappingEntry,
    SourceMapping,
    dump_mapping,
    load_mapping,
    mapping_path,
    parse_mapping,
    save_mapping,
)
from intake.readers import RawTable

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)
HEADERS = ["Client ID", "Mbr DOB", "Cust Ref"]
OLD_YAML = """source: crm
entries:
- header: Client ID
  table: clients
  field: client_id
  method: synonym
  confidence: 1.0
  decided_at: '2026-10-01T09:00:00+00:00'
- header: Cust Ref
  table: null
  field: null
  method: manual
  confidence: null
  decided_at: '2026-10-01T09:00:00+00:00'
"""


def _manual(header: str, field: str | None, fingerprint: str | None) -> SourceMapping:
    table, _, name = field.partition(".") if field else (None, "", None)
    entry = MappingEntry(
        header=header,
        table=table,
        field=name or None,
        method="manual",
        confidence=None,
        decided_at=NOW.isoformat(),
        reviewer="Pat Reviewer",
        suggested_field="clients.email",
        suggested_origin="jev_replay",
    )
    return SourceMapping(source="crm", format_fingerprint=fingerprint, entries=(entry,))


def test_old_yaml_without_review_fields_round_trips_byte_for_byte(tmp_path: Path) -> None:
    mapping = parse_mapping(OLD_YAML)
    assert mapping.format_fingerprint is None
    assert dump_mapping(mapping) == OLD_YAML
    save_mapping(tmp_path, mapping)
    assert mapping_path(tmp_path, "crm").read_text() == OLD_YAML


def test_review_fields_round_trip(tmp_path: Path) -> None:
    mapping = _manual("Cust Ref", "clients.client_id", format_fingerprint(HEADERS))
    save_mapping(tmp_path, mapping)
    text = mapping_path(tmp_path, "crm").read_text()
    assert "format_fingerprint: " in text and "reviewer: Pat Reviewer" in text
    assert load_mapping(tmp_path, "crm") == mapping
    assert dump_mapping(parse_mapping(text)) == text


def test_a_matching_fingerprint_reuses_the_saved_decision(tmp_path: Path) -> None:
    save_mapping(tmp_path, _manual("Cust Ref", "clients.email", format_fingerprint(HEADERS)))
    result = map_headers("crm", None, HEADERS, tmp_path, NOW)
    entry = result.mapping.entry("Cust Ref")
    assert entry is not None and entry.method == "manual" and entry.field == "email"
    assert result.mapping.format_fingerprint == format_fingerprint(HEADERS)
    assert format_changes([_table(HEADERS)], tmp_path) == []


def test_a_saved_file_with_no_fingerprint_is_reused_as_before(tmp_path: Path) -> None:
    save_mapping(tmp_path, _manual("Cust Ref", "clients.email", None))
    entry = map_headers("crm", None, HEADERS, tmp_path, NOW).mapping.entry("Cust Ref")
    assert entry is not None and entry.method == "manual"
    assert format_changes([_table(HEADERS)], tmp_path) == []


def test_a_changed_format_is_not_reused_and_raises_map_005(tmp_path: Path) -> None:
    saved = _manual("Cust Ref", "clients.email", format_fingerprint(["Client ID", "Cust Ref"]))
    saved = saved.model_copy(
        update={"entries": (*saved.entries, *parse_mapping(OLD_YAML).entries[:1])}
    )
    save_mapping(tmp_path, saved)
    new = ["Client ID", "Mbr DOB", "Cust Ref", "Lead Source"]
    (record,) = format_changes([_table(new)], tmp_path)  # reads the saved folder only
    result = map_headers("crm", None, new, tmp_path, NOW)
    entry = result.mapping.entry("Cust Ref")
    assert entry is not None and entry.method == "unmapped"  # falls through to synonyms, then Jev
    assert all(e.method != "manual" for e in result.mapping.entries)
    assert record.rule_id == "MAP-005" and record.severity.value == "WARNING"
    assert "Export format changed since mappings were saved" in record.message
    assert '"Mbr DOB"' in record.message and '"Lead Source"' in record.message


def test_format_changes_with_no_saved_folder_is_empty(tmp_path: Path) -> None:
    assert format_changes([_table(HEADERS)], tmp_path / "absent") == []


def _table(headers: list[str]) -> RawTable:
    frame = pl.DataFrame({h: ["x"] for h in headers})
    return RawTable(
        source="crm",
        source_file="crm.csv",
        sheet=None,
        frame=frame,
        header_row=1,
        encoding="utf-8",
        delimiter=",",
        dropped_rows=0,
        total_row_count=None,
        exceptions=(),
    )

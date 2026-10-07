"""The adapter consumes pipeline output, not an invented snapshot format."""

import csv
import json
import shutil
from pathlib import Path

import pytest

from intake.adapters.contract import Packet, canonical_json, verify
from intake.adapters.export import export_run
from intake.run.pipeline import RunResult


def test_actual_clean_output_is_deterministic(clean_world: RunResult) -> None:
    root = clean_world.run_dir
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    assert len(packet.clients) == 2000
    assert packet.policies
    assert all(c.provenance.run_id == root.name for c in packet.clients)
    assert canonical_json(packet) == canonical_json(
        export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    )
    assert Packet.model_validate_json(canonical_json(packet)) == packet
    assert '"notes"' not in canonical_json(packet)
    verify(root, packet)


def test_failed_run_preserves_blocker(truncated: RunResult) -> None:
    packet = export_run(truncated.run_dir, agency_id="synthetic-a", data_kind="synthetic")
    assert not packet.clients and not packet.policies
    assert any(i.code == "INTAKE_FAILED" for i in packet.issues)
    assert any(i.code == "CMP-001" for i in packet.issues)


def test_stale_artifact_is_refused(clean_world: RunResult, tmp_path: Path) -> None:
    import shutil

    root = tmp_path / "copy"
    shutil.copytree(clean_world.run_dir, root)
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    with (root / "clean/clients.csv").open("a") as f:
        f.write("\n")
    with pytest.raises(ValueError, match="stale"):
        verify(root, packet)


def test_invalid_clean_row_keeps_an_artifact_reference(tmp_path: Path) -> None:
    import shutil

    source = Path(__file__).resolve().parents[3] / "fixtures/integration-v1/intake-run"
    root = tmp_path / "run"
    shutil.copytree(source, root)
    p = root / "clean/clients.csv"
    text = p.read_text()
    p.write_text(text.replace("2001-01-02", "not-a-date", 1))
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    assert len(packet.clients) == 7
    assert any(i.code == "INVALID_CLEAN_ROW" and i.artifact_row == 1 for i in packet.issues)
    assert any(i.code == "MISSING_CLIENT" for i in packet.issues)


def test_duplicate_csv_header_is_not_silently_used(tmp_path: Path) -> None:
    import shutil

    source = Path(__file__).resolve().parents[3] / "fixtures/integration-v1/intake-run"
    root = tmp_path / "run"
    shutil.copytree(source, root)
    p = root / "clean/clients.csv"
    p.write_text(p.read_text().replace("first_name,last_name", "first_name,first_name", 1))
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    assert not packet.clients
    assert any(i.code == "INVALID_CLEAN_COLUMNS" for i in packet.issues)


def _fixture_run(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parents[3] / "fixtures/integration-v1/intake-run"
    root = tmp_path / "run"
    shutil.copytree(source, root)
    return root


@pytest.mark.parametrize("table", ["clients", "policies"])
def test_surplus_csv_cell_is_visible_and_excluded(tmp_path: Path, table: str) -> None:
    root = _fixture_run(tmp_path)
    path = root / f"clean/{table}.csv"
    lines = path.read_text().splitlines()
    lines[1] += ",unexpected-cell"
    path.write_text("\n".join(lines) + "\n")
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    rows = getattr(packet, table)
    assert len(rows) == len(lines) - 2
    assert all(row.provenance.artifact_row != 1 for row in rows)
    assert any(
        issue.code == "INVALID_CLEAN_ROW"
        and issue.artifact == f"clean/{table}.csv"
        and issue.artifact_row == 1
        for issue in packet.issues
    )


@pytest.mark.parametrize("table", ["clients", "policies"])
def test_missing_nullable_csv_cell_is_visible_and_excluded(tmp_path: Path, table: str) -> None:
    root = _fixture_run(tmp_path)
    path = root / f"clean/{table}.csv"
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        original_headers = reader.fieldnames
        rows = list(reader)
    assert original_headers is not None
    headers = [key for key in original_headers if key != "lineage_sheet"] + ["lineage_sheet"]
    assert rows[0]["lineage_sheet"] == ""
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    lines = path.read_text().splitlines()
    assert lines[1].endswith(",")
    lines[1] = lines[1][:-1]
    path.write_text("\n".join(lines) + "\n")
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    exported = getattr(packet, table)
    assert len(exported) == len(rows) - 1
    assert all(row.provenance.artifact_row != 1 for row in exported)
    assert any(
        issue.code == "INVALID_CLEAN_ROW"
        and issue.artifact == f"clean/{table}.csv"
        and issue.artifact_row == 1
        for issue in packet.issues
    )


def test_malformed_csv_quoting_is_visible(tmp_path: Path) -> None:
    root = _fixture_run(tmp_path)
    path = root / "clean/clients.csv"
    header = path.read_text().splitlines()[0]
    path.write_text(header + '\n"unterminated\n')
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    assert not packet.clients
    assert any(
        issue.code == "INVALID_CLEAN_ROW"
        and issue.artifact == "clean/clients.csv"
        and issue.artifact_row == 1
        for issue in packet.issues
    )


def test_original_csv_provenance_and_notes_exclusion(tmp_path: Path) -> None:
    root = _fixture_run(tmp_path)
    path = root / "clean/clients.csv"
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        clients = list(reader)
    assert headers is not None
    clients[0]["notes"] = "private-notes-sentinel"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(clients)
    review_path = root / "exceptions.jsonl"
    evidence = [json.loads(line) for line in review_path.read_text().splitlines()]
    evidence[0]["message"] = "private-review-message-sentinel"
    review_path.write_text("".join(json.dumps(row) + "\n" for row in evidence))
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    for table, rows in (("clients", packet.clients), ("policies", packet.policies)):
        with (root / f"clean/{table}.csv").open(newline="") as stream:
            source_rows = list(csv.DictReader(stream))
        for exported in rows:
            provenance = exported.provenance
            raw = source_rows[provenance.artifact_row - 1]
            assert provenance.artifact == f"clean/{table}.csv"
            assert provenance.source_file == raw["lineage_source_file"]
            assert provenance.sheet == (raw["lineage_sheet"] or None)
            assert provenance.row_number == int(raw["lineage_row_number"])
            assert provenance.raw_hash == raw["lineage_raw_hash"]
            assert provenance.run_id == raw["lineage_run_id"]
            assert provenance.mapping_version == raw["lineage_mapping_version"]
    serialized = canonical_json(packet)
    assert "private-notes-sentinel" not in serialized
    assert "private-review-message-sentinel" not in serialized
    assert all(issue.review_state == "needs_review" for issue in packet.issues)


@pytest.mark.parametrize("table,key", [("clients", "client_id"), ("policies", "policy_id")])
def test_duplicate_ids_keep_every_candidate_visible(tmp_path: Path, table: str, key: str) -> None:
    root = _fixture_run(tmp_path)
    path = root / f"clean/{table}.csv"
    with path.open(newline="") as stream:
        reader = csv.DictReader(stream)
        headers = reader.fieldnames
        rows = list(reader)
    assert headers is not None
    rows[1][key] = rows[0][key]
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)
    packet = export_run(root, agency_id="synthetic-a", data_kind="synthetic")
    exported = getattr(packet, table)
    assert len(exported) == len(rows)
    candidates = [row for row in exported if getattr(row, key) == rows[0][key]]
    issues = [issue for issue in packet.issues if issue.code == f"DUPLICATE_{key.upper()}"]
    assert len(candidates) == len(issues) == 2
    assert {record_id for issue in issues for record_id in issue.record_ids} == {
        row.record_id for row in candidates
    }
    assert all(issue.review_state == "needs_review" for issue in issues)


@pytest.mark.parametrize("path", ["exceptions.jsonl", "unresolved_evidence.jsonl"])
def test_malformed_review_evidence_is_refused(tmp_path: Path, path: str) -> None:
    root = _fixture_run(tmp_path)
    (root / path).write_text('{"unexpected":true}\n')
    with pytest.raises(ValueError):
        export_run(root, agency_id="synthetic-a", data_kind="synthetic")

"""Synthetic security regressions; assertions state the required safe behavior."""

import json
from datetime import UTC, datetime

import pytest

from intake.gates.refusal import check_ssn
from intake.ingest import ingest
from intake.mapping.enums import fill_drop
from intake.mapping.headers import map_headers
from intake.mapping.jev_mapping import Asker, decide_header
from intake.mapping.store import SourceMapping, save_mapping
from intake.readers import LINEAGE_COLUMN

NOW = datetime(2026, 10, 1, tzinfo=UTC)


def drop_table(tmp_path, source="crm", header="Unrecognized"):
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "crm.csv").write_text(f"{header}\nsafe synthetic text\n")
    (drop / "manifest.json").write_text(
        json.dumps({"files": [{"source": source, "file_name": "crm.csv", "rows": 1}]})
    )
    return ingest(drop, run_id="security-audit").tables[0]


def test_manifest_source_cannot_create_mapping_outside_mapping_dir(tmp_path):
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    try:
        table = drop_table(tmp_path, source="../escaped")
        map_headers(
            table.source,
            None,
            [c for c in table.frame.columns if c != LINEAGE_COLUMN],
            mapping,
            NOW,
        )
    except ValueError:
        pass
    escaped = tmp_path / "escaped.yaml"
    print("OBSERVED source traversal escaped YAML created:", escaped.exists())
    assert not escaped.exists(), "untrusted manifest source wrote a YAML outside mapping/"


def test_mapping_store_cannot_overwrite_absolute_target(tmp_path):
    target = tmp_path / "outside.yaml"
    target.write_text("preserve unrelated synthetic file\n")
    mapping = tmp_path / "mapping"
    mapping.mkdir()
    source = str(target.with_suffix(""))
    try:
        save_mapping(mapping, SourceMapping(source=source, entries=()))
    except ValueError:
        pass
    changed = target.read_text() != "preserve unrelated synthetic file\n"
    print("OBSERVED absolute mapping destination overwritten:", changed)
    assert not changed


def test_ingest_rejects_symlink_to_csv_outside_drop(tmp_path):
    outside = tmp_path / "unrelated.csv"
    outside.write_text("Unrecognized\nSYNTHETIC_OUTSIDE_MARKER\n")
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "crm.csv").symlink_to(outside)
    (drop / "manifest.json").write_text(
        json.dumps({"files": [{"source": "crm", "file_name": "crm.csv", "rows": 1}]})
    )
    try:
        result = ingest(drop, run_id="security-audit")
    except ValueError:
        return
    print(
        "OBSERVED external symlink CSV content ingested:", result.tables[0].frame["Unrecognized"][0]
    )
    assert not result.tables, "untrusted drop symlink crossed the input boundary"


@pytest.mark.parametrize("header", ["000-00-0000", "000000000"])
def test_ssn_shaped_header_is_blocked_before_model_request(tmp_path, header):
    # Intentionally invalid all-zero synthetic identity shape; never use real personal data.
    # Text companion headers ensure the reader recognizes the numeric cell as a header.
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "crm.csv").write_text(
        f"{header},Unrecognized,Description\nsafe synthetic text,synthetic,synthetic\n"
    )
    (drop / "manifest.json").write_text(
        json.dumps({"files": [{"source": "crm", "file_name": "crm.csv", "rows": 1}]})
    )
    table = ingest(drop, run_id="security-audit").tables[0]
    gates = check_ssn((table,))
    collector = Asker(None)
    if not gates:
        decide_header("crm", header, table.frame[header], collector)
    exposed = any(r.state.get("header") == header for r in collector.requests.values())
    print(
        "OBSERVED SSN-shaped header blockers:",
        len(gates),
        "model request contains header:",
        exposed,
    )
    assert any(r.rule_id == "SSN-001" for r in gates)
    assert not exposed


def test_record_mapping_applies_raw_ssn_gate_before_header_requests(tmp_path):
    drop = tmp_path / "drop"
    drop.mkdir()
    (drop / "crm.csv").write_text("000-00-0000\nsafe synthetic text\n")
    (drop / "manifest.json").write_text(
        json.dumps({"files": [{"source": "crm", "file_name": "crm.csv", "rows": 1}]})
    )
    collector = Asker(None)
    try:
        fill_drop(drop, tmp_path / "mapping", NOW, collector)
    except ValueError:
        pass
    exposed = any(r.state.get("header") == "000-00-0000" for r in collector.requests.values())
    print("OBSERVED record-mapping sends SSN-shaped header:", exposed)
    assert not exposed, "record-mapping omitted the run's raw SSN gate"

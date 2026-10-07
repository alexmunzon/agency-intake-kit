"""Check the published synthetic sample's exact bytes and row links."""

import hashlib
import json
from pathlib import Path

from intake.finance_adapter import StatementAdapter, import_statement
from intake.readers import raw_hash

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures/finance-durable"


def test_sample_pins_and_revision_row_provenance():
    sidecar = json.loads((FIXTURE / "provenance.json").read_text())
    ledger_bytes = (FIXTURE / "ledger.json").read_bytes()
    ledger = json.loads(ledger_bytes)
    batch = json.loads((FIXTURE / "batch.json").read_text())

    assert sidecar["artifact_type"] == "finance_provenance"
    assert sidecar["data_kind"] == "synthetic"
    assert sidecar["agency_id"] == "synthetic-agency"
    assert sidecar["run_id"] == "synthetic-finance-run"
    assert (ROOT / "dashboard/public/demo-ledger.json").read_bytes() == ledger_bytes

    paths = [artifact["path"] for artifact in sidecar["artifacts"]]
    assert len(paths) == len(set(paths))
    assert set(paths) == {p.name for p in FIXTURE.iterdir() if p.name != "provenance.json"}
    for artifact in sidecar["artifacts"]:
        path = Path(artifact["path"])
        assert len(path.parts) == 1  # every pin resolves within this fixture directory
        data = (FIXTURE / path).read_bytes()
        assert len(data) == artifact["size_bytes"]
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]

    assert len(ledger["receipts"]) == len(ledger["revisions"]) == len(batch["receipts"]) == 3
    assert [r["state"] for r in ledger["receipts"]] == ["superseded", "duplicate", "active"]
    assert [r["receipt_id"] for r in ledger["receipts"]] == ["original", "duplicate", "correction"]
    expected = []
    for revision_index, (receipt, revision) in enumerate(
        zip(ledger["receipts"], ledger["revisions"], strict=True), 1
    ):
        assert revision == batch["receipts"][revision_index - 1]["package"]
        source = FIXTURE / revision["rows"][0]["lineage"]["source_file"]
        assert hashlib.sha256(source.read_bytes()).hexdigest() == revision["content_sha256"]
        for row_index, row in enumerate(revision["rows"], 1):
            lineage = row["lineage"]
            raw_cells = source.read_text().splitlines()[lineage["row_number"] - 1].split(",")
            assert raw_hash(raw_cells) == lineage["raw_hash"]
            expected.append(
                dict(
                    lineage,
                    artifact=source.name,
                    artifact_row=lineage["row_number"] - 1,
                    ledger_artifact="ledger.json",
                    ledger_revision_index=revision_index,
                    ledger_row_index=row_index,
                    receipt_id=receipt["receipt_id"],
                    revision_id=revision["revision_id"],
                    row_id=row["row_id"],
                )
            )
    assert sidecar["rows"] == expected

    csv_config = StatementAdapter.model_validate_json((FIXTURE / "adapter.json").read_bytes())
    xlsx_config = StatementAdapter.model_validate_json((FIXTURE / "adapter-xlsx.json").read_bytes())
    imported_csv = import_statement(FIXTURE / "statement.csv", csv_config)
    assert imported_csv.model_dump(mode="json") == ledger["revisions"][0]
    assert import_statement(FIXTURE / "statement.xlsx", xlsx_config).rows[0].amount == 100

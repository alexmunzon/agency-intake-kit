"""Generate synthetic adapter inputs and durable-ledger sample exports."""

import hashlib
import io
import json
import re
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

from intake.finance_adapter import StatementAdapter, import_statement
from intake.finance_store import ReceiptStore
from intake.revenue import RevenueMapping
from intake.revenue_ledger import ReceiptBatch, StatementReceipt
from openpyxl import Workbook

root = Path(__file__).resolve().parents[2]
out = root / "fixtures/finance-durable"
out.mkdir(exist_ok=True)
cells = [
    ["Value", "Label", "Kind"],
    ["100.00", "Renewal", "Payment"],
    ["-25.00", "Renewal", "Chargeback"],
    ["0.03", "Unknown incentive", "Payment"],
]
(out / "statement.csv").write_text("\n".join(",".join(row) for row in cells) + "\n")
book = Workbook()
for row in cells:
    book.active.append(row)
book.properties.created = datetime(2026, 10, 7, tzinfo=UTC)
book.properties.modified = datetime(2026, 10, 7, tzinfo=UTC)
workbook_bytes = io.BytesIO()
book.save(workbook_bytes)
# openpyxl writes the current time into ZIP headers. Fix archive metadata so the
# exact-byte XLSX pin stays stable across repeated sample generation.
with (
    zipfile.ZipFile(io.BytesIO(workbook_bytes.getvalue())) as source,
    zipfile.ZipFile(out / "statement.xlsx", "w") as stable,
):
    for member in source.infolist():
        info = zipfile.ZipInfo(member.filename, (2026, 10, 7, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        info.external_attr = member.external_attr
        info.create_system = 3
        payload = source.read(member.filename)
        if member.filename == "docProps/core.xml":
            payload, count = re.subn(
                rb"(<dcterms:modified[^>]*>)[^<]*(</dcterms:modified>)",
                rb"\g<1>2026-10-07T00:00:00Z\g<2>",
                payload,
            )
            if count != 1:
                raise ValueError("XLSX modified-time metadata is missing")
        stable.writestr(info, payload)
config = StatementAdapter(
    adapter_version="synthetic-layout-v1",
    agency_id="synthetic-agency",
    carrier="Synthetic Carrier",
    period="2026-09",
    statement_id="synthetic-september",
    revision_id="r1",
    run_id="synthetic-finance-run",
    format="csv",
    source_sha256=hashlib.sha256((out / "statement.csv").read_bytes()).hexdigest(),
    amount_column="Value",
    category_column="Label",
    transaction_column="Kind",
    control_total="75.03",
)
(out / "adapter.json").write_text(config.model_dump_json(indent=2) + "\n")
package = import_statement(out / "statement.csv", config)
receipts = [
    StatementReceipt(
        receipt_id="original",
        received_at=datetime(2026, 10, 7, tzinfo=UTC),
        package=package,
    )
]
receipts.append(
    receipts[0].model_copy(
        update={
            "receipt_id": "duplicate",
            "received_at": receipts[0].received_at + timedelta(seconds=1),
        }
    )
)
corrected = (out / "statement.csv").read_text().replace("100.00", "110.00")
(out / "correction.csv").write_text(corrected)
config2 = config.model_copy(
    update={
        "revision_id": "r2",
        "control_total": None,
        "source_sha256": hashlib.sha256(
            (out / "correction.csv").read_bytes()
        ).hexdigest(),
    }
)
receipts.append(
    StatementReceipt(
        receipt_id="correction",
        received_at=receipts[0].received_at + timedelta(seconds=2),
        package=import_statement(out / "correction.csv", config2),
        replaces_revision_id="r1",
    )
)
batch = ReceiptBatch(receipts=tuple(receipts))
(out / "batch.json").write_text(batch.model_dump_json(indent=2) + "\n")
mapping = RevenueMapping.model_validate_json(
    (root / "fixtures/finance-review/mapping.json").read_bytes()
)
with tempfile.TemporaryDirectory() as directory:
    store = ReceiptStore.create(Path(directory) / "ledger.sqlite", mapping)
    store.append("synthetic-operation-1", batch)
    text = store.read().model_dump_json(indent=2) + "\n"
    (out / "ledger.json").write_text(text)
    (root / "dashboard/public/demo-ledger.json").write_text(text)
(out / "adapter-xlsx.json").write_text(
    config.model_copy(
        update={
            "format": "xlsx",
            "source_sha256": hashlib.sha256(
                (out / "statement.xlsx").read_bytes()
            ).hexdigest(),
        }
    ).model_dump_json(indent=2)
    + "\n"
)
# Pins follow Session 1's exact-byte provenance contract; no authenticity claim.
pins = [
    {
        "path": p.name,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "size_bytes": p.stat().st_size,
    }
    for p in sorted(out.iterdir())
    if p.name != "provenance.json"
]
ledger = json.loads(text)
rows = []
for revision_index, (receipt, revision) in enumerate(
    zip(ledger["receipts"], ledger["revisions"], strict=True), 1
):
    for row_index, row in enumerate(revision["rows"], 1):
        lineage = row["lineage"]
        rows.append(
            dict(
                lineage,
                artifact=lineage["source_file"],
                artifact_row=lineage["row_number"] - config.header_row,
                ledger_artifact="ledger.json",
                ledger_revision_index=revision_index,
                ledger_row_index=row_index,
                receipt_id=receipt["receipt_id"],
                revision_id=revision["revision_id"],
                row_id=row["row_id"],
            )
        )
(out / "provenance.json").write_text(
    json.dumps(
        {
            "schema_version": "1.0.0",
            "artifact_type": "finance_provenance",
            "agency_id": config.agency_id,
            "run_id": config.run_id,
            "data_kind": "synthetic",
            "artifacts": pins,
            "rows": rows,
        },
        sort_keys=True,
        indent=2,
    )
    + "\n"
)

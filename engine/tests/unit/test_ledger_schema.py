"""Focused input and serialization contracts for the finance receipt ledger."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agency_schema.lineage import Lineage
from intake.revenue import RevenueInputRow, RevenueMapping, StatementPackage
from intake.revenue_ledger import (
    ReceiptBatch,
    RevenueLedger,
    StatementReceipt,
    reconcile_receipts,
)

NOW = datetime(2026, 10, 5, 12, tzinfo=UTC)


def _mapping() -> RevenueMapping:
    return RevenueMapping(
        mapping_id="mapping-synthetic-v1",
        carrier="Synthetic Carrier",
        version="v1",
        approved_by="Synthetic Reviewer",
        approved_at=NOW,
        categories={"Renewal": "renewal"},
        transaction_kinds={"Payment": "payment"},
        accounts={"renewal": "4100"},
    )


def _package(revision: str, amount: str) -> StatementPackage:
    row = RevenueInputRow(
        row_id=f"row-{revision}",
        amount=Decimal(amount),
        raw_amount=amount,
        raw_category_label="Renewal",
        raw_transaction_label="Payment",
        lineage=Lineage(
            source_file=f"statement-{revision}.csv",
            sheet=None,
            row_number=2,
            raw_hash=(revision.encode().hex() * 32)[:64],
            run_id="synthetic-run",
            mapping_version="v1",
        ),
    )
    return StatementPackage(
        agency_id="agency-synthetic",
        carrier="Synthetic Carrier",
        period="2026-09",
        statement_id="statement-synthetic",
        revision_id=revision,
        content_sha256=(revision.encode().hex() * 32)[:64],
        expected_row_count=1,
        rows=(row,),
        control_total=Decimal(amount),
    )


def _receipt(number: int, package: StatementPackage, replaces: str | None = None):
    return StatementReceipt(
        receipt_id=f"receipt-{number}",
        received_at=NOW + timedelta(seconds=number),
        package=package,
        replaces_revision_id=replaces,
    )


@pytest.mark.parametrize("received_at", [0, 1_791_200_000, 1_791_200_000.0, "1791200000"])
def test_received_at_rejects_numeric_and_numeric_string_timestamps(received_at: object) -> None:
    with pytest.raises(ValidationError):
        StatementReceipt(
            receipt_id="receipt-invalid-time",
            received_at=received_at,
            package=_package("A", "10.00"),
        )


@pytest.mark.parametrize("received_at", [NOW, "2026-10-05T12:00:00+00:00"])
def test_received_at_accepts_aware_datetime_and_iso_datetime(received_at: object) -> None:
    receipt = StatementReceipt(
        receipt_id="receipt-valid-time",
        received_at=received_at,
        package=_package("A", "10.00"),
    )

    assert receipt.received_at == NOW
    assert receipt.received_at.utcoffset() == timedelta(0)


def test_receipt_batch_json_refuses_duplicate_object_keys() -> None:
    with pytest.raises(ValueError, match="duplicate JSON object key"):
        ReceiptBatch.model_validate_json('{"receipts": [], "receipts": []}')


def test_ledger_json_round_trip_keeps_envelope_receipts_and_superseded_package() -> None:
    ledger = reconcile_receipts(
        (
            _receipt(1, _package("revision-A", "10.00")),
            _receipt(2, _package("revision-B", "12.34"), "revision-A"),
        ),
        _mapping(),
    )
    payload = ledger.model_dump_json()
    document = json.loads(payload)

    assert document["artifact_type"] == "neutral_finance_ledger"
    assert document["schema_version"] == 1
    restored = RevenueLedger.model_validate_json(payload)
    assert restored.artifact_type == "neutral_finance_ledger"
    assert restored.schema_version == 1
    assert [item.receipt_id for item in restored.receipts] == ["receipt-1", "receipt-2"]
    assert [item.state for item in restored.receipts] == ["superseded", "active"]
    assert [item.revision_id for item in restored.revisions] == ["revision-A", "revision-B"]
    assert [item.rows[0].amount for item in restored.revisions] == [
        Decimal("10.00"),
        Decimal("12.34"),
    ]
    assert [item.revision_id for item in restored.active_reviews] == ["revision-B"]

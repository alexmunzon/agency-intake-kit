"""Focused CLI checks for the synthetic receipt ledger."""

import json
from pathlib import Path

from typer.testing import CliRunner

from intake.cli import app

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures" / "finance-review"
RECEIPTS = FIXTURES / "receipts.json"
MAPPING = FIXTURES / "mapping.json"
GENERIC_REFUSAL = "Finance ledger refused: invalid receipts or mapping."


def invoke(receipts: Path, mapping: Path):
    return CliRunner().invoke(
        app,
        ["finance-ledger", "--receipts", str(receipts), "--mapping", str(mapping)],
    )


def test_cli_exports_active_and_conflict_totals_as_json_without_changing_inputs() -> None:
    receipts_before = RECEIPTS.read_bytes()
    mapping_before = MAPPING.read_bytes()

    result = invoke(RECEIPTS, MAPPING)

    assert result.exit_code == 0
    ledger = json.loads(result.output)
    assert [receipt["state"] for receipt in ledger["receipts"]] == [
        "superseded",
        "duplicate",
        "active",
        "conflict",
    ]
    assert [row["statement_total"] for row in ledger["grouped_totals"]] == ["85.03"]
    assert [row["statement_total"] for row in ledger["unresolved_conflict_totals"]] == ["95.03"]
    assert RECEIPTS.read_bytes() == receipts_before
    assert MAPPING.read_bytes() == mapping_before


def test_cli_rejects_malformed_receipt_batch_without_echo_and_preserves_inputs(
    tmp_path: Path,
) -> None:
    marker = "SENSITIVE_MALFORMED_RECEIPT_31"
    receipts = tmp_path / "receipts.json"
    mapping = tmp_path / "mapping.json"
    receipts.write_text(f'{{"receipts": [{{"marker": "{marker}"}},')
    mapping.write_bytes(MAPPING.read_bytes())
    before = (receipts.read_bytes(), mapping.read_bytes())

    result = invoke(receipts, mapping)

    assert result.exit_code == 2
    assert result.output.strip() == GENERIC_REFUSAL
    assert marker not in result.output
    assert str(receipts) not in result.output
    assert receipts.read_bytes() == before[0]
    assert mapping.read_bytes() == before[1]


def test_cli_rejects_duplicate_json_keys_without_echo_and_preserves_inputs(
    tmp_path: Path,
) -> None:
    marker = "SENSITIVE_DUPLICATE_RECEIPT_42"
    receipts = tmp_path / "receipts.json"
    mapping = tmp_path / "mapping.json"
    receipts.write_text(f'{{"receipts": [], "receipts": [{{"marker": "{marker}"}}]}}')
    mapping.write_bytes(MAPPING.read_bytes())
    before = (receipts.read_bytes(), mapping.read_bytes())

    result = invoke(receipts, mapping)

    assert result.exit_code == 2
    assert result.output.strip() == GENERIC_REFUSAL
    assert marker not in result.output
    assert str(receipts) not in result.output
    assert receipts.read_bytes() == before[0]
    assert mapping.read_bytes() == before[1]

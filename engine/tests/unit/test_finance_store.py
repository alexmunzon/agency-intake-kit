"""Durable transaction acceptance with synthetic receipts."""

import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_revenue_ledger import mapping, package, receipt, states, total

from intake.finance_store import ReceiptStore
from intake.revenue_ledger import ReceiptBatch


def test_restart_retry_correction_and_conflicting_ids(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ReceiptStore.create(path, mapping())
    batch = ReceiptBatch(receipts=(receipt(1, package()),))
    original = ReceiptStore(path).append("op-1", batch)
    assert ReceiptStore(path).append("op-1", batch) == original
    with pytest.raises(ValueError, match="operation"):
        ReceiptStore(path).append("op-1", ReceiptBatch(receipts=()))
    with pytest.raises(ValueError, match="receipt_id"):
        ReceiptStore(path).append("op-2", batch)
    corrected = ReceiptStore(path).append(
        "op-3", ReceiptBatch(receipts=(receipt(2, package("B", ("12.00",)), "A"),))
    )
    assert states(corrected) == ["superseded", "active"]
    assert ReceiptStore(path).append("op-1", batch) == original
    assert len(ReceiptStore(path).read().revisions) == 2


def test_atomic_rollback(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    with pytest.raises(ValueError):
        store.append("bad", ReceiptBatch(receipts=(receipt(1, package()), receipt(1, package()))))
    assert store.read().receipts == ()
    assert len(store.append("bad", ReceiptBatch(receipts=(receipt(1, package()),))).receipts) == 1


def test_model_copy_cannot_bypass_validation_or_reserve_operation_id(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    valid = ReceiptBatch(receipts=(receipt(1, package()),))
    invalid = valid.model_copy(
        update={"receipts": (valid.receipts[0].model_copy(update={"receipt_id": ""}),)}
    )
    with pytest.raises(ValueError):
        store.append("retryable", invalid)
    assert store.read().receipts == ()
    assert len(store.append("retryable", valid).receipts) == 1


def test_mapping_is_pinned_and_late_receipt_is_atomic_refusal(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    store.append("later", ReceiptBatch(receipts=(receipt(2, package()),)))
    with pytest.raises(FileExistsError):
        ReceiptStore.create(path, mapping().model_copy(update={"version": "v2"}))
    with pytest.raises(ValueError, match="ordered"):
        ReceiptStore(path).append(
            "earlier", ReceiptBatch(receipts=(receipt(1, package(statement="earlier")),))
        )
    ledger = ReceiptStore(path).read()
    assert len(ledger.receipts) == 1
    assert ledger.active_reviews[0].mapping_version == "v1"
    assert len(store.append("later", ReceiptBatch(receipts=(receipt(2, package()),))).receipts) == 1


def test_concurrent_appends_and_duplicate_retries(tmp_path):
    path = tmp_path / "ledger.sqlite"
    ReceiptStore.create(path, mapping())

    def append(i):
        row = receipt(1, package(statement=f"s-{i}")).model_copy(update={"receipt_id": f"r-{i}"})
        return ReceiptStore(path).append(f"op-{i}", ReceiptBatch(receipts=(row,)))

    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(append, [*range(12), *range(12)]))
    assert len(ReceiptStore(path).read().receipts) == 12
    assert total(ReceiptStore(path).read()) == 120


def test_corrupt_store_refused_without_replacement(tmp_path):
    path = tmp_path / "ledger.sqlite"
    path.write_bytes(b"not a sqlite database")
    with pytest.raises((ValueError, sqlite3.DatabaseError)):
        ReceiptStore(path).read()
    with pytest.raises(FileExistsError):
        ReceiptStore.create(path, mapping())
    assert path.read_bytes() == b"not a sqlite database"


def test_immutable_and_tampered_payload_refusal(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    store.append("op", ReceiptBatch(receipts=(receipt(1, package()),)))
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("UPDATE operations SET payload = '{}' ")
        db.execute("DROP TRIGGER operations_no_update")
        db.execute("UPDATE operations SET payload = '{}' ")
    with pytest.raises(ValueError, match="corrupt"):
        store.read()


def test_process_crash_rolls_back_and_restart_retries(tmp_path):
    import os
    import subprocess
    import sys

    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    batch = ReceiptBatch(receipts=(receipt(1, package()),))
    store.append("committed", batch)
    env = dict(os.environ, PYTHONPATH=str(__import__("pathlib").Path("src").resolve()))
    # A process exits while holding a write transaction after a real INSERT.
    crash = """
import os, sqlite3, sys
con = sqlite3.connect(sys.argv[1])
con.execute('BEGIN IMMEDIATE')
con.execute("INSERT INTO operations VALUES (2, 'crashed', '{}', 'bad')")
os._exit(23)
"""
    result = subprocess.run([sys.executable, "-c", crash, str(path)], env=env)
    assert result.returncode == 23
    assert len(ReceiptStore(path).read().receipts) == 1
    assert ReceiptStore(path).append("committed", batch) == store.read()


def test_database_insert_failure_rolls_back(tmp_path):
    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TRIGGER fail BEFORE INSERT ON operations "
            "BEGIN SELECT RAISE(ABORT, 'simulated disk failure'); END"
        )
    batch = ReceiptBatch(receipts=(receipt(1, package()),))
    with pytest.raises(sqlite3.IntegrityError):
        store.append("retry", batch)
    assert store.read().receipts == ()
    with sqlite3.connect(path) as db:
        db.execute("DROP TRIGGER fail")
    assert len(store.append("retry", batch).receipts) == 1


def test_commit_without_response_is_retryable_after_process_exit(tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path

    path = tmp_path / "ledger.sqlite"
    store = ReceiptStore.create(path, mapping())
    batch = ReceiptBatch(receipts=(receipt(1, package()),))
    payload = tmp_path / "batch.json"
    payload.write_text(batch.model_dump_json())
    program = """
import os, sys
from pathlib import Path
from intake.finance_store import ReceiptStore
from intake.revenue_ledger import ReceiptBatch
batch = ReceiptBatch.model_validate_json(Path(sys.argv[2]).read_bytes())
ReceiptStore(Path(sys.argv[1])).append('lost-response', batch)
os._exit(23)
"""
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[2] / "src"))
    assert (
        subprocess.run([sys.executable, "-c", program, str(path), str(payload)], env=env).returncode
        == 23
    )
    assert store.append("lost-response", batch) == store.read()
    assert len(store.read().receipts) == 1

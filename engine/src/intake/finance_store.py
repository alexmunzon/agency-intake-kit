"""Local SQLite receipt journal, with atomic batches and immutable operation identity.

One store pins one carrier mapping snapshot. A different mapping is a new store;
reclassification never silently rewrites historical classification evidence.
"""

import hashlib
import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from intake.revenue import RevenueMapping
from intake.revenue_ledger import ReceiptBatch, RevenueLedger, StatementReceipt, reconcile_receipts


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _canonical(batch: ReceiptBatch) -> str:
    return json.dumps(batch.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


class ReceiptStore:
    def __init__(self, path: Path):
        self.path = path.resolve()

    @classmethod
    def create(cls, path: Path, mapping: RevenueMapping) -> "ReceiptStore":
        mapping = RevenueMapping.model_validate_json(mapping.model_dump_json())
        # Exclusive creation distinguishes a new store from damaged/empty existing files.
        with path.open("xb"):
            pass
        store = cls(path)
        with store._connect() as db:
            db.executescript("""
                CREATE TABLE metadata (version INTEGER NOT NULL, mapping TEXT NOT NULL,
                                       digest TEXT NOT NULL);
                CREATE TABLE operations (sequence INTEGER PRIMARY KEY,
                    operation_id TEXT NOT NULL UNIQUE, payload TEXT NOT NULL,
                    digest TEXT NOT NULL);
                CREATE TRIGGER operations_no_update BEFORE UPDATE ON operations
                    BEGIN SELECT RAISE(ABORT, 'immutable operation'); END;
                CREATE TRIGGER operations_no_delete BEFORE DELETE ON operations
                    BEGIN SELECT RAISE(ABORT, 'immutable operation'); END;
                CREATE TRIGGER metadata_no_update BEFORE UPDATE ON metadata
                    BEGIN SELECT RAISE(ABORT, 'immutable mapping'); END;
                CREATE TRIGGER metadata_no_delete BEFORE DELETE ON metadata
                    BEGIN SELECT RAISE(ABORT, 'immutable mapping'); END;
            """)
            encoded = mapping.model_dump_json()
            db.execute("INSERT INTO metadata VALUES (1, ?, ?)", (encoded, _digest(encoded)))
        return store

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=30)
        try:
            db.execute("PRAGMA synchronous=FULL")
            with db:
                yield db
        finally:
            db.close()

    def _load(
        self, db: sqlite3.Connection
    ) -> tuple[
        RevenueMapping, tuple[StatementReceipt, ...], dict[str, tuple[str, RevenueLedger]], str
    ]:
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise ValueError("corrupt receipt store")
        metadata = db.execute("SELECT version, mapping, digest FROM metadata").fetchall()
        if len(metadata) != 1 or metadata[0][0] != 1:
            raise ValueError("corrupt or unsupported receipt store")
        _, encoded, chain = metadata[0]
        if _digest(encoded) != chain:
            raise ValueError("corrupt mapping snapshot")
        mapping = RevenueMapping.model_validate_json(encoded)
        receipts: tuple[StatementReceipt, ...] = ()
        operations = {}
        for expected, (sequence, operation, payload, digest) in enumerate(
            db.execute(
                "SELECT sequence, operation_id, payload, digest FROM operations ORDER BY sequence"
            ),
            1,
        ):
            if sequence != expected or _digest(chain + operation + payload) != digest:
                raise ValueError("corrupt operation history")
            batch = ReceiptBatch.model_validate_json(payload)
            receipts += batch.receipts
            ledger = reconcile_receipts(receipts, mapping)
            operations[operation] = (payload, ledger)
            chain = digest
        return mapping, receipts, operations, chain

    def read(self) -> RevenueLedger:
        with self._connect() as db:
            db.execute("BEGIN")
            mapping, receipts, _, _ = self._load(db)
            return reconcile_receipts(receipts, mapping)

    def append(self, operation_id: str, batch: ReceiptBatch) -> RevenueLedger:
        if not operation_id.strip():
            raise ValueError("operation_id must not be blank")
        payload = _canonical(batch)
        batch = ReceiptBatch.model_validate_json(payload)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            mapping, receipts, operations, chain = self._load(db)
            if operation_id in operations:
                prior, result = operations[operation_id]
                if prior != payload:
                    raise ValueError("operation_id already used with different payload")
                return result
            result = reconcile_receipts(receipts + batch.receipts, mapping)
            db.execute(
                "INSERT INTO operations VALUES (?, ?, ?, ?)",
                (
                    len(operations) + 1,
                    operation_id,
                    payload,
                    _digest(chain + operation_id + payload),
                ),
            )
            return result

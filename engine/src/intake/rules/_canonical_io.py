"""TEMPORARY test loader for canonical CSVs. PR 4's readers replace it; import it only in tests.

Every cell stays text (blank becomes None) and each row gets a `lineage` struct column with
row_number counted like the ground truth's row_ref: the header is row 1.
"""

import csv
import hashlib
from pathlib import Path
from typing import Any

import polars as pl

RUN_ID = "canonical-test"
MAPPING_VERSION = "canonical"


def frame_from_rows(source_file: str, rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Rows of text cells to a frame with lineage, as a reader would produce it."""
    header = list(rows[0]) if rows else []
    frame = pl.DataFrame(
        {h: [r.get(h) or None for r in rows] for h in header},
        schema={h: pl.String for h in header},
    )
    lineage = pl.DataFrame(
        {
            "source_file": [source_file] * len(rows),
            "sheet": [None] * len(rows),
            "row_number": list(range(2, len(rows) + 2)),
            "raw_hash": [
                hashlib.sha256("\x1f".join(str(v or "") for v in r.values()).encode()).hexdigest()
                for r in rows
            ],
            "run_id": [RUN_ID] * len(rows),
            "mapping_version": [MAPPING_VERSION] * len(rows),
        },
        schema_overrides={"sheet": pl.String, "row_number": pl.Int64},
    )
    return frame.with_columns(lineage.to_struct("lineage"))


def load_canonical(folder: Path) -> dict[str, pl.DataFrame]:
    """Every <table>.csv in folder, keyed by table name."""
    tables = {}
    for path in sorted(folder.glob("*.csv")):
        with path.open(newline="", encoding="utf-8") as f:
            tables[path.stem] = frame_from_rows(path.name, list(csv.DictReader(f)))
    return tables

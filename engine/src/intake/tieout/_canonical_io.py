"""A stopgap reader for canonical CSVs, private to the tie-out. Replaced by the PR 4 readers.

Every cell stays text exactly as read (blank becomes None); the SQL types it. Each frame gets
three lineage columns: _source_file, _row_number (row 1 is the header), and _raw_hash.
"""

import csv
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

import polars as pl

TABLES = ("policies", "clients", "commission_lines")


def frame_from_rows(
    header: Sequence[str], rows: Sequence[Sequence[str | None]], source_file: str
) -> pl.DataFrame:
    cells = [[cell or None for cell in row] for row in rows]
    columns = {name: [row[i] for row in cells] for i, name in enumerate(header)}
    return pl.DataFrame(
        {
            **columns,
            "_source_file": [source_file] * len(cells),
            "_row_number": list(range(2, len(cells) + 2)),
            "_raw_hash": [hashlib.sha256(json.dumps(r).encode()).hexdigest() for r in cells],
        },
        schema={
            **dict.fromkeys(header, pl.String),
            "_source_file": pl.String,
            "_row_number": pl.Int64,
            "_raw_hash": pl.String,
        },
    )


def read_canonical(folder: Path) -> dict[str, pl.DataFrame | None]:
    """The tables the tie-out needs. A missing file is None, so its legs report NOT_RUN."""
    tables: dict[str, pl.DataFrame | None] = {}
    for name in TABLES:
        path = folder / f"{name}.csv"
        if not path.exists():
            tables[name] = None
            continue
        with path.open(newline="", encoding="utf-8") as f:
            header, *rows = list(csv.reader(f))
        tables[name] = frame_from_rows(header, rows, path.name)
    return tables

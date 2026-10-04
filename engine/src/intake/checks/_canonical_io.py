"""Read canonical CSVs into string frames with lineage columns.

Temporary: PR 4's readers replace this loader. It lives inside intake.checks on purpose so the
parallel PR 8 and PR 10 loaders never collide with it.
"""

import hashlib
from pathlib import Path

import polars as pl

RAW_SEPARATOR = "\x1f"  # joins raw cells before hashing; PR 4 owns the final raw_hash recipe


def load_canonical(
    folder: Path, run_id: str = "local", mapping_version: str = "canonical"
) -> dict[str, pl.DataFrame]:
    """One frame per CSV in folder, every cell a string (blank is null), plus lineage columns.

    _row is the 1-based line in the file (row 1 is the header), _hash is the sha256 of the raw
    cells, _source is the table name, and _file, _run_id, _mapping_version complete Lineage.
    """
    tables: dict[str, pl.DataFrame] = {}
    for path in sorted(folder.glob("*.csv")):
        frame = pl.read_csv(path, infer_schema=False)
        hashes = [
            hashlib.sha256(RAW_SEPARATOR.join(c or "" for c in row).encode()).hexdigest()
            for row in frame.iter_rows()
        ]
        tables[path.stem] = frame.with_columns(
            pl.Series("_row", range(2, frame.height + 2), dtype=pl.Int64),
            pl.Series("_hash", hashes, dtype=pl.String),
            pl.lit(path.stem).alias("_source"),
            pl.lit(path.name).alias("_file"),
            pl.lit(run_id).alias("_run_id"),
            pl.lit(mapping_version).alias("_mapping_version"),
        )
    return tables

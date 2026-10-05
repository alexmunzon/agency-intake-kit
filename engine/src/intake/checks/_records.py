"""Build an ExceptionRecord from a row that carries the lineage columns of with_lineage."""

from pathlib import Path
from typing import Any

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.lineage import Lineage

LINEAGE = "lineage"
# Flat lineage columns the checks read, from the reader's lineage struct (or the stopgap loader).
FLAT = {
    "_file": "source_file",
    "_sheet": "sheet",
    "_row": "row_number",
    "_hash": "raw_hash",
    "_run_id": "run_id",
    "_mapping_version": "mapping_version",
}


def with_lineage(name: str, frame: pl.DataFrame) -> pl.DataFrame:
    """The frame plus flat lineage columns, _source (the table), and _rec (its position).

    A reader frame's lineage struct wins over any flat column. _rec is the only row key the
    checks use: row numbers repeat when a table comes from several files or sheets.
    """
    if LINEAGE in frame.columns:
        fields = pl.col(LINEAGE).struct
        frame = frame.with_columns(fields.field(f).alias(c) for c, f in FLAT.items())
    elif "_sheet" not in frame.columns:
        frame = frame.with_columns(pl.lit(None, dtype=pl.String).alias("_sheet"))
    if "_source" not in frame.columns:
        frame = frame.with_columns(pl.lit(name).alias("_source"))
    return frame.with_columns(pl.int_range(pl.len(), dtype=pl.Int64).alias("_rec"))


def record_id(rule_id: str, row: dict[str, Any]) -> str:
    """Rule, source, and row; the file and sheet join in when the file is not the table's own.

    PR 12 may renumber ids; it must then remap rts_coverage exception_ids too.
    """
    where = [row["_source"]]
    stem = Path(row["_file"]).stem
    if stem != row["_source"]:
        where.append(stem)
    if row.get("_sheet"):
        where.append(row["_sheet"])
    return ":".join([rule_id, *where, str(row["_row"])])


def record(
    rule_id: str,
    severity: Severity,
    row: dict[str, Any],
    message: str,
    fix: str,
    field: str | None = None,
) -> ExceptionRecord:
    """One record per rule per row, with the row's own lineage carried through unchanged."""
    return ExceptionRecord(
        id=record_id(rule_id, row),
        rule_id=rule_id,
        severity=severity,
        family=Family(rule_id[:3]),
        source=row["_source"],
        row_number=row["_row"],
        raw_hash=row["_hash"],
        field=field,
        value_minimized=minimize_value(row.get(field)) if field else None,
        message=message,
        suggested_fix=fix,
        blocks_load=False,
        lane=Lane.UNREVIEWED,
        jev=None,
        lineage=Lineage(**{f: row[c] for c, f in FLAT.items()}),
    )

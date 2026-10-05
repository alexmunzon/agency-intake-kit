"""File readers: every source file becomes a raw frame of text cells plus a lineage column.

A raw frame keeps each source column under its header exactly as read (every cell a string,
blank cells null) and adds one struct column, `lineage`, whose fields match
agency_schema.Lineage: source_file, sheet, row_number, raw_hash, run_id, mapping_version.
"""

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import ExceptionRecord
from intake.config import DEFAULT_ENCODING
from intake.readers.sniff import count_trailers, find_header_row, total_row_count

LINEAGE_COLUMN = "lineage"
RAW_SEPARATOR = "\x1f"  # joins a row's raw cells before hashing
INFO = Severity.INFO


@dataclass(frozen=True)
class RawTable:
    """One file (or one xlsx sheet) as read, before any mapping."""

    source: str  # the drop's name for it, for example "crm" or "statement_bluepeak"
    source_file: str
    sheet: str | None
    frame: pl.DataFrame
    header_row: int  # 1-based row the header was found on
    encoding: str | None  # None for xlsx
    delimiter: str | None  # None for xlsx
    dropped_rows: int  # trailing total block (totals, footers, blanks) or blank rows removed
    total_row_count: int | None  # data row count printed on a trailing total row, if any
    exceptions: tuple[ExceptionRecord, ...]  # ING records about how the file was read
    expected_rows: int | None = None  # from drop/manifest.json, filled by ingest

    @property
    def rows(self) -> int:
        return self.frame.height


def raw_hash(cells: Sequence[str | None]) -> str:
    """sha256 of the row's raw cells joined by the unit separator, blank as empty."""
    return hashlib.sha256(RAW_SEPARATOR.join(c or "" for c in cells).encode()).hexdigest()


def file_exception(
    rule_id: str, severity: Severity, source: str, message: str, fix: str | None = None
) -> ExceptionRecord:
    """A file-level ExceptionRecord (no row, no lineage) with an id stable across runs."""
    digest = hashlib.sha256(f"{rule_id}|{source}|{message}".encode()).hexdigest()[:12]
    return ExceptionRecord(
        id=f"{rule_id}-{digest}",
        rule_id=rule_id,
        severity=severity,
        family=Family(rule_id[:3]),
        source=source,
        row_number=None,
        raw_hash=None,
        field=None,
        value_minimized=None,
        message=message,
        suggested_fix=fix,
        blocks_load=severity == Severity.BLOCKER,
        lane=Lane.UNREVIEWED,
        jev=None,
        lineage=None,
    )


def column_names(header: Sequence[str | None]) -> list[str]:
    """Header cells as column names: blanks become column_N, repeats get _2, _3."""
    names: list[str] = []
    seen = {LINEAGE_COLUMN}
    for i, cell in enumerate(header, start=1):
        base = cell if cell else f"column_{i}"
        name, n = base, 1
        while name in seen:
            n += 1
            name = f"{base}_{n}"
        seen.add(name)
        names.append(name)
    return names


def build_frame(
    header: Sequence[str | None],
    rows: Sequence[tuple[int, Sequence[str | None]]],
    *,
    source_file: str,
    sheet: str | None,
    run_id: str,
    mapping_version: str,
) -> pl.DataFrame:
    """Rows of (1-based row number, raw cells) to a raw frame with the lineage column."""
    names = column_names(header)
    width = len(names)
    cells = [list(r[:width]) + [None] * (width - len(r)) for _, r in rows]
    data = {n: [row[i] or None for row in cells] for i, n in enumerate(names)}
    lineage = pl.DataFrame(
        {
            "source_file": [source_file] * len(rows),
            "sheet": [sheet] * len(rows),
            "row_number": [n for n, _ in rows],
            "raw_hash": [raw_hash(r) for r in cells],
            "run_id": [run_id] * len(rows),
            "mapping_version": [mapping_version] * len(rows),
        },
        schema={
            "source_file": pl.String,
            "sheet": pl.String,
            "row_number": pl.Int64,
            "raw_hash": pl.String,
            "run_id": pl.String,
            "mapping_version": pl.String,
        },
    )
    frame = pl.DataFrame(data, schema=dict.fromkeys(names, pl.String))
    return frame.with_columns(lineage.to_struct(LINEAGE_COLUMN))


def table_from_rows(
    rows: Sequence[Sequence[str | None]],
    *,
    source: str,
    source_file: str,
    sheet: str | None,
    run_id: str,
    mapping_version: str,
    encoding: str | None = None,
    delimiter: str | None = None,
    delimiter_confident: bool = True,
) -> RawTable:
    """Find the header, drop the trailing total block, attach lineage, and note what was unusual."""
    header_at = find_header_row(rows)
    body = rows[header_at + 1 :]
    dropped = count_trailers(body)
    data = body[: len(body) - dropped]
    frame = build_frame(
        rows[header_at] if rows else [],
        [(header_at + 2 + i, row) for i, row in enumerate(data)],
        source_file=source_file,
        sheet=sheet,
        run_id=run_id,
        mapping_version=mapping_version,
    )
    where = f"{source_file} ({sheet})" if sheet else source_file
    notes = []
    if encoding is not None and encoding != DEFAULT_ENCODING:
        notes.append(file_exception("ING-001", INFO, source, f"Read {where} as {encoding}"))
    if header_at:
        notes.append(
            file_exception(
                "ING-002", INFO, source, f"Header found on row {header_at + 1} of {where}"
            )
        )
    if dropped:
        notes.append(
            file_exception(
                "ING-003", INFO, source, f"Dropped {dropped} non-data rows at end of {where}"
            )
        )
    if not delimiter_confident:
        message = f'{where} parsed with "{delimiter}"'
        notes.append(
            file_exception("ING-004", Severity.WARNING, source, message, "Confirm delimiter")
        )
    return RawTable(
        source=source,
        source_file=source_file,
        sheet=sheet,
        frame=frame,
        header_row=header_at + 1,
        encoding=encoding,
        delimiter=delimiter,
        dropped_rows=dropped,
        total_row_count=total_row_count(body[len(data) :]),
        exceptions=tuple(notes),
    )

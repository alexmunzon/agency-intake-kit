"""Read the raw text cells once, in Python, before DuckDB sees them.

Dates go through parse_date_loose and come out ISO, amounts through parse_money and come out as
plain decimals, and the SQL then casts strictly. A non-blank value that does not read is counted
(and logged) instead of vanishing. Each row gets _rec, its position in its table: the only row
key the SQL joins on, because lineage row numbers repeat across statement files (#53).
"""

import logging
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import polars as pl

from agency_schema.formats import parse_date_loose
from agency_schema.lineage import Lineage
from intake.normalize import NotMoney, parse_money

log = logging.getLogger(__name__)
CANONICAL_MAPPING = "canonical"  # the stopgap loader's frames need no header mapping
REC = "_rec"
COLUMNS = {
    "policies": ["policy_id", "client_id", "carrier", "carrier_member_id", "line_of_business",
                 "effective_date", "termination_date", "status", "writing_agent_npn"],
    "clients": ["client_id", "first_name", "last_name", "dob"],
    "commission_lines": ["carrier", "statement_period", "line_no", "carrier_member_id",
                         "member_name", "member_dob", "policy_ref", "agent_npn", "amount",
                         "commission_type"],
}  # fmt: skip
DATES = {
    "policies": ("effective_date", "termination_date"),
    "clients": ("dob",),
    "commission_lines": ("member_dob",),
}
_PERIOD = re.compile(r"(\d{4})-(\d{1,2})")


@dataclass(frozen=True)
class Prepared:
    frames: dict[str, pl.DataFrame]  # COLUMNS plus _rec; lines add amount_raw, amount_problem
    lineage: dict[str, list[Lineage]]  # table -> lineage by _rec
    skipped: dict[str, int]  # "table.field" -> non-blank values that could not be read


def _iso_date(value: str | None) -> str | None:
    parsed = parse_date_loose(value or "")
    return parsed.isoformat() if parsed else None


def _period(value: str | None) -> str | None:
    """'2026-08', '2026-8', or any date inside the month -> '2026-08'."""
    text = (value or "").strip()
    if match := _PERIOD.fullmatch(text):
        year, month = int(match[1]), int(match[2])
        return f"{year:04d}-{month:02d}" if 1 <= month <= 12 else None
    parsed = parse_date_loose(text)
    return f"{parsed.year:04d}-{parsed.month:02d}" if parsed else None


def _amount(value: str | None) -> tuple[str | None, str | None]:
    try:
        amount = parse_money(value)
    except NotMoney:
        return None, "NOT_A_NUMBER"
    return (None, "BLANK") if amount is None else (str(amount), None)


def _lineage(frame: pl.DataFrame, run_id: str) -> list[Lineage]:
    if "lineage" in frame.columns:
        return [Lineage(**cells) for cells in frame["lineage"].to_list()]
    flat = frame.select("_source_file", "_row_number", "_raw_hash").iter_rows()
    return [
        Lineage(source_file=f, sheet=None, row_number=n, raw_hash=h, run_id=run_id,
                mapping_version=CANONICAL_MAPPING)
        for f, n, h in flat
    ]  # fmt: skip


def _read(frame: pl.DataFrame, column: str, fn: Callable[[str | None], Any]) -> list[Any]:
    return [fn(v) for v in frame[column].to_list()]


def prepare(tables: Mapping[str, pl.DataFrame | None], run_id: str) -> Prepared:
    frames, lineage, skipped = {}, {}, {}
    for name, columns in COLUMNS.items():
        raw = tables.get(name)
        if raw is None:
            raw = pl.DataFrame(schema={**dict.fromkeys(columns, pl.String), "lineage": pl.Null})
        lineage[name] = _lineage(raw, run_id) if raw.height else []
        frame = raw.select(
            pl.col(c) if c in raw.columns else pl.lit(None, dtype=pl.String).alias(c)
            for c in columns
        ).with_columns(pl.int_range(pl.len(), dtype=pl.Int64).alias(REC))
        cleaned: dict[str, list[Any]] = {}
        for column in DATES[name]:
            cleaned[column] = _read(frame, column, _iso_date)
        if name == "commission_lines":
            cleaned["statement_period"] = _read(frame, "statement_period", _period)
            cleaned["amount_raw"] = frame["amount"].to_list()  # as sent, for the finding
            amounts = _read(frame, "amount", _amount)
            cleaned["amount"] = [a for a, _ in amounts]
            cleaned["amount_problem"] = [p for _, p in amounts]
        for column, values in cleaned.items():
            if column in frame.columns and column != "amount":
                bad = sum(
                    1 for raw_v, v in zip(frame[column].to_list(), values, strict=True)
                    if (raw_v or "").strip() and v is None
                )  # fmt: skip
                if bad:
                    skipped[f"{name}.{column}"] = bad
        if name == "commission_lines":
            bad = sum(p is not None for p in cleaned["amount_problem"])
            if bad:
                skipped["commission_lines.amount"] = bad
        frames[name] = frame.with_columns(
            pl.Series(c, v, dtype=pl.String) for c, v in cleaned.items()
        )
    for where, n in skipped.items():
        log.warning("Tie-out could not read %d values of %s", n, where)
    return Prepared(frames, lineage, skipped)

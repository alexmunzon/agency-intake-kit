"""The two frames row rules read, and the one place their exceptions are built.

Client rules read the client frame: canonical client rows plus `lineage` and `as_of` (the
run date). Policy rules read the policy frame: policy rows plus the client's dob, mbi, and
lineage (`client_dob`, `client_mbi`, `client_lineage`), whether the writing agent is in the
roster (`agent_in_roster`), and `as_of`. A rule handed the other frame returns nothing.
"""

import hashlib
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any

import polars as pl

from agency_schema.enums import Family, Lane, LineOfBusiness
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.lineage import Lineage
from agency_schema.registry import catalog

Row = dict[str, Any]
MEDICARE = frozenset({LineOfBusiness.MA, LineOfBusiness.PDP, LineOfBusiness.MEDSUPP})
MA_PDP = frozenset({LineOfBusiness.MA, LineOfBusiness.PDP})


def client_frame(clients: pl.DataFrame, as_of: date) -> pl.DataFrame:
    return clients.with_columns(as_of=pl.lit(as_of))


def policy_frame(
    policies: pl.DataFrame, clients: pl.DataFrame, agents: pl.DataFrame, as_of: date
) -> pl.DataFrame:
    """Policies with the client fields policy rules need. Duplicate client ids keep the first."""
    client = clients.unique("client_id", keep="first", maintain_order=True).select(
        "client_id",
        client_dob="dob",
        client_mbi="mbi",
        client_lineage="lineage",
    )
    roster = agents["npn"].drop_nulls().str.strip_chars().to_list()
    return policies.join(client, on="client_id", how="left", maintain_order="left").with_columns(
        agent_in_roster=pl.col("writing_agent_npn").str.strip_chars().is_in(roster),
        as_of=pl.lit(as_of),
    )


def client_rows(frame: pl.DataFrame) -> Iterator[Row]:
    if "client_id" in frame.columns and "policy_id" not in frame.columns:
        yield from frame.iter_rows(named=True)


def policy_rows(frame: pl.DataFrame) -> Iterator[Row]:
    if "policy_id" in frame.columns:
        yield from frame.iter_rows(named=True)


def raw(row: Row, field: str) -> str | None:
    """The value as the source wrote it: `<field>_raw` when canonicalizing normalized it (#58)."""
    return row.get(f"{field}_raw", row.get(field))


def norm(value: str | None) -> str:
    """Trimmed and uppercased, so " ma " compares equal to MA. Blank stays blank."""
    return (value or "").strip().upper()


def shown(value: str | None) -> str:
    """How a value appears in a message: always minimized, never raw."""
    return minimize_value(value) or "(blank)"


def age_on(born: date, on: date) -> int:
    return on.year - born.year - ((on.month, on.day) < (born.month, born.day))


def hit(
    rule_id: str,
    row: Row,
    field: str,
    value: str | None,
    message: str,
    fix: str,
    *,
    lineage: str = "lineage",
    extra: str = "",
) -> ExceptionRecord:
    """Build one row-level ExceptionRecord. Severity comes from the registry, never retyped."""
    meta = next(m for m in catalog() if m.rule_id == rule_id)
    where = Lineage(**row[lineage])
    key = f"{rule_id}|{where.source_file}|{where.sheet}|{where.row_number}|{field}|{extra}"
    return ExceptionRecord(
        id=f"{rule_id}-{hashlib.sha256(key.encode()).hexdigest()[:12]}",
        rule_id=rule_id,
        severity=meta.severity,
        family=Family(rule_id[:3]),
        source=Path(where.source_file).stem,
        row_number=where.row_number,
        raw_hash=where.raw_hash,
        field=field,
        value_minimized=minimize_value(value),
        message=message,
        suggested_fix=fix,
        blocks_load=False,
        lane=Lane.UNREVIEWED,
        jev=None,
        lineage=where,
    )

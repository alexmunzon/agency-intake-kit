"""clean/: the load-ready tables, written only when no blocker fired (#63).

An error keeps its row out of the table it is about, matched by lineage (file, sheet, row),
never by row number alone: a client rule (DOB, MBI-001, ADR) removes the client, any other
error on a CRM row removes the policy and leaves its client (an RTS gap excludes the policy,
not the person). A policy whose client stayed out stays out too, since it cannot load alone.
A duplicated policy keeps one copy: the first row of each policy id. Warnings pass with their
rule ids in a `warnings` column. Each row keeps its lineage as lineage_* columns. Dates are
real dates and money is Decimal(12, 2) in Parquet, never a float; CSV holds the same values.
"""

from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from pathlib import Path

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from intake.config import LIST_SEPARATOR
from intake.run.canonicalize import DATES, FIELDS, MONEY

LINEAGE_FIELDS = ("source_file", "sheet", "row_number", "raw_hash", "run_id", "mapping_version")
UNIT = ["_file", "_sheet", "_row"]
CLIENT_RULES = frozenset({"DOB-001", "DOB-002", "MBI-001", "ADR-001", "ADR-002", "ADR-003"})
WHOLE = {"line_no": pl.Int64, "plan_year": pl.Int64}
FLAGS = ("appointed", "certified")


def _units(
    records: Iterable[ExceptionRecord], keep: AbstractSet[str] | None = None
) -> pl.DataFrame:
    rows = [
        (r.lineage.source_file, r.lineage.sheet, r.lineage.row_number, r.rule_id)
        for r in records
        if r.lineage is not None and (keep is None or r.rule_id in keep)
    ]
    schema = {"_file": pl.String, "_sheet": pl.String, "_row": pl.Int64, "_rule": pl.String}
    return pl.DataFrame(rows, schema=schema, orient="row")


def _flat(frame: pl.DataFrame) -> pl.DataFrame:
    lin = pl.col("lineage").struct
    return frame.with_columns(
        lin.field("source_file").alias("_file"),
        lin.field("sheet").alias("_sheet"),
        lin.field("row_number").alias("_row"),
    )


def excluded_units(records: list[ExceptionRecord], table: str) -> pl.DataFrame:
    """The (file, sheet, row) units whose errors keep them out of this table.

    Households follow their primary client instead: their lineage is that client's CRM row,
    which also holds a policy whose errors are no reason to drop the household.
    """
    errors = [r for r in records if r.severity == Severity.ERROR]
    every = {r.rule_id for r in errors}
    rules = {"clients": CLIENT_RULES, "policies": every - CLIENT_RULES, "households": set()}
    return _units(errors, rules.get(table, every)).select(UNIT).unique()


def clean_tables(
    tables: Mapping[str, pl.DataFrame], records: list[ExceptionRecord]
) -> dict[str, pl.DataFrame]:
    warnings = (
        _units(r for r in records if r.severity == Severity.WARNING)
        .unique()
        .sort("_rule")
        .group_by(UNIT, maintain_order=True)
        .agg(pl.col("_rule").str.join(LIST_SEPARATOR).alias("warnings"))
    )
    out: dict[str, pl.DataFrame] = {}
    for name, frame in tables.items():
        kept = _flat(frame).join(
            excluded_units(records, name), on=UNIT, how="anti", nulls_equal=True
        )
        out[name] = kept.join(warnings, on=UNIT, how="left", nulls_equal=True)
    if "policies" in out:
        policies = out["policies"].unique("policy_id", keep="first", maintain_order=True)
        if "clients" in out:
            clients = out["clients"].select("client_id")
            policies = policies.join(clients, on="client_id", how="semi")
        out["policies"] = policies
    if "clients" in out and "households" in out:
        primary = out["clients"].select(pl.col("client_id").alias("primary_client_id"))
        out["households"] = out["households"].join(primary, on="primary_client_id", how="semi")
    lin = pl.col("lineage").struct
    return {
        name: _typed(
            frame.select(
                *FIELDS[name],
                "warnings",
                *(lin.field(f).alias(f"lineage_{f}") for f in LINEAGE_FIELDS),
            )
        )
        for name, frame in out.items()
    }


def _typed(frame: pl.DataFrame) -> pl.DataFrame:
    """Dates as Date, money as Decimal(12, 2), whole numbers as Int64, flags as Boolean."""
    casts = []
    for column in frame.columns:
        if column in DATES:
            casts.append(pl.col(column).str.to_date("%Y-%m-%d", strict=False))
        elif column in MONEY:
            casts.append(pl.col(column).cast(pl.Decimal(12, 2), strict=False))
        elif column in WHOLE:
            casts.append(pl.col(column).cast(WHOLE[column], strict=False))
        elif column in FLAGS:
            casts.append(pl.col(column) == "true")
    return frame.with_columns(casts)


def write_clean(clean: Mapping[str, pl.DataFrame], run_dir: Path) -> None:
    folder = run_dir / "clean"
    folder.mkdir()
    for name, frame in clean.items():
        frame.write_csv(folder / f"{name}.csv")
        frame.write_parquet(folder / f"{name}.parquet")


def clean_row_count(clean: Mapping[str, pl.DataFrame]) -> int:
    """Distinct source rows that reached clean/ (one CRM row can feed a client and a policy)."""
    cols = ["lineage_source_file", "lineage_sheet", "lineage_row_number"]
    units = [frame.select(cols) for frame in clean.values()]
    return pl.concat(units).unique().height if units else 0

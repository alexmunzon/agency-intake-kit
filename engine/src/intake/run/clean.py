"""clean/: the load-ready tables, written only when no blocker fired (#63).

An error keeps its row out of the table it is about, matched by lineage (file, sheet, row),
never by row number alone: a client rule (DOB, MBI-001, ADR) removes the client, any other
error on a CRM row removes the policy and leaves its client (an RTS gap excludes the policy,
not the person). A policy whose client stayed out stays out too, since it cannot load alone.
A duplicated policy keeps one copy: the first row of each policy id. Warnings pass with their
rule ids in a `warnings` column. Each row keeps its lineage as lineage_* columns. Dates are
real dates and money is Decimal(12, 2) in Parquet, never a float; CSV holds the same values.
"""

import logging
from collections.abc import Iterable, Mapping
from collections.abc import Set as AbstractSet
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from agency_schema.enums import PolicyStatus, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.models import TABLE_MODELS
from intake.config import LIST_SEPARATOR
from intake.rules import catalog as _catalog  # noqa: F401 (registers MAP-004)
from intake.rules.frames import hit
from intake.run.canonicalize import DATES, FIELDS, MONEY

log = logging.getLogger(__name__)
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
    errors = [r for r in records if r.severity == Severity.ERROR and r.rule_id != "MAP-004"]
    every = {r.rule_id for r in errors}
    rules = {"clients": CLIENT_RULES, "policies": every - CLIENT_RULES, "households": set()}
    targeted = [
        r for r in records if r.rule_id == "MAP-004" and (r.field or "").startswith(f"{table}.")
    ]
    return (
        pl.concat([_units(errors, rules.get(table, every)), _units(targeted)]).select(UNIT).unique()
    )


def clean_tables(
    tables: Mapping[str, pl.DataFrame], records: list[ExceptionRecord]
) -> dict[str, pl.DataFrame]:
    """Build load tables and retain every schema error in the caller's records list.

    The pipeline collects these errors before status/triage. Direct callers receive the
    same visible evidence; invalid rows and the existing client dependents are excluded.
    """
    clean = _clean_tables(tables, records)
    invalid = _schema_records(clean, tables)
    invalid += _dependent_records(clean, invalid)
    if invalid:
        records.extend(invalid)
        clean = _clean_tables(tables, records)
    return clean


def clean_model_records(
    tables: Mapping[str, pl.DataFrame], records: list[ExceptionRecord]
) -> list[ExceptionRecord]:
    """Validate prospective load rows before run status or files are calculated."""
    clean = _clean_tables(tables, records)
    invalid = _schema_records(clean, tables)
    return invalid + _dependent_records(clean, invalid)


def _schema_records(
    clean: Mapping[str, pl.DataFrame], raw: Mapping[str, pl.DataFrame]
) -> list[ExceptionRecord]:
    records = []
    source_rows = {}
    for table, frame in clean.items():
        model = TABLE_MODELS[table]
        for row in frame.iter_rows(named=True):
            lineage = {f: row[f"lineage_{f}"] for f in LINEAGE_FIELDS}
            values = {f: row.get(f) for f in model.model_fields if f != "lineage"}
            for field in ("members", "license_states"):
                if field in values:
                    values[field] = (
                        tuple((values[field] or "").split(LIST_SEPARATOR)) if values[field] else ()
                    )
            try:
                model.model_validate({**values, "lineage": lineage})
            except ValidationError as exc:
                if table not in source_rows:
                    source_rows[table] = {
                        (
                            r["lineage"]["source_file"],
                            r["lineage"]["sheet"],
                            r["lineage"]["row_number"],
                        ): r
                        for r in raw[table].iter_rows(named=True)
                    }
                original_row = source_rows[table][
                    (lineage["source_file"], lineage["sheet"], lineage["row_number"])
                ]
                for error in exc.errors(
                    include_input=False, include_context=False, include_url=False
                ):
                    field = ".".join(str(part) for part in error["loc"])
                    original = original_row.get(str(error["loc"][0]))
                    records.append(
                        hit(
                            "MAP-004",
                            {"lineage": lineage},
                            f"{table}.{field}",
                            None if original is None else str(original),
                            f"{table}: {field} is missing or invalid for the load file",
                            "Correct the required or invalid field before loading this row",
                        )
                    )
    return records


def _dependent_records(
    clean: Mapping[str, pl.DataFrame], invalid: list[ExceptionRecord]
) -> list[ExceptionRecord]:
    """Keep evidence for rows that cannot load after a required parent fails validation."""
    failures = {
        (r.field.split(".")[0], r.lineage.source_file, r.lineage.sheet, r.row_number)
        for r in invalid
        if r.field and r.lineage
    }
    bad = {}
    for table, key in (("clients", "client_id"), ("agents", "npn")):
        frame = clean.get(table)
        bad[table] = (
            {
                row[key]
                for row in frame.iter_rows(named=True)
                if (
                    table,
                    row["lineage_source_file"],
                    row["lineage_sheet"],
                    row["lineage_row_number"],
                )
                in failures
            }
            if frame is not None
            else set()
        )
    records = []
    seen = {r.id for r in invalid}
    for table, field, parent in (
        ("policies", "client_id", "clients"),
        ("households", "primary_client_id", "clients"),
        ("policies", "writing_agent_npn", "agents"),
        ("rts", "npn", "agents"),
    ):
        frame = clean.get(table)
        if frame is None or not bad[parent]:
            continue
        for row in frame.iter_rows(named=True):
            if row[field] not in bad[parent]:
                continue
            record = hit(
                "MAP-004",
                {"lineage": {f: row[f"lineage_{f}"] for f in LINEAGE_FIELDS}},
                f"{table}.{field}",
                row[field],
                f"{table}: {field} references a {parent} row excluded from the load file",
                "Correct the required parent row before loading this dependent row",
            )
            if record.id not in seen:
                records.append(record)
                seen.add(record.id)
    return records


def _clean_tables(
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
        client_ids = set(out["clients"]["client_id"])
        out["households"] = out["households"].with_columns(
            pl.col("members").map_elements(
                lambda value: LIST_SEPARATOR.join(
                    member for member in value.split(LIST_SEPARATOR) if member in client_ids
                ),
                return_dtype=pl.String,
            )
        )
    lin = pl.col("lineage").struct
    return {
        name: _typed(
            frame.select(
                *FIELDS[name],
                "warnings",
                *(lin.field(f).alias(f"lineage_{f}") for f in LINEAGE_FIELDS),
            ),
            name,
        )
        for name, frame in out.items()
    }


def _typed(frame: pl.DataFrame, table: str = "") -> pl.DataFrame:
    """Dates as Date, money as Decimal(12, 2), whole numbers as Int64, flags as Boolean.

    A value that does not cast (money no rule judges, such as a premium that is not a number)
    becomes null in clean/; each such column is counted and logged so the loss is never silent.
    A flag that is not a recognized yes is false, which never grants RTS by accident.
    """
    casts = {}
    for column in frame.columns:
        if column in DATES:
            casts[column] = pl.col(column).str.to_date("%Y-%m-%d", strict=False)
        elif column in MONEY:
            casts[column] = pl.col(column).cast(pl.Decimal(12, 2), strict=False)
        elif column in WHOLE:
            casts[column] = pl.col(column).cast(WHOLE[column], strict=False)
        elif column in FLAGS:
            casts[column] = pl.col(column) == "true"
    typed = frame.with_columns(expr.alias(c) for c, expr in casts.items())
    if table == "policies" and "status" in typed.columns:
        # STA-001 keeps the raw value in the exception; the load table uses its promised fix.
        typed = typed.with_columns(
            pl.when(pl.col("status").is_in([status.value for status in PolicyStatus]))
            .then(pl.col("status"))
            .otherwise(pl.lit("UNKNOWN"))
            .alias("status")
        )
    for column in casts:
        if column in FLAGS:
            continue
        lost = typed.filter(pl.col(column).is_null() & frame[column].is_not_null()).height
        if lost:
            log.warning(
                "clean/%s: %d %s values could not be typed and are blank", table, lost, column
            )
    return typed


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

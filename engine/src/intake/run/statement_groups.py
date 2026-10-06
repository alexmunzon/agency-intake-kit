"""Observed statement dimensions, separate from the unchanged received-amount ledger."""

import re
from pathlib import Path
from typing import Literal, Self

from pydantic import model_validator

from agency_schema.lineage import Lineage, NonEmpty, StrictModel
from intake.ingest import IngestResult
from intake.mapping.headers import mapping_key
from intake.mapping.store import load_mapping, mapping_dir_for
from intake.mapping.synonyms import Target, load_synonyms, normalize_header
from intake.readers import RawTable
from intake.run.statement_totals import StatementTotals


def _period(value: str | None) -> str | None:
    text = value.strip() if value else ""
    return text if re.fullmatch(r"(?!0000)[0-9]{4}-(0[1-9]|1[0-2])", text) else None


class StatementDimensions(StrictModel):
    lineage: Lineage
    carrier: str | None
    statement_period: str | None

    @model_validator(mode="after")
    def canonical_dimensions(self) -> Self:
        if self.carrier is not None and (not self.carrier or self.carrier != self.carrier.strip()):
            raise ValueError("carrier must be nonblank trimmed text or null")
        if self.statement_period is not None and self.statement_period != _period(
            self.statement_period
        ):
            raise ValueError("statement period must be canonical YYYY-MM or null")
        return self


class StatementGroups(StrictModel):
    schema_version: Literal[1] = 1
    run_id: NonEmpty
    lines: tuple[StatementDimensions, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        if any(line.lineage.run_id != self.run_id for line in self.lines):
            raise ValueError("statement dimensions are from another run")
        locations = [
            (line.lineage.source_file, line.lineage.sheet, line.lineage.row_number)
            for line in self.lines
        ]
        if len(locations) != len(set(locations)):
            raise ValueError("duplicate statement dimension location")
        return self


def _header(table: RawTable, drop: Path, field: str) -> str | None:
    """Honor saved decisions; exact carrier aliases apply only to this evidence artifact."""
    stored = load_mapping(mapping_dir_for(drop), mapping_key(table.source, table.sheet))
    target = Target("commission_lines", field)
    selected: list[str] = []
    for header in table.frame.columns:
        if header == "lineage":
            continue
        prior = stored.entry(header) if stored else None
        if prior is None or prior.method == "unmapped":
            mapped = load_synonyms().match(header, ("commission_lines",)).target
            if field == "carrier" and normalize_header(header) in ("carrier", "carrier name"):
                mapped = target
        else:
            mapped = Target(prior.table, prior.field) if prior.table and prior.field else None
        if mapped == target:
            selected.append(header)
    return selected[0] if len(selected) == 1 else None


def collect_statement_groups(
    raw: IngestResult, drop: Path, totals: StatementTotals
) -> StatementGroups:
    """Join dimensions to the exact existing amount lines, including excluded amounts.

    Empty or raw-blocked ledgers expose no dimensions. No source-name inference, model
    calls, saved mapping writes, identity attribution, or receipt deduplication occurs.
    """
    dimensions: dict[Lineage, StatementDimensions] = {}
    if totals.lines:
        for table in raw.tables:
            if not table.source.startswith("statement_"):
                continue
            carrier_header = _header(table, drop, "carrier")
            period_header = _header(table, drop, "statement_period")
            for row in table.frame.iter_rows(named=True):
                lineage = Lineage.model_validate(row["lineage"])
                carrier = row[carrier_header] if carrier_header else None
                dimensions[lineage] = StatementDimensions(
                    lineage=lineage,
                    carrier=carrier.strip() or None if carrier else None,
                    statement_period=_period(row[period_header] if period_header else None),
                )
    return StatementGroups(
        run_id=totals.run_id,
        lines=tuple(dimensions[line.lineage] for line in totals.lines),
    )

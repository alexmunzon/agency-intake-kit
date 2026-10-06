"""Signed received-statement amounts when no CRM book is available.

This review artifact never changes reconciliation, load status, or clean outputs.
"""

from decimal import Decimal, DecimalException
from pathlib import Path
from typing import Literal, Self

from pydantic import StrictInt, model_validator

from agency_schema.lineage import Lineage, NonEmpty, StrictModel
from intake.ingest import IngestResult
from intake.mapping.headers import mapping_key
from intake.mapping.store import load_mapping, mapping_dir_for
from intake.mapping.synonyms import Target, load_synonyms
from intake.normalize import MONEY_LIMIT, NotMoney, parse_money
from intake.readers import RawTable

CENT = Decimal("0.01")
LineReason = Literal["valid", "amount_blank", "amount_malformed", "amount_mapping_unavailable"]
Status = Literal["AVAILABLE", "PARTIAL", "UNAVAILABLE", "BLOCKED"]
StatusReason = Literal["excluded_rows", "no_statements", "no_statement_rows", "raw_gate_blocked"]


class StatementAmount(StrictModel):
    source: NonEmpty
    lineage: Lineage
    amount: str | None
    reason: LineReason

    @model_validator(mode="after")
    def valid_amount(self) -> Self:
        if not self.source.startswith("statement_"):
            raise ValueError("statement line needs a statement source")
        if self.reason == "valid":
            if self.amount is None or not _is_cents(self.amount):
                raise ValueError("a valid statement line needs a two-place amount")
        elif self.amount is not None:
            raise ValueError("an excluded statement line cannot claim an amount")
        return self


class StatementTotals(StrictModel):
    schema_version: Literal[1] = 1
    run_id: NonEmpty
    status: Status
    reason: StatusReason | None
    valid_line_count: StrictInt
    excluded_line_count: StrictInt
    total_paid: str | None
    lines: tuple[StatementAmount, ...]

    @model_validator(mode="after")
    def consistent(self) -> Self:
        valid = [line for line in self.lines if line.reason == "valid"]
        if self.valid_line_count != len(valid) or self.excluded_line_count != len(self.lines) - len(
            valid
        ):
            raise ValueError("statement line counts disagree")
        if any(line.lineage.run_id != self.run_id for line in self.lines):
            raise ValueError("statement line is from another run")
        if self.total_paid != (
            _money_text(sum((Decimal(line.amount) for line in valid if line.amount), Decimal(0)))
            if valid
            else None
        ):
            raise ValueError("statement total disagrees with valid lines")
        expected = (
            ("BLOCKED", "raw_gate_blocked")
            if self.status == "BLOCKED"
            else ("UNAVAILABLE", self.reason)
            if self.status == "UNAVAILABLE"
            else ("PARTIAL", "excluded_rows")
            if self.excluded_line_count
            else ("AVAILABLE", None)
        )
        if (self.status, self.reason) != expected:
            raise ValueError("statement status and reason disagree")
        if self.status == "UNAVAILABLE" and self.reason not in (
            "no_statements",
            "no_statement_rows",
        ):
            raise ValueError("unavailable statement reason is invalid")
        if self.status in ("BLOCKED", "UNAVAILABLE") and self.lines:
            raise ValueError("blocked or unavailable statements cannot have lines")
        if self.status == "AVAILABLE" and not self.lines:
            raise ValueError("available statements need valid rows")
        locations = [
            (line.lineage.source_file, line.lineage.sheet, line.lineage.row_number)
            for line in self.lines
        ]
        if len(locations) != len(set(locations)):
            raise ValueError("duplicate statement row location")
        return self


def _is_cents(value: str) -> bool:
    try:
        amount = Decimal(value)
        return bool(
            amount.is_finite() and abs(amount) < MONEY_LIMIT and value == _money_text(amount)
        )
    except DecimalException:
        return False


def _money_text(value: Decimal) -> str:
    return f"{Decimal(0) if value == 0 else value:.2f}"


def _amount_header(table: RawTable, drop: Path) -> str | None:
    """Read prior decisions, including manual ignore, without writing mapping files."""
    stored = load_mapping(mapping_dir_for(drop), mapping_key(table.source, table.sheet))
    target = Target("commission_lines", "amount")
    selected: list[str] = []
    for header in table.frame.columns:
        if header == "lineage":
            continue
        prior = stored.entry(header) if stored else None
        if prior is None or prior.method == "unmapped":
            mapped = load_synonyms().match(header, ("commission_lines",)).target
        else:
            mapped = Target(prior.table, prior.field) if prior.table and prior.field else None
        if mapped == target:
            selected.append(header)
    return selected[0] if len(selected) == 1 else None


def _line_amount(value: str | None) -> tuple[str | None, LineReason]:
    try:
        amount = parse_money(value)
        if amount is None:
            return None, "amount_blank"
        if amount == amount.quantize(CENT):
            return _money_text(amount), "valid"
    except (NotMoney, DecimalException):
        pass
    return None, "amount_malformed"


def _empty(run_id: str, reason: StatusReason) -> StatementTotals:
    return StatementTotals(
        run_id=run_id,
        status="BLOCKED" if reason == "raw_gate_blocked" else "UNAVAILABLE",
        reason=reason,
        valid_line_count=0,
        excluded_line_count=0,
        total_paid=None,
        lines=(),
    )


def collect_statement_totals(
    raw: IngestResult, drop: Path, run_id: str, raw_blocked: bool
) -> StatementTotals:
    """Collect received source amounts only after raw safety/completeness gates."""
    if raw_blocked:
        return _empty(run_id, "raw_gate_blocked")
    tables = [table for table in raw.tables if table.source.startswith("statement_")]
    if not tables:
        return _empty(run_id, "no_statements")
    lines: list[StatementAmount] = []
    for table in tables:
        header = _amount_header(table, drop)
        values = table.frame[header].to_list() if header else [None] * table.rows
        for value, raw_lineage in zip(values, table.frame["lineage"].to_list(), strict=True):
            amount, reason = _line_amount(value) if header else (None, "amount_mapping_unavailable")
            lines.append(
                StatementAmount(
                    source=table.source,
                    lineage=Lineage.model_validate(raw_lineage),
                    amount=amount,
                    reason=reason,
                )
            )
    lines.sort(
        key=lambda line: (
            line.source,
            line.lineage.source_file,
            line.lineage.sheet or "",
            line.lineage.row_number,
        )
    )
    if not lines:
        return _empty(run_id, "no_statement_rows")
    valid = [line for line in lines if line.reason == "valid"]
    excluded = len(lines) - len(valid)
    return StatementTotals(
        run_id=run_id,
        status="PARTIAL" if excluded else "AVAILABLE",
        reason="excluded_rows" if excluded else None,
        valid_line_count=len(valid),
        excluded_line_count=excluded,
        total_paid=_money_text(
            sum((Decimal(line.amount) for line in valid if line.amount), Decimal(0))
        )
        if valid
        else None,
        lines=tuple(lines),
    )

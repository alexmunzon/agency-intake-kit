"""Standalone synthetic statement review, without customer attribution or journal posting."""

import csv
import hashlib
import io
import json
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from types import MappingProxyType
from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, Field, field_serializer, model_validator

from agency_schema.lineage import Lineage, NonEmpty, Sha256, StrictModel
from agency_schema.models import Money
from intake.exceptions.pii import flagged

Category = Literal["new_business", "renewal", "override", "bonus", "marketing", "unclassified"]
Kind = Literal["payment", "reversal", "adjustment"]
CATEGORIES: tuple[Category, ...] = (
    "new_business",
    "renewal",
    "override",
    "bonus",
    "marketing",
    "unclassified",
)


def _exact_money(value: object) -> object:
    if isinstance(value, (float, bool)):
        raise ValueError("money must be a decimal string or Decimal, never float")
    try:
        amount = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("invalid money") from exc
    if not amount.is_finite() or amount.adjusted() > 9:
        raise ValueError("money must be finite and within supported bounds")
    try:
        if amount != amount.quantize(Decimal("0.01")):
            raise ValueError("money must be finite and exact to the cent")
    except InvalidOperation as exc:
        raise ValueError("money outside supported precision") from exc
    return amount


ExactMoney = Annotated[Money, BeforeValidator(_exact_money)]


def _safe_label(value: object) -> object:
    if isinstance(value, str) and (
        len(value) > 80 or "\n" in value or "\r" in value or flagged(value)
    ):
        raise ValueError("label refused: expected a short non-sensitive statement label")
    return value


Label = Annotated[str, BeforeValidator(_safe_label)]


class RevenueInputRow(StrictModel):
    row_id: NonEmpty
    amount: ExactMoney
    raw_amount: NonEmpty
    raw_category_label: Label | None
    raw_transaction_label: Label | None
    lineage: Lineage

    @model_validator(mode="after")
    def raw_amount_agrees(self) -> Self:
        if _exact_money(self.raw_amount) != self.amount:
            raise ValueError("raw_amount must agree with amount")
        return self


class StatementPackage(StrictModel):
    agency_id: NonEmpty
    carrier: NonEmpty
    period: Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]
    statement_id: NonEmpty
    revision_id: NonEmpty
    content_sha256: Sha256
    expected_row_count: Annotated[int, Field(strict=True, ge=0)]
    rows: tuple[RevenueInputRow, ...]
    control_total: ExactMoney | None = None

    @model_validator(mode="after")
    def complete_rows(self) -> Self:
        if len(self.rows) != self.expected_row_count:
            raise ValueError("expected_row_count does not match rows; package refused")
        if len({row.row_id for row in self.rows}) != len(self.rows):
            raise ValueError("row_id must be unique within a statement revision")
        return self


class RevenueMapping(StrictModel):
    mapping_id: NonEmpty
    carrier: NonEmpty
    version: NonEmpty
    approved_by: NonEmpty | None = None
    approved_at: datetime | None = None
    categories: dict[Annotated[Label, Field(min_length=1)], Category]
    transaction_kinds: dict[Annotated[Label, Field(min_length=1)], Kind]
    accounts: dict[Category, NonEmpty] = Field(default_factory=dict)

    @model_validator(mode="after")
    def approval_metadata(self) -> Self:
        if (self.approved_by is None) != (self.approved_at is None):
            raise ValueError("approval requires both person and timestamp")
        if self.approved_at is not None and self.approved_at.utcoffset() is None:
            raise ValueError("approval timestamp requires a timezone")
        values = [self.mapping_id, self.carrier, self.version, self.approved_by]
        values += (
            list(self.categories) + list(self.transaction_kinds) + list(self.accounts.values())
        )
        if any(value is not None and not value.strip() for value in values):
            raise ValueError("mapping identifiers, labels and accounts cannot be blank")
        for field in ("categories", "transaction_kinds", "accounts"):
            object.__setattr__(self, field, MappingProxyType(dict(getattr(self, field))))
        return self

    @field_serializer("categories", "transaction_kinds", "accounts")
    def serialize_rules(self, value: dict[str, str]) -> dict[str, str]:
        return dict(value)


class RevenueReviewRow(RevenueInputRow):
    category: Category
    transaction_kind: Kind | None
    classification_method: Literal["approved_mapping", "unresolved"]
    unresolved_reasons: tuple[str, ...]
    account_code: str | None
    authoritative_policy_id: None = None


class FinanceReview(StrictModel):
    artifact_type: Literal["neutral_finance_review"] = "neutral_finance_review"
    schema_version: Literal[1] = 1
    agency_id: str
    carrier: str
    period: str
    statement_id: str
    revision_id: str
    content_sha256: str
    mapping_id: str
    mapping_version: str
    mapping_approved: bool
    approved_by: str | None
    approved_at: datetime | None
    mapping_snapshot: RevenueMapping
    mapping_sha256: Sha256
    rows: tuple[RevenueReviewRow, ...]
    category_totals: dict[Category, Decimal]
    statement_total: Decimal
    control_total: Decimal | None
    total_check: Literal["PASS", "FAIL", "NOT_RUN"]


def classify_statement(package: StatementPackage, mapping: RevenueMapping) -> FinanceReview:
    """Reject an invalid package as a whole; classify every valid row exactly once.

    Approval metadata is declared by the caller, not authenticated by this offline tool.
    Raw labels require an exact approved lookup. Sign never supplies missing semantics.
    Statement identity is provenance only; persistent receipt/revision selection is separate.
    """
    if package.carrier != mapping.carrier:
        raise ValueError("mapping carrier does not match statement carrier")
    approved = mapping.approved_by is not None
    rows = []
    totals: dict[Category, Decimal] = dict.fromkeys(CATEGORIES, Decimal("0.00"))
    with localcontext() as context:
        context.prec = 28 + len(str(len(package.rows)))
        for row in package.rows:
            category = mapping.categories.get(row.raw_category_label or "") if approved else None
            kind = (
                mapping.transaction_kinds.get(row.raw_transaction_label or "") if approved else None
            )
            reasons = []
            if not approved:
                reasons.append("mapping_not_approved")
            else:
                if category is None or category == "unclassified":
                    reasons.append("unknown_category_label")
                if kind is None:
                    reasons.append("unknown_transaction_label")
            category = category or "unclassified"
            account = mapping.accounts.get(category) if approved else None
            if account is None:
                reasons.append("missing_account_mapping")
            rows.append(
                RevenueReviewRow(
                    **row.model_dump(),
                    category=category,
                    transaction_kind=kind,
                    classification_method=(
                        "approved_mapping"
                        if approved and kind is not None and category != "unclassified"
                        else "unresolved"
                    ),
                    unresolved_reasons=tuple(reasons),
                    account_code=account,
                )
            )
            totals[category] += row.amount
        statement_total = sum(totals.values(), Decimal("0.00"))
    total_check: Literal["PASS", "FAIL", "NOT_RUN"] = "NOT_RUN"
    if package.control_total is not None:
        total_check = "PASS" if statement_total == package.control_total else "FAIL"
    return FinanceReview(
        **package.model_dump(exclude={"rows", "expected_row_count", "control_total"}),
        mapping_id=mapping.mapping_id,
        mapping_version=mapping.version,
        mapping_approved=approved,
        approved_by=mapping.approved_by,
        approved_at=mapping.approved_at,
        mapping_snapshot=mapping,
        mapping_sha256=hashlib.sha256(
            json.dumps(
                mapping.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest(),
        rows=tuple(rows),
        category_totals=totals,
        statement_total=statement_total,
        control_total=package.control_total,
        total_check=total_check,
    )


def review_json(review: FinanceReview) -> str:
    """Decimal values serialize as strings, without a binary floating point conversion."""
    return review.model_dump_json(indent=2)


def review_csv(review: FinanceReview) -> str:
    """Neutral row review with scope and source lineage; no vendor import assertions."""
    fields = [
        "agency_id",
        "carrier",
        "period",
        "statement_id",
        "revision_id",
        "content_sha256",
        "mapping_id",
        "mapping_version",
        "mapping_approved",
        "approved_by",
        "approved_at",
        "row_id",
        "amount",
        "raw_amount",
        "raw_category_label",
        "raw_transaction_label",
        "category",
        "transaction_kind",
        "classification_method",
        "unresolved_reasons",
        "account_code",
        "authoritative_policy_id",
        *(f"lineage.{field}" for field in Lineage.model_fields),
    ]
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    metadata = review.model_dump(mode="json", include=set(fields[:11]))
    for row in review.rows:
        values = row.model_dump(mode="json", exclude={"lineage", "unresolved_reasons", "amount"})
        values.update(
            {f"lineage.{key}": value for key, value in row.lineage.model_dump(mode="json").items()}
        )
        values.update(metadata)
        values["amount"] = format(row.amount, ".2f")
        values["unresolved_reasons"] = "|".join(row.unresolved_reasons)
        writer.writerow(
            {key: _csv_text(value) if key != "amount" else value for key, value in values.items()}
        )
    return output.getvalue()


def _csv_text(value: object) -> object:
    # Spreadsheet applications may execute text beginning with a formula marker.
    # Preserve originals in JSON; the apostrophe is a CSV-only presentation guard.
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    if isinstance(value, str) and value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value

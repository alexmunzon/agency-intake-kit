"""Finance label mapping approval, separation, and neutral fallback contracts."""

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agency_schema.lineage import Lineage
from intake.revenue import RevenueInputRow, RevenueMapping, StatementPackage, classify_statement


def source_row(category: str, transaction: str, amount: str = "-18.25") -> RevenueInputRow:
    return RevenueInputRow(
        row_id="line-42",
        amount=Decimal(amount),
        raw_amount=amount,
        raw_category_label=category,
        raw_transaction_label=transaction,
        lineage=Lineage(
            source_file="synthetic_statement.csv",
            sheet=None,
            row_number=42,
            raw_hash="4" * 64,
            run_id="synthetic-run",
            mapping_version="carrier-map-v2",
        ),
    )


def statement(row: RevenueInputRow) -> StatementPackage:
    return StatementPackage(
        agency_id="synthetic-agency",
        carrier="Harborline",
        period="2026-09",
        statement_id="statement-2026-09",
        revision_id="revision-1",
        content_sha256="5" * 64,
        expected_row_count=1,
        rows=(row,),
    )


def mapping(*, approved: bool = True, accounts: dict[str, str] | None = None) -> RevenueMapping:
    return RevenueMapping(
        mapping_id="harborline-revenue",
        carrier="Harborline",
        version="v2",
        approved_by="finance-reviewer" if approved else None,
        approved_at=datetime(2026, 10, 5, tzinfo=UTC) if approved else None,
        categories={"Renewal commission": "renewal"},
        transaction_kinds={"Chargeback": "reversal"},
        accounts=accounts if accounts is not None else {"renewal": "4100"},
    )


def test_approved_versioned_mapping_keeps_renewal_chargeback_signed_and_separate() -> None:
    review = classify_statement(
        statement(source_row("Renewal commission", "Chargeback")), mapping()
    )

    row = review.rows[0]
    assert review.mapping_approved is True
    assert review.mapping_version == "v2"
    assert row.category == "renewal"
    assert row.transaction_kind == "reversal"
    assert row.amount == Decimal("-18.25")
    assert review.category_totals["renewal"] == review.statement_total == Decimal("-18.25")
    assert row.classification_method == "approved_mapping"


def test_draft_mapping_does_not_resolve_labels_before_finance_approval() -> None:
    review = classify_statement(
        statement(source_row("Renewal commission", "Chargeback")), mapping(approved=False)
    )

    row = review.rows[0]
    assert review.mapping_approved is False
    assert review.mapping_version == "v2"
    assert row.raw_category_label == "Renewal commission"
    assert row.raw_transaction_label == "Chargeback"
    assert row.category == "unclassified"
    assert row.transaction_kind is None
    assert row.classification_method == "unresolved"
    assert row.unresolved_reasons == ("mapping_not_approved", "missing_account_mapping")
    assert review.category_totals["unclassified"] == review.statement_total == Decimal("-18.25")


def test_unknown_labels_require_exact_lookup_and_remain_visible() -> None:
    review = classify_statement(
        statement(source_row(" renewal commission ", "chargeback")), mapping()
    )

    row = review.rows[0]
    assert row.raw_category_label == " renewal commission "
    assert row.raw_transaction_label == "chargeback"
    assert row.category == "unclassified"
    assert row.transaction_kind is None
    assert row.classification_method == "unresolved"
    assert "unknown_category_label" in row.unresolved_reasons
    assert "unknown_transaction_label" in row.unresolved_reasons
    assert review.category_totals["unclassified"] == review.statement_total == Decimal("-18.25")


def test_missing_account_mapping_leaves_classification_without_an_account_code() -> None:
    review = classify_statement(
        statement(source_row("Renewal commission", "Chargeback")), mapping(accounts={})
    )

    row = review.rows[0]
    assert row.category == "renewal"
    assert row.transaction_kind == "reversal"
    assert row.account_code is None
    assert row.classification_method == "approved_mapping"
    assert row.unresolved_reasons == ("missing_account_mapping",)
    assert review.category_totals["renewal"] == review.statement_total == Decimal("-18.25")


def test_finance_review_preserves_immutable_mapping_snapshot_and_its_hash() -> None:
    source_mapping = mapping()
    review = classify_statement(
        statement(source_row("Renewal commission", "Chargeback")), source_mapping
    )
    snapshot = review.mapping_snapshot.model_dump(mode="json")
    expected_hash = hashlib.sha256(
        json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    assert snapshot == source_mapping.model_dump(mode="json")
    assert review.mapping_sha256 == expected_hash
    with pytest.raises(TypeError):
        review.mapping_snapshot.categories["Renewal commission"] = "bonus"


def test_classifier_refuses_mapping_for_a_different_carrier() -> None:
    foreign_mapping = mapping().model_copy(update={"carrier": "Other Carrier"})

    with pytest.raises(ValueError, match="carrier"):
        classify_statement(
            statement(source_row("Renewal commission", "Chargeback")), foreign_mapping
        )


@pytest.mark.parametrize(
    ("approver", "approved_at"),
    [
        (None, datetime(2026, 10, 5, tzinfo=UTC)),
        ("finance-reviewer", None),
        ("finance-reviewer", datetime(2026, 10, 5)),
    ],
)
def test_mapping_rejects_incomplete_or_timezone_naive_approval(
    approver: str | None, approved_at: datetime | None
) -> None:
    values = mapping(approved=False).model_dump()
    values.update(approved_by=approver, approved_at=approved_at)

    with pytest.raises(ValidationError):
        RevenueMapping(**values)


def test_mapping_refuses_ssn_like_category_label_at_input_boundary() -> None:
    with pytest.raises(ValidationError, match="short non-sensitive statement label"):
        source_row("SSN 000-00-0000", "Chargeback")

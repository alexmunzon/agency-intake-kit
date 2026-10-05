"""Standalone synthetic statement classification and finance-review export contracts."""

import csv
import io
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from agency_schema.lineage import Lineage
from intake.revenue import (
    RevenueInputRow,
    RevenueMapping,
    StatementPackage,
    classify_statement,
    review_csv,
    review_json,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


def lineage(row_number: int) -> Lineage:
    return Lineage(
        source_file="statement.csv",
        sheet=None,
        row_number=row_number,
        raw_hash=f"{row_number:064x}",
        run_id="synthetic-run",
        mapping_version="mapping-v1",
    )


def row(
    number: int,
    amount: str,
    category: str | None = "Recurring commission",
    transaction: str | None = "Payment",
) -> RevenueInputRow:
    return RevenueInputRow(
        row_id=f"line-{number}",
        amount=Decimal(amount),
        raw_amount=amount,
        raw_category_label=category,
        raw_transaction_label=transaction,
        lineage=lineage(number),
    )


def package(*rows: RevenueInputRow, control_total: Decimal | None = None) -> StatementPackage:
    return StatementPackage(
        agency_id="agency-synthetic",
        carrier="Harborline",
        period="2026-09",
        statement_id="stmt-2026-09-a",
        revision_id="rev-1",
        content_sha256="a" * 64,
        expected_row_count=len(rows),
        rows=rows,
        control_total=control_total,
    )


def approved_mapping(**overrides: object) -> RevenueMapping:
    values: dict[str, object] = {
        "mapping_id": "map-harborline-v1",
        "carrier": "Harborline",
        "version": "v1",
        "approved_by": "finance-reviewer",
        "approved_at": NOW,
        "categories": {
            "Recurring commission": "renewal",
            "New commission": "new_business",
            "Override": "override",
            "Bonus": "bonus",
            "Marketing": "marketing",
        },
        "transaction_kinds": {
            "Payment": "payment",
            "Chargeback": "reversal",
            "Correction": "adjustment",
        },
        "accounts": {
            "renewal": "4100",
            "new_business": "4110",
            "override": "4120",
            "bonus": "4130",
            "marketing": "4140",
        },
    }
    values.update(overrides)
    return RevenueMapping(**values)


def test_signed_amounts_keep_revenue_category_and_sum_exactly() -> None:
    statement = package(
        row(1, "125.30", "Recurring commission", "Payment"),
        row(2, "-25.30", "Recurring commission", "Chargeback"),
        row(3, "10.00", "New commission", "Correction"),
        control_total=Decimal("110.00"),
    )

    review = classify_statement(statement, approved_mapping())

    assert [item.amount for item in review.rows] == [
        Decimal("125.30"),
        Decimal("-25.30"),
        Decimal("10.00"),
    ]
    assert [item.category for item in review.rows] == ["renewal", "renewal", "new_business"]
    assert [item.transaction_kind for item in review.rows] == ["payment", "reversal", "adjustment"]
    assert review.category_totals["renewal"] == Decimal("100.00")
    assert review.category_totals["new_business"] == Decimal("10.00")
    assert (
        sum(review.category_totals.values(), Decimal("0"))
        == review.statement_total
        == Decimal("110.00")
    )
    assert review.total_check == "PASS"


@pytest.mark.parametrize("bad_amount", ["1.001", "NaN", "Infinity", "-Infinity"])
def test_rejects_non_cent_or_non_finite_amounts(bad_amount: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        item = row(1, bad_amount)
        classify_statement(package(item), approved_mapping())


def test_rejects_float_amounts_instead_of_accepting_binary_rounding() -> None:
    with pytest.raises((ValueError, ValidationError)):
        item = RevenueInputRow(
            row_id="line-1",
            amount=1.10,
            raw_amount="1.10",
            raw_category_label="Recurring commission",
            raw_transaction_label="Payment",
            lineage=lineage(1),
        )
        classify_statement(package(item), approved_mapping())


def test_unknown_labels_stay_unclassified_and_preserve_exact_signed_total() -> None:
    statement = package(
        row(1, "20.10", "Recurring commission", "Payment"),
        row(2, "-3.05", "Mystery incentive", "Correction"),
    )

    review = classify_statement(statement, approved_mapping())

    unknown = review.rows[1]
    assert unknown.category == "unclassified"
    assert unknown.transaction_kind == "adjustment"
    assert unknown.classification_method == "unresolved"
    assert "unknown_category_label" in unknown.unresolved_reasons
    assert unknown.raw_category_label == "Mystery incentive"
    assert review.category_totals["unclassified"] == Decimal("-3.05")
    assert (
        sum(review.category_totals.values(), Decimal("0"))
        == review.statement_total
        == Decimal("17.05")
    )


def test_missing_transaction_and_account_mapping_remain_reviewable() -> None:
    statement = package(row(1, "6.25", "Recurring commission", "Unfamiliar transaction"))
    mapping = approved_mapping(accounts={})

    review = classify_statement(statement, mapping)

    item = review.rows[0]
    assert item.category == "renewal"
    assert item.transaction_kind is None
    assert item.account_code is None
    assert item.classification_method == "unresolved"
    assert "unknown_transaction_label" in item.unresolved_reasons
    assert "missing_account_mapping" in item.unresolved_reasons
    assert review.category_totals["renewal"] == review.statement_total == Decimal("6.25")


def test_unknown_category_and_transaction_are_unclassified_without_dropping_dollars() -> None:
    review = classify_statement(
        package(row(1, "8.40", "Mystery incentive", "Mystery event")),
        approved_mapping(),
    )

    item = review.rows[0]
    assert item.category == "unclassified"
    assert item.transaction_kind is None
    assert {"unknown_category_label", "unknown_transaction_label"} <= set(item.unresolved_reasons)
    assert review.category_totals["unclassified"] == review.statement_total == Decimal("8.40")


@pytest.mark.parametrize(
    ("control_total", "expected"),
    [(Decimal("10.00"), "PASS"), (Decimal("10.01"), "FAIL"), (None, "NOT_RUN")],
)
def test_statement_control_total_reports_pass_fail_or_not_run(
    control_total: Decimal | None, expected: str
) -> None:
    review = classify_statement(
        package(row(1, "10.00"), control_total=control_total), approved_mapping()
    )
    assert review.statement_total == Decimal("10.00")
    assert review.control_total == control_total
    assert review.total_check == expected


def test_never_assigns_authoritative_policy_identity_and_retains_raw_lineage_in_exports() -> None:
    source_row = row(7, "12.50", "Recurring commission for policy P-00417", "Payment")
    review = classify_statement(package(source_row), approved_mapping())

    assert review.rows[0].authoritative_policy_id is None
    assert review.rows[0].raw_category_label == "Recurring commission for policy P-00417"
    assert review.rows[0].lineage == source_row.lineage

    exported = json.loads(review_json(review))
    assert exported["rows"][0]["amount"] == "12.50"
    assert exported["rows"][0]["authoritative_policy_id"] is None
    assert exported["rows"][0]["raw_category_label"] == "Recurring commission for policy P-00417"
    assert exported["rows"][0]["lineage"]["source_file"] == "statement.csv"
    assert exported["rows"][0]["lineage"]["row_number"] == 7

    csv_rows = list(csv.DictReader(io.StringIO(review_csv(review))))
    assert len(csv_rows) == 1
    assert csv_rows[0]["agency_id"] == "agency-synthetic"
    assert csv_rows[0]["carrier"] == "Harborline"
    assert csv_rows[0]["period"] == "2026-09"
    assert csv_rows[0]["raw_category_label"] == "Recurring commission for policy P-00417"
    assert csv_rows[0]["mapping_version"] == "v1"
    assert csv_rows[0]["lineage.mapping_version"] == "mapping-v1"
    assert csv_rows[0]["lineage.source_file"] == "statement.csv"
    assert csv_rows[0]["lineage.row_number"] == "7"
    assert csv_rows[0]["authoritative_policy_id"] == ""


def test_package_rejects_row_count_mismatch_as_a_whole() -> None:
    with pytest.raises((ValueError, ValidationError)):
        classify_statement(
            StatementPackage(
                agency_id="agency-synthetic",
                carrier="Harborline",
                period="2026-09",
                statement_id="stmt-2026-09-a",
                revision_id="rev-1",
                content_sha256="a" * 64,
                expected_row_count=2,
                rows=(row(1, "1.00"),),
            ),
            approved_mapping(),
        )


def test_legitimate_identical_rows_are_each_counted_once() -> None:
    statement = package(
        row(1, "5.00", "Recurring commission", "Payment"),
        row(2, "5.00", "Recurring commission", "Payment"),
    )

    review = classify_statement(statement, approved_mapping())

    assert len(review.rows) == 2
    assert review.category_totals["renewal"] == review.statement_total == Decimal("10.00")


def test_duplicate_row_ids_are_refused() -> None:
    duplicate = row(1, "5.00", "Recurring commission", "Payment")

    with pytest.raises((ValueError, ValidationError), match="row_id"):
        package(duplicate, duplicate)


def test_csv_guards_formula_text_but_json_preserves_raw_label_and_signed_amount() -> None:
    source = row(8, "-2.50", '  =IMPORTXML("https://invalid.example")', "\tunsafe")
    review = classify_statement(package(source), approved_mapping())

    exported = json.loads(review_json(review))["rows"][0]
    csv_row = next(csv.DictReader(io.StringIO(review_csv(review))))

    assert exported["raw_category_label"] == source.raw_category_label
    assert exported["raw_transaction_label"] == source.raw_transaction_label
    assert csv_row["raw_category_label"].startswith("'  =")
    assert csv_row["raw_transaction_label"] == "'\tunsafe"
    assert csv_row["raw_amount"] == "'-2.50"
    assert csv_row["amount"] == "-2.50"

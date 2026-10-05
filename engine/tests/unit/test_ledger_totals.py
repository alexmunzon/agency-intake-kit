"""Synthetic grouped-ledger totals invariants, independent of integration."""

import hashlib
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from agency_schema.lineage import Lineage
from intake.revenue import RevenueInputRow, RevenueMapping, StatementPackage
from intake.revenue_ledger import StatementReceipt, reconcile_receipts

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def mapping():
    return RevenueMapping(
        mapping_id="mapping",
        carrier="Synthetic Carrier",
        version="v1",
        approved_by="Synthetic Reviewer",
        approved_at=NOW,
        categories={"Renewal": "renewal", "New": "new_business"},
        transaction_kinds={"Pay": "payment", "Reverse": "reversal"},
    )


def package(
    revision: str,
    amounts: tuple[tuple[str, str], ...],
    *,
    agency: str = "agency",
    period: str = "2026-09",
    statement: str = "statement",
) -> StatementPackage:
    rows = tuple(
        RevenueInputRow(
            row_id=f"row-{i}",
            amount=amount,
            raw_amount=amount,
            raw_category_label=category,
            raw_transaction_label="Reverse" if Decimal(amount) < 0 else "Pay",
            lineage=Lineage(
                source_file="synthetic.csv",
                sheet=None,
                row_number=i + 1,
                raw_hash=hashlib.sha256(f"{category}:{amount}".encode()).hexdigest(),
                run_id="synthetic",
                mapping_version="v1",
            ),
        )
        for i, (category, amount) in enumerate(amounts)
    )
    return StatementPackage(
        agency_id=agency,
        carrier="Synthetic Carrier",
        period=period,
        statement_id=statement,
        revision_id=revision,
        content_sha256=revision.encode().hex().ljust(64, "0"),
        expected_row_count=len(rows),
        rows=rows,
        control_total=sum((Decimal(amount) for _, amount in amounts), Decimal("0.00")),
    )


def receipt(number: int, pkg: StatementPackage, replaces: str | None = None) -> StatementReceipt:
    return StatementReceipt(
        receipt_id=f"receipt-{number}",
        received_at=NOW + timedelta(seconds=number),
        package=pkg,
        replaces_revision_id=replaces,
    )


def test_grouped_categories_conserve_active_amounts_per_agency_carrier_period():
    ledger = reconcile_receipts(
        (
            receipt(1, package("A", (("Renewal", "10.25"), ("New", "3.00")), statement="one")),
            receipt(2, package("B", (("Renewal", "-1.25"),), statement="two")),
            receipt(3, package("C", (("Renewal", "7.00"),), agency="other-agency")),
            receipt(4, package("D", (("Renewal", "5.00"),), period="2026-10")),
        ),
        mapping(),
    )

    groups = {(item.agency_id, item.carrier, item.period): item for item in ledger.grouped_totals}
    same_scope = groups[("agency", "Synthetic Carrier", "2026-09")]
    assert same_scope.category_totals["renewal"] == Decimal("9.00")
    assert same_scope.category_totals["new_business"] == Decimal("3.00")
    assert same_scope.statement_total == Decimal("12.00")
    assert sum(same_scope.category_totals.values(), Decimal("0.00")) == same_scope.statement_total
    assert groups[("other-agency", "Synthetic Carrier", "2026-09")].statement_total == Decimal(
        "7.00"
    )
    assert groups[("agency", "Synthetic Carrier", "2026-10")].statement_total == Decimal("5.00")


def test_distinct_statement_ids_in_same_period_both_contribute_to_group():
    ledger = reconcile_receipts(
        (
            receipt(1, package("A", (("Renewal", "10.00"),), statement="statement-1")),
            receipt(2, package("B", (("Renewal", "12.50"),), statement="statement-2")),
        ),
        mapping(),
    )

    assert len(ledger.grouped_totals) == 1
    assert ledger.grouped_totals[0].statement_total == Decimal("22.50")
    assert ledger.grouped_totals[0].category_totals["renewal"] == Decimal("22.50")


def test_conflict_totals_are_separate_from_active_totals():
    ledger = reconcile_receipts(
        (
            receipt(1, package("A", (("Renewal", "10.00"),))),
            receipt(2, package("B", (("Renewal", "15.00"),))),
        ),
        mapping(),
    )

    assert [decision.state for decision in ledger.receipts] == ["active", "conflict"]
    assert ledger.grouped_totals[0].statement_total == Decimal("10.00")
    assert ledger.unresolved_conflict_totals[0].statement_total == Decimal("15.00")
    assert ledger.grouped_totals[0].statement_total != (
        ledger.grouped_totals[0].statement_total
        + ledger.unresolved_conflict_totals[0].statement_total
    )


def test_accepted_new_revision_resolves_conflict_dollars_without_erasing_history():
    conflicted = package("C", (("Renewal", "15.00"),))
    ledger = reconcile_receipts(
        (
            receipt(1, package("A", (("Renewal", "10.00"),))),
            receipt(2, package("B", (("Renewal", "12.00"),)), replaces="A"),
            receipt(3, conflicted, replaces="A"),
            receipt(4, package("D", (("Renewal", "15.00"),)), replaces="B"),
        ),
        mapping(),
    )

    assert [decision.state for decision in ledger.receipts] == [
        "superseded",
        "superseded",
        "conflict",
        "active",
    ]
    assert ledger.grouped_totals[0].statement_total == Decimal("15.00")
    assert ledger.unresolved_conflict_totals == ()
    assert len(ledger.conflicts) == 1
    assert ledger.conflicts[0].statement_total == Decimal("15.00")


def test_negative_replacement_is_exact_and_replaces_positive_active_total():
    ledger = reconcile_receipts(
        (
            receipt(1, package("A", (("Renewal", "10.00"),))),
            receipt(2, package("B", (("Renewal", "-2.35"),)), replaces="A"),
        ),
        mapping(),
    )

    assert [decision.state for decision in ledger.receipts] == ["superseded", "active"]
    assert ledger.grouped_totals[0].category_totals["renewal"] == Decimal("-2.35")
    assert ledger.grouped_totals[0].statement_total == Decimal("-2.35")
    assert ledger.unresolved_conflict_totals == ()

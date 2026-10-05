"""Synthetic receipt conservation and revision acceptance, independent of integration."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from agency_schema.lineage import Lineage
from intake.revenue import RevenueInputRow, RevenueMapping, StatementPackage
from intake.revenue_ledger import StatementReceipt, reconcile_receipts

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def mapping(carrier="Synthetic Carrier"):
    return RevenueMapping(
        mapping_id="mapping",
        carrier=carrier,
        version="v1",
        approved_by="Synthetic Reviewer",
        approved_at=NOW,
        categories={"Renewal": "renewal"},
        transaction_kinds={"Pay": "payment", "Reverse": "reversal"},
    )


def package(
    revision="A",
    amounts=("10.00",),
    agency="agency",
    carrier="Synthetic Carrier",
    period="2026-09",
    statement="statement",
    declared_hash=None,
):
    rows = tuple(
        RevenueInputRow(
            row_id=f"row-{i}",
            amount=amount,
            raw_amount=amount,
            raw_category_label="Renewal",
            raw_transaction_label="Reverse" if Decimal(amount) < 0 else "Pay",
            lineage=Lineage(
                source_file="synthetic.csv",
                sheet=None,
                row_number=i + 1,
                raw_hash=f"{i + 1:064x}",
                run_id="synthetic",
                mapping_version="v1",
            ),
        )
        for i, amount in enumerate(amounts)
    )
    return StatementPackage(
        agency_id=agency,
        carrier=carrier,
        period=period,
        statement_id=statement,
        revision_id=revision,
        content_sha256=declared_hash or revision.encode().hex().ljust(64, "0"),
        expected_row_count=len(rows),
        rows=rows,
        control_total=sum(map(Decimal, amounts), Decimal("0.00")),
    )


def receipt(number, pkg, replaces=None):
    return StatementReceipt(
        receipt_id=f"receipt-{number}",
        received_at=NOW + timedelta(seconds=number),
        package=pkg,
        replaces_revision_id=replaces,
    )


def total(ledger, conflict=False):
    groups = ledger.unresolved_conflict_totals if conflict else ledger.grouped_totals
    return sum((group.statement_total for group in groups), Decimal("0.00"))


def states(ledger):
    return [decision.state for decision in ledger.receipts]


def test_duplicate_delivery_adds_no_money():
    first = package()
    repeat = first.model_copy(update={"revision_id": "delivery-copy"})
    ledger = reconcile_receipts((receipt(1, first), receipt(2, repeat)), mapping())
    assert states(ledger) == ["active", "duplicate"]
    assert total(ledger) == Decimal("10.00")
    assert len(ledger.active_reviews) == 1


def test_identical_legitimate_rows_are_both_counted():
    ledger = reconcile_receipts((receipt(1, package(amounts=("10.00", "10.00"))),), mapping())
    assert total(ledger) == Decimal("20.00")
    assert len(ledger.active_reviews[0].rows) == 2


def test_replacement_activates_only_new_revision():
    ledger = reconcile_receipts(
        (receipt(1, package()), receipt(2, package("B", ("12.00",)), "A")), mapping()
    )
    assert states(ledger) == ["superseded", "active"]
    assert [review.revision_id for review in ledger.active_reviews] == ["B"]
    assert total(ledger) == Decimal("12.00")
    assert len(ledger.revisions) == 2


def test_stale_correction_is_conflict_and_preserves_active_money():
    ledger = reconcile_receipts(
        (
            receipt(1, package()),
            receipt(2, package("B", ("12.00",)), "A"),
            receipt(3, package("C", ("15.00",)), "A"),
        ),
        mapping(),
    )
    assert states(ledger) == ["superseded", "active", "conflict"]
    assert total(ledger) == Decimal("12.00")
    assert total(ledger, True) == Decimal("15.00")


def test_duplicate_superseded_revision_does_not_reactivate():
    first = package()
    ledger = reconcile_receipts(
        (
            receipt(1, first),
            receipt(2, package("B", ("12.00",)), "A"),
            receipt(3, first.model_copy(update={"revision_id": "A-copy"})),
        ),
        mapping(),
    )
    assert states(ledger) == ["superseded", "active", "duplicate"]
    assert total(ledger) == Decimal("12.00")


def test_forged_declared_hash_does_not_suppress_distinct_content():
    first = package()
    altered = package("B", ("99.00",), declared_hash=first.content_sha256)
    ledger = reconcile_receipts((receipt(1, first), receipt(2, altered, "A")), mapping())
    assert states(ledger) == ["active", "conflict"]
    assert total(ledger) == Decimal("10.00")
    assert total(ledger, True) == Decimal("99.00")
    assert ledger.receipts[0].canonical_rows_sha256 != ledger.receipts[1].canonical_rows_sha256


@pytest.mark.parametrize(
    "changes", [{"agency": "other-agency"}, {"period": "2026-10"}, {"statement": "other-statement"}]
)
def test_identical_content_in_distinct_scope_is_not_duplicate(changes):
    ledger = reconcile_receipts(
        (receipt(1, package()), receipt(2, package("B", **changes))), mapping()
    )
    assert states(ledger) == ["active", "active"]
    assert total(ledger) == Decimal("20.00")


def test_carrier_scope_rejects_wrong_mapping_instead_of_conflating():
    with pytest.raises(ValueError):
        reconcile_receipts(
            (receipt(1, package()), receipt(2, package("B", carrier="Other Carrier"))), mapping()
        )
    other = reconcile_receipts(
        (receipt(1, package(carrier="Other Carrier")),), mapping("Other Carrier")
    )
    assert other.grouped_totals[0].carrier == "Other Carrier"
    assert total(other) == Decimal("10.00")


def test_exact_signed_amounts_conserve_negative_total():
    ledger = reconcile_receipts(
        (receipt(1, package(amounts=("0.01", "-0.02", "-10.00"))),), mapping()
    )
    assert total(ledger) == Decimal("-10.01")
    assert ledger.grouped_totals[0].category_totals["renewal"] == Decimal("-10.01")
    assert sum(ledger.grouped_totals[0].category_totals.values()) == Decimal("-10.01")


def test_repeated_conflict_evidence_does_not_double_unresolved_money():
    conflict = package("B", ("15.00",))
    ledger = reconcile_receipts(
        (
            receipt(1, package()),
            receipt(2, conflict),
            receipt(3, conflict.model_copy(update={"revision_id": "B-copy"})),
        ),
        mapping(),
    )
    assert states(ledger) == ["active", "conflict", "duplicate"]
    assert total(ledger) == Decimal("10.00")
    assert total(ledger, True) == Decimal("15.00")
    assert ledger.receipts[2].reason == "duplicate_conflict_evidence"


def test_explicit_current_replacement_can_revert_to_historical_content():
    ledger = reconcile_receipts(
        (
            receipt(1, package()),
            receipt(2, package("B", ("12.00",)), "A"),
            receipt(3, package("C", ("10.00",)), "B"),
        ),
        mapping(),
    )
    assert states(ledger) == ["superseded", "superseded", "active"]
    assert [review.revision_id for review in ledger.active_reviews] == ["C"]
    assert total(ledger) == Decimal("10.00")
    assert total(ledger, True) == Decimal("0.00")

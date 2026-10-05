"""Pure structured receipt ledger. Canonical equivalence is not file-byte verification."""

import hashlib
import json
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal, localcontext
from itertools import pairwise
from typing import Annotated, Literal, Self

from pydantic import BeforeValidator, model_validator

from agency_schema.lineage import NonEmpty, StrictModel
from intake.revenue import (
    CATEGORIES,
    Category,
    FinanceInput,
    FinanceReview,
    RevenueMapping,
    StatementPackage,
)

Scope = tuple[str, str, str, str]


def _received_time(value: object) -> object:
    if not isinstance(value, (datetime, str)):
        raise ValueError("received_at must be an ISO datetime string or datetime")
    if isinstance(value, str):
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("received_at must be an ISO datetime string") from exc
    return value


class StatementReceipt(StrictModel):
    receipt_id: NonEmpty
    received_at: Annotated[datetime, BeforeValidator(_received_time)]
    package: StatementPackage
    replaces_revision_id: NonEmpty | None = None

    @model_validator(mode="after")
    def aware_received_time(self) -> Self:
        if self.received_at.utcoffset() is None:
            raise ValueError("received_at requires a timezone")
        return self


class ReceiptBatch(FinanceInput):
    receipts: tuple[StatementReceipt, ...]


class ReceiptDecision(StrictModel):
    receipt_id: str
    received_at: datetime
    replaces_revision_id: str | None
    logical_key: Scope
    revision_id: str
    canonical_rows_sha256: str
    state: Literal["active", "duplicate", "superseded", "conflict"]
    reason: str | None


class LedgerTotal(StrictModel):
    agency_id: str
    carrier: str
    period: str
    category_totals: dict[Category, Decimal]
    statement_total: Decimal


class RevenueLedger(StrictModel):
    schema_version: Literal[1] = 1
    artifact_type: Literal["neutral_finance_ledger"] = "neutral_finance_ledger"
    receipts: tuple[ReceiptDecision, ...]
    revisions: tuple[StatementPackage, ...]
    active_reviews: tuple[FinanceReview, ...]
    conflicts: tuple[FinanceReview, ...]
    grouped_totals: tuple[LedgerTotal, ...]
    unresolved_conflict_totals: tuple[LedgerTotal, ...]


def canonical_rows_sha256(package: StatementPackage) -> str:
    """Compute from structured evidence; never trust the caller's declared file hash."""
    content = {
        "expected_row_count": package.expected_row_count,
        "control_total": None
        if package.control_total is None
        else format(package.control_total, ".2f"),
        "rows": [
            {
                "row_id": row.row_id,
                "amount": format(row.amount, ".2f"),
                "raw_amount": row.raw_amount,
                "raw_category_label": row.raw_category_label,
                "raw_transaction_label": row.raw_transaction_label,
                "sheet": row.lineage.sheet,
                "row_number": row.lineage.row_number,
                "raw_hash": row.lineage.raw_hash,
            }
            for row in package.rows
        ],
    }
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _totals(reviews: Sequence[FinanceReview]) -> tuple[LedgerTotal, ...]:
    groups: dict[tuple[str, str, str], dict[Category, Decimal]] = {}
    with localcontext() as context:
        context.prec = 28 + len(str(sum(len(review.rows) for review in reviews)))
        for review in reviews:
            scope = (review.agency_id, review.carrier, review.period)
            categories = groups.setdefault(scope, dict.fromkeys(CATEGORIES, Decimal("0.00")))
            for category, amount in review.category_totals.items():
                categories[category] += amount
        return tuple(
            LedgerTotal(
                agency_id=scope[0],
                carrier=scope[1],
                period=scope[2],
                category_totals=categories,
                statement_total=sum(categories.values(), Decimal("0.00")),
            )
            for scope, categories in sorted(groups.items())
        )


def reconcile_receipts(
    receipts: tuple[StatementReceipt, ...], mapping: RevenueMapping
) -> RevenueLedger:
    """Retain every receipt; only unambiguous originals and explicit corrections are active.

    Sequence order is authoritative and must have nondecreasing aware timestamps.
    Conflict dollars are a separate review measure, not additional recognized revenue.
    Identical legitimate source rows remain distinct inside each classified package.
    """
    from intake.revenue import classify_statement

    if len({receipt.receipt_id for receipt in receipts}) != len(receipts):
        raise ValueError("receipt_id must be unique")
    if any(left.received_at > right.received_at for left, right in pairwise(receipts)):
        raise ValueError("receipts must be ordered by received_at")
    decisions: list[ReceiptDecision] = []
    active: dict[Scope, tuple[StatementPackage, FinanceReview, int]] = {}
    canonical_seen: dict[Scope, set[str]] = {}
    revision_seen: dict[Scope, set[str]] = {}
    declared_seen: dict[Scope, dict[str, str]] = {}
    conflict_seen: dict[Scope, set[str]] = {}
    conflicts: list[FinanceReview] = []
    unresolved: dict[tuple[Scope, str], FinanceReview] = {}
    for receipt in receipts:
        package = receipt.package
        scope = (
            package.agency_id,
            package.carrier,
            package.period,
            package.statement_id,
        )
        digest = canonical_rows_sha256(package)
        review = classify_statement(package, mapping)
        known_content = canonical_seen.setdefault(scope, set())
        known_revisions = revision_seen.setdefault(scope, set())
        known_declared = declared_seen.setdefault(scope, {})
        known_conflicts = conflict_seen.setdefault(scope, set())
        current = active.get(scope)
        reason = None
        state: Literal["active", "duplicate", "superseded", "conflict"] = "active"
        collision = known_declared.get(package.content_sha256)
        valid_replacement = (
            current is not None
            and receipt.replaces_revision_id == current[0].revision_id
            and package.revision_id not in known_revisions
        )
        if digest in known_conflicts and not (
            valid_replacement and (collision is None or collision == digest)
        ):
            state = "duplicate"
            reason = "duplicate_conflict_evidence"
        elif collision is not None and collision != digest:
            reason = "declared_hash_collision"
        elif digest in known_content and not valid_replacement:
            if receipt.replaces_revision_id is not None and (
                current is None or receipt.replaces_revision_id != current[0].revision_id
            ):
                reason = "replacement_not_current"
            else:
                state = "duplicate"
        elif package.revision_id in known_revisions:
            reason = "revision_id_reused"
        elif current is None:
            if receipt.replaces_revision_id is not None:
                reason = "replacement_without_original"
        elif receipt.replaces_revision_id != current[0].revision_id:
            reason = "replacement_not_current"
        if reason is not None and state != "duplicate":
            state = "conflict"
            conflicts.append(review)
            unresolved[(scope, digest)] = review
            known_conflicts.add(digest)
        elif state == "active":
            if current is not None:
                previous = decisions[current[2]]
                decisions[current[2]] = previous.model_copy(update={"state": "superseded"})
            active[scope] = (package, review, len(decisions))
            known_conflicts.discard(digest)
            unresolved.pop((scope, digest), None)
            known_content.add(digest)
            known_revisions.add(package.revision_id)
            known_declared[package.content_sha256] = digest
        known_revisions.add(package.revision_id)
        known_declared.setdefault(package.content_sha256, digest)
        decisions.append(
            ReceiptDecision(
                receipt_id=receipt.receipt_id,
                received_at=receipt.received_at,
                replaces_revision_id=receipt.replaces_revision_id,
                logical_key=scope,
                revision_id=package.revision_id,
                canonical_rows_sha256=digest,
                state=state,
                reason=reason,
            )
        )
    active_reviews = tuple(active[scope][1] for scope in sorted(active))
    return RevenueLedger(
        receipts=tuple(decisions),
        revisions=tuple(receipt.package for receipt in receipts),
        active_reviews=active_reviews,
        conflicts=tuple(conflicts),
        grouped_totals=_totals(active_reviews),
        unresolved_conflict_totals=_totals(tuple(unresolved.values())),
    )

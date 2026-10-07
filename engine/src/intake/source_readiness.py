"""Expected coverage with immutable versions and self-contained synthetic evidence.

No identity/financial approval authority. A receipt timestamp is not a source date.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import AwareDatetime, BeforeValidator, Field, model_validator

from agency_schema.lineage import Sha256, StrictModel

Text = Annotated[str, Field(min_length=1, pattern=r"\S")]
Period = Annotated[str, Field(pattern=r"^[0-9]{4}-(0[1-9]|1[0-2])$")]
State = Literal["missing", "stale", "current", "conflicting", "unknown"]


def _iso_date(value: object) -> object:
    if isinstance(value, str):
        if len(value) != 10 or date.fromisoformat(value).isoformat() != value:
            raise ValueError("Source date must be YYYY-MM-DD")
    elif type(value) is not date:
        raise ValueError("Source date must be YYYY-MM-DD")
    return value


def _iso_time(value: object) -> object:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]"
        r"(?:\.[0-9]{1,6})?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])",
        value,
    ):
        raise ValueError("Timestamp must be an ISO string with timezone")
    return value


SourceDate = Annotated[date, BeforeValidator(_iso_date)]
Timestamp = Annotated[AwareDatetime, BeforeValidator(_iso_time)]


class Scope(StrictModel):
    agency_id: Text
    carrier: Text
    file_type: Text
    period: Period

    def key(self) -> tuple[str, str, str, str]:
        return self.agency_id, self.carrier, self.file_type, self.period


class ExpectedFile(Scope):
    minimum_source_date: SourceDate | None
    owner: Text | None
    next_action: Text | None


class FileVersion(Scope):
    version_id: Text
    source_date: SourceDate | None
    file_name: Text
    file_sha256: Sha256
    supersedes_version_id: Text | None


class Receipt(StrictModel):
    receipt_id: Text
    version_id: Text
    received_at: Timestamp
    owner: Text | None
    next_action: Text | None


class Evidence(StrictModel):
    sha256: Sha256
    content: str  # exact UTF-8 synthetic source, carried into onboarding export

    @model_validator(mode="after")
    def verified_bytes(self) -> Self:
        if hashlib.sha256(self.content.encode("utf-8")).hexdigest() != self.sha256:
            raise ValueError("Evidence hash does not match its UTF-8 bytes")
        return self


def _unique(values: list[object], label: str) -> None:
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {label}")


class ReadinessPackage(StrictModel):
    artifact_type: Literal["source_readiness"]
    schema_version: Literal["1.0.0"]
    data_kind: Literal["synthetic"]
    agency_id: Text
    run_id: Text
    intake_run_id: Text | None
    as_of: Timestamp
    expected_inventory: tuple[ExpectedFile, ...] | None
    versions: tuple[FileVersion, ...]
    receipts: tuple[Receipt, ...]
    evidence: tuple[Evidence, ...]

    @model_validator(mode="after")
    def linked_evidence(self) -> Self:
        _unique([v.key() for v in self.expected_inventory or ()], "expected scope")
        _unique([v.version_id for v in self.versions], "version ID")
        _unique([r.receipt_id for r in self.receipts], "receipt ID")
        _unique([e.sha256 for e in self.evidence], "evidence hash")
        if any(
            v.agency_id != self.agency_id
            for v in (*self.versions, *(self.expected_inventory or ()))
        ):
            raise ValueError("Scope agency must match the package agency")
        versions = {v.version_id: v for v in self.versions}
        hashes = {e.sha256 for e in self.evidence}
        for v in self.versions:
            if v.file_sha256 not in hashes:
                raise ValueError("Every version requires its original evidence")
            if v.source_date is not None and v.source_date > self.as_of.date():
                raise ValueError("Source date is after the evaluation clock")
            seen = {v.version_id}
            parent = v.supersedes_version_id
            while parent is not None:
                if parent in seen or parent not in versions:
                    raise ValueError("Correction target is absent or cyclic")
                seen.add(parent)
                previous = versions[parent]
                if previous.key() != v.key():
                    raise ValueError(
                        "Correction target must have the same agency/carrier/type/period"
                    )
                parent = previous.supersedes_version_id
        for r in self.receipts:
            if r.version_id not in versions:
                raise ValueError("Receipt references an absent version")
            if r.received_at > self.as_of:
                raise ValueError("Receipt is after the evaluation clock")
        return self


class CoverageEntry(StrictModel):
    expected: ExpectedFile
    state: State
    reason: str
    active_version_ids: list[str]
    receipt_ids: list[str]


class ReadinessSummary(StrictModel):
    state: State
    complete: bool
    expected_count: int
    current_count: int
    receipt_count: int
    duplicate_receipt_count: int
    entries: list[CoverageEntry]
    unexpected_version_ids: list[str]
    superseded_version_ids: list[str]


def _version_groups(versions: dict[str, FileVersion]) -> dict[str, int]:
    """Identify duplicate versions using the evidence and their canonical ancestry.

    Parent IDs can be aliases themselves. Keeping the parent group in the signature
    also distinguishes a same-byte correction from the version it supersedes.
    Package validation has already checked this graph for absent targets and cycles.
    """
    groups: dict[str, int] = {}
    signatures: dict[tuple[tuple[str, str, str, str], str, date | None, int | None], int] = {}
    for version_id in versions:
        pending = []
        current: str | None = version_id
        while current is not None and current not in groups:
            pending.append(current)
            current = versions[current].supersedes_version_id
        for member in reversed(pending):
            version = versions[member]
            parent = version.supersedes_version_id
            signature = (
                version.key(),
                version.file_sha256,
                version.source_date,
                groups[parent] if parent is not None else None,
            )
            groups[member] = signatures.setdefault(signature, len(signatures))
    return groups


def evaluate(package: ReadinessPackage) -> ReadinessSummary:
    delivered = {r.version_id for r in package.receipts}
    versions = {v.version_id: v for v in package.versions}
    groups = _version_groups(versions)
    superseded: set[str] = set()
    # Only delivered corrections supersede a version; follow the complete chain.
    for version_id in delivered:
        parent = versions[version_id].supersedes_version_id
        while parent is not None:
            superseded.add(parent)
            parent = versions[parent].supersedes_version_id
    superseded_groups = {groups[v] for v in superseded}
    superseded.update(
        version_id for version_id, group in groups.items() if group in superseded_groups
    )
    entries = []
    for expected in package.expected_inventory or ():
        active = sorted(
            (
                v
                for v in package.versions
                if v.key() == expected.key() and v.version_id in delivered - superseded
            ),
            key=lambda v: v.version_id,
        )
        # Identical bytes and source dates are repeated evidence, even under another version ID.
        distinct = {(v.file_sha256, v.source_date) for v in active}
        state: State
        if not active:
            state, reason = (
                "missing",
                "No delivery for this exact agency, carrier, type and period.",
            )
        elif len(distinct) > 1:
            state, reason = (
                "conflicting",
                "Multiple active versions require an explicit correction.",
            )
        elif expected.minimum_source_date is None or active[0].source_date is None:
            state, reason = "unknown", "Source date or freshness cutoff is unknown."
        elif active[0].source_date < expected.minimum_source_date:
            state, reason = "stale", "Source date is earlier than the required cutoff."
        else:
            state, reason = "current", "Delivered source meets the explicit freshness cutoff."
        entries.append(
            CoverageEntry(
                expected=expected,
                state=state,
                reason=reason,
                active_version_ids=[v.version_id for v in active],
                receipt_ids=sorted(
                    r.receipt_id
                    for r in package.receipts
                    if versions[r.version_id].key() == expected.key()
                ),
            )
        )
    scopes = {e.key() for e in package.expected_inventory or ()}
    unexpected = sorted(v.version_id for v in package.versions if v.key() not in scopes)
    states = {e.state for e in entries}
    priority: tuple[State, ...] = ("conflicting", "missing", "unknown", "stale")
    overall: State = next((s for s in priority if s in states), "current")
    if not entries:
        overall = "unknown"
    distinct_receipts = {groups[r.version_id] for r in package.receipts}
    return ReadinessSummary(
        state=overall,
        complete=bool(entries) and overall == "current",
        expected_count=len(entries),
        current_count=sum(e.state == "current" for e in entries),
        receipt_count=len(package.receipts),
        duplicate_receipt_count=len(package.receipts) - len(distinct_receipts),
        entries=entries,
        unexpected_version_ids=unexpected,
        superseded_version_ids=sorted(superseded),
    )


def _object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def parse_package(source: str) -> ReadinessPackage:
    return ReadinessPackage.model_validate(json.loads(source, object_pairs_hook=_object))


def validate_continuity(previous: ReadinessPackage, incoming: ReadinessPackage) -> None:
    """A same-run snapshot may append history, but cannot rewrite its recorded evidence."""
    if (previous.agency_id, previous.run_id) != (incoming.agency_id, incoming.run_id):
        return
    if incoming.as_of < previous.as_of:
        raise ValueError("A same-run snapshot cannot move its evaluation clock backward")
    if previous.intake_run_id is not None and incoming.intake_run_id != previous.intake_run_id:
        raise ValueError("An existing Intake run link cannot change")
    versions = {version.version_id: version for version in incoming.versions}
    if any(versions.get(version.version_id) != version for version in previous.versions):
        raise ValueError("A same-run snapshot must retain every original version unchanged")
    receipts = {receipt.receipt_id: receipt for receipt in incoming.receipts}
    if any(receipts.get(receipt.receipt_id) != receipt for receipt in previous.receipts):
        raise ValueError("A same-run snapshot must retain every original receipt unchanged")
    evidence = {item.sha256: item for item in incoming.evidence}
    if any(evidence.get(item.sha256) != item for item in previous.evidence):
        raise ValueError("A same-run snapshot must retain every original evidence item unchanged")


def import_package(source: str, destination: Path) -> ReadinessPackage:
    """Validate entirely before atomic snapshot replacement; no prior state changes on failure."""
    package = parse_package(source)
    if destination.exists() or destination.is_symlink():
        previous = parse_package(destination.read_text(encoding="utf-8"))
        validate_continuity(previous, package)
    content = package.model_dump_json(indent=2) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".readiness-", dir=destination.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return package

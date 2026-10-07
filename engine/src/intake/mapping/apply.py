"""intake mapping apply: turn a reviewer's decisions file into saved mapping entries.

The decisions file comes from the dashboard's "Download decisions". It is checked against the
run's mapping_review.json and against the drop the decisions will sit beside: the same run,
mapping version, review items, headers, format fingerprints, and only fields that column was
offered. Any mismatch, two decisions that disagree about one column, or two columns that would
map to the same field refuses the whole file before anything is written. Accepted decisions
become manual entries in mapping/<source>.yaml with that file's format fingerprint. Saved
entries for the same format stay; entries saved for another format are never carried over
(interface section 4, amended 2026-10-07). The replaced file is copied to <source>.yaml.prev.

The file is a reviewer's note, not an authenticated approval. It can map or ignore a column;
it can never clear a blocker, lower a severity, or approve a package.
"""

import shutil
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import ValidationError

from agency_schema.mapping_review import (
    MappingDecision,
    MappingDecisions,
    MappingReview,
    MappingReviewItem,
)
from intake.ingest import ingest
from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.headers import SOURCE_TABLES, _shown, mapping_key
from intake.mapping.review import REVIEW_FILE, file_label, item_id
from intake.mapping.store import (
    MappingEntry,
    SourceMapping,
    dump_mapping,
    load_mapping,
    mapping_dir_for,
    mapping_path,
    save_mapping,
)
from intake.mapping.synonyms import Target, is_canonical, load_synonyms
from intake.readers import LINEAGE_COLUMN

PREVIOUS_SUFFIX = ".prev"  # mapping/<source>.yaml.prev keeps the file apply replaced


class ApplyRefused(Exception):  # noqa: N818  (a refusal, not a crash)
    """The decisions file does not fit this run or drop. The message never repeats its input.

    `written` lists files already saved when a write failed part way; it is empty for every
    refusal found while checking, because every check runs before the first write.
    """

    def __init__(self, message: str, written: tuple[Path, ...] = ()) -> None:
        super().__init__(message)
        self.written = written


@dataclass(frozen=True)
class ApplySummary:
    approved: int
    corrected: int
    ignored: int
    files: tuple[Path, ...]


def _read(path: Path, what: str) -> str:
    if path.is_symlink():
        raise ApplyRefused(f"{what} cannot be a symlink")
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        raise ApplyRefused(f"could not read {what}") from None


def _invalid(what: str, error: ValidationError) -> ApplyRefused:
    # Name the fields only: pydantic's text can echo rejected values, such as a header.
    where = sorted({".".join(str(p) for p in e["loc"]) or "file" for e in error.errors()})
    return ApplyRefused(f"{what} is not valid (check: {', '.join(where)})")


def load_decisions(path: Path) -> MappingDecisions:
    try:
        return MappingDecisions.model_validate_json(_read(path, "the decisions file"))
    except ValidationError as error:
        raise _invalid("the decisions file", error) from None


def load_review(run_dir: Path) -> MappingReview:
    path = run_dir / REVIEW_FILE
    if not path.exists() and not path.is_symlink():
        raise ApplyRefused(f"this run has no {REVIEW_FILE}; run it again with this engine")
    try:
        return MappingReview.model_validate_json(_read(path, REVIEW_FILE))
    except ValidationError as error:
        raise _invalid(REVIEW_FILE, error) from None


Files = dict[tuple[str, str], list[str]]  # (mapping key, file name as in the review) -> headers


def drop_headers(drop: Path) -> Files:
    """Each file in the drop with its headers in file order, read as `intake run` does."""
    if drop.is_symlink() or not drop.is_dir():
        raise ApplyRefused("the drop folder is missing or a symlink")
    try:
        tables = ingest(drop, run_id="mapping-apply").tables
    except (OSError, ValueError):
        raise ApplyRefused("could not read the drop folder") from None
    return {
        (mapping_key(t.source, t.sheet), file_label(t)): [
            c for c in t.frame.columns if c != LINEAGE_COLUMN
        ]
        for t in tables
    }


def _kind(key: str) -> str:
    return "statement" if key.startswith("statement_") else key


def _check(n: int, d: MappingDecision, item: MappingReviewItem | None, files: Files) -> list[str]:
    """Refuse a decision that does not fit its review item or the drop; return the file's headers.

    Messages name the decision by number and never repeat a header, a field or other input.
    """
    where = f"decision {n}"
    if item is None:
        raise ApplyRefused(f"{where}: its item is not in this run's mapping review")
    if d.source != item.source:
        raise ApplyRefused(f"{where}: the source does not match the review item")
    if d.header != item.header or d.item_id != item_id(d.source, item.file_name, d.header):
        raise ApplyRefused(f"{where}: the header does not match the review item")
    if d.format_fingerprint != item.format_fingerprint:
        raise ApplyRefused(f"{where}: the format fingerprint does not match the review item")
    if d.action == "approve" and (item.proposed_field is None or d.field != item.proposed_field):
        raise ApplyRefused(f"{where}: approve must keep the proposed field")
    if d.field is not None and d.field not in item.allowed_fields:
        raise ApplyRefused(f"{where}: the field is not an allowed option for this column")
    headers = files.get((d.source, item.file_name))
    if headers is None:
        raise ApplyRefused(f"{where}: the drop has no such file for this source")
    if format_fingerprint(headers) != d.format_fingerprint:
        raise ApplyRefused(f"{where}: the drop's file has a different format than the reviewed run")
    if d.header not in headers:
        if any(_shown(h) == d.header for h in headers):
            raise ApplyRefused(
                f"{where}: that column's header looks like an SSN, so no decision can be saved "
                "for it; remove the column from the export"
            )
        raise ApplyRefused(f"{where}: the drop has no such column for this source")
    if d.field is not None:
        table, field = d.field.split(".")
        if table not in SOURCE_TABLES.get(_kind(d.source), ()) or not is_canonical(
            Target(table, field)
        ):
            raise ApplyRefused(f"{where}: the field is not one this source can map to")
    return headers


def _entry(d: MappingDecision, item: MappingReviewItem, reviewer: str, at: str) -> MappingEntry:
    table, field = d.field.split(".") if d.field else (None, None)
    return MappingEntry(
        header=d.header,
        table=table,
        field=field,
        method="manual",
        confidence=None,
        decided_at=at,
        reviewer=reviewer,
        suggested_field=item.proposed_field,
        suggested_origin=item.origin,
    )


@dataclass(frozen=True)
class Planned:
    key: str
    headers: list[str]  # the reviewed file's headers, in file order
    decided: dict[str, MappingEntry]  # header -> the new manual entry


def _kept(old: SourceMapping | None, plan: Planned) -> dict[str, MappingEntry]:
    """Saved entries still in force for this format: same fingerprint (or none saved), headers
    still in the file, and not decided again now. A changed format keeps nothing (section 4)."""
    if old is None or old.format_fingerprint not in (None, format_fingerprint(plan.headers)):
        return {}
    return {
        e.header: e
        for e in old.entries
        if e.header in plan.headers and e.header not in plan.decided and e.method != "unmapped"
    }


def _check_targets(plan: Planned, kept: dict[str, MappingEntry]) -> None:
    """Refuse when two columns of one source would map to the same field after this apply."""
    tables = SOURCE_TABLES.get(_kind(plan.key), ())
    held: Counter[tuple[str, str]] = Counter()
    for header in plan.headers:
        entry = plan.decided.get(header) or kept.get(header)
        if entry is not None:
            if entry.table and entry.field:
                held[(entry.table, entry.field)] += 1
            continue
        target = load_synonyms().match(header, tables).target
        if target is not None:
            held[(target.table, target.field)] += 1
    for (table, field), count in held.items():
        if count > 1 and any((e.table, e.field) == (table, field) for e in plan.decided.values()):
            raise ApplyRefused(
                f"in {plan.key}, {table}.{field} is already held by another column, so two "
                "columns would map to it; pick a different field or ignore one of them"
            )


def _merged(plan: Planned, kept: dict[str, MappingEntry], at: str) -> SourceMapping:
    """The new saved file: one entry per header of the reviewed file, in file order.

    Decided headers get their manual entry, entries still in force are kept, and every other
    header gets an unmapped entry, which a run treats exactly like no entry. Listing every
    header lets a later run name the added and removed headers if the format changes.
    """
    entries = [
        plan.decided.get(h)
        or kept.get(h)
        or MappingEntry(
            header=h, table=None, field=None, method="unmapped", confidence=None, decided_at=at
        )
        for h in plan.headers
    ]
    return SourceMapping(
        source=plan.key, format_fingerprint=format_fingerprint(plan.headers), entries=tuple(entries)
    )


def _previous_path(mapping_dir: Path, key: str) -> Path | None:
    """Where mapping/<key>.yaml is copied before it is replaced; None when there is no file yet.

    Checks the paths only, so it is safe to call for every source before anything is written.
    """
    path = mapping_path(mapping_dir, key)
    if not path.exists():
        return None
    previous = path.with_name(path.name + PREVIOUS_SUFFIX)
    if previous.is_symlink():
        raise ValueError("refusing to write through a symlink")
    return previous


def apply_decisions(decisions_path: Path, run_dir: Path, drop: Path) -> ApplySummary:
    """Check the whole decisions file, then write mapping/<source>.yaml beside drop/."""
    decisions = load_decisions(decisions_path)
    review = load_review(run_dir)
    if decisions.run_id != review.run_id:
        raise ApplyRefused("the decisions file is for a different run id")
    if decisions.mapping_version != review.mapping_version:
        raise ApplyRefused("the decisions file is for a different mapping version")
    try:
        at = datetime.fromisoformat(decisions.decided_at)
    except ValueError:
        raise ApplyRefused("decided_at is not an ISO 8601 date and time") from None
    if at.tzinfo is None:
        raise ApplyRefused("decided_at needs a time zone")
    files = drop_headers(drop)
    items = {item.item_id: item for item in review.items}
    plans: dict[str, Planned] = {}
    agreed: dict[tuple[str, str], tuple[str, str | None]] = {}
    for n, d in enumerate(decisions.decisions, start=1):
        item = items.get(d.item_id)
        headers = _check(n, d, item, files)
        assert item is not None  # _check refused otherwise
        said = agreed.setdefault((d.source, d.header), (d.action, d.field))
        if said != (d.action, d.field):
            raise ApplyRefused(
                f"decision {n}: another decision for the same column in another file disagrees"
            )
        plan = plans.setdefault(d.source, Planned(d.source, headers, {}))
        if format_fingerprint(plan.headers) != d.format_fingerprint:
            raise ApplyRefused(
                f"decision {n}: decisions for one source come from files with different formats; "
                "apply them from separate reviews"
            )
        plan.decided[d.header] = _entry(d, item, decisions.reviewer, at.isoformat())
    mapping_dir = mapping_dir_for(drop)
    try:
        olds = {key: load_mapping(mapping_dir, key) for key in plans}
        kept = {key: _kept(olds[key], plan) for key, plan in plans.items()}
        for key, plan in plans.items():
            _check_targets(plan, kept[key])
        # Build every new file and check every path first, so a refusal writes nothing.
        merged = {key: _merged(plan, kept[key], at.isoformat()) for key, plan in plans.items()}
        for mapping in merged.values():
            dump_mapping(mapping)
        previous = {key: _previous_path(mapping_dir, key) for key in merged}
    except (OSError, ValueError) as error:
        message = "symlink" if "symlink" in str(error) else "unreadable or invalid"
        raise ApplyRefused(f"the saved mapping folder is {message}") from None
    written: list[Path] = []
    try:
        for key, mapping in merged.items():
            prev = previous[key]
            if prev is not None:
                shutil.copyfile(mapping_path(mapping_dir, key), prev)
            written.append(save_mapping(mapping_dir, mapping))
    except (OSError, ValueError):
        raise ApplyRefused("a saved mapping file could not be written", tuple(written)) from None
    actions = Counter(d.action for d in decisions.decisions)
    return ApplySummary(actions["approve"], actions["correct"], actions["ignore"], tuple(written))

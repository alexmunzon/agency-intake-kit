"""Map one source's headers to canonical fields and raise MAP-001 and MAP-003.

A decision stored in mapping/<key>.yaml wins; otherwise the synonym table decides. The
result is written back, so the next run starts from it and an unchanged file stays unchanged.
A stored file with a format fingerprint is reused only for a file with the same headers;
otherwise nothing in it is reused and MAP-005 (`format_changes`) names what changed.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from agency_schema.enums import Severity
from agency_schema.exceptions import SSN_PATTERN, ExceptionRecord, minimize_value
from intake.config import CARRIED_FIELDS, NINE_DIGIT_PATTERN, REQUIRED_FIELDS
from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.store import (
    MappingEntry,
    SourceMapping,
    dump_mapping,
    load_mapping,
    reusable,
    save_mapping,
)
from intake.mapping.synonyms import COMPOSITE_FIELDS, Target, is_canonical, load_synonyms
from intake.readers import LINEAGE_COLUMN, RawTable, file_exception

# The canonical tables each kind of source feeds. Headers are looked up only in these.
SOURCE_TABLES: dict[str, tuple[str, ...]] = {
    "crm": ("clients", "policies"),
    "enrollment": ("clients", "policies"),
    "statement": ("commission_lines",),
    "roster_agents": ("agents",),
    "roster_rts": ("rts",),
}
# Enrollment rows are checked against the CRM, never loaded on their own, so a field the
# export lacks (it has no client id or address) is no reason to block the run.
NOT_LOADED = frozenset({"enrollment"})


@dataclass(frozen=True)
class MappingResult:
    mapping: SourceMapping
    exceptions: list[ExceptionRecord]
    version: str  # goes into lineage.mapping_version; changes whenever the mapping does


def mapping_key(source: str, sheet: str | None) -> str:
    """The roster has two sheets, so each gets its own mapping file: roster_agents, roster_rts."""
    return f"{source}_{sheet.casefold()}" if source == "roster" and sheet else source


def _kind(key: str) -> str:
    return "statement" if key.startswith("statement_") else key


def _shown(header: str) -> str:
    """A header as outputs and Jev may see it: masked when it looks like an SSN, with or
    without separators (123-45-6789 or 123456789)."""
    risky = SSN_PATTERN.search(header) or re.search(NINE_DIGIT_PATTERN, header)
    return (minimize_value(header) or "") if risky else header


def _target(entry: MappingEntry) -> Target | None:
    return Target(entry.table, entry.field) if entry.table and entry.field else None


def _unmapped(header: str, now: datetime) -> MappingEntry:
    return MappingEntry(
        header=header,
        table=None,
        field=None,
        method="unmapped",
        confidence=None,
        decided_at=now.isoformat(),
    )


def _decide(header: str, tables: tuple[str, ...], now: datetime) -> MappingEntry:
    match = load_synonyms().match(header, tables)
    if match.target is None:
        return _unmapped(header, now)
    return MappingEntry(
        header=header,
        table=match.target.table,
        field=match.target.field,
        method="synonym",
        confidence=1.0,
        decided_at=now.isoformat(),
    )


def _map_001(source: str, key: str, header: str, near: list[Target]) -> ExceptionRecord:
    closest = ", ".join(str(t) for t in near) or "none"
    return file_exception(
        "MAP-001",
        Severity.WARNING,
        source,
        f'"{_shown(header)}" in {key} has no canonical field',
        f"Map manually in mapping/{key}.yaml. Closest fields: {closest}",
    )


def _missing_required(
    source: str, tables: tuple[str, ...], mapped: set[Target]
) -> list[ExceptionRecord]:
    covered = set(mapped)
    for target in mapped:
        covered |= {Target(target.table, f) for f in COMPOSITE_FIELDS.get(target.field, ())}
    records = []
    for table in tables:
        for field in REQUIRED_FIELDS.get(table, ()):
            if Target(table, field) in covered:
                continue
            carrier = CARRIED_FIELDS.get(f"{table}.{field}")
            if carrier is not None and carrier.split(".")[0] in tables:
                continue  # reported once, under the table it is carried from
            record = file_exception(
                "MAP-003",
                Severity.BLOCKER,
                source,
                f"{source} is missing {field} ({table})",
                "Add the column or map an existing one",
            )
            records.append(record.model_copy(update={"field": field}))
    return records


def map_headers(
    source: str, sheet: str | None, headers: list[str], mapping_dir: Path, now: datetime
) -> MappingResult:
    """Map one source's headers, save the mapping, and return it with its exceptions."""
    key = mapping_key(source, sheet)
    tables = SOURCE_TABLES.get(_kind(key), tuple(REQUIRED_FIELDS))
    stored = reusable(load_mapping(mapping_dir, key), format_fingerprint(headers))
    entries: list[MappingEntry] = []
    records: list[ExceptionRecord] = []
    taken: set[Target] = set()
    for header in headers:
        prior = stored.entry(header) if stored else None
        entry = prior or _decide(header, tables, now)
        if entry.method == "unmapped":
            fresh = _decide(header, tables, now)  # the synonym table may have learned it
            entry = fresh if fresh.method != "unmapped" else entry
        target = _target(entry)
        if target is not None and (target.table not in tables or not is_canonical(target)):
            raise ValueError(f"mapping/{key}.yaml maps a column to {target}, which {key} lacks")
        if target is not None and target in taken:
            entry = prior if prior and prior.method == "unmapped" else _unmapped(header, now)
            records.append(_map_001(source, key, header, [target]))
        elif target is not None:
            taken.add(target)
        elif entry.method == "unmapped":
            near = list(load_synonyms().match(header, tables).candidates)
            records.append(_map_001(source, key, header, near))
        entries.append(entry)
    if stored is not None and stored.format_fingerprint is None:
        # An older file with no fingerprint keeps its other entries, as before. A file with a
        # fingerprint lists exactly one format's headers, so nothing stale is carried forward.
        entries += [e for e in stored.entries if e.header not in headers]
    fingerprint = stored.format_fingerprint if stored else None
    mapping = SourceMapping(source=key, format_fingerprint=fingerprint, entries=tuple(entries))
    save_mapping(mapping_dir, mapping)
    if _kind(key) in SOURCE_TABLES and _kind(key) not in NOT_LOADED:
        records += _missing_required(source, tables, taken)
    version = hashlib.sha256(dump_mapping(mapping).encode()).hexdigest()[:12]
    return MappingResult(mapping, records, f"{key}-{version}")


MAX_LISTED = 10  # headers named in one MAP-005 message; the rest are counted


def _listed(headers: list[str]) -> str:
    if not headers:
        return "none"
    shown = ", ".join(f'"{_shown(h)}"' for h in headers[:MAX_LISTED])
    more = len(headers) - MAX_LISTED
    return shown + (f", and {more} more" if more > 0 else "")


def format_changes(tables: Sequence[RawTable], stored_dir: Path) -> list[ExceptionRecord]:
    """MAP-005 for each file whose headers differ from the format its saved decisions are for.

    Reads the saved mapping/ folder beside drop/ and writes nothing. Call it before mapping;
    map_headers already refuses to reuse those decisions, so the changed headers fall back to
    the synonym table and then Jev, and land in mapping_review.json.
    """
    if not stored_dir.is_dir():
        return []
    records = []
    for table in tables:
        key = mapping_key(table.source, table.sheet)
        headers = [c for c in table.frame.columns if c != LINEAGE_COLUMN]
        stored = load_mapping(stored_dir, key)
        if stored is None or reusable(stored, format_fingerprint(headers)) is not None:
            continue
        added = [h for h in headers if stored.entry(h) is None]
        removed = [e.header for e in stored.entries if e.header not in headers]
        records.append(
            file_exception(
                "MAP-005",
                Severity.WARNING,
                table.source,
                f"Export format changed since mappings were saved for {key}, so saved "
                f"decisions were not reused. Added: {_listed(added)}. "
                f"Removed: {_listed(removed)}.",
                f"Review the mapping again and apply the decisions to mapping/{key}.yaml",
            )
        )
    return records


def map_table(table: RawTable, mapping_dir: Path, now: datetime) -> MappingResult:
    headers = [c for c in table.frame.columns if c != LINEAGE_COLUMN]
    return map_headers(table.source, table.sheet, headers, mapping_dir, now)

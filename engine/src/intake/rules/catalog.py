"""Catalog-only entries for the rules that run outside the registry (#52).

Readers (ING), raw gates (SSN, CMP), mapping (MAP), and the tie-out (TIE) emit their records
themselves, because they need files, a mapping store, or DuckDB rather than one frame. They
register here so the catalog and docs/rules.md list every rule. Each function returns nothing.
"""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.registry import rule

B, E, W, N = Severity.BLOCKER, Severity.ERROR, Severity.WARNING, Severity.INFO  # N: info
ENTRIES = (
    ("ING-001", N, "File encoding was not UTF-8"),
    ("ING-002", N, "Header row was not the first row"),
    ("ING-003", N, "Trailing total or blank rows dropped"),
    ("ING-004", W, "Delimiter guessed with low confidence"),
    ("MAP-001", W, "Column could not be mapped"),
    ("MAP-002", W, "Mapping confidence between thresholds, or Jev gave no usable answer"),
    ("MAP-003", B, "Required canonical field missing (a drop with no CRM misses them all)"),
    (
        "MAP-004",
        E,
        "Canonical row violates its declared load-table schema or depends on an excluded parent",
    ),
    ("MAP-005", W, "Export format changed since mappings were saved; saved decisions not reused"),
    ("SSN-001", B, "A column looks like SSNs; runs on raw frames before any model call"),
    ("CMP-001", B, "Rows received differ from rows expected; runs on raw frames"),
    ("CMP-002", W, "A source is missing entirely"),
    ("TIE-001", W, "Active policy with no commission line in period"),
    ("TIE-002", E, "Commission paid on a policy not in the book"),
    ("TIE-003", W, "Commission amount off schedule beyond tolerance"),
    ("TIE-004", W, "CRM status disagrees with carrier statement"),
    ("TIE-005", E, "Totals by carrier or agent off beyond tolerance, or a statement is missing"),
    ("TIE-006", N, "Match made on name plus DOB only (weak key)"),
)


def _catalog_only(frame: pl.DataFrame) -> list[ExceptionRecord]:
    return []


for _rule_id, _severity, _description in ENTRIES:
    rule(
        _rule_id,
        _severity,
        Family(_rule_id[:3]),
        _description,
        blocks=_severity == Severity.BLOCKER,
    )(_catalog_only)

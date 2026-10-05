"""SSN-001: refuse any column that looks like Social Security numbers.

Decision rule, checked per column in this order:
1. The header names an SSN ("SSN", "Social", "Soc Sec", "Tax ID", "TIN"): block, whatever
   the values are.
2. The header names a known id field (NPN, MBI, policy, member, phone, ZIP, plan ids): never
   block on values alone, even when they are nine digits.
3. Dashed or spaced SSN-shaped text (123-45-6789, 123 45 6789) in at least 1 percent of the
   non-empty cells, anywhere in the cell: block. Free text that leaks an SSN counts.
4. Bare nine-digit cells in at least 90 percent of the non-empty cells: block only when some
   value cannot be an NPN (is_valid_npn fails, for example a leading zero). Bare nine digits
   alone are weak evidence, because NPNs can be nine digits.

The gate records the column's header only. It never copies, counts, or masks a value, so no
SSN can reach an exception, a log, or an output.
"""

import re
from collections.abc import Iterable

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import SSN_PATTERN, ExceptionRecord
from agency_schema.formats import is_valid_npn
from intake.config import (
    SSN_HEADER_PHRASES,
    SSN_HEADER_WORDS,
    SSN_ID_HEADER_WORDS,
    SSN_MIN_SHARE,
    SSN_SHAPED_MIN_SHARE,
    SSN_VALUE_PATTERN,
)
from intake.readers import LINEAGE_COLUMN, RawTable, file_exception


def _header_words(name: str) -> list[str]:
    return re.findall(r"[a-z]+", name.lower())


def _header_says_ssn(name: str) -> bool:
    words = _header_words(name)
    spaced = f" {' '.join(words)} "
    return any(w in SSN_HEADER_WORDS for w in words) or any(
        f" {phrase} " in spaced for phrase in SSN_HEADER_PHRASES
    )


def _header_is_known_id(name: str) -> bool:
    return any(w in SSN_ID_HEADER_WORDS for w in _header_words(name))


def _values_look_like_ssns(column: pl.Series) -> bool:
    values = column.drop_nulls().str.strip_chars()
    values = values.filter(values != "")
    if values.is_empty():
        return False
    if values.str.contains(SSN_PATTERN.pattern).sum() / values.len() >= SSN_SHAPED_MIN_SHARE:
        return True
    bare = values.filter(values.str.contains(SSN_VALUE_PATTERN))
    if bare.len() / values.len() < SSN_MIN_SHARE:
        return False
    return not all(is_valid_npn(v) for v in bare)


def _is_ssn_column(name: str, column: pl.Series) -> bool:
    if _header_says_ssn(name):
        return True
    if _header_is_known_id(name):
        return False
    return _values_look_like_ssns(column)


def check_ssn(tables: Iterable[RawTable]) -> list[ExceptionRecord]:
    records = []
    for table in tables:
        for i, name in enumerate(table.frame.columns, start=1):
            if name == LINEAGE_COLUMN or not _is_ssn_column(name, table.frame[name]):
                continue
            label = f"column {i}" if SSN_PATTERN.search(name) else f'column "{name}"'
            where = f"{table.source_file} ({table.sheet})" if table.sheet else table.source_file
            records.append(
                file_exception(
                    "SSN-001",
                    Severity.BLOCKER,
                    table.source,
                    f"SSNs are not accepted: {label} in {where} looks like Social Security numbers",
                    "Remove the column before intake",
                )
            )
    return records

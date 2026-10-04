"""SSN-001: refuse any column that looks like Social Security numbers.

The gate records the column's header only. It never copies, counts, or masks a value, so no
SSN can reach an exception, a log, or an output.
"""

import re
from collections.abc import Iterable

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import SSN_PATTERN, ExceptionRecord
from intake.config import SSN_HEADER_WORDS, SSN_MIN_SHARE, SSN_VALUE_PATTERN
from intake.readers import LINEAGE_COLUMN, RawTable, file_exception


def _header_says_ssn(name: str) -> bool:
    return any(word in SSN_HEADER_WORDS for word in re.findall(r"[a-z]+", name.lower()))


def _values_look_like_ssns(column: pl.Series) -> bool:
    values = column.drop_nulls().str.strip_chars()
    if values.is_empty():
        return False
    share = values.str.contains(SSN_VALUE_PATTERN).sum() / values.len()
    return bool(share >= SSN_MIN_SHARE)


def check_ssn(tables: Iterable[RawTable]) -> list[ExceptionRecord]:
    records = []
    for table in tables:
        for i, name in enumerate(table.frame.columns, start=1):
            if name == LINEAGE_COLUMN:
                continue
            if not (_header_says_ssn(name) or _values_look_like_ssns(table.frame[name])):
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

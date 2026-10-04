"""Build an ExceptionRecord from a canonical row that carries the loader's lineage columns."""

from typing import Any

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.lineage import Lineage


def record(
    rule_id: str,
    severity: Severity,
    row: dict[str, Any],
    message: str,
    fix: str,
    field: str | None = None,
) -> ExceptionRecord:
    """The id is rule, source, and row, so it is stable and unique (one record per rule per row).

    PR 12 may renumber ids; it must then remap rts_coverage exception_ids too.
    """
    return ExceptionRecord(
        id=f"{rule_id}:{row['_source']}:{row['_row']}",
        rule_id=rule_id,
        severity=severity,
        family=Family(rule_id[:3]),
        source=row["_source"],
        row_number=row["_row"],
        raw_hash=row["_hash"],
        field=field,
        value_minimized=minimize_value(row.get(field)) if field else None,
        message=message,
        suggested_fix=fix,
        blocks_load=False,
        lane=Lane.UNREVIEWED,
        jev=None,
        lineage=Lineage(
            source_file=row["_file"],
            sheet=None,
            row_number=row["_row"],
            raw_hash=row["_hash"],
            run_id=row["_run_id"],
            mapping_version=row["_mapping_version"],
        ),
    )

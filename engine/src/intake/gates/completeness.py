"""CMP-001: rows received differ from rows expected. CMP-002: a source is missing."""

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import TieOutLeg
from intake.ingest import IngestResult
from intake.readers import file_exception

STATEMENT_PREFIX = "statement_"


def legs_needing(source: str) -> list[TieOutLeg]:
    """Tie-out legs that cannot run without this source. The book of policies comes from the CRM."""
    if source == "crm" or source.startswith(STATEMENT_PREFIX):
        return list(TieOutLeg)
    return []


def check_completeness(result: IngestResult) -> list[ExceptionRecord]:
    records = []
    for table in result.tables:
        # drop/manifest.json wins; a statement's own total row is the fallback.
        expected = table.expected_rows if table.expected_rows is not None else table.total_row_count
        if expected is None or expected == table.rows:
            continue
        where = f"{table.source_file} ({table.sheet})" if table.sheet else table.source_file
        records.append(
            file_exception(
                "CMP-001",
                Severity.BLOCKER,
                table.source,
                f"{table.source}: expected {expected} rows, received {table.rows} ({where})",
                "Re-export the file; check for truncation",
            )
        )
    for entry in result.missing:
        legs = ", ".join(leg.value for leg in legs_needing(entry.source)) or "none"
        where = f"{entry.file_name} ({entry.sheet})" if entry.sheet else entry.file_name
        records.append(
            file_exception(
                "CMP-002",
                Severity.WARNING,
                entry.source,
                f"No {entry.source} file in drop: {where} is missing",
                f"Tie-out legs marked NOT_RUN: {legs}",
            )
        )
    return records

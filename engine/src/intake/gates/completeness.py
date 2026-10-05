"""CMP-001: rows received differ from rows expected. CMP-002: a source is missing."""

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import TieOutLeg
from intake.ingest import IngestResult
from intake.readers import file_exception

STATEMENT_PREFIX = "statement_"


def legs_needing(source: str) -> list[TieOutLeg]:
    """Tie-out legs that cannot run without this source. The book of policies comes from the CRM.

    One missing carrier statement does not stop the tie-out: it runs on the other statements
    and reports that carrier's periods as missing statements (see tie_out_effect).
    """
    return list(TieOutLeg) if source == "crm" else []


def tie_out_effect(source: str) -> str:
    """What the tie-out does about this missing source, for CMP-002's suggested fix."""
    if source.startswith(STATEMENT_PREFIX):
        return (
            "Tie-out reports this carrier's periods as missing statements (TIE-005); "
            "legs BOOK_VS_STATEMENT, STATEMENT_VS_BOOK, CRM_VS_STATEMENT are NOT_RUN only "
            "when no statement arrived at all"
        )
    legs = ", ".join(leg.value for leg in legs_needing(source)) or "none"
    return f"Tie-out legs marked NOT_RUN: {legs}"


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
        where = f"{entry.file_name} ({entry.sheet})" if entry.sheet else entry.file_name
        records.append(
            file_exception(
                "CMP-002",
                Severity.WARNING,
                entry.source,
                f"No {entry.source} file in drop: {where} is missing",
                tie_out_effect(entry.source),
            )
        )
    return records

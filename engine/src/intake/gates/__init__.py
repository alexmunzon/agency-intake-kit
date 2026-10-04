"""Raw gates: checks that run on raw frames right after reading, before mapping or any model."""

from agency_schema.exceptions import ExceptionRecord
from intake.gates.completeness import check_completeness
from intake.gates.refusal import check_ssn
from intake.ingest import IngestResult


def run_raw_gates(result: IngestResult) -> list[ExceptionRecord]:
    """SSN refusal first, then completeness. Any record with blocks_load means status FAILED."""
    return check_ssn(result.tables) + check_completeness(result)

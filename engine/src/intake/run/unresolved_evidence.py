"""Safe row references for evidence that cannot make a load-ready customer."""

from collections.abc import Sequence
from typing import Literal, Self

from pydantic import model_validator

from agency_schema.formats import parse_date_loose
from agency_schema.lineage import Lineage, NonEmpty, StrictModel
from intake.ingest import IngestResult
from intake.run.canonicalize import MappedSource

Reason = Literal["crm_absent", "dob_column_missing", "dob_blank", "dob_malformed"]


class UnresolvedEvidence(StrictModel):
    schema_version: Literal[1] = 1
    run_id: NonEmpty
    source: NonEmpty
    reason: Reason
    lineage: Lineage | None

    @model_validator(mode="after")
    def valid_scope(self) -> Self:
        if self.reason == "crm_absent" and (self.lineage is None) != (self.source == "crm"):
            raise ValueError("CRM absence needs a CRM summary or another source's row")
        if self.reason in ("dob_blank", "dob_malformed") and self.lineage is None:
            raise ValueError("a DOB cell reason requires row lineage")
        if self.reason != "crm_absent" and self.source != "crm":
            raise ValueError("a DOB reason requires the CRM source")
        if self.lineage is not None and self.lineage.run_id != self.run_id:
            raise ValueError("lineage run_id does not match evidence run_id")
        return self


def _row_case(
    source: str,
    reason: Reason,
    raw_lineage: dict[str, object],
    run_id: str,
    mapping_version: str | None = None,
) -> UnresolvedEvidence:
    lineage = Lineage.model_validate(
        raw_lineage | ({"mapping_version": mapping_version} if mapping_version else {})
    )
    return UnresolvedEvidence(run_id=run_id, source=source, reason=reason, lineage=lineage)


def collect_unresolved_evidence(
    raw: IngestResult, sources: Sequence[MappedSource], run_id: str, raw_blocked: bool
) -> tuple[UnresolvedEvidence, ...]:
    """Inspect only source presence, mapped DOB cells and reader lineage after raw gates."""
    if raw_blocked:
        return ()
    if not any(table.source == "crm" for table in raw.tables):
        cases = [UnresolvedEvidence(run_id=run_id, source="crm", reason="crm_absent", lineage=None)]
        for table in raw.tables:
            cases.extend(
                _row_case(table.source, "crm_absent", lin, run_id)
                for lin in table.frame["lineage"].to_list()
            )
        return tuple(cases)

    crm_sources = [source for source in sources if source.table.source == "crm"]
    if not crm_sources:
        raise ValueError("mapped CRM sources are required when CRM was received")
    cases = []
    for source in crm_sources:
        dob_header = next(
            (
                header
                for header, target in source.targets().items()
                if target.table == "clients" and target.field == "dob"
            ),
            None,
        )
        rows = source.table.frame["lineage"].to_list()
        if dob_header is None and not rows:
            cases.append(
                UnresolvedEvidence(
                    run_id=run_id, source="crm", reason="dob_column_missing", lineage=None
                )
            )
        values = (
            [None] * len(rows) if dob_header is None else source.table.frame[dob_header].to_list()
        )
        for raw_value, lineage in zip(values, rows, strict=True):
            reason: Reason | None = None
            if dob_header is None:
                reason = "dob_column_missing"
            elif raw_value is None or not raw_value.strip():
                reason = "dob_blank"
            elif parse_date_loose(raw_value) is None:
                reason = "dob_malformed"
            if reason is not None:
                cases.append(_row_case("crm", reason, lineage, run_id, source.result.version))
    return tuple(cases)


def serialize_unresolved_evidence(cases: Sequence[UnresolvedEvidence], run_id: str) -> str:
    """Stable JSONL. A repeated source row/reason is an error, not silently deduplicated."""
    seen: set[tuple[str, str, str | None, str | None, int | None]] = set()
    ordered = []
    for case in cases:
        if case.run_id != run_id or (case.lineage and case.lineage.run_id != run_id):
            raise ValueError("evidence run_id does not match the writer run_id")
        lin = case.lineage
        key = (
            case.source,
            case.reason,
            lin.source_file if lin else None,
            lin.sheet if lin else None,
            lin.row_number if lin else None,
        )
        if key in seen:
            raise ValueError("duplicate unresolved evidence case")
        seen.add(key)
        ordered.append((key, case))
    ordered.sort(
        key=lambda item: (
            item[0][0],
            item[0][1],
            item[0][2] or "",
            item[0][3] or "",
            item[0][4] or 0,
        )
    )
    return "".join(case.model_dump_json() + "\n" for _, case in ordered)

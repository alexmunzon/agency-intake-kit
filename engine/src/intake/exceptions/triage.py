"""Jev triage (SPEC question 3): is an error or warning a data-entry slip or a real event?

Each error and warning becomes one request with a minimized state: the rule, the field, the
value's shape (digits become 9, letters A), and a few neighbor fields from config. Requests
with the same public hash are sent once per run and the answer is reused, so 40 missing MBIs
on MA policies cost one call. The answer sets the lane and orders the queue; it never changes
severity or blocks_load. In off mode, or after the spend guard trips, items stay UNREVIEWED,
which is the human queue.
"""

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import ExceptionRecord, JevScores
from intake.config import (
    TRIAGE_BUSINESS_EVENT,
    TRIAGE_ENTRY_ERROR,
    TRIAGE_KEEP_AS_IS,
    TRIAGE_NEIGHBORS,
    TRIAGE_SHAPE_MAX_CHARS,
)
from jev_client import (
    JevClient,
    JevRequest,
    JevResponse,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    Unresolved,
    minimize_state,
    request_hash,
)
from jev_client.types import is_notes_key

TRIAGED = frozenset({Severity.ERROR, Severity.WARNING})
ENTRY_ERROR = NoulQuestion(
    type="noul",
    instructions=(
        "Is this most likely a data-entry error that can be fixed from the surrounding "
        "record, rather than a real business event?"
    ),
    criteria=NoulCriteria(
        true="A typo or keying mistake", false="A genuine fact about the policy or client"
    ),
)
IMPACT = ScoreQuestion(
    type="score",
    instructions="How much does this matter before the agency goes live?",
    criteria=["Cosmetic", "Affects reporting", "Affects compliance or money"],
)
_LANE_ORDER = {Lane.SUGGESTED_FIX: 0, Lane.REVIEW: 1, Lane.BUSINESS_EVENT: 2, Lane.UNREVIEWED: 3}


@dataclass(frozen=True)
class TriageItem:
    """An exception plus its source row (raw cells), or None for file-level problems."""

    record: ExceptionRecord
    row: Mapping[str, Any] | None = None


def attach_rows(
    records: Iterable[ExceptionRecord], frames: Iterable[pl.DataFrame]
) -> list[TriageItem]:
    """Pair each record with the frame row its lineage points to (frames carry `lineage`)."""
    rows = {_where(row): row for frame in frames for row in frame.iter_rows(named=True)}
    return [
        TriageItem(
            r, rows.get((r.lineage.source_file, r.lineage.row_number)) if r.lineage else None
        )
        for r in records
    ]


def _where(row: Mapping[str, Any]) -> tuple[str, int]:
    # A `lineage` struct (PR 8 frames) or flat _file and _row columns (PR 9's loader, until
    # PR 4's readers give every frame one shape).
    if "lineage" in row:
        return row["lineage"]["source_file"], row["lineage"]["row_number"]
    return row["_file"], row["_row"]


def value_shape(value: Any) -> str | None:
    """'1958-03-12' becomes '9999-99-99'. Only the pattern is sent, never the value."""
    if value is None or str(value).strip() == "":
        return None
    shape = re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", str(value).strip()))
    return shape[:TRIAGE_SHAPE_MAX_CHARS]


def _neighbor(name: str, value: Any) -> str | None:
    if name in TRIAGE_KEEP_AS_IS and value is not None:
        return str(value).strip().upper() or None
    return value_shape(value)


def triage_state(item: TriageItem) -> dict[str, Any]:
    r, row = item.record, item.row or {}
    names = TRIAGE_NEIGHBORS.get(r.family, ())
    allowed = minimize_state(dict(row), set(names))  # drops any notes field, even if named
    return {
        "rule_id": r.rule_id,
        "field": r.field,
        "value_shape": None
        if r.field is None or is_notes_key(r.field)
        else value_shape(row.get(r.field)),
        "neighbors": {name: _neighbor(name, allowed.get(name)) for name in names},
    }


def triage_request(item: TriageItem) -> JevRequest:
    return JevRequest(
        state=triage_state(item), questions={"is_entry_error": ENTRY_ERROR, "impact": IMPACT}
    )


def needs_triage(record: ExceptionRecord) -> bool:
    # PII-001 is decided by the PII gate; nothing derived from notes goes to triage.
    return record.severity in TRIAGED and record.family != Family.PII


def planned_requests(items: Iterable[TriageItem]) -> dict[str, JevRequest]:
    """The distinct requests a run sends, keyed by hash. len() is the expected call count."""
    return {
        request_hash(req.body()): req
        for req in (triage_request(i) for i in items if needs_triage(i.record))
    }


def route(answer: JevResponse | Unresolved) -> tuple[Lane, JevScores | None]:
    if isinstance(answer, Unresolved):
        return Lane.UNREVIEWED, None
    entry = answer.answers["is_entry_error"]
    impact = answer.answers["impact"]
    assert isinstance(entry, NoulAnswer) and isinstance(impact, ScoreAnswer)
    scores = JevScores(
        entry_error_probability=entry.noul, impact_score=impact.score, pii_probability=None
    )
    if entry.noul >= TRIAGE_ENTRY_ERROR:
        return Lane.SUGGESTED_FIX, scores
    if entry.noul <= TRIAGE_BUSINESS_EVENT:
        return Lane.BUSINESS_EVENT, scores
    return Lane.REVIEW, scores


def triage(items: Sequence[TriageItem], client: JevClient) -> list[ExceptionRecord]:
    """Route every error and warning. A cassette miss in replay raises CassetteMiss."""
    answers: dict[str, JevResponse | Unresolved] = {}
    out = []
    for item in items:
        if not needs_triage(item.record):
            out.append(item.record)
            continue
        request = triage_request(item)
        key = request_hash(request.body())
        if key not in answers:
            answers[key] = client.ask(request)
        lane, scores = route(answers[key])
        update = {"lane": lane, "jev": scores}
        out.append(ExceptionRecord.model_validate({**item.record.model_dump(), **update}))
    return out


def queue_order(records: Iterable[ExceptionRecord]) -> list[ExceptionRecord]:
    """Fix-first order: severity, then lane, then impact high to low, then id. Deterministic."""
    severity_rank = list(Severity)

    def key(r: ExceptionRecord) -> tuple[int, int, float, str]:
        impact = r.jev.impact_score if r.jev and r.jev.impact_score is not None else -1.0
        return (severity_rank.index(r.severity), _LANE_ORDER[r.lane], -impact, r.id)

    return sorted(records, key=key)

"""Jev fills the header gaps the synonym table leaves (SPEC "Jev usage", question 1).

Each header PR 5 left unmapped gets one choice question: which canonical field of this
source's tables does it hold? Sample values are masked with minimize_value first, and a
column that looks like free text or holds 9-digit values sends its header only. Routing:
at or above MAP_AUTO maps, from MAP_SUGGEST up maps with MAP-002 for a person to confirm,
below stays unmapped (PR 5's MAP-001 stays). No answer (off mode, budget spent) is MAP-002.
A reply that does not fit the question is never applied: it stays unmapped with MAP-002 too.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import JsonValue

from agency_schema.enums import Lane, Severity
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.mapping_review import Origin
from agency_schema.models import TABLE_MODELS
from agency_schema.outputs import JevMode
from intake.config import (
    MAP_AUTO,
    MAP_FREE_TEXT_AVG_CHARS,
    MAP_FREE_TEXT_MAX_SPACES,
    MAP_SAMPLE_MAX_CHARS,
    MAP_SAMPLE_VALUES,
    MAP_SUGGEST,
    NINE_DIGIT_PATTERN,
)
from intake.mapping.headers import SOURCE_TABLES, MappingResult, _shown, map_headers
from intake.mapping.store import MappingEntry, save_mapping
from intake.mapping.synonyms import COMPOSITE_FIELDS, normalize_header
from intake.readers import LINEAGE_COLUMN, RawTable, file_exception
from jev_client import (
    ChoiceAnswer,
    ChoiceQuestion,
    JevBadReply,
    JevClient,
    JevHTTPError,
    JevRequest,
    JevResponse,
    Unresolved,
    request_hash,
)
from jev_client.client import DEFAULT_CASSETTE_DIR

log = logging.getLogger("intake.mapping")

MAPPING_CASSETTES = DEFAULT_CASSETTE_DIR / "mapping"
NONE = "none"
NOTES_WORDS = frozenset({"note", "notes", "comment", "comments", "memo"})
INSTRUCTIONS = (
    "Which canonical field does `header` hold, judging by the header and `sample_values`? "
    "Sample values are masked: after the first characters, letters and digits are *."
)
# One-line hints where field names alone could be confused. Other fields are named only.
HINTS: dict[str, str] = {
    "dob": "date of birth of the client",
    "member_dob": "date of birth of the member on the statement line",
    "effective_date": "date coverage or appointment starts",
    "termination_date": "date coverage ends",
    "end_date": "date the appointment ends",
    "paid_date": "date the carrier paid the commission",
    "statement_period": "month the statement covers, YYYY-MM",
    "amount": "commission dollars paid on the line",
    "monthly_premium": "monthly premium in dollars",
    "mbi": "Medicare Beneficiary Identifier, 11 characters",
    "carrier_member_id": "member id the carrier assigned",
    "full_name": "first and last name in one column",
    "state": "two-letter US state",
}

Route = Literal["auto", "suggest", "unmapped", "person"]


class Asker:
    """Sends each distinct request once per run, keyed by the public request hash.

    With no client it only collects the requests (to count and price them) and answers
    each one Unresolved, the same as off mode. A reply that does not fit the question
    (JevBadReply) is answered Unresolved("invalid_reply"), and an HTTP error from the API
    (JevHTTPError) Unresolved("http_error"), so one bad answer goes to a person instead of
    stopping the import.
    """

    def __init__(self, client: JevClient | None) -> None:
        self.client = client
        self.requests: dict[str, JevRequest] = {}
        self.asked = 0
        self.invalid = 0  # distinct requests whose reply was rejected and not used
        self._answers: dict[str, JevResponse | Unresolved] = {}
        self._origins: dict[str, Origin] = {}  # how each answered request was obtained

    def ask(self, request: JevRequest) -> JevResponse | Unresolved:
        self.asked += 1
        key = request_hash(request.body())
        if key not in self._answers:
            self.requests[key] = request
            if self.client is None:
                self._answers[key] = Unresolved(reason="mode_off", question_ids=("planned",))
            else:
                try:
                    self._answers[key] = self.client.ask(request)
                    self._origins[key] = answer_origin(self.client)
                except JevBadReply as error:
                    log.warning("Jev answer not used, a person decides (%s)", error.log_safe())
                    self.invalid += 1
                    qids = tuple(request.questions)
                    self._answers[key] = Unresolved(reason="invalid_reply", question_ids=qids)
                except JevHTTPError as error:  # status code only: the body may echo the request
                    log.warning("Jev did not answer (%s), a person decides", error.what)
                    qids = tuple(request.questions)
                    self._answers[key] = Unresolved(reason="http_error", question_ids=qids)
        return self._answers[key]

    def origin(self, request: JevRequest) -> Origin:
        """Where the answer to this request came from; "none" when there was no answer."""
        return self._origins.get(request_hash(request.body()), "none")


def answer_origin(client: JevClient) -> Origin:
    """A saved cassette is a replay in any mode; an API reply is live or record."""
    if client.last_source == "cassette":
        return "jev_replay"
    if client.last_source == "api":
        return "jev_record" if client.mode == JevMode.RECORD else "jev_live"
    return "none"


def choice_of(reply: JevResponse, qid: str) -> tuple[str, float]:
    answer = reply.answers[qid]
    if not isinstance(answer, ChoiceAnswer):
        raise TypeError(f"Jev answered {qid} with {answer.type}, expected choice")
    return answer.choice, answer.confidence


@dataclass(frozen=True)
class HeaderDecision:
    header: str
    choice: str | None  # "table.field", None when Jev said none or gave no answer
    confidence: float | None
    route: Route
    reason: str | None  # why a person decides: mode_off, budget_tripped, notes, invalid_reply, ...
    origin: Origin = "none"  # how Jev's answer was obtained; "none" when there was no answer


def tables_for(key: str) -> tuple[str, ...]:
    return SOURCE_TABLES.get("statement" if key.startswith("statement_") else key, ())


def criteria_for(tables: tuple[str, ...]) -> dict[str, JsonValue]:
    options: dict[str, JsonValue] = {}
    for table in tables:
        fields = [f for f in TABLE_MODELS[table].model_fields if f != "lineage"]
        if "first_name" in fields:
            fields += list(COMPOSITE_FIELDS)
        for field in fields:
            options[f"{table}.{field}"] = HINTS.get(field)
    options[NONE] = "none of these"
    return options


def filled_values(series: pl.Series) -> list[str]:
    """The column's non-blank values, trimmed."""
    return [v.strip() for v in series.drop_nulls().to_list() if v and v.strip()]


def samples_withheld(series: pl.Series) -> bool:
    """True when the column looks like free text or holds a 9-digit value: header only."""
    values = filled_values(series)
    if not values:
        return False
    average = sum(len(v) for v in values) / len(values)
    spaces = max(v.count(" ") for v in values)
    if average > MAP_FREE_TEXT_AVG_CHARS or spaces > MAP_FREE_TEXT_MAX_SPACES:
        return True
    return any(re.search(NINE_DIGIT_PATTERN, v) for v in values)


def sample_values(series: pl.Series) -> list[str]:
    """Up to MAP_SAMPLE_VALUES distinct masked values, or none for risky columns."""
    values = filled_values(series)
    if not values or samples_withheld(series):
        return []
    samples: list[str] = []
    for value in values:
        masked = minimize_value(value[:MAP_SAMPLE_MAX_CHARS])
        if masked and masked not in samples:
            samples.append(masked)
            if len(samples) == MAP_SAMPLE_VALUES:
                break
    return samples


def header_request(key: str, header: str, series: pl.Series) -> JevRequest:
    tables = tables_for(key)
    state: dict[str, JsonValue] = {
        "header": _shown(header),  # an SSN-shaped header is masked before it reaches Jev
        "sample_values": list[JsonValue](sample_values(series)),
        "source_table": ", ".join(tables),
    }
    question = ChoiceQuestion(
        type="choice", instructions=INSTRUCTIONS, criteria=criteria_for(tables)
    )
    return JevRequest(state=state, questions={"field": question})


def route(choice: str | None, confidence: float) -> Route:
    if choice is None or confidence < MAP_SUGGEST:
        return "unmapped"
    return "auto" if confidence >= MAP_AUTO else "suggest"


def decide_header(key: str, header: str, series: pl.Series, asker: Asker) -> HeaderDecision:
    if NOTES_WORDS & set(normalize_header(header).split()):
        return HeaderDecision(header, None, None, "person", "notes")  # never sent to a model
    request = header_request(key, header, series)
    reply = asker.ask(request)
    if isinstance(reply, Unresolved):
        return HeaderDecision(header, None, None, "person", reply.reason)
    choice, confidence = choice_of(reply, "field")
    picked = None if choice == NONE else choice
    origin = asker.origin(request)
    return HeaderDecision(header, picked, confidence, route(picked, confidence), None, origin)


def _map_002(source: str, key: str, header: str, field: str | None, text: str) -> ExceptionRecord:
    record = file_exception(
        "MAP-002",
        Severity.WARNING,
        source,
        f'"{_shown(header)}" in {key} {text}',
        f"Confirm or correct the mapping in mapping/{key}.yaml",
    )
    return record.model_copy(update={"field": field, "lane": Lane.REVIEW})


def map_with_jev(
    table: RawTable, result: MappingResult, mapping_dir: Path, now: datetime, asker: Asker
) -> tuple[MappingResult, list[HeaderDecision]]:
    """Ask Jev about the headers PR 5 left unmapped, save its picks, and map again.

    Mapping again lets PR 5 recheck taken fields and MAP-001 and MAP-003 with Jev's picks.
    A saved Jev pick below MAP_AUTO raises MAP-002 every run until a person confirms it.
    """
    key = result.mapping.source
    entries = list(result.mapping.entries)
    decisions: list[HeaderDecision] = []
    for i, entry in enumerate(entries):
        if entry.method != "unmapped" or entry.header not in table.frame.columns:
            continue
        decision = decide_header(key, entry.header, table.frame[entry.header], asker)
        decisions.append(decision)
        if decision.choice and decision.route in ("auto", "suggest"):
            target_table, field = decision.choice.split(".")
            entries[i] = MappingEntry(
                header=entry.header,
                table=target_table,
                field=field,
                method="jev",
                confidence=decision.confidence,
                decided_at=now.isoformat(),
            )
    if decisions:
        save_mapping(mapping_dir, result.mapping.model_copy(update={"entries": tuple(entries)}))
        headers = [c for c in table.frame.columns if c != LINEAGE_COLUMN]
        result = map_headers(table.source, table.sheet, headers, mapping_dir, now)
    extra = []
    for entry in result.mapping.entries:
        confidence = entry.confidence or 0.0
        if entry.method == "jev" and confidence < MAP_AUTO:
            at = f"mapped to {entry.table}.{entry.field} at {confidence:.2f}"
            extra.append(_map_002(table.source, key, entry.header, entry.field, at))
    for decision in decisions:
        if decision.route == "person":
            said = "invalid model answer" if decision.reason == "invalid_reply" else "no answer"
            why = f"needs a person: Jev gave {said} ({decision.reason})"
            extra.append(_map_002(table.source, key, decision.header, None, why))
    return MappingResult(result.mapping, result.exceptions + extra, result.version), decisions

"""mapping_review.json: evidence for each header the synonyms and saved decisions left open.

One item per such header, built from what the run already decided (its HeaderDecision), the
masked samples Jev saw, and the file itself. The explanation is assembled from those fields,
never from model text. The file carries no authority: it cannot map, approve or clear anything.
"""

import hashlib
from collections.abc import Mapping, Sequence

from agency_schema.enums import JevMode
from agency_schema.exceptions import ExceptionRecord
from agency_schema.mapping_review import MappingReview, MappingReviewItem, Origin, Route
from intake.config import MAP_SUGGEST
from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.headers import MappingResult, _shown
from intake.mapping.jev_mapping import (
    HeaderDecision,
    criteria_for,
    filled_values,
    sample_values,
    samples_withheld,
    tables_for,
)
from intake.readers import LINEAGE_COLUMN, RawTable

REVIEW_FILE = "mapping_review.json"
MAP_RULES = frozenset({"MAP-001", "MAP-002"})
NO_ANSWER = {
    "mode_off": "Jev is off",
    "budget_tripped": "the spend cap was reached",
    "not_recorded": "no recorded answer exists for this question",
    "invalid_reply": "its answer did not fit the question and was not used",
    "http_error": "the API returned an error",
}
SENT = frozenset({"invalid_reply", "http_error"})  # the request went out, the answer was not used


def item_id(source: str, file_name: str, header: str) -> str:
    """Interface section 1 (amended 2026-10-07): two files under one source never collide."""
    text = f"{source}\0{file_name}\0{header}"
    return "mr-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def file_label(table: RawTable) -> str:
    """The file an item came from. A workbook sheet read as its own input names its sheet."""
    return table.source_file if table.sheet is None else f"{table.source_file} [{table.sheet}]"


def _jev_sentence(
    origin: Origin, route: Route, reason: str | None, choice: str | None, confidence: float | None
) -> str:
    if reason == "notes":
        return "It looks like a notes column, so it was never sent to Jev."
    if confidence is None:
        why = NO_ANSWER.get(reason or "", "of an unknown problem")
        return f"Jev gave no answer because {why} ({reason})."
    said = "said none of the offered fields fit" if choice is None else f"chose {choice}"
    how = origin.removeprefix("jev_")
    head = f"Jev ({how}) {said} with confidence {confidence:.2f} (the model's own number)"
    if reason == "field_taken":
        return f"{head}, but another column already had that field, so it stayed unmapped."
    if route == "auto":
        return f"{head}, so it was mapped."
    if route == "suggest":
        return f"{head}, so it was mapped but a person should confirm it."
    if choice is None:
        return f"{head}, so it stayed unmapped."
    return f"{head}, below the {MAP_SUGGEST:.2f} line, so it stayed unmapped."


def _samples_sentence(n: int, withheld: bool, reason: str | None, answered: bool) -> str:
    if reason == "notes":
        return ""
    if withheld:
        return (
            " Sample values were withheld because the column looks like free text "
            "or holds 9-digit numbers."
        )
    if n == 0:
        return " The column has no values to sample."
    values = "1 masked sample value was" if n == 1 else f"{n} masked sample values were"
    seen = "shown to Jev" if answered or reason in SENT else "kept for the reviewer"
    return f" {values} {seen}."


def explain(
    header: str,
    origin: Origin,
    route: Route,
    reason: str | None,
    choice: str | None,
    confidence: float | None,
    samples: int,
    withheld: bool,
    rows: int,
) -> str:
    """Plain sentences from the item's own fields. No model text goes in."""
    if reason == "field_taken" and confidence is None:
        first = (
            f"'{header}' was mapped by a synonym or saved decision, but another column "
            "took that field, so it stayed unmapped."
        )
        jev = ""
    else:
        first = f"No synonym or saved mapping matched '{header}'."
        jev = " " + _jev_sentence(origin, route, reason, choice, confidence)
    answered = confidence is not None
    count = "1 row has a value." if rows == 1 else f"{rows:,} rows have a value."
    return f"{first}{jev}{_samples_sentence(samples, withheld, reason, answered)} {count}"


def review_items(
    table: RawTable,
    result: MappingResult,
    decisions: Sequence[HeaderDecision],
    earlier: Mapping[str, HeaderDecision] | None = None,
) -> list[MappingReviewItem]:
    """One item per header Jev was asked about or that the final mapping left unmapped.

    `earlier` holds Jev's decisions for the same source from files mapped before this one in
    the run. A second file under one source reuses those in-run picks without asking again,
    but they are not a reviewer's saved decision, so its headers still get their own items.
    """
    key = result.mapping.source
    headers = [c for c in table.frame.columns if c != LINEAGE_COLUMN]
    fingerprint = format_fingerprint(headers)
    file_name = file_label(table)
    allowed = tuple(criteria_for(tables_for(key)))
    asked = {**(earlier or {}), **{d.header: d for d in decisions}}
    items = []
    for header in headers:
        final = result.mapping.entry(header)
        left_open = final is not None and final.method == "unmapped"
        decision = asked.get(header)
        if decision is None and not left_open:
            continue  # the synonym table or a saved decision settled it
        route: Route
        reason: str | None
        choice: str | None
        confidence: float | None
        origin: Origin = "none"
        if decision is None:  # it lost its field to a column Jev mapped
            route, reason, choice, confidence = "unmapped", "field_taken", None, None
        else:
            route, reason = decision.route, decision.reason
            choice, confidence = decision.choice, decision.confidence
            origin = decision.origin
            if route in ("auto", "suggest") and left_open:
                route, reason = "unmapped", "field_taken"
        answered = confidence is not None
        series = table.frame[header]
        withheld = reason == "notes" or samples_withheld(series)
        samples = () if withheld else tuple(sample_values(series))
        rows = len(filled_values(series))
        shown = _shown(header)
        items.append(
            MappingReviewItem(
                item_id=item_id(key, file_name, shown),
                source=key,
                file_name=file_name,
                header=shown,
                format_fingerprint=fingerprint,
                samples=samples,
                samples_withheld=withheld,
                allowed_fields=allowed,
                proposed_field=choice,
                origin=origin if answered else "none",
                confidence=confidence,
                route=route,
                reason=reason,
                rows_with_value=rows,
                exception_ids=(),
                explanation=explain(
                    shown, origin, route, reason, choice, confidence, len(samples), withheld, rows
                ),
            )
        )
    return items


def build_review(
    run_id: str,
    mapping_version: str,
    mode: JevMode,
    items: Sequence[MappingReviewItem],
    records: Sequence[ExceptionRecord],
) -> MappingReview:
    """Link each item to its MAP-001 and MAP-002 records (by the header they name) and sort."""
    linked = []
    for item in items:
        prefix = f'"{item.header}" in {item.source} '
        ids = tuple(
            r.id for r in records if r.rule_id in MAP_RULES and r.message.startswith(prefix)
        )
        linked.append(item.model_copy(update={"exception_ids": ids}))
    linked.sort(key=lambda i: (i.source, i.file_name, i.header))
    return MappingReview(
        run_id=run_id, mapping_version=mapping_version, jev_mode=mode, items=tuple(linked)
    )

"""The PII gate (SPEC question 4): free text is checked before any log, export, or model call.

Step 1, a regex pre-filter, decides which notes need a look at all. Text with no date, long
number, drug-like word, or health word is cleared without a call. Step 2: text holding an
SSN-shaped value or a 9 to 11 digit number is redacted at once, with no call, so it never
leaves the machine. Step 3: other flagged text goes to Jev's noul question with every digit
masked; at or above PII_REDACT it is redacted. If Jev cannot answer (off mode or the spend
guard), the text is redacted too: the gate fails closed. Identical texts are asked once.
"""

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import SSN_PATTERN, ExceptionRecord, JevScores
from agency_schema.lineage import Lineage
from agency_schema.registry import rule
from intake.config import PII_HEALTH_WORDS, PII_REDACT, PII_REDACTED_TEXT
from jev_client import (
    JevClient,
    JevRequest,
    JevResponse,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    request_hash,
)

_DATE = re.compile(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b")
_LONG_NUMBER = re.compile(r"\b\d{9,11}\b")
_DRUG = re.compile(r"\b\w+(pril|olol|statin|formin|sartan|cillin|azole|prazole|mab)\b|\bmg\b", re.I)
_WORDS = re.compile(r"\b(" + "|".join(sorted(PII_HEALTH_WORDS)) + r")\w*\b", re.I)
QUESTION = NoulQuestion(
    type="noul",
    instructions="Does this text contain personal health or identity details about a specific "
    "person?",
    criteria=NoulCriteria(
        true="Health, medication, or identity details", false="Routine account notes"
    ),
)


@rule(
    "PII-001",
    Severity.WARNING,
    Family.PII,
    "Free text appears to contain personal health or identity details",
)
def pii_catalog_entry(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """Catalog entry only. The gate needs a Jev client, so it runs as pii_gate(), not here."""
    return []


@dataclass(frozen=True)
class FreeText:
    field: str
    text: str | None
    lineage: Lineage


@dataclass(frozen=True)
class GateResult:
    text: str | None  # what every output may show: the text, or PII_REDACTED_TEXT
    redacted: bool
    record: ExceptionRecord | None  # PII-001 when redacted


def flagged(text: str) -> bool:
    return any(p.search(text) for p in (_DATE, _LONG_NUMBER, SSN_PATTERN, _DRUG, _WORDS))


def hard_identifier(text: str) -> bool:
    return bool(SSN_PATTERN.search(text) or _LONG_NUMBER.search(text))


def pii_request(text: str) -> JevRequest:
    """Digits are masked, so dates and numbers reach Jev as shapes only."""
    return JevRequest(state={"text": re.sub(r"\d", "#", text)}, questions={"pii": QUESTION})


def _record(item: FreeText, probability: float | None) -> ExceptionRecord:
    where = item.lineage
    key = f"PII-001|{where.source_file}|{where.sheet}|{where.row_number}|{item.field}"
    return ExceptionRecord(
        id=f"PII-001-{hashlib.sha256(key.encode()).hexdigest()[:12]}",
        rule_id="PII-001",
        severity=Severity.WARNING,
        family=Family.PII,
        source=Path(where.source_file).stem,
        row_number=where.row_number,
        raw_hash=where.raw_hash,
        field=item.field,
        value_minimized=None,  # never shown, not even masked
        message=f"Notes on row {where.row_number} redacted",
        suggested_fix="Keep notes out of exports",
        blocks_load=False,
        lane=Lane.REVIEW,
        jev=None
        if probability is None
        else JevScores(
            entry_error_probability=None, impact_score=None, pii_probability=probability
        ),
        lineage=where,
    )


def pii_gate(items: Sequence[FreeText], client: JevClient) -> list[GateResult]:
    """One result per item, in order. Only flagged, non-identifier text is sent to Jev."""
    asked: dict[str, float | None] = {}
    out = []
    for item in items:
        text = item.text
        if not text or not flagged(text):
            out.append(GateResult(text, redacted=False, record=None))
            continue
        probability = None  # None: decided by the regex, or Jev could not answer
        if not hard_identifier(text):
            request = pii_request(text)
            key = request_hash(request.body())
            if key not in asked:
                answer = client.ask(request)
                pii = answer.answers["pii"] if isinstance(answer, JevResponse) else None
                asked[key] = pii.noul if isinstance(pii, NoulAnswer) else None
            probability = asked[key]
        if probability is not None and probability < PII_REDACT:
            out.append(GateResult(text, redacted=False, record=None))
        else:
            record = _record(item, probability)
            out.append(GateResult(PII_REDACTED_TEXT, redacted=True, record=record))
    return out

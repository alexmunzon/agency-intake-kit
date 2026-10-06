"""The PII gate (SPEC question 4): free text is checked before any log, export, or model call.

Layer 1, the regex layer, finds identity shapes: SSNs, emails, phones, dates of birth, card,
bank, routing, license, Medicare, and member numbers, passwords and PINs, and a name after a
relationship word. Each match is replaced in place by a typed placeholder such as
[REDACTED:phone], with no Jev call, so the value never leaves the machine. Layer 2: text that
still holds a date, a drug-like word, or a health word goes to Jev's noul question, already
redacted and with every digit masked. At or above PII_REDACT the whole text is redacted. If Jev
cannot answer (off mode, the spend guard, or a reply that does not fit the question), it is
redacted too: the gate fails closed.
Identical texts are asked once.
"""

import hashlib
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import polars as pl

from agency_schema.enums import Family, Lane, Severity
from agency_schema.exceptions import SSN_PATTERN, ExceptionRecord, JevScores, minimize_value
from agency_schema.lineage import Lineage
from agency_schema.registry import rule
from intake.config import PII_HEALTH_WORDS, PII_REDACT, PII_REDACTED_TEXT, PII_RELATION_WORDS
from jev_client import (
    JevBadReply,
    JevClient,
    JevRequest,
    JevResponse,
    NoulAnswer,
    NoulCriteria,
    NoulQuestion,
    request_hash,
)

log = logging.getLogger("intake.pii")
_DATE = re.compile(r"\b\d{1,4}[/-]\d{1,2}[/-]\d{1,4}\b")
_DRUG = re.compile(r"\b\w+(pril|olol|statin|formin|sartan|cillin|azole|prazole|mab)\b|\bmg\b", re.I)
_WORDS = re.compile(r"\b(" + "|".join(sorted(PII_HEALTH_WORDS)) + r")\w*\b", re.I)

# Layer 1. Each pattern's "v" group (or the whole match) is the span that gets redacted, so a
# label such as "cell" stays readable. Earlier kinds win where two matches overlap.
_NO = r"(?:\s*(?:no\.?|num\.?|number|#))?"
_SEP = r"(?:\s+(?:is|was|=))?[\s:#=-]*"
_ID = r"(?P<v>(?=[A-Za-z0-9-]*\d)[A-Za-z0-9][A-Za-z0-9-]{3,})"  # holds at least one digit
_MONTH = r"(?i:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ssn", SSN_PATTERN),
    (
        "ssn",
        re.compile(
            r"(?i:\b(?:ssn|social(?:\s+security)?)" + _NO + r")" + _SEP + r"(?P<v>\d[\d -]{3,10}\d)"
        ),
    ),
    ("email", re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")),
    (
        "dob",
        re.compile(
            r"(?i:\b(?:dob|d\.o\.b\.?|date\s+of\s+birth|born(?:\s+on)?))"
            + _SEP
            + r"(?P<v>\d{1,4}[/.-]\d{1,2}[/.-]\d{1,4}|"
            + _MONTH
            + r"\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+"
            + _MONTH
            + r"\s+\d{4})"
        ),
    ),
    (
        "phone",
        re.compile(
            r"(?i:\b(?:phone|cell|mobile|tel|telephone|fax)\b)"
            + _NO
            + _SEP
            + r"(?P<v>\+?\d[\d ().-]{6,}\d)"
        ),
    ),
    ("phone", re.compile(r"(?<![\w-])(?:\+?1[ .-]?)?\(?\d{3}\)?[ .-]?\d{3}[ .-]\d{4}\b")),
    ("card", re.compile(r"(?i:\b(?:card|cc)\b)[^\d.\n]{0,30}?(?P<v>\d[\d -]{2,22}\d)")),
    ("medicare_id", re.compile(r"(?i:\b(?:medicare|mbi)(?:\s+id)?)" + _NO + _SEP + _ID)),
    ("medicare_id", re.compile(r"\b[1-9][A-Z][A-Z0-9]\d[A-Z][A-Z0-9]\d[A-Z]{2}\d{2}\b")),
    ("member_id", re.compile(r"(?i:\b(?:member|subscriber)\s*(?:id|no\.?|number|#))" + _SEP + _ID)),
    (
        "license",
        re.compile(
            r"(?i:\b(?:driver'?s?\s+licen[cs]e|licen[cs]e(?=\s*(?:no|num|#))|dl)\b)"
            + _NO
            + _SEP
            + _ID
        ),
    ),
    ("license", re.compile(r"\b[A-Z]{1,2}\d{6,12}\b")),  # a state letter or two, then digits
    (
        "account",
        re.compile(r"(?i:\b(?:bank\s+)?(?:account|acct|routing|iban|aba)\b)" + _NO + _SEP + _ID),
    ),
    ("account", re.compile(r"\b\d{8,17}\b")),
    (
        "secret",
        re.compile(
            r"(?i:\b(?:password|passcode|passwd|pin)\b)"
            + _NO
            + r"(?:\s*(?:is|was|=|:)\s*|\s+)(?P<v>(?=[^\s,;]*\d)[^\s,;]+)"
        ),
    ),
    (
        "secret",
        re.compile(
            r"(?i:\b(?:password|passcode|passwd)\b)\s*(?:is|was|=|:)\s*"
            r"(?P<v>[^\s,;]+)"
        ),
    ),
    (
        "name",
        re.compile(
            r"(?i:\b(?:" + "|".join(sorted(PII_RELATION_WORDS)) + r")\b)"
            r"(?:\s+(?:is|named|called))?,?\s+(?P<v>[A-Z][a-z'-]+(?:\s+[A-Z][a-z'-]+)?)"
        ),
    ),
)
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


def _spans(text: str) -> list[tuple[int, int, str]]:
    taken: list[tuple[int, int, str]] = []
    for kind, pattern in _PATTERNS:
        for match in pattern.finditer(text):
            group = "v" if "v" in pattern.groupindex else 0
            start, end = match.span(group)
            if all(end <= s or start >= e for s, e, _ in taken):
                taken.append((start, end, kind))
    return sorted(taken)


def find_pii(text: str) -> list[tuple[str, str]]:
    """Every identity shape the regex layer finds, as (kind, raw value), in text order."""
    return [(kind, text[start:end]) for start, end, kind in _spans(text)]


def redact(text: str) -> tuple[str, list[tuple[str, str]]]:
    """The text with each match replaced by [REDACTED:kind], plus what was found."""
    spans = _spans(text)
    out = text
    for start, end, kind in reversed(spans):
        out = out[:start] + f"[REDACTED:{kind}]" + out[end:]
    return out, [(kind, text[start:end]) for start, end, kind in spans]


def _needs_jev(text: str) -> bool:
    return any(p.search(text) for p in (_DATE, _DRUG, _WORDS))


def flagged(text: str) -> bool:
    """True when the gate must act: an identity shape, or text worth asking Jev about."""
    return bool(_spans(text)) or _needs_jev(text)


def pii_request(text: str) -> JevRequest:
    """Digits are masked, so dates and numbers reach Jev as shapes only."""
    return JevRequest(state={"text": re.sub(r"\d", "#", text)}, questions={"pii": QUESTION})


def _record(
    item: FreeText, probability: float | None, found: list[tuple[str, str]]
) -> ExceptionRecord:
    where = item.lineage
    kinds = ", ".join(sorted({kind for kind, _ in found}))
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
        value_minimized=minimize_value(found[0][1]) if found else None,
        message=f"Notes on row {where.row_number} redacted" + (f" ({kinds})" if kinds else ""),
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
    """One result per item, in order. Only redacted text with health or date hints goes to Jev."""
    asked: dict[str, float | None] = {}
    out = []
    for item in items:
        text = item.text
        if not text or not flagged(text):
            out.append(GateResult(text, redacted=False, record=None))
            continue
        cleaned, found = redact(text)
        if not _needs_jev(cleaned):  # the regex layer decided, with no call
            out.append(GateResult(cleaned, redacted=True, record=_record(item, None, found)))
            continue
        request = pii_request(cleaned)
        key = request_hash(request.body())
        if key not in asked:
            try:
                answer = client.ask(request)
            except JevBadReply as error:  # an answer that does not fit is no answer: fail closed
                log.warning("Jev PII answer not used, text redacted (%s)", error.log_safe())
                answer = None
            pii = answer.answers["pii"] if isinstance(answer, JevResponse) else None
            asked[key] = pii.noul if isinstance(pii, NoulAnswer) else None
        probability = asked[key]  # None: Jev could not answer, so fail closed
        if probability is not None and probability < PII_REDACT:
            record = _record(item, probability, found) if found else None
            out.append(GateResult(cleaned, redacted=bool(found), record=record))
        else:
            record = _record(item, probability, found)
            out.append(GateResult(PII_REDACTED_TEXT, redacted=True, record=record))
    return out

"""Normalize messy status, line of business, commission type, and state strings (question 2).

A deterministic table decides first. Only the leftovers go to Jev, one choice question per
distinct value. A pick at or above ENUM_AUTO is used. Anything else, including "unknown"
and no answer at all, stays exactly as written, so the deterministic rules downstream
(STA-001 for status) still flag it and a person decides. Jev never overrides a rule.
"""

import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

import polars as pl
from pydantic import JsonValue

from agency_schema.enums import AgentStatus, CommissionType, LineOfBusiness, PolicyStatus
from agency_schema.formats import zip3_table
from intake.config import (
    ENUM_AUTO,
    MAP_FREE_TEXT_MAX_SPACES,
    MAP_SAMPLE_MAX_CHARS,
    NINE_DIGIT_PATTERN,
)
from intake.ingest import ingest
from intake.mapping.headers import MappingResult, map_table
from intake.mapping.jev_mapping import Asker, choice_of, map_with_jev
from intake.mapping.synonyms import Target
from jev_client import ChoiceQuestion, JevRequest, Unresolved

UNKNOWN = "unknown"
INSTRUCTIONS = "Which of the allowed values does `value` mean for the field `field`?"


def _options(enum: type[StrEnum], hints: dict[str, str] | None = None) -> dict[str, JsonValue]:
    return {v.value: (hints or {}).get(v.value) for v in enum if v.value != "UNKNOWN"}


STATUS_HINTS = {
    "ACTIVE": "coverage is in force",
    "PENDING": "submitted, not yet in force",
    "TERMINATED": "coverage ended after it started",
    "CANCELLED": "stopped before coverage started",
}
LOB_HINTS = {
    "MA": "Medicare Advantage",
    "PDP": "Medicare Part D drug plan",
    "MEDSUPP": "Medicare Supplement (Medigap)",
    "ACA": "ACA marketplace health plan",
}
STATES = sorted({s for states in zip3_table().values() for s in states})
LOB = _options(LineOfBusiness, LOB_HINTS)
ENUM_OPTIONS: dict[Target, dict[str, JsonValue]] = {
    Target("policies", "status"): _options(PolicyStatus, STATUS_HINTS),
    Target("agents", "status"): _options(AgentStatus),
    Target("policies", "line_of_business"): LOB,
    Target("rts", "line_of_business"): LOB,
    Target("commission_lines", "commission_type"): _options(CommissionType),
    **{Target(t, "state"): dict.fromkeys(STATES) for t in ("clients", "policies", "rts")},
}
# Words that mean an enum value without asking anyone, after lowercasing and punctuation.
WORDS: dict[str, dict[str, str]] = {
    "status": {
        "in force": "ACTIVE",
        "inforce": "ACTIVE",
        "approved": "ACTIVE",
        "enrolled": "ACTIVE",
        "submitted": "PENDING",
        "pend": "PENDING",
        "termed": "TERMINATED",
        "term d": "TERMINATED",
        "termd": "TERMINATED",
        "disenrolled": "TERMINATED",
        "canceled": "CANCELLED",
        "withdrawn": "CANCELLED",
        "unknown": "UNKNOWN",
    },
    "line_of_business": {
        "medicare advantage": "MA",
        "mapd": "MA",
        "part d": "PDP",
        "med supp": "MEDSUPP",
        "medicare supplement": "MEDSUPP",
        "medigap": "MEDSUPP",
        "marketplace": "ACA",
    },
    "commission_type": {"renew": "RENEWAL", "chargeback": "CHARGEBACK", "clawback": "CHARGEBACK"},
}


@dataclass(frozen=True)
class EnumDecision:
    value: str  # as written in the source
    normalized: str | None  # the enum value, None when a person decides
    method: Literal["table", "jev", "person"]
    confidence: float | None
    reason: str | None  # why: low_confidence, unknown, mode_off, risky_value, invalid_reply


def _key(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def from_table(target: Target, value: str) -> str | None:
    options = ENUM_OPTIONS[target]
    direct = {_key(o): o for o in options}
    if target.field == "status":
        direct[UNKNOWN] = "UNKNOWN"
    return direct.get(_key(value)) or WORDS.get(target.field, {}).get(_key(value))


def enum_request(target: Target, value: str) -> JevRequest:
    criteria: dict[str, JsonValue] = {**ENUM_OPTIONS[target], UNKNOWN: "cannot tell from the value"}
    question = ChoiceQuestion(type="choice", instructions=INSTRUCTIONS, criteria=criteria)
    return JevRequest(state={"field": target.field, "value": value}, questions={"value": question})


def decide_value(target: Target, value: str, asker: Asker) -> EnumDecision:
    found = from_table(target, value)
    if found is not None:
        return EnumDecision(value, found, "table", None, None)
    risky = re.search(NINE_DIGIT_PATTERN, value) or value.count(" ") > MAP_FREE_TEXT_MAX_SPACES
    if risky or len(value) > MAP_SAMPLE_MAX_CHARS:
        return EnumDecision(value, None, "person", None, "risky_value")  # never sent
    reply = asker.ask(enum_request(target, value))
    if isinstance(reply, Unresolved):
        return EnumDecision(value, None, "person", None, reply.reason)
    choice, confidence = choice_of(reply, "value")
    if choice == UNKNOWN:
        return EnumDecision(value, None, "person", confidence, "unknown")
    if confidence < ENUM_AUTO:
        return EnumDecision(value, None, "person", confidence, "low_confidence")
    return EnumDecision(value, choice, "jev", confidence, None)


def normalize_column(
    series: pl.Series, target: Target, asker: Asker
) -> tuple[pl.Series, list[EnumDecision]]:
    """Replace each value with its enum value where one was found; leave the rest as written."""
    distinct = series.drop_nulls().unique(maintain_order=True).to_list()
    decisions = [decide_value(target, v, asker) for v in distinct if v.strip()]
    found = {d.value: d.normalized for d in decisions if d.normalized is not None}
    return series.replace(found), decisions


def fill_drop(drop: Path, mapping_dir: Path, now: datetime, asker: Asker) -> list[MappingResult]:
    """Map every source in a drop with synonyms then Jev, and normalize its enum columns.

    The record-mapping command runs this, so its requests are exactly the pipeline's.
    """
    from intake.gates import run_raw_gates

    raw = ingest(drop, run_id="jev-mapping")
    if any(record.blocks_load for record in run_raw_gates(raw)):
        raise ValueError("raw gates refused the drop before header or enum questions")
    results = []
    for table in raw.tables:
        result, _ = map_with_jev(table, map_table(table, mapping_dir, now), mapping_dir, now, asker)
        for entry in result.mapping.entries:
            target = Target(entry.table or "", entry.field or "")
            if target in ENUM_OPTIONS and entry.header in table.frame.columns:
                normalize_column(table.frame[entry.header], target, asker)
        results.append(result)
    return results

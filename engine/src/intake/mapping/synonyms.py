"""Deterministic header mapping: normalize a header, then look it up in data/synonyms.yaml.

Only an exact match after normalizing maps. A near match never maps on its own; it is
offered as a candidate so a person (or Jev in PR 7) can decide.
"""

import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from functools import cache
from pathlib import Path

import yaml

from agency_schema.models import TABLE_MODELS
from intake.config import MAP_CANDIDATE_LIMIT, MAP_CANDIDATE_MIN_SCORE

SYNONYMS_PATH = Path(__file__).resolve().parent.parent / "data" / "synonyms.yaml"

# Combined columns that stand for several canonical fields. The table builder splits them.
COMPOSITE_FIELDS: dict[str, tuple[str, ...]] = {"full_name": ("first_name", "last_name")}

# Common header abbreviations, one word each. No value may itself be a key, so
# normalizing twice gives the same result as normalizing once.
ABBREVIATIONS: dict[str, str] = {
    "addr": "address",
    "amt": "amount",
    "comm": "commission",
    "dt": "date",
    "eff": "effective",
    "mbr": "member",
    "nbr": "number",
    "no": "number",
    "num": "number",
    "pmt": "payment",
    "seq": "sequence",
    "stmt": "statement",
    "term": "termination",
    "txn": "transaction",
    "yr": "year",
}


def normalize_header(header: str) -> str:
    """Lowercase words separated by single spaces: "Mbr DOB" becomes "member dob".

    Splits camelCase, turns "#" into "number", drops accents and punctuation, and expands
    the abbreviations above. The one normalization used for headers and synonyms alike.
    """
    text = unicodedata.normalize("NFKD", header)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text).replace("#", " number ")
    words = re.sub(r"[^a-z0-9]+", " ", text.casefold()).split()
    return " ".join(ABBREVIATIONS.get(word, word) for word in words)


@dataclass(frozen=True, order=True)
class Target:
    """A canonical field in a canonical table, such as clients.dob."""

    table: str
    field: str

    def __str__(self) -> str:
        return f"{self.table}.{self.field}"


@dataclass(frozen=True)
class HeaderMatch:
    header: str
    target: Target | None  # None when unmapped
    candidates: tuple[Target, ...]  # closest targets when unmapped, best first


def _similarity(a: str, b: str) -> float:
    words_a, words_b = set(a.split()), set(b.split())
    overlap = len(words_a & words_b) / len(words_a | words_b) if words_a | words_b else 0.0
    return max(SequenceMatcher(None, a, b).ratio(), overlap)


def is_canonical(target: Target) -> bool:
    """True for a real field of a canonical table (lineage excluded) or a combined column."""
    model = TABLE_MODELS.get(target.table)
    if model is None or target.field == "lineage":
        return False
    return target.field in model.model_fields or target.field in COMPOSITE_FIELDS


class SynonymTable:
    def __init__(self, raw: dict[str, dict[str, list[str]]]) -> None:
        self._index: dict[str, set[Target]] = {}
        for table, fields in raw.items():
            for field, spellings in fields.items():
                if not is_canonical(Target(table, field)):
                    raise ValueError(f"synonyms: {table} has no field {field}")
                for spelling in spellings:
                    key = normalize_header(spelling)
                    clash = {t for t in self._index.get(key, set()) if t.table == table}
                    if clash - {Target(table, field)}:
                        raise ValueError(f"synonyms: {spelling!r} means two fields of {table}")
                    self._index.setdefault(key, set()).add(Target(table, field))

    def match(self, header: str, tables: tuple[str, ...]) -> HeaderMatch:
        """Map a header to one field of the given tables, or leave it unmapped with candidates."""
        key = normalize_header(header)
        hits = sorted(t for t in self._index.get(key, set()) if t.table in tables)
        if len(hits) == 1:
            return HeaderMatch(header, hits[0], ())
        return HeaderMatch(header, None, tuple(hits) or self._closest(key, tables))

    def _closest(self, key: str, tables: tuple[str, ...]) -> tuple[Target, ...]:
        best: dict[Target, float] = {}
        for spelling, targets in self._index.items():
            score = _similarity(key, spelling)
            for target in targets:
                if target.table in tables and score > best.get(target, 0.0):
                    best[target] = score
        ranked = sorted(best.items(), key=lambda item: (-item[1], item[0]))
        return tuple(t for t, s in ranked if s >= MAP_CANDIDATE_MIN_SCORE)[:MAP_CANDIDATE_LIMIT]


@cache
def load_synonyms(path: Path = SYNONYMS_PATH) -> SynonymTable:
    with path.open(encoding="utf-8") as handle:
        return SynonymTable(yaml.safe_load(handle))

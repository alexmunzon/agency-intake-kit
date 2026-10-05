"""Score a run against ground_truth.json by record key, never by row position (#26, #61).

Each exception is tied to the source row its lineage points at (file, sheet, row), and that
row to the record keys it holds in the canonical tables: a CRM row holds its policy_id and its
client_id, a statement line holds carrier plus statement_period plus line_no and the policy it
names. TIE-005 has no row, so its keys come from its variance: {"carrier"} or {"agent_npn"}.

- Recall: a planted defect is detected when an exception with one of its expected rule ids
  carries its key. Unscored defects (no expected rule) are reported, never gated.
- False positives, on clean rows only: a clean row holds no key of any planted defect. One that
  gets any blocker, error, or warning is a false positive. The rate is false positive rows over
  clean rows. Both copies of a DUP-002 pair are labeled in ground truth (#26), so a DUP-002 on
  a labeled original is explained, never a false positive. File-level records are not rows.
"""

import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import polars as pl

from agency_schema.enums import Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import DetectionClass, DetectionSummary, Variance

Key = tuple[tuple[str, str], ...]
Unit = tuple[str, str | None, int]  # source_file, sheet, row_number
# (key field in ground truth, column in the canonical table)
KEY_COLUMNS: dict[str, tuple[tuple[tuple[str, str], ...], ...]] = {
    "policies": ((("policy_id", "policy_id"),),),
    "clients": ((("client_id", "client_id"),),),
    "agents": ((("npn", "npn"),),),
    "rts": ((("npn", "npn"),),),  # no defect is keyed by an RTS row, but its rows still count
    "commission_lines": (
        (("carrier", "carrier"), ("statement_period", "statement_period"), ("line_no", "line_no")),
        (("policy_id", "policy_ref"),),
    ),
}
# A CRM policy row also carries its client, so a client defect makes the row not clean. It
# never earns recall there: a client-keyed defect is found only on the client's own row.
NOT_CLEAN_ALSO = {"policies": ((("client_id", "client_id"),),)}
LOUD = frozenset({Severity.BLOCKER, Severity.ERROR, Severity.WARNING})


def key_of(record_key: Mapping[str, Any]) -> Key:
    return tuple(sorted((k, str(v).strip()) for k, v in record_key.items()))


def load_ground_truth(path: Path) -> list[dict[str, Any]]:
    defects: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))["defects"]
    return defects


def unit_of(record: ExceptionRecord) -> Unit | None:
    lin = record.lineage
    return None if lin is None else (lin.source_file, lin.sheet, lin.row_number)


def row_keys(
    tables: Mapping[str, pl.DataFrame],
    columns: Mapping[str, tuple[tuple[tuple[str, str], ...], ...]] = KEY_COLUMNS,
) -> dict[Unit, set[Key]]:
    """Every source row behind a canonical row, with the record keys it holds."""
    keys: dict[Unit, set[Key]] = {}
    for table, key_sets in columns.items():
        if table not in tables:
            continue
        for row in tables[table].iter_rows(named=True):
            lin = row["lineage"]
            found = keys.setdefault((lin["source_file"], lin["sheet"], lin["row_number"]), set())
            for pairs in key_sets:
                if all(row[column] is not None for _, column in pairs):
                    found.add(key_of({k: row[column] for k, column in pairs}))
    return keys


def variance_keys(variances: Iterable[Variance]) -> dict[str, set[Key]]:
    """TIE-005 totals: the carrier or the agent the total is for."""
    out: dict[str, set[Key]] = {}
    for v in variances:
        if v.rule_id == "TIE-005":
            key = {"agent_npn": v.agent_npn} if v.agent_npn else {"carrier": v.carrier}
            out.setdefault(v.exception_id, set()).add(key_of(key))
    return out


@dataclass
class Score:
    summary: DetectionSummary
    clean_rows: int
    false_positive_rows: int
    false_positives_by_rule: dict[str, int]  # clean rows each rule flagged
    missed: dict[str, list[Key]] = field(default_factory=dict)

    def recall(self) -> dict[str, float]:
        return {
            c.defect_class: c.detected / c.planted
            for c in self.summary.classes
            if c.scored and c.planted
        }


def score(
    defects: list[dict[str, Any]],
    records: list[ExceptionRecord],
    tables: Mapping[str, pl.DataFrame],
    variances: Iterable[Variance] = (),
) -> Score:
    units = row_keys(tables)
    extra = variance_keys(variances)
    hits: dict[Key, set[str]] = {}  # record key -> rule ids that fired on it
    for r in records:
        unit = unit_of(r)
        for k in extra.get(r.id, set()) | (units.get(unit, set()) if unit else set()):
            hits.setdefault(k, set()).add(r.rule_id)

    tally: dict[str, list[int]] = {}
    scored: dict[str, bool] = {}
    missed: dict[str, list[Key]] = {}
    for d in defects:
        name = d["defect_type"]
        counts = tally.setdefault(name, [0, 0])
        scored[name] = scored.get(name, False) or bool(d["scored"])
        counts[0] += 1
        if set(d["expected_rule_ids"]) & hits.get(key_of(d["record_key"]), set()):
            counts[1] += 1
        elif d["expected_rule_ids"]:
            missed.setdefault(name, []).append(key_of(d["record_key"]))

    planted = {key_of(d["record_key"]) for d in defects}
    also = row_keys(tables, NOT_CLEAN_ALSO)
    clean = {u for u, keys in units.items() if not (keys | also.get(u, set())) & planted}
    flagged: dict[Unit, set[str]] = {}
    for r in records:
        unit = unit_of(r)
        if r.severity in LOUD and unit in clean:
            flagged.setdefault(unit, set()).add(r.rule_id)
    by_rule = Counter(rule for rules in flagged.values() for rule in rules)
    rate = len(flagged) / len(clean) if clean else 0.0
    summary = DetectionSummary(
        classes=tuple(
            DetectionClass(defect_class=name, scored=scored[name], planted=p, detected=n)
            for name, (p, n) in sorted(tally.items())
        ),
        false_positive_rate=round(rate, 6),
    )
    return Score(summary, len(clean), len(flagged), dict(sorted(by_rule.items())), missed)

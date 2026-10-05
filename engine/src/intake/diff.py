"""intake diff: what changed between two runs, in plain language.

Exception ids are numbered per run, so the same problem gets a different id next time. Two
records are the same problem when they share rule, source, field, and the row's raw hash (or,
for file-level records with no row, the message).
"""

from collections import Counter
from decimal import Decimal
from pathlib import Path

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import LegStatus, LegSummary, Manifest, Scorecard, VarianceReport

STATUS_WORDS = {
    "PASSED": "Passed",
    "PASSED_WITH_WARNINGS": "Passed with warnings",
    "FAILED": "Failed",
}
LEG_TITLES = {
    "BOOK_VS_STATEMENT": "A. Book vs statement",
    "STATEMENT_VS_BOOK": "B. Statement vs book",
    "CRM_VS_STATEMENT": "C. CRM vs statement",
}
SEVERITIES = ["BLOCKER", "ERROR", "WARNING", "INFO"]
ZERO = Decimal(0)

Key = tuple[str, str, str | None, str]


class Run:
    def __init__(self, path: Path) -> None:
        self.manifest = Manifest.model_validate_json(_read(path, "manifest.json"))
        self.scorecard = Scorecard.model_validate_json(_read(path, "scorecard.json"))
        lines = _read(path, "exceptions.jsonl").splitlines()
        self.exceptions = [ExceptionRecord.model_validate_json(line) for line in lines if line]
        report = VarianceReport.model_validate_json(_read(path, "tie_out/variances.json"))
        self.other = [v for v in report.variances if v.leg is None]


def _read(path: Path, name: str) -> str:
    try:
        return (path / name).read_text()
    except OSError:
        raise ValueError(f"{path}: {name} is missing, so this is not a run folder") from None


def _key(record: ExceptionRecord) -> Key:
    return (record.rule_id, record.source, record.field, record.raw_hash or record.message)


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _money(amount: Decimal) -> str:
    return f"${amount:,.2f}"


def _by_rule(keys: list[Key]) -> list[str]:
    return [f"  {rule}: {n}" for rule, n in sorted(Counter(k[0] for k in keys).items())]


def _changes(title: str, keys: list[Key]) -> list[str]:
    return [f"{title}: none."] if not keys else [f"{title}: {len(keys)}.", *_by_rule(keys)]


def _leg_text(leg: LegSummary | None) -> str:
    if leg is None or leg.status != LegStatus.RAN:
        return "not checked"
    count = _plural(leg.variance_count or 0, "difference")
    return f"{count}, {_money(leg.variance_dollars or ZERO)}"


def _compare(title: str, before: LegSummary | None, after: LegSummary | None) -> str:
    old, new = _leg_text(before), _leg_text(after)
    if old == new:
        return f"{title}: {old}, unchanged."
    line = f"{title}: {old}, now {new}"
    if after is None or after.status != LegStatus.RAN:
        reason = after.not_run_reason if after else None
        return f"{line}. {reason}" if reason else f"{line}."
    if before is not None and before.status == LegStatus.RAN:
        delta = (after.variance_dollars or ZERO) - (before.variance_dollars or ZERO)
        if delta:
            line += f" ({'up' if delta > 0 else 'down'} {_money(abs(delta))})"
    return f"{line}."


def diff_runs(path_a: Path, path_b: Path) -> list[str]:
    """The summary as lines. Raises ValueError or ValidationError for a folder that is no run."""
    a, b = Run(path_a), Run(path_b)
    status_a = STATUS_WORDS[a.manifest.status]
    status_b = STATUS_WORDS[b.manifest.status]
    status = "unchanged" if status_a == status_b else f"now {status_b}"
    lines = [
        f"Comparing {a.manifest.run_id} (before) with {b.manifest.run_id} (after).",
        f"Status: {status_a}, {status}.",
        f"Exceptions: {len(a.exceptions)} before, {len(b.exceptions)} after.",
    ]
    count_a = Counter(str(r.severity) for r in a.exceptions)
    count_b = Counter(str(r.severity) for r in b.exceptions)
    for severity in SEVERITIES:
        was, now = count_a[severity], count_b[severity]
        change = "" if was == now else f" ({'up' if now > was else 'down'} {abs(now - was)})"
        lines.append(f"  {severity.capitalize()}: {was} to {now}{change}")

    keys_a = Counter(_key(r) for r in a.exceptions)
    keys_b = Counter(_key(r) for r in b.exceptions)
    lines += _changes("New exceptions", list((keys_b - keys_a).elements()))
    lines += _changes("Resolved exceptions", list((keys_a - keys_b).elements()))
    lines.append(f"Unchanged exceptions: {sum((keys_a & keys_b).values())}.")

    lines.append("Tie-out differences:")
    legs_a = {str(leg.leg): leg for leg in a.scorecard.tie_out}
    legs_b = {str(leg.leg): leg for leg in b.scorecard.tie_out}
    for leg, title in LEG_TITLES.items():
        lines.append("  " + _compare(title, legs_a.get(leg), legs_b.get(leg)))
    other_a = sum((abs(v.difference) for v in a.other), ZERO)
    other_b = sum((abs(v.difference) for v in b.other), ZERO)
    old = f"{_plural(len(a.other), 'difference')}, {_money(other_a)}"
    new = f"{_plural(len(b.other), 'difference')}, {_money(other_b)}"
    tail = "unchanged" if old == new else f"now {new}"
    lines.append(f"  Rate table and totals checks: {old}, {tail}.")
    return lines

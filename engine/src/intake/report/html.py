"""report.html: one self-contained page with the same numbers as the dashboard.

Read from the run's own files, so it can never disagree with them. Inline CSS, no scripts, no
external assets, so it opens from an email attachment. Money stays exact text ("$1,234.50").
"""

from decimal import Decimal
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from agency_schema.exceptions import ExceptionRecord
from agency_schema.outputs import (
    RUN_FILE_MODELS,
    LegResult,
    Manifest,
    RunStatus,
    Scorecard,
    TieOutLeg,
    Totals,
)

TOP_EXCEPTIONS = 50  # the report lists the first ones in fix-first order; the rest are in the file
ANSWER = {
    RunStatus.PASSED: "Yes. This agency can go live.",
    RunStatus.PASSED_WITH_WARNINGS: "Yes, with fixes. The load files exclude the rows below.",
    RunStatus.FAILED: "No. A blocker stopped the run, so no load files were written.",
}
LEG_NAMES = {
    TieOutLeg.BOOK_VS_STATEMENT: "Book vs statement (is every active policy paid?)",
    TieOutLeg.STATEMENT_VS_BOOK: "Statement vs book (is every payment for a known policy?)",
    TieOutLeg.CRM_VS_STATEMENT: "CRM vs statement (do the statuses agree?)",
}


def money(value: Decimal | str | None) -> str:
    """Exact dollars with thousands separators, never through a float: -1234.5 is -$1,234.50."""
    if value is None:
        return "Not checked"
    amount = Decimal(value).quantize(Decimal("0.01"))
    sign = "-" if amount < 0 else ""
    whole, cents = f"{abs(amount):.2f}".split(".")
    return f"{sign}${int(whole):,}.{cents}"


def count(value: int | None) -> str:
    return "Not checked" if value is None else f"{value:,}"


def _load(run_dir: Path) -> dict[str, Any]:
    files: dict[str, Any] = {
        name: model.model_validate_json((run_dir / name).read_text(encoding="utf-8"))
        for name, model in RUN_FILE_MODELS.items()
    }
    lines = (run_dir / "exceptions.jsonl").read_text(encoding="utf-8").splitlines()
    records = [ExceptionRecord.model_validate_json(line) for line in lines if line]
    manifest: Manifest = files["manifest.json"]
    card: Scorecard = files["scorecard.json"]
    legs: list[LegResult] = [files[f"tie_out/leg_{s}.json"] for s in TieOutLeg.file_stems()]
    totals: Totals = files["tie_out/totals_by_carrier.json"]
    return {
        "m": manifest,
        "card": card,
        "answer": ANSWER[manifest.status],
        "legs": [(LEG_NAMES[leg.leg], leg) for leg in legs],
        "totals": totals,
        "records": records[:TOP_EXCEPTIONS],
        "more": max(0, len(records) - TOP_EXCEPTIONS),
        "by_rule": sorted(card.exceptions_by_rule.items(), key=lambda kv: (-kv[1], kv[0])),
        "detection": card.detection,
        "clean": (run_dir / "clean").is_dir(),
    }


def render_report(run_dir: Path) -> str:
    env = Environment(
        loader=PackageLoader("intake.report", "templates"),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["money"] = money
    env.filters["count"] = count
    env.filters["pct"] = lambda v: f"{v * 100:.1f} percent"
    return env.get_template("report.html.j2").render(**_load(run_dir))

"""docs/rules.md is generated from the registry and must match it."""

from pathlib import Path

from typer.testing import CliRunner

from agency_schema.registry import catalog
from intake.cli import app
from intake.rules import ROW_FAMILIES
from intake.rules.docs import render_rules_md

RULES_MD = Path(__file__).resolve().parents[3] / "docs" / "rules.md"
# BUILD-GUIDE section 6: the 22 row rules and their severities.
EXPECTED = {
    **dict.fromkeys(["DOB-001", "DOB-002", "MBI-001", "NPN-001", "NPN-002"], "ERROR"),
    **dict.fromkeys(["PLN-001", "PLN-002", "PLN-003", "PLN-004"], "ERROR"),
    **dict.fromkeys(["ADR-001", "ADR-002", "ADR-003", "DAT-001", "DAT-002", "DAT-003"], "ERROR"),
    **dict.fromkeys(["DOB-003", "MBI-002", "MBI-003", "CON-001", "CON-002", "STA-001"], "WARNING"),
    "DAT-004": "INFO",
}


def test_row_rules_match_the_guide_catalog() -> None:
    row = {m.rule_id: m.severity for m in catalog() if m.family in ROW_FAMILIES}
    assert row == EXPECTED


def test_committed_rules_md_is_current() -> None:
    assert RULES_MD.read_text() == render_rules_md(), (
        "run: uv run intake rules --md > ../docs/rules.md"
    )


def test_rules_md_lists_exactly_the_catalog() -> None:
    text = render_rules_md()
    assert [
        line.split(" | ")[0][2:]
        for line in text.splitlines()
        if line.startswith("| ") and "-" in line[2:9]
    ] == [m.rule_id for m in catalog()]


def test_cli_prints_the_markdown() -> None:
    result = CliRunner().invoke(app, ["rules", "--md"])
    assert result.exit_code == 0
    assert result.output == render_rules_md()

import json
from pathlib import Path

from typer.testing import CliRunner

from intake.cli import app


def test_finance_invalid_input_does_not_echo_source(tmp_path: Path) -> None:
    source = tmp_path / "statement.json"
    source.write_text('{"private_note": "do-not-log-this"}')
    result = CliRunner().invoke(
        app, ["finance-review", "--statement", str(source), "--mapping", str(source)]
    )
    assert result.exit_code == 2
    assert "Finance review refused" in result.output
    assert "do-not-log-this" not in result.output
    assert source.read_text() == '{"private_note": "do-not-log-this"}'


def test_finance_cli_exports_synthetic_fixture() -> None:
    fixtures = Path(__file__).resolve().parents[3] / "fixtures" / "finance-review"
    result = CliRunner().invoke(
        app,
        [
            "finance-review",
            "--statement",
            str(fixtures / "statement.json"),
            "--mapping",
            str(fixtures / "mapping.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["statement_total"] == "75.03"
    assert output["category_totals"]["renewal"] == "75.00"
    assert output["category_totals"]["unclassified"] == "0.03"
    assert output["total_check"] == "PASS"

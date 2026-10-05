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


def test_finance_rejects_conflicting_json_keys_and_numeric_approval(tmp_path: Path) -> None:
    import pytest

    from intake.revenue import RevenueMapping

    fixtures = Path(__file__).resolve().parents[3] / "fixtures" / "finance-review"
    mapping_text = (fixtures / "mapping.json").read_text()
    invalid_mappings = [
        mapping_text.replace('"Renewal": "renewal"', '"Renewal": "renewal", "Renewal": "bonus"'),
        mapping_text.replace('"2026-10-05T12:00:00Z"', "1791201600"),
        mapping_text.replace('"2026-10-05T12:00:00Z"', '"0"'),
    ]
    for invalid in invalid_mappings:
        with pytest.raises(ValueError):
            RevenueMapping.model_validate_json(invalid)
        mapping = tmp_path / "mapping.json"
        mapping.write_text(invalid)
        result = CliRunner().invoke(
            app,
            [
                "finance-review",
                "--statement",
                str(fixtures / "statement.json"),
                "--mapping",
                str(mapping),
            ],
        )
        assert result.exit_code == 2
        assert "Finance review refused" in result.output
        assert "Synthetic Finance Reviewer" not in result.output

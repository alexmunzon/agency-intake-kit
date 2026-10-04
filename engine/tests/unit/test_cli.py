from typer.testing import CliRunner

from intake.cli import app as intake_app
from synth_agency_data.cli import app as synth_app

runner = CliRunner()


def test_intake_version() -> None:
    result = runner.invoke(intake_app, ["version"])
    assert result.exit_code == 0
    assert "0.0.0" in result.output


def test_synth_version() -> None:
    result = runner.invoke(synth_app, ["version"])
    assert result.exit_code == 0
    assert "0.0.0" in result.output

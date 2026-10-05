"""Shared end-to-end runs: each fixture runs through the real pipeline once per session."""

from datetime import datetime
from pathlib import Path

import pytest

from agency_schema.outputs import JevMode
from intake.run.pipeline import RunOptions, RunResult, run
from synth_agency_data.world import build_world
from synth_agency_data.writers import write_drop

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures"
AS_OF = datetime.fromisoformat("2026-10-01T09:00:00+00:00")


def run_drop(drop: Path, out: Path, mode: JevMode = JevMode.REPLAY) -> RunResult:
    return run(RunOptions(drop=drop, out=out, jev_mode=mode, as_of=AS_OF))


@pytest.fixture(scope="session")
def agency_a(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    return run_drop(FIXTURES / "agency-a" / "drop", tmp_path_factory.mktemp("a") / "agency-a")


@pytest.fixture(scope="session")
def agency_a_again(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    return run_drop(FIXTURES / "agency-a" / "drop", tmp_path_factory.mktemp("b") / "agency-a")


@pytest.fixture(scope="session")
def truncated(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    drop = FIXTURES / "agency-a-truncated" / "drop"
    return run_drop(drop, tmp_path_factory.mktemp("t") / "truncated")


@pytest.fixture(scope="session")
def ssn(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    return run_drop(FIXTURES / "agency-a-ssn" / "drop", tmp_path_factory.mktemp("s") / "ssn")


@pytest.fixture(scope="session")
def clean_world(tmp_path_factory: pytest.TempPathFactory) -> RunResult:
    """The PR 2 world with no injectors (`synth generate --no-inject`), as a real drop."""
    folder = tmp_path_factory.mktemp("clean")
    write_drop(build_world(seed=42, n_clients=2000), [], folder / "drop", plant_pii=False)
    return run_drop(folder / "drop", folder / "clean-world")

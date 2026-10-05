"""The run's Jev client: per-question cassette folders, replay misses, and record-run's guard."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from agency_schema.outputs import JevMode
from intake.cli import app
from intake.exceptions.pii import pii_request
from intake.mapping.enums import enum_request
from intake.mapping.synonyms import Target
from intake.run.jev import (
    MAPPING_CASSETTES,
    RUN_CASSETTES,
    RunJevClient,
    cassette_dir_for,
    estimate_cost,
)
from jev_client import Unresolved, request_hash


def test_mapping_questions_read_mapping_cassettes_and_the_rest_read_run() -> None:
    assert cassette_dir_for(enum_request(Target("policies", "status"), "XFER")) == MAPPING_CASSETTES
    assert cassette_dir_for(pii_request("Daughter is the contact")) == RUN_CASSETTES


def test_a_replay_miss_goes_to_a_person_and_is_kept_for_recording() -> None:
    client = RunJevClient(mode=JevMode.REPLAY, api_key=None)
    request = pii_request("not recorded anywhere 0000")
    answer = client.ask(request, pii_cleared=True)
    assert isinstance(answer, Unresolved) and answer.reason == "not_recorded"
    assert list(client.misses) == [request_hash(request.body())]
    assert client.usage.calls == 0  # a miss is not a call and costs nothing
    assert estimate_cost(client.misses) > 0


def test_a_recorded_mapping_question_is_answered_in_replay() -> None:
    client = RunJevClient(mode=JevMode.REPLAY, api_key=None)
    answer = client.ask(enum_request(Target("policies", "status"), "XFER"))
    assert not isinstance(answer, Unresolved) and client.usage.calls == 1


def test_record_run_refuses_without_jev_mode_record(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_MODE", raising=False)
    drop = Path(__file__).resolve().parents[3] / "fixtures" / "agency-a"
    result = CliRunner().invoke(app, ["jev", "record-run", "--drop", str(drop)])
    assert result.exit_code == 2 and "Refusing: set JEV_MODE=record" in result.output
    monkeypatch.setenv("JEV_MODE", "replay")
    assert CliRunner().invoke(app, ["jev", "record-run", "--drop", str(drop)]).exit_code == 2

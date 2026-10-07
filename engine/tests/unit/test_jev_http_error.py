"""Live mode: an HTTP error from the API fails safe like a bad reply, and bad replies are counted.

A mock transport stands in for the API, so nothing reaches the network or spends money.
"""

import logging
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.enums import Lane
from agency_schema.exceptions import ExceptionRecord
from agency_schema.lineage import Lineage
from agency_schema.outputs import JevMode
from intake.config import PII_REDACTED_TEXT
from intake.exceptions.pii import FreeText, pii_gate, pii_request
from intake.exceptions.triage import TriageItem, triage
from intake.mapping.enums import decide_value
from intake.mapping.jev_mapping import Asker, decide_header
from intake.mapping.synonyms import Target
from jev_client import JevClient
from jev_client.cassettes import save_cassette

SECRET_BODY = "server says: patient has diabetes, key sk-live-123"
HEALTH = "Client said the new prescription started on 03/12/2026"
STATUS = Target("policies", "status")


def failing(status: int = 500) -> JevClient:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=SECRET_BODY)

    transport = httpx.MockTransport(handle)
    return JevClient(mode=JevMode.LIVE, api_key="k-test", allow_spend=True, transport=transport)


def test_an_http_error_leaves_the_header_for_a_person(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    import polars as pl

    client = failing()
    decision = decide_header("enrollment", "Birth Dt", pl.Series(["1958-03-12"]), Asker(client))
    assert (decision.choice, decision.route, decision.reason) == (None, "person", "http_error")
    assert "500" in caplog.text and "diabetes" not in caplog.text and "sk-live" not in caplog.text
    usage = client.usage
    assert (usage.calls, usage.budget_tripped, usage.invalid_answers) == (0, False, 0)


def test_an_http_error_keeps_an_enum_value_as_written() -> None:
    decision = decide_value(STATUS, "chk w/ carrier", Asker(failing(400)))
    assert (decision.normalized, decision.method, decision.reason) == (
        None,
        "person",
        "http_error",
    )


def test_an_http_error_leaves_the_triage_record_for_a_person(
    exception_kwargs: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    item = TriageItem(ExceptionRecord.model_validate(exception_kwargs), {"dob": "1890-03-12"})
    [left] = triage([item], failing(503))
    off = triage([item], JevClient(mode=JevMode.OFF, api_key=None))[0]
    assert left == off and (left.lane, left.jev) == (Lane.UNREVIEWED, None)
    assert "503" in caplog.text and "diabetes" not in caplog.text


def test_an_http_error_fails_the_pii_gate_closed(
    lineage_kwargs: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    item = FreeText("notes", HEALTH, Lineage(**lineage_kwargs))
    [result] = pii_gate([item], failing(500))
    assert (result.text, result.redacted) == (PII_REDACTED_TEXT, True)
    assert result.record is not None and result.record.rule_id == "PII-001"
    assert result.record.jev is None
    assert "500" in caplog.text and "diabetes" not in caplog.text
    assert "prescription" not in caplog.text


def test_bad_replies_are_counted_in_usage(tmp_path: Path) -> None:
    bad = {"model": "m", "answers": {"pii": {"type": "noul", "noul": "low"}},
           "usage": {"input_tokens": 10, "output_tokens": 1}}  # fmt: skip
    save_cassette(tmp_path, pii_request(HEALTH).body(), bad)
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    assert client.usage.invalid_answers == 0
    lineage = {"source_file": "crm.csv", "sheet": None, "row_number": 2, "raw_hash": "a" * 64,
               "run_id": "r", "mapping_version": "v"}  # fmt: skip
    pii_gate([FreeText("notes", HEALTH, Lineage(**lineage))], client)
    assert client.usage.invalid_answers == 1


def test_record_run_prints_the_invalid_count(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import shutil

    from typer.testing import CliRunner

    from intake import cli
    from intake.run import jev as run_jev

    drop = Path(__file__).parents[3] / "fixtures" / "agency-a" / "drop"
    shutil.copytree(run_jev.MAPPING_CASSETTES, tmp_path / "mapping")
    monkeypatch.setattr(run_jev, "MAPPING_CASSETTES", tmp_path / "mapping")
    monkeypatch.setattr(run_jev, "RUN_CASSETTES", tmp_path / "run")  # empty: every run question
    monkeypatch.setenv("JEV_MODE", "record")  # the command's guard; the API below is a mock

    reply = {
        "model": "m",
        "answers": {"x": {"type": "noul", "noul": 0.1}},  # answers no question asked
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=reply)

    class MockedApi(run_jev.RunJevClient):  # record mode against the mock, never the network
        def __init__(self, **_: Any) -> None:
            mock = httpx.MockTransport(handle)
            super().__init__(
                mode=JevMode.RECORD, api_key="k-test", allow_spend=True, transport=mock
            )

    import intake.run.pipeline  # noqa: F401  (imported before the patch, as in a real session)

    monkeypatch.setattr(run_jev, "RunJevClient", MockedApi)
    out = CliRunner().invoke(cli.app, ["jev", "record-run", "--drop", str(drop)])
    assert out.exit_code == 0, out.output
    done = out.output.strip().splitlines()[-1]
    assert done.startswith("Done.") and "invalid answers 0" not in done
    assert "(not used, a person decides)" in done
    count = int(done.split("invalid answers ")[1].split(" ")[0])
    assert count > 0


def unreachable(error: type[httpx.TransportError]) -> JevClient:
    def handle(request: httpx.Request) -> httpx.Response:
        raise error("no reply", request=request)

    transport = httpx.MockTransport(handle)
    return JevClient(mode=JevMode.LIVE, api_key="k-test", allow_spend=True, transport=transport)


@pytest.mark.parametrize("error", [httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout])
def test_a_timeout_or_refused_connection_fails_safe(
    error: type[httpx.TransportError],
    lineage_kwargs: dict[str, Any],
    exception_kwargs: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    import polars as pl

    caplog.set_level(logging.DEBUG)
    header = decide_header(
        "enrollment", "Birth Dt", pl.Series(["1958-03-12"]), Asker(unreachable(error))
    )
    assert (header.choice, header.route, header.reason) == (None, "person", "http_error")
    value = decide_value(STATUS, "chk w/ carrier", Asker(unreachable(error)))
    assert (value.normalized, value.reason) == (None, "http_error")
    item = TriageItem(ExceptionRecord.model_validate(exception_kwargs), {"dob": "1890-03-12"})
    [left] = triage([item], unreachable(error))
    assert (left.lane, left.jev) == (Lane.UNREVIEWED, None)
    [gated] = pii_gate([FreeText("notes", HEALTH, Lineage(**lineage_kwargs))], unreachable(error))
    assert (gated.text, gated.redacted) == (PII_REDACTED_TEXT, True)
    assert error.__name__ in caplog.text and "prescription" not in caplog.text

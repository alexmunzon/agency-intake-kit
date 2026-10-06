"""A Jev reply that does not fit the question stays unresolved and never crashes the import.

Hand-written cassettes in a temporary folder, replay mode only, so nothing reaches the network.
"""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from agency_schema.enums import Lane
from agency_schema.exceptions import ExceptionRecord
from agency_schema.lineage import Lineage
from agency_schema.outputs import JevMode
from intake.config import PII_REDACTED_TEXT
from intake.exceptions.pii import FreeText, pii_gate, pii_request
from intake.exceptions.triage import TriageItem, triage, triage_request
from intake.ingest import ingest
from intake.mapping.enums import decide_value, enum_request, normalize_column
from intake.mapping.headers import map_table
from intake.mapping.jev_mapping import Asker, header_request, map_with_jev
from intake.mapping.synonyms import Target
from jev_client import JevBadReply, JevClient, JevRequest
from jev_client.cassettes import save_cassette

DROP = Path(__file__).parents[3] / "fixtures" / "agency-a" / "drop"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
BIRTH = "Birth Dt (mm/dd/yy)"
STATUS = Target("policies", "status")
USAGE = {"input_tokens": 100, "output_tokens": 1}


def _answer(choice: Any) -> dict[str, Any]:
    return {"type": "choice", "choice": choice, "probabilities": {}, "confidence": 0.99}


def malformed(qid: str) -> dict[str, Any]:
    return {"model": "jev-mock", "answers": {qid: _answer(7)}, "usage": USAGE}


def off_options(qid: str) -> dict[str, Any]:
    return {"model": "jev-mock", "answers": {qid: _answer("made.up_field")}, "usage": USAGE}


def wrong_question(qid: str) -> dict[str, Any]:
    return {"model": "jev-mock", "answers": {f"{qid}_x": _answer("unknown")}, "usage": USAGE}


BAD = pytest.mark.parametrize("bad", [malformed, off_options, wrong_question])


def asker_with(tmp: Path, request: JevRequest, response: dict[str, Any]) -> Asker:
    save_cassette(tmp, request.body(), response)
    return Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp))


@BAD
def test_a_bad_header_reply_leaves_the_header_unmapped_for_a_person(
    bad: Callable[[str], dict[str, Any]], tmp_path: Path
) -> None:
    table = next(t for t in ingest(DROP, run_id="t").tables if t.source == "enrollment")
    request = header_request("enrollment", BIRTH, table.frame[BIRTH])
    asker = asker_with(tmp_path / "cassettes", request, bad("field"))
    mapped = map_table(table, tmp_path / "m", NOW)
    result, [decision] = map_with_jev(table, mapped, tmp_path / "m", NOW, asker)
    assert (decision.choice, decision.route, decision.reason) == (None, "person", "invalid_reply")
    entry = result.mapping.entry(BIRTH)
    assert entry is not None and entry.method == "unmapped" and entry.field is None
    birth = [e for e in result.exceptions if "Birth" in e.message]
    assert {e.rule_id for e in birth} == {"MAP-001", "MAP-002"}
    assert any("invalid model answer" in e.message for e in birth if e.rule_id == "MAP-002")
    assert asker.client is not None and asker.client.usage.calls == 1  # billed, so counted


@BAD
def test_a_bad_enum_reply_keeps_the_value_as_written(
    bad: Callable[[str], dict[str, Any]], tmp_path: Path
) -> None:
    asker = asker_with(tmp_path, enum_request(STATUS, "chk w/ carrier"), bad("value"))
    decision = decide_value(STATUS, "chk w/ carrier", asker)
    assert (decision.normalized, decision.method, decision.reason) == (
        None,
        "person",
        "invalid_reply",
    )


def test_one_bad_enum_reply_does_not_stop_the_other_values(tmp_path: Path) -> None:
    target = STATUS
    save_cassette(tmp_path, enum_request(target, "XFER").body(), off_options("value"))
    good = {"model": "jev-mock", "answers": {"value": _answer("PENDING")}, "usage": USAGE}
    save_cassette(tmp_path, enum_request(target, "chk w/ carrier").body(), good)
    asker = Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path))
    values, decisions = normalize_column(pl.Series(["XFER", "chk w/ carrier"]), target, asker)
    assert values.to_list() == ["XFER", "PENDING"]
    assert [d.reason for d in decisions] == ["invalid_reply", None]


NOUL = {"type": "noul", "noul": 0.95}
SCORE = {
    "type": "score",
    "score": 1.0,
    "confidence": 0.5,
    "legend": {"0": "Cosmetic", "1": "Reporting", "2": "Compliance or money"},
    "probabilities": {"0": 0.2, "1": 0.6, "2": 0.2},
}
BAD_TRIAGE = {
    "malformed": {"is_entry_error": {"type": "noul", "noul": "high"}, "impact": SCORE},
    "off_options": {"is_entry_error": NOUL, "impact": {**SCORE, "score": 7.0}},
    "wrong_question": {"is_entry_error_x": NOUL, "impact": SCORE},
}


@pytest.mark.parametrize("bad", BAD_TRIAGE)
def test_a_bad_triage_reply_leaves_the_record_for_a_person(
    bad: str, tmp_path: Path, exception_kwargs: dict[str, Any]
) -> None:
    rows = ({"dob": "1890-03-12"}, {"dob": "abc"})
    items = [
        TriageItem(ExceptionRecord.model_validate({**exception_kwargs, "id": f"EX-{i}"}), row)
        for i, row in enumerate(rows)
    ]
    bad_reply = {"model": "m", "answers": BAD_TRIAGE[bad], "usage": USAGE}
    good_reply = {
        "model": "m",
        "answers": {"is_entry_error": NOUL, "impact": SCORE},
        "usage": USAGE,
    }
    save_cassette(tmp_path, triage_request(items[0]).body(), bad_reply)
    save_cassette(tmp_path, triage_request(items[1]).body(), good_reply)
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    left, routed = triage(items, client)
    off = triage(items[:1], JevClient(mode=JevMode.OFF, api_key=None))[0]
    assert left == off  # the same as no answer: the rules' record, in the human queue
    kept = ("severity", "blocks_load", "suggested_fix", "message", "rule_id")
    assert [getattr(left, k) for k in kept] == [getattr(items[0].record, k) for k in kept]
    assert (left.lane, left.jev) == (Lane.UNREVIEWED, None)
    assert routed.lane == Lane.SUGGESTED_FIX and routed.jev is not None  # the run goes on


BAD_PII = {
    "malformed": {"pii": {"type": "noul", "noul": "low"}},
    "off_options": {"pii": {"type": "noul", "noul": 1.5}},
    "wrong_question": {"pii_x": {"type": "noul", "noul": 0.01}},
}
HEALTH = "Client said the new prescription started on 03/12/2026"


@pytest.mark.parametrize("bad", BAD_PII)
def test_a_bad_pii_reply_fails_closed(
    bad: str, tmp_path: Path, lineage_kwargs: dict[str, Any]
) -> None:
    item = FreeText("notes", HEALTH, Lineage(**lineage_kwargs))
    reply = {"model": "m", "answers": BAD_PII[bad], "usage": USAGE}
    save_cassette(tmp_path, pii_request(HEALTH).body(), reply)
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    [result] = pii_gate([item], client)
    assert (result.text, result.redacted) == (PII_REDACTED_TEXT, True)
    assert result.record is not None and result.record.rule_id == "PII-001"
    assert result.record.jev is None  # no probability from a reply that was not used
    assert "prescription" not in result.record.model_dump_json()


SECRET = "patient has diabetes"


def test_no_reply_content_reaches_the_logs(
    tmp_path: Path,
    exception_kwargs: dict[str, Any],
    lineage_kwargs: dict[str, Any],
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    leak = {"model": "m", "answers": {"value": _answer([SECRET])}, "usage": USAGE}
    decide_value(STATUS, "XFER", asker_with(tmp_path / "e", enum_request(STATUS, "XFER"), leak))
    item = TriageItem(ExceptionRecord.model_validate(exception_kwargs), {"dob": "1890-03-12"})
    answers = {"is_entry_error": {"type": "noul", "noul": SECRET}, "impact": SCORE}
    save_cassette(tmp_path, triage_request(item).body(), {"model": "m", "answers": answers})
    triage([item], JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path))
    pii = {"model": "m", "answers": {"pii": {"type": "noul", "noul": SECRET}}, "usage": USAGE}
    save_cassette(tmp_path, pii_request(HEALTH).body(), pii)
    note = FreeText("notes", HEALTH, Lineage(**lineage_kwargs))
    pii_gate([note], JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path))
    assert {"intake.mapping", "intake.triage", "intake.pii"} <= {r.name for r in caplog.records}
    assert SECRET not in caplog.text


def test_the_error_text_never_echoes_the_reply(tmp_path: Path) -> None:
    pii = {"model": "m", "answers": {"pii": {"type": "noul", "noul": SECRET}}, "usage": USAGE}
    save_cassette(tmp_path, pii_request(HEALTH).body(), pii)
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    with pytest.raises(JevBadReply) as caught:
        client.ask(pii_request(HEALTH))
    assert SECRET not in str(caught.value)


def test_a_bad_pii_reply_stays_closed_for_identical_notes(
    tmp_path: Path, lineage_kwargs: dict[str, Any]
) -> None:
    save_cassette(
        tmp_path, pii_request(HEALTH).body(), {"model": "m", "answers": BAD_PII["malformed"]}
    )
    notes = [
        FreeText("notes", HEALTH, Lineage(**{**lineage_kwargs, "row_number": n})) for n in (2, 3)
    ]
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    results = pii_gate(notes, client)
    assert [(r.text, r.redacted) for r in results] == [(PII_REDACTED_TEXT, True)] * 2
    assert client.usage.calls == 1  # asked once, and the cached "no answer" stays closed


def test_record_mapping_reports_invalid_answers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from typer.testing import CliRunner

    from intake import cli
    from intake.mapping.jev_mapping import MAPPING_CASSETTES

    for path in MAPPING_CASSETTES.glob("*.json"):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["request"]["state"].get("header") == BIRTH:
            next(iter(data["response"]["answers"].values()))["choice"] = "made.up_field"
        (tmp_path / path.name).write_text(json.dumps(data), encoding="utf-8")
    monkeypatch.setenv("JEV_MODE", "record")  # the command's guard; the client below replays
    monkeypatch.setattr(
        cli,
        "_record_client",
        lambda c: JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=c),
    )
    args = ["jev", "record-mapping", "--drop", str(DROP.parent), "--cassettes", str(tmp_path)]
    out = CliRunner().invoke(cli.app, args)
    assert out.exit_code == 0, out.output
    assert "invalid answers 1 (not used, a person decides)" in out.output

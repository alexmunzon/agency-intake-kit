"""Jev triage (PR 11): routing at the thresholds, off mode, deduplication, and the agency-a count.

No test reaches the network: Jev answers come from httpx.MockTransport or from the hand-made
cassettes in tests/cassettes/synthetic/ (made up, not recorded; PR 12 records the real ones).
"""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.enums import Lane, Severity
from agency_schema.exceptions import ExceptionRecord, minimize_value
from agency_schema.outputs import JevMode
from intake.exceptions.triage import (
    TriageItem,
    attach_rows,
    needs_triage,
    planned_requests,
    queue_order,
    triage,
    triage_request,
    value_shape,
)
from jev_client import CassetteMiss, JevClient, request_hash

SYNTHETIC = Path(__file__).resolve().parents[1] / "cassettes" / "synthetic"
FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "agency-a"
# A real run of fixtures/agency-a (PR 12): 705 errors and warnings from row rules, cross-record
# checks, and the tie-out (PII-001 is the gate's own), sent as 157 distinct requests. Stated in
# docs/jev.md.
AGENCY_A_TRIAGE_EXCEPTIONS = 705
AGENCY_A_TRIAGE_CALLS = 157


def item(base: dict[str, Any], rule_id: str, field: str, row: dict[str, Any]) -> TriageItem:
    record = ExceptionRecord.model_validate(
        {
            **base,
            "id": f"{rule_id}-{row.get('row', 2)}",
            "rule_id": rule_id,
            "family": rule_id[:3],
            "severity": "ERROR" if rule_id != "CON-001" else "WARNING",
            "field": field,
            "value_minimized": minimize_value(row[field]),
        }
    )
    return TriageItem(record, row)


def dob_typo(base: dict[str, Any], dob: str = "1890-03-12") -> TriageItem:
    return item(base, "DOB-002", "dob", {"dob": dob, "first_name": "Ana", "notes": "secret"})


def orphan(base: dict[str, Any]) -> TriageItem:
    row = {"carrier_member_id": "HL-998213", "carrier": "Harborline", "commission_type": "NEW"}
    return item({**base, "source": "commission_lines"}, "TIE-002", "carrier_member_id", row)


def answer(noul: float, score: float = 1.0) -> dict[str, Any]:
    return {
        "model": "synthetic-test",
        "answers": {
            "is_entry_error": {"type": "noul", "noul": noul},
            "impact": {
                "type": "score",
                "score": score,
                "confidence": 0.5,
                "legend": {"0": "Cosmetic", "1": "Reporting", "2": "Compliance or money"},
                "probabilities": {"0": 0.2, "1": 0.6, "2": 0.2},
            },
        },
        "usage": {"input_tokens": 120, "output_tokens": 4},
    }


def mock_client(
    tmp_path: Path, reply: Callable[[dict[str, Any]], dict[str, Any]], sent: list[Any]
) -> JevClient:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        return httpx.Response(200, json=reply(body))

    return JevClient(
        mode=JevMode.LIVE,
        api_key="mock-key-not-real",
        cassette_dir=tmp_path,
        allow_spend=True,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(
    ("noul", "lane"),
    [
        (0.80, Lane.SUGGESTED_FIX),
        (0.7999, Lane.REVIEW),
        (0.2001, Lane.REVIEW),
        (0.20, Lane.BUSINESS_EVENT),
    ],
)
def test_routes_at_the_thresholds(
    tmp_path: Path, exception_kwargs: dict[str, Any], noul: float, lane: Lane
) -> None:
    sent: list[Any] = []
    (out,) = triage(
        [dob_typo(exception_kwargs)], mock_client(tmp_path, lambda _: answer(noul), sent)
    )
    assert out.lane == lane
    assert out.jev is not None and out.jev.entry_error_probability == noul
    assert (out.severity, out.blocks_load) == (Severity.ERROR, False)  # Jev never changes these


def test_off_mode_sends_everything_to_the_human_queue(exception_kwargs: dict[str, Any]) -> None:
    client = JevClient(mode=JevMode.OFF, api_key=None)
    out = triage([dob_typo(exception_kwargs), orphan(exception_kwargs)], client)
    assert [(r.lane, r.jev) for r in out] == [(Lane.UNREVIEWED, None)] * 2
    assert client.usage.calls == 0


def test_identical_requests_are_sent_once(tmp_path: Path, exception_kwargs: dict[str, Any]) -> None:
    sent: list[Any] = []
    items = [
        dob_typo(exception_kwargs, "1890-03-12"),
        dob_typo(exception_kwargs, "1885-11-30"),  # same rule, shape, and neighbors
        orphan(exception_kwargs),
    ]
    out = triage(items, mock_client(tmp_path, lambda _: answer(0.9), sent))
    assert len(sent) == 2 == len(planned_requests(items))
    assert [r.lane for r in out] == [Lane.SUGGESTED_FIX] * 3


def test_state_is_minimized(tmp_path: Path, exception_kwargs: dict[str, Any]) -> None:
    sent: list[Any] = []
    triage([dob_typo(exception_kwargs)], mock_client(tmp_path, lambda _: answer(0.9), sent))
    text = json.dumps(sent)
    assert "1890" not in text and "secret" not in text and "Ana" not in text
    assert sent[0]["state"]["value_shape"] == "9999-99-99" == value_shape("1890-03-12")


def test_info_and_blockers_are_not_triaged(exception_kwargs: dict[str, Any]) -> None:
    info = ExceptionRecord.model_validate(
        {**exception_kwargs, "rule_id": "DAT-004", "family": "DAT", "severity": "INFO"}
    )
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=SYNTHETIC)
    assert triage([TriageItem(info, None)], client) == [info]


def test_replay_cassettes_route_a_typo_and_an_orphan_payment(
    exception_kwargs: dict[str, Any],
) -> None:
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=SYNTHETIC)
    typo, paid = triage([dob_typo(exception_kwargs), orphan(exception_kwargs)], client)
    assert (typo.lane, paid.lane) == (Lane.SUGGESTED_FIX, Lane.BUSINESS_EVENT)


def test_cassette_miss_fails_loudly_with_the_hash(
    tmp_path: Path, exception_kwargs: dict[str, Any]
) -> None:
    one = dob_typo(exception_kwargs)
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    with pytest.raises(CassetteMiss) as miss:
        triage([one], client)
    assert miss.value.request_hash == request_hash(triage_request(one).body())
    assert miss.value.request_hash in str(miss.value)


def test_queue_order_is_deterministic(tmp_path: Path, exception_kwargs: dict[str, Any]) -> None:
    sent: list[Any] = []
    items = [orphan(exception_kwargs), dob_typo(exception_kwargs)]
    reply = lambda body: answer(0.1 if body["state"]["rule_id"] == "TIE-002" else 0.9)  # noqa: E731
    out = triage(items, mock_client(tmp_path, reply, sent))
    ordered = queue_order(out)
    assert [r.rule_id for r in ordered] == ["DOB-002", "TIE-002"]
    assert queue_order(reversed(out)) == ordered


def test_agency_a_expected_call_count(tmp_path: Path) -> None:
    """The distinct triage requests a real run of fixtures/agency-a sends (PR 12 records these).

    Counted from the run's own records and frames, so the number holds before and after the
    triage cassettes are recorded. Before recording each one is a replay miss; no PII text
    needs Jev, because the regex layer catches all 26 planted notes.
    """
    from datetime import datetime

    from intake.run.pipeline import RunOptions, run, triage_frames

    as_of = datetime.fromisoformat("2026-10-01T09:00:00+00:00")
    result = run(RunOptions(drop=FIXTURE / "drop", out=tmp_path / "count", as_of=as_of))
    triaged = [r for r in result.records if needs_triage(r)]
    planned = planned_requests(attach_rows(result.records, triage_frames(result.tables)))
    assert (len(triaged), len(planned)) == (AGENCY_A_TRIAGE_EXCEPTIONS, AGENCY_A_TRIAGE_CALLS)
    assert set(result.client.misses) <= set(planned)  # every miss is a triage request

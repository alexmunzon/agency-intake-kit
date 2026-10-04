import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.outputs import JevMode
from jev_client import (
    CassetteMiss,
    ChoiceAnswer,
    ChoiceQuestion,
    JevClient,
    JevHTTPError,
    JevRequest,
    JevResponse,
    NoulAnswer,
    NoulQuestion,
    ScoreAnswer,
    ScoreQuestion,
    SpendNotApproved,
    Unresolved,
    estimate_cost_usd,
    minimize_state,
    request_hash,
)
from jev_client.cassettes import save_cassette

KEY = "ts-test-key-DO-NOT-LEAK-1234"

TRIAGE = JevRequest(
    state={"rule_id": "DOB-002", "field": "dob", "value_shape": "19**-**-**"},
    questions={
        "is_entry_error": NoulQuestion(
            type="noul",
            instructions="Is this most likely a data-entry error?",
            criteria={"true": "A typo", "false": "A real fact"},
        ),
        "impact": ScoreQuestion(
            type="score",
            instructions="How much does this matter?",
            criteria=["Cosmetic", "Affects reporting", "Affects compliance or money"],
        ),
        "field": ChoiceQuestion(
            type="choice",
            instructions="Which field is this?",
            criteria={"dob": "date of birth", "first_name": None, "none": "none of these"},
        ),
    },
)

ANSWER: dict[str, Any] = {
    "model": "jev-1.13.0",
    "answers": {
        "is_entry_error": {"type": "noul", "noul": 0.91},
        "impact": {
            "type": "score",
            "score": 1.43,
            "confidence": 0.35,
            "legend": {"0": "Cosmetic", "1": "Affects reporting", "2": "Affects compliance"},
            "probabilities": {"0": 0.0, "1": 0.57, "2": 0.43},
        },
        "field": {
            "type": "choice",
            "choice": "dob",
            "confidence": 0.9,
            "probabilities": {"dob": 0.95, "first_name": 0.0, "none": 0.05},
        },
    },
    "usage": {"input_tokens": 1_000_000, "output_tokens": 12},
}


class FakeClock:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def transport(statuses: list[int], seen: list[httpx.Request]) -> httpx.MockTransport:
    """Answers with each status in turn; 200 returns ANSWER."""

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        status = statuses[min(len(seen) - 1, len(statuses) - 1)]
        if status == 200:
            return httpx.Response(200, json=ANSWER)
        return httpx.Response(status, json={"detail": f"status {status}"})

    return httpx.MockTransport(handler)


def make(
    tmp_path: Path,
    mode: JevMode,
    statuses: list[int] | None = None,
    seen: list[httpx.Request] | None = None,
    clock: FakeClock | None = None,
    budget: Decimal = Decimal("0.50"),
) -> JevClient:
    return JevClient(
        mode=mode,
        api_key=KEY,
        cassette_dir=tmp_path,
        allow_spend=mode in (JevMode.LIVE, JevMode.RECORD),
        transport=transport(statuses or [200], seen if seen is not None else []),
        sleep=(clock or FakeClock()).sleep,
        rand=lambda: 0.0,
        budget_usd=budget,
    )


# Cassette hashing


def test_hash_ignores_key_order() -> None:
    a = {"state": {"x": 1, "y": [1, 2]}, "model": "jev-latest", "questions": {}}
    b = {"questions": {}, "model": "jev-latest", "state": {"y": [1, 2], "x": 1}}
    assert request_hash(a) == request_hash(b)
    assert len(request_hash(a)) == 64


def test_hash_changes_with_content() -> None:
    a = {"state": "x", "model": "jev-latest", "questions": {}}
    assert request_hash(a) != request_hash({**a, "state": "y"})


def test_request_body_shape() -> None:
    body = TRIAGE.body()
    assert body["model"] == "jev-latest"
    assert body["questions"]["field"]["criteria"]["first_name"] is None
    assert body["questions"]["impact"]["criteria"][0] == "Cosmetic"
    no_criteria = NoulQuestion(type="noul", instructions="Yes?", criteria=None)
    assert (
        "criteria"
        not in JevRequest(state="t", questions={"q": no_criteria}).body()["questions"]["q"]
    )


# Modes


def test_off_returns_unresolved_and_makes_no_calls(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    client = make(tmp_path, JevMode.OFF, seen=seen)
    result = client.ask(TRIAGE)
    assert isinstance(result, Unresolved)
    assert result.reason == "mode_off"
    assert set(result.question_ids) == {"is_entry_error", "impact", "field"}
    assert seen == []
    assert client.usage.calls == 0


def test_replay_miss_raises_with_hash(tmp_path: Path) -> None:
    client = make(tmp_path, JevMode.REPLAY)
    with pytest.raises(CassetteMiss) as info:
        client.ask(TRIAGE)
    assert info.value.request_hash == request_hash(TRIAGE.body())
    assert request_hash(TRIAGE.body()) in str(info.value)


def test_replay_hit_parses_all_answer_types(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    save_cassette(tmp_path, TRIAGE.body(), ANSWER)
    client = make(tmp_path, JevMode.REPLAY, seen=seen)
    result = client.ask(TRIAGE)
    assert isinstance(result, JevResponse)
    assert seen == []
    noul = result.answers["is_entry_error"]
    score = result.answers["impact"]
    choice = result.answers["field"]
    assert isinstance(noul, NoulAnswer) and noul.noul == 0.91
    assert (
        isinstance(score, ScoreAnswer) and score.score == 1.43 and score.legend["0"] == "Cosmetic"
    )
    assert isinstance(choice, ChoiceAnswer) and choice.choice == "dob"
    assert client.usage.calls == 1
    assert client.usage.input_tokens == 1_000_000


def test_live_sends_documented_request(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    result = make(tmp_path, JevMode.LIVE, seen=seen).ask(TRIAGE)
    assert isinstance(result, JevResponse)
    (request,) = seen
    assert request.method == "POST"
    assert str(request.url) == "https://api.typesafe.ai/v1/systemone"
    assert request.headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(request.content) == TRIAGE.body()
    assert list(tmp_path.iterdir()) == [], "live mode does not write cassettes"


def test_record_writes_cassette_then_replay_hits(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    make(tmp_path, JevMode.RECORD, seen=seen).ask(TRIAGE)
    path = tmp_path / f"{request_hash(TRIAGE.body())}.json"
    assert json.loads(path.read_text()) == {"request": TRIAGE.body(), "response": ANSWER}
    make(tmp_path, JevMode.RECORD, seen=seen).ask(TRIAGE)
    assert len(seen) == 1, "record reuses an existing cassette instead of paying again"
    assert isinstance(make(tmp_path, JevMode.REPLAY).ask(TRIAGE), JevResponse)


@pytest.mark.parametrize("mode", [JevMode.LIVE, JevMode.RECORD])
def test_spending_modes_need_explicit_approval(tmp_path: Path, mode: JevMode) -> None:
    with pytest.raises(SpendNotApproved):
        JevClient(mode=mode, api_key=KEY, cassette_dir=tmp_path)


def test_spending_modes_need_a_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        JevClient(mode=JevMode.LIVE, api_key=None, cassette_dir=tmp_path, allow_spend=True)


def test_from_env_defaults_to_replay(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("JEV_MODE", raising=False)
    assert JevClient.from_env(cassette_dir=tmp_path).mode == JevMode.REPLAY
    monkeypatch.setenv("JEV_MODE", "live")
    with pytest.raises(SpendNotApproved):
        JevClient.from_env(cassette_dir=tmp_path)


# Backoff


def test_backoff_on_429_and_529_with_fake_clock(tmp_path: Path) -> None:
    clock = FakeClock()
    seen: list[httpx.Request] = []
    client = make(tmp_path, JevMode.LIVE, [429, 529, 429, 529, 200], seen, clock)
    assert isinstance(client.ask(TRIAGE), JevResponse)
    assert len(seen) == 5
    assert clock.sleeps == [0.5, 1.0, 2.0, 4.0]  # half of 1, 2, 4, 8 seconds with zero jitter


def test_jitter_stays_within_each_window(tmp_path: Path) -> None:
    clock = FakeClock()
    client = make(tmp_path, JevMode.LIVE, [429, 200], [], clock)
    client._rand = lambda: 0.999
    client.ask(TRIAGE)
    assert 0.5 <= clock.sleeps[0] < 1.0


def test_gives_up_after_five_tries(tmp_path: Path) -> None:
    clock = FakeClock()
    seen: list[httpx.Request] = []
    with pytest.raises(JevHTTPError) as info:
        make(tmp_path, JevMode.LIVE, [529], seen, clock).ask(TRIAGE)
    assert info.value.status_code == 529
    assert len(seen) == 5
    assert len(clock.sleeps) == 4


@pytest.mark.parametrize("status", [401, 422])
def test_401_and_422_raise_at_once_with_body(tmp_path: Path, status: int) -> None:
    clock = FakeClock()
    seen: list[httpx.Request] = []
    with pytest.raises(JevHTTPError) as info:
        make(tmp_path, JevMode.LIVE, [status], seen, clock).ask(TRIAGE)
    assert info.value.status_code == status
    assert f"status {status}" in str(info.value)
    assert len(seen) == 1 and clock.sleeps == []


def test_answer_for_wrong_question_is_refused(tmp_path: Path) -> None:
    other = JevRequest(state="x", questions={"q": TRIAGE.questions["field"]})
    save_cassette(tmp_path, other.body(), ANSWER)
    with pytest.raises(ValueError, match="answers"):
        make(tmp_path, JevMode.REPLAY).ask(other)


# Usage and budget


def test_cost_is_an_estimate_from_input_tokens() -> None:
    assert estimate_cost_usd(1_000_000) == Decimal("0.042000")
    assert estimate_cost_usd(1) == Decimal("0.000000")
    assert estimate_cost_usd(25_000) == Decimal("0.001050")


def test_budget_trip_switches_rest_of_run_to_off(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    seen: list[httpx.Request] = []
    # Each call is 1M input tokens, about $0.042, so a $0.10 budget trips on the third call.
    client = make(tmp_path, JevMode.LIVE, seen=seen, budget=Decimal("0.10"))
    with caplog.at_level(logging.WARNING, logger="jev_client"):
        results = [client.ask(TRIAGE) for _ in range(5)]
    assert [type(r).__name__ for r in results[:3]] == ["JevResponse"] * 3
    assert all(isinstance(r, Unresolved) and r.reason == "budget_tripped" for r in results[3:])
    assert len(seen) == 3
    usage = client.usage
    assert usage.budget_tripped is True
    assert usage.mode == JevMode.LIVE, "the configured mode stays as configured"
    assert (usage.calls, usage.input_tokens, usage.output_tokens) == (3, 3_000_000, 36)
    assert usage.estimated_cost_usd == Decimal("0.126000")
    assert "budget" in caplog.text


def test_budget_untripped_by_default(tmp_path: Path) -> None:
    client = make(tmp_path, JevMode.LIVE)
    client.ask(TRIAGE)
    assert client.usage.budget_tripped is False
    assert client.usage.budget_usd == Decimal("0.50")


# Minimization and PII


def test_minimize_keeps_only_allowlisted_fields() -> None:
    record = {"header": "Birth Dt", "sample_values": ["03/14/51"], "ssn": "x", "phone": "y"}
    assert minimize_state(record, {"header", "sample_values"}) == {
        "header": "Birth Dt",
        "sample_values": ["03/14/51"],
    }


def test_minimize_never_keeps_notes_before_pii_clearance() -> None:
    record = {"rule_id": "DOB-002", "Notes": "call back", "neighbors": {"notes": "x", "lob": "MA"}}
    allow = {"rule_id", "notes", "Notes", "neighbors"}
    assert minimize_state(record, allow) == {"rule_id": "DOB-002", "neighbors": {"lob": "MA"}}
    assert minimize_state(record, allow, pii_cleared=True) == record


def test_client_refuses_notes_before_pii_clearance(tmp_path: Path) -> None:
    seen: list[httpx.Request] = []
    request = JevRequest(state={"notes": "free text"}, questions=TRIAGE.questions)
    client = make(tmp_path, JevMode.LIVE, seen=seen)
    with pytest.raises(ValueError, match="notes"):
        client.ask(request)
    assert seen == []
    assert isinstance(client.ask(request, pii_cleared=True), JevResponse)


# Secrets


def test_key_never_in_cassette_or_log(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    clock = FakeClock()
    with caplog.at_level(logging.DEBUG):
        client = make(tmp_path, JevMode.RECORD, [429, 200], [], clock, budget=Decimal("0.01"))
        client.ask(TRIAGE)
        client.ask(JevRequest(state="other", questions=TRIAGE.questions))
        with pytest.raises(JevHTTPError) as info:
            make(tmp_path / "x", JevMode.LIVE, [401]).ask(TRIAGE)
    files = list(tmp_path.glob("*.json"))
    assert files
    for text in [caplog.text, repr(client), str(info.value), *(f.read_text() for f in files)]:
        assert KEY not in text
        assert "authorization" not in text.lower()
        assert "bearer" not in text.lower()

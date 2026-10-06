"""MockTransport only: no network, credentials, or paid calls."""

import json
from decimal import Decimal

import httpx
import pytest

from agency_schema.outputs import JevMode
from jev_client import JevClient
from jev_client.cassettes import cassette_path, load_cassette
from jev_client.types import JevRequest, NoulQuestion, Unresolved


def question():
    return JevRequest(
        state={"synthetic": True},
        questions={
            "q": NoulQuestion(type="noul", instructions="Synthetic question", criteria=None)
        },
    )


def reply(usage):
    return {
        "model": "synthetic-model",
        "answers": {"q": {"type": "noul", "noul": 0.5}},
        "usage": usage,
    }


def test_zero_budget_blocks_first_paid_request(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json=reply({"input_tokens": 1, "output_tokens": 0}))

    client = JevClient(
        mode=JevMode.LIVE,
        api_key="synthetic-key",
        cassette_dir=tmp_path,
        budget_usd=Decimal("0"),
        allow_spend=True,
        transport=httpx.MockTransport(handler),
    )
    answer = client.ask(question())
    print("OBSERVED mock paid requests with zero budget:", len(seen))
    assert not seen
    assert isinstance(answer, Unresolved)


def test_unknown_usage_stops_subsequent_paid_requests(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json=reply({"input_tokens": None, "output_tokens": None}))

    client = JevClient(
        mode=JevMode.LIVE,
        api_key="synthetic-key",
        cassette_dir=tmp_path,
        budget_usd=Decimal("0.50"),
        allow_spend=True,
        transport=httpx.MockTransport(handler),
    )
    client.ask(question())
    client.ask(question())
    print(
        "OBSERVED mock requests after unknown usage:",
        len(seen),
        "budget tripped:",
        client.usage.budget_tripped,
    )
    assert len(seen) == 1, "unknown billed usage left spending enabled"


def test_invalid_mode_cannot_fall_through_to_paid_request(tmp_path):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json=reply({"input_tokens": 1, "output_tokens": 0}))

    try:
        client = JevClient(
            mode="invalid",
            api_key="synthetic-key",
            cassette_dir=tmp_path,
            budget_usd=Decimal("0.50"),
            transport=httpx.MockTransport(handler),
        )
        client.ask(question())
    except ValueError:
        pass
    print("OBSERVED invalid-mode unapproved mock requests:", len(seen))
    assert not seen


def test_cassette_request_identity_must_match(tmp_path):
    body = question().body()
    path = cassette_path(tmp_path, body)
    path.write_text(
        json.dumps(
            {
                "request": {"state": "different"},
                "response": reply({"input_tokens": 1, "output_tokens": 0}),
            }
        )
    )
    try:
        raw = load_cassette(tmp_path, body)
    except ValueError:
        return
    print("OBSERVED mismatched cassette request accepted:", raw is not None)
    assert raw is None


@pytest.mark.parametrize("budget", [Decimal("NaN"), Decimal("Infinity"), Decimal("-1")])
def test_invalid_budget_rejected_before_any_paid_call(tmp_path, budget):
    seen = []

    def handler(request):
        seen.append(request.url.host)
        return httpx.Response(200, json=reply({"input_tokens": 1, "output_tokens": 0}))

    try:
        client = JevClient(
            mode=JevMode.LIVE,
            api_key="synthetic-key",
            cassette_dir=tmp_path,
            budget_usd=budget,
            allow_spend=True,
            transport=httpx.MockTransport(handler),
        )
        client.ask(question())
    except (ValueError, ArithmeticError):
        pass
    print("OBSERVED invalid-budget mock requests:", str(budget), len(seen))
    assert not seen

"""Bench follow-up: a bad Jev reply or HTTP error never crashes the bench and is counted apart.

The seen-set caveat is covered by main's test_bench_header_mapping.py.
"""

from pathlib import Path

import pytest

from agency_schema.outputs import JevMode
from intake.bench.header_mapping import (
    HTTP_ERROR,
    INVALID_ANSWER,
    NOT_RECORDED,
    LabeledHeader,
    jev_request,
    run_jev,
    score,
)
from jev_client import JevBadReply, JevClient, JevHTTPError

ITEM = LabeledHeader("crm", "Cust Ref", "clients.client_id", "synthetic")
SECRET = "reply text that must never be shown"


def _client(tmp_path: Path, error: Exception, monkeypatch: pytest.MonkeyPatch) -> JevClient:
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)

    def broken(request: object) -> object:
        raise error

    monkeypatch.setattr(client, "ask", broken)
    return client


@pytest.mark.parametrize(
    ("error", "status"),
    [
        (JevBadReply(SECRET, key="abc"), INVALID_ANSWER),
        (JevHTTPError(500, SECRET), HTTP_ERROR),
        (JevHTTPError(None, "ConnectTimeout"), HTTP_ERROR),
    ],
    ids=["bad", "http", "no-reply"],
)
def test_a_bad_or_refused_reply_gets_its_own_status_not_a_crash(
    tmp_path: Path, error: Exception, status: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    jev_request(ITEM)  # the header the synonyms leave to Jev
    arm = run_jev((ITEM,), _client(tmp_path, error, monkeypatch), tmp_path)
    assert arm.guesses == (status,) and status != NOT_RECORDED
    assert SECRET not in repr(arm)
    metrics = score((ITEM,), arm.guesses)
    assert (metrics.scored, metrics.wrong, metrics.not_recorded) == (0, 0, 0)
    assert (metrics.invalid, metrics.http_error) == ((1, 0) if status == INVALID_ANSWER else (0, 1))

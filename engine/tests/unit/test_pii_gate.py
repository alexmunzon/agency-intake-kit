"""The PII gate (PR 11): pre-filter, redaction at 0.50, masking, and no notes before clearance.

All notes here are invented. Jev answers come from MockTransport or hand-made cassettes.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.enums import Lane, Severity
from agency_schema.lineage import Lineage
from agency_schema.outputs import JevMode
from agency_schema.registry import catalog
from intake.config import PII_REDACTED_TEXT
from intake.exceptions.pii import FreeText, flagged, pii_gate, pii_request
from jev_client import CassetteMiss, JevClient, JevRequest, NoulQuestion, request_hash

SYNTHETIC = Path(__file__).resolve().parents[1] / "cassettes" / "synthetic"
HEALTH = "Client said the new prescription started on 03/12/2026"
ROUTINE = "Prefers a call after lunch"


def note(lineage_kwargs: dict[str, Any], text: str | None, row: int = 2) -> FreeText:
    return FreeText("notes", text, Lineage(**{**lineage_kwargs, "row_number": row}))


def mock_client(tmp_path: Path, noul: float, sent: list[Any]) -> JevClient:
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        reply = {"type": "noul", "noul": noul}
        usage = {"input_tokens": 40, "output_tokens": 1}
        return httpx.Response(
            200, json={"model": "synthetic-test", "answers": {"pii": reply}, "usage": usage}
        )

    return JevClient(
        mode=JevMode.LIVE,
        api_key="mock-key-not-real",
        cassette_dir=tmp_path,
        allow_spend=True,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.parametrize(("noul", "redacted"), [(0.50, True), (0.93, True), (0.4999, False)])
def test_redacts_at_or_above_half(
    tmp_path: Path, lineage_kwargs: dict[str, Any], noul: float, redacted: bool
) -> None:
    sent: list[Any] = []
    (result,) = pii_gate([note(lineage_kwargs, HEALTH)], mock_client(tmp_path, noul, sent))
    assert result.redacted is redacted
    assert result.text == (PII_REDACTED_TEXT if redacted else HEALTH)
    assert (result.record is not None) is redacted


def test_redaction_masks_every_output(tmp_path: Path, lineage_kwargs: dict[str, Any]) -> None:
    (result,) = pii_gate([note(lineage_kwargs, HEALTH, row=7)], mock_client(tmp_path, 0.9, []))
    record = result.record
    assert record is not None
    assert (record.rule_id, record.severity, record.lane) == (
        "PII-001",
        Severity.WARNING,
        Lane.REVIEW,
    )
    assert record.message == "Notes on row 7 redacted" and record.value_minimized is None
    assert record.jev is not None and record.jev.pii_probability == 0.9
    assert "prescription" not in record.model_dump_json()


def test_only_flagged_text_is_sent_and_digits_are_masked(
    tmp_path: Path, lineage_kwargs: dict[str, Any]
) -> None:
    sent: list[Any] = []
    texts = [ROUTINE, None, HEALTH, HEALTH, "Member id 123456789 on file"]
    results = pii_gate([note(lineage_kwargs, t) for t in texts], mock_client(tmp_path, 0.9, sent))
    assert len(sent) == 1  # routine text cleared, blank skipped, duplicate asked once
    assert sent[0]["state"] == {"text": "Client said the new prescription started on ##/##/####"}
    assert [r.redacted for r in results] == [False, False, True, True, True]
    assert results[4].record is not None and results[4].record.jev is None  # no call for ids
    assert "123456789" not in json.dumps(sent)


def test_off_mode_fails_closed(lineage_kwargs: dict[str, Any]) -> None:
    client = JevClient(mode=JevMode.OFF, api_key=None)
    (result,) = pii_gate([note(lineage_kwargs, HEALTH)], client)
    assert result.redacted and result.text == PII_REDACTED_TEXT


def test_notes_never_reach_jev_before_the_gate() -> None:
    client = JevClient(mode=JevMode.OFF, api_key=None)
    question = NoulQuestion(type="noul", instructions="x", criteria=None)
    leaked = JevRequest(state={"notes": HEALTH}, questions={"q": question})
    with pytest.raises(ValueError, match="PII gate"):
        client.ask(leaked)
    assert "notes" not in pii_request(HEALTH).body()["state"]
    assert flagged(HEALTH) and not flagged(ROUTINE)


def test_replay_cassette_redacts(lineage_kwargs: dict[str, Any]) -> None:
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=SYNTHETIC)
    (result,) = pii_gate([note(lineage_kwargs, HEALTH)], client)
    assert result.redacted


def test_cassette_miss_fails_loudly(tmp_path: Path, lineage_kwargs: dict[str, Any]) -> None:
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path)
    with pytest.raises(CassetteMiss, match=request_hash(pii_request(HEALTH).body())):
        pii_gate([note(lineage_kwargs, HEALTH)], client)


def test_pii_001_is_in_the_catalog() -> None:
    (meta,) = [m for m in catalog() if m.rule_id == "PII-001"]
    assert (meta.severity, meta.blocks) == (Severity.WARNING, False)

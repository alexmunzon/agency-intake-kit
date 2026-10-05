"""PII gate fix (#55): the regex layer catches every planted identity shape with no Jev call.

The fixture notes come from fixtures/agency-a. Other notes here are invented. Jev runs in off
mode (no network) or replays a hand-made cassette.
"""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.lineage import Lineage
from agency_schema.outputs import JevMode
from intake.config import PII_REDACTED_TEXT
from intake.exceptions.pii import FreeText, find_pii, pii_gate, pii_request, redact
from intake.readers.csv import read_csv
from jev_client import JevClient

FIXTURE = Path(__file__).parents[3] / "fixtures" / "agency-a"
SYNTHETIC = Path(__file__).resolve().parents[1] / "cassettes" / "synthetic"
OFF = JevClient(mode=JevMode.OFF, api_key=None)


def fixture_notes() -> list[tuple[str, FreeText]]:
    table = read_csv(
        FIXTURE / "drop" / "crm_export.csv", source="crm", run_id="r1", mapping_version="v1"
    )
    out = []
    for row in table.frame.iter_rows(named=True):
        if row["Notes"]:
            out.append(
                (row["Policy #"], FreeText("notes", row["Notes"], Lineage(**row["lineage"])))
            )
    return out


def planted() -> dict[str, dict[str, Any]]:
    truth = json.loads((FIXTURE / "ground_truth.json").read_text())["defects"]
    return {d["record_key"]["policy_id"]: d for d in truth if d["defect_type"] == "pii_in_notes"}


def note(lineage_kwargs: dict[str, Any], text: str) -> FreeText:
    return FreeText("notes", text, Lineage(**lineage_kwargs))


def test_all_26_planted_notes_raise_pii_001_with_no_jev_call() -> None:
    truth = planted()
    assert len(truth) == 26
    items = fixture_notes()
    results = pii_gate([item for _, item in items], OFF)  # off mode: any call would fail closed
    hits = {pid: r for (pid, _), r in zip(items, results, strict=True) if r.record is not None}
    assert set(hits) == set(truth)
    for pid, result in hits.items():
        record, defect = result.record, truth[pid]
        assert record is not None and record.rule_id == "PII-001"
        assert record.jev is None  # decided by the regex layer
        assert record.lineage is not None
        assert (record.lineage.source_file, record.row_number) == (
            defect["source_file"],
            defect["source_row"],
        )
        assert result.text is not None and "[REDACTED:" in result.text
        assert record.value_minimized is not None


def test_clean_fixture_notes_produce_nothing() -> None:
    truth = planted()
    clean = [item for pid, item in fixture_notes() if pid not in truth]
    assert len(clean) > 100
    results = pii_gate(clean, OFF)
    assert all(not r.redacted and r.record is None for r in results)
    assert [r.text for r in results] == [item.text for item in clean]


def test_no_raw_value_leaves_the_gate(lineage_kwargs: dict[str, Any]) -> None:
    truth = planted()
    for pid, item in fixture_notes():
        if pid not in truth:
            continue
        (result,) = pii_gate([item], OFF)
        assert result.record is not None and result.text is not None
        dumped = result.record.model_dump_json()
        for _, raw in find_pii(item.text or ""):
            assert raw not in result.text, pid
            assert raw not in dumped, pid
            assert raw not in result.record.message


@pytest.mark.parametrize(
    ("text", "kind", "redacted"),
    [
        ("Client gave bank account 00046201 for the draft.", "account", "00046201"),
        ("Routing 021000021 and acct 12345678901234", "account", "021000021"),
        ("IBAN: GB29NWBK60161331926819 on file", "account", "GB29NWBK60161331926819"),
        ("Client read out driver license TEST60026 on the call.", "license", "TEST60026"),
        ("DL# D1234567 shown at the office", "license", "D1234567"),
        ("License no. CA-99881 renewed", "license", "CA-99881"),
        ("Bare id W12345678 seen", "license", "W12345678"),
        ("Daughter is the contact, cell (555) 555-0145.", "phone", "(555) 555-0145"),
        ("Call 555.555.0199 after noon", "phone", "555.555.0199"),
        ("Phone: 5555550123", "phone", "5555550123"),
        (
            "Spouse wants copies sent to Jamie.Testperson@example.com.",
            "email",
            "Jamie.Testperson@example.com",
        ),
        ("DOB 03/12/1950 confirmed", "dob", "03/12/1950"),
        ("Date of birth: March 12, 1950", "dob", "March 12, 1950"),
        ("Medicare id 1EG4TE5MK73 checked", "medicare_id", "1EG4TE5MK73"),
        ("Member ID SH-542828 on the card", "member_id", "SH-542828"),
        ("SSN 123-45-6789 given", "ssn", "123-45-6789"),
        ("social security number 123456789", "ssn", "123456789"),
        ("Password is hunter22 per client", "secret", "hunter22"),
        ("PIN: 4321 for the portal", "secret", "4321"),
        ("Card on file ends in 0029, read aloud.", "card", "0029"),
        ("Daughter Jamie Testperson is the contact", "name", "Jamie Testperson"),
    ],
)
def test_each_shape_redacts_its_span_with_a_typed_placeholder(
    lineage_kwargs: dict[str, Any], text: str, kind: str, redacted: str
) -> None:
    (result,) = pii_gate([note(lineage_kwargs, text)], OFF)
    assert result.redacted and result.record is not None
    assert result.text is not None and f"[REDACTED:{kind}]" in result.text
    assert redacted not in result.text
    assert redacted not in result.record.model_dump_json()


@pytest.mark.parametrize(
    "text",
    [
        "Prefers mail over phone.",
        "Call after 2pm.",
        "Asked about dental add-ons at renewal.",
        "Social visit planned, son will join.",
        "Pin the renewal letter to the file.",
        "Policy P-00112 renewed with plan H5371-027-003.",
    ],
)
def test_routine_text_is_left_alone(lineage_kwargs: dict[str, Any], text: str) -> None:
    (result,) = pii_gate([note(lineage_kwargs, text)], OFF)
    assert not result.redacted and result.text == text


def test_text_past_the_regex_still_asks_jev_in_replay(lineage_kwargs: dict[str, Any]) -> None:
    text = "Client said the new prescription started on 03/12/2026"
    client = JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=SYNTHETIC)
    (result,) = pii_gate([note(lineage_kwargs, text)], client)
    assert result.redacted and result.text == PII_REDACTED_TEXT
    assert result.record is not None and result.record.jev is not None


def test_regex_hit_plus_health_words_asks_jev_on_the_redacted_text(
    lineage_kwargs: dict[str, Any],
) -> None:
    text = "Cell 555-555-0145, diagnosed last spring"
    request = pii_request(redact(text)[0])
    assert "555" not in json.dumps(request.body())
    (result,) = pii_gate([note(lineage_kwargs, text)], OFF)  # no answer: fail closed
    assert result.redacted and result.text == PII_REDACTED_TEXT
    assert result.record is not None and "phone" in result.record.message


def test_no_cassette_holds_a_raw_planted_value() -> None:
    raws = [
        raw
        for pid, item in fixture_notes()
        if pid in planted()
        for _, raw in find_pii(item.text or "")
    ]
    for path in SYNTHETIC.glob("*.json"):
        body = path.read_text()
        assert not any(raw in body for raw in raws), path.name


def test_jev_sees_only_the_redacted_text_and_a_low_score_keeps_the_spans(
    tmp_path: Path, lineage_kwargs: dict[str, Any]
) -> None:
    sent: list[Any] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        body = {"model": "synthetic-test", "answers": {"pii": {"type": "noul", "noul": 0.1}}}
        return httpx.Response(200, json={**body, "usage": {"input_tokens": 9, "output_tokens": 1}})

    client = JevClient(
        mode=JevMode.LIVE,
        api_key="mock-key-not-real",
        cassette_dir=tmp_path,
        allow_spend=True,
        transport=httpx.MockTransport(handler),
    )
    text = "Cell (555) 555-0145, condition noted"
    (result,) = pii_gate([note(lineage_kwargs, text)], client)
    assert sent[0]["state"] == {"text": "Cell [REDACTED:phone], condition noted"}
    assert result.text == "Cell [REDACTED:phone], condition noted"
    assert result.record is not None and result.record.jev is not None
    assert "555-0145" not in json.dumps(sent) + "".join(p.read_text() for p in tmp_path.iterdir())

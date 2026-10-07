"""mapping_review.json items: one per header the synonym table and saved decisions left open.

Replay cassettes or a mock transport only, so nothing reaches the network or spends money.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from agency_schema.mapping_review import MappingReview
from agency_schema.outputs import JevMode
from intake.ingest import ingest
from intake.mapping.fingerprint import format_fingerprint
from intake.mapping.headers import map_table
from intake.mapping.jev_mapping import MAPPING_CASSETTES, Asker, map_with_jev, sample_values
from intake.mapping.review import build_review, review_items
from intake.mapping.store import MappingEntry, SourceMapping, save_mapping
from intake.readers import LINEAGE_COLUMN, RawTable, table_from_rows
from jev_client import JevClient

DROP = Path(__file__).parents[3] / "fixtures" / "agency-a" / "drop"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
BIRTH = "Birth Dt (mm/dd/yy)"
SSN_HEADER = "Member 123-45-6789"


@pytest.fixture(scope="module")
def enrollment() -> RawTable:
    return next(t for t in ingest(DROP, run_id="t").tables if t.source == "enrollment")


def live(choice: str, confidence: float) -> Asker:
    def handle(request: httpx.Request) -> httpx.Response:
        qid = next(iter(json.loads(request.content)["questions"]))
        answer = {"type": "choice", "choice": choice, "probabilities": {}, "confidence": confidence}
        usage = {"input_tokens": 100, "output_tokens": 1}
        return httpx.Response(200, json={"model": "m", "answers": {qid: answer}, "usage": usage})

    transport = httpx.MockTransport(handle)
    client = JevClient(mode=JevMode.LIVE, api_key="k-test", allow_spend=True, transport=transport)
    return Asker(client)


def items_for(table: RawTable, folder: Path, asker: Asker) -> list[Any]:
    result, decisions = map_with_jev(table, map_table(table, folder, NOW), folder, NOW, asker)
    return review_items(table, result, decisions)


def headers_of(table: RawTable) -> list[str]:
    return [c for c in table.frame.columns if c != LINEAGE_COLUMN]


def test_one_item_per_unsettled_header_and_none_for_synonym_headers(
    enrollment: RawTable, tmp_path: Path
) -> None:
    replay = Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=MAPPING_CASSETTES))
    first = map_table(enrollment, tmp_path / "plain", NOW)
    unsettled = [e.header for e in first.mapping.entries if e.method == "unmapped"]
    items = items_for(enrollment, tmp_path / "m", replay)
    assert unsettled and sorted(i.header for i in items) == sorted(unsettled)
    synonym = [e.header for e in first.mapping.entries if e.method == "synonym"]
    assert synonym and not {i.header for i in items} & set(synonym)
    [birth] = [i for i in items if i.header == BIRTH]
    assert birth.source == "enrollment" and birth.file_name == enrollment.source_file
    assert birth.format_fingerprint == format_fingerprint(headers_of(enrollment))
    assert birth.origin == "jev_replay" and birth.route == "auto"
    assert birth.proposed_field == "clients.dob" and birth.confidence is not None
    assert "clients.dob" in birth.allowed_fields and "none" in birth.allowed_fields
    assert list(birth.samples) == sample_values(enrollment.frame[BIRTH])
    assert birth.samples_withheld is False
    filled = [v for v in enrollment.frame[BIRTH].to_list() if v and v.strip()]
    assert birth.rows_with_value == len(filled)
    text = f"enrollment\0{enrollment.source_file}\0{BIRTH}"
    assert birth.item_id == "mr-" + hashlib.sha256(text.encode()).hexdigest()[:12]


def test_a_saved_decision_produces_no_item(enrollment: RawTable, tmp_path: Path) -> None:
    folder = tmp_path / "m"
    stored = MappingEntry(
        header=BIRTH,
        table="clients",
        field="dob",
        method="manual",
        confidence=None,
        decided_at=NOW.isoformat(),
    )
    save_mapping(folder, SourceMapping(source="enrollment", entries=(stored,)))
    items = items_for(enrollment, folder, Asker(None))
    assert BIRTH not in {i.header for i in items}


def test_the_explanation_is_built_from_evidence(enrollment: RawTable, tmp_path: Path) -> None:
    [birth] = [i for i in items_for(enrollment, tmp_path, live("clients.dob", 0.72)) if
               i.header == BIRTH]  # fmt: skip
    assert (birth.origin, birth.route, birth.confidence) == ("jev_live", "suggest", 0.72)
    n = len(birth.samples)
    assert birth.explanation == (
        f"No synonym or saved mapping matched '{BIRTH}'. "
        "Jev (live) chose clients.dob with confidence 0.72 (the model's own number), "
        "so it was mapped but a person should confirm it. "
        f"{n} masked sample values were shown to Jev. "
        f"{birth.rows_with_value:,} rows have a value."
    )


def test_no_answer_means_origin_none_and_no_confidence(
    enrollment: RawTable, tmp_path: Path
) -> None:
    [birth] = [i for i in items_for(enrollment, tmp_path, Asker(None)) if i.header == BIRTH]
    assert (birth.origin, birth.confidence, birth.proposed_field) == ("none", None, None)
    assert (birth.route, birth.reason) == ("person", "mode_off")
    assert "Jev gave no answer because Jev is off (mode_off)." in birth.explanation


def table(rows: list[list[str | None]]) -> RawTable:
    return table_from_rows(rows, source="crm", source_file="crm.csv", sheet=None,
                           run_id="t", mapping_version="unmapped")  # fmt: skip


def test_withheld_samples_notes_and_ssn_shaped_headers(tmp_path: Path) -> None:
    raw = table(
        [
            ["Client ID", "Agent comments", "Misc Code", SSN_HEADER],
            ["C1", "called about the plan", "123456789", "x1"],
            ["C2", None, "987654321", "x2"],
        ]
    )
    items = {i.header: i for i in items_for(raw, tmp_path, live("none", 0.9))}
    notes = items["Agent comments"]
    assert (notes.samples, notes.samples_withheld) == ((), True)
    assert (notes.route, notes.reason, notes.origin) == ("person", "notes", "none")
    assert "never sent to Jev" in notes.explanation and notes.rows_with_value == 1
    ref = items["Misc Code"]
    assert (ref.samples, ref.samples_withheld) == ((), True)
    assert (ref.proposed_field, ref.route, ref.confidence) == (None, "unmapped", 0.9)
    masked = [h for h in items if h not in ("Agent comments", "Misc Code", "Client ID")]
    assert masked == ["Me**** ***-**-****"]
    dumped = json.dumps([i.model_dump(mode="json") for i in items.values()])
    assert "6789" not in dumped and "called about" not in dumped and "123456789" not in dumped


def test_build_review_links_map_exceptions_and_sorts(enrollment: RawTable, tmp_path: Path) -> None:
    asker = live("clients.dob", 0.4)  # below the line: stays unmapped with MAP-001
    result, decisions = map_with_jev(
        enrollment, map_table(enrollment, tmp_path, NOW), tmp_path, NOW, asker
    )
    items = review_items(enrollment, result, decisions)
    review = build_review("r1", "enrollment-abc", JevMode.LIVE, items, result.exceptions)
    assert isinstance(review, MappingReview)
    [birth] = [i for i in review.items if i.header == BIRTH]
    birth_map = [e.id for e in result.exceptions if e.rule_id == "MAP-001" and BIRTH in e.message]
    assert list(birth.exception_ids) == birth_map and birth_map
    assert birth.proposed_field == "clients.dob" and birth.route == "unmapped"
    keys = [(i.source, i.file_name, i.header) for i in review.items]
    assert keys == sorted(keys)


def test_an_empty_review_is_still_a_valid_file() -> None:
    review = build_review("r1", "unmapped", JevMode.REPLAY, [], [])
    assert review.items == ()
    assert MappingReview.model_validate_json(review.model_dump_json()) == review


def test_unseparated_nine_digit_header_is_masked_in_the_item_and_the_jev_request(
    tmp_path: Path,
) -> None:
    sent: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(json.dumps(body))
        qid = next(iter(body["questions"]))
        answer = {"type": "choice", "choice": "none", "probabilities": {}, "confidence": 0.9}
        usage = {"input_tokens": 10, "output_tokens": 1}
        return httpx.Response(200, json={"model": "m", "answers": {qid: answer}, "usage": usage})

    client = JevClient(
        mode=JevMode.LIVE, api_key="k", allow_spend=True, transport=httpx.MockTransport(handle)
    )
    raw = table([["Client ID", "Member 123456789"], ["C1", "x1"], ["C2", "x2"]])
    [item] = [i for i in items_for(raw, tmp_path, Asker(client)) if i.header != "Client ID"]
    assert item.header == "Me**** *********" and sent
    assert "123456789" not in json.dumps(item.model_dump(mode="json"))
    assert all("123456789" not in body for body in sent)


def record_client(folder: Path, cached: bool) -> Asker:
    def handle(request: httpx.Request) -> httpx.Response:
        qid = next(iter(json.loads(request.content)["questions"]))
        answer = {"type": "choice", "choice": "clients.dob", "probabilities": {}, "confidence": 0.9}
        usage = {"input_tokens": 10, "output_tokens": 1}
        return httpx.Response(200, json={"model": "m", "answers": {qid: answer}, "usage": usage})

    transport = httpx.MockTransport(handle)
    client = JevClient(
        mode=JevMode.RECORD, api_key="k", allow_spend=True, transport=transport, cassette_dir=folder
    )
    return Asker(client)


def test_origin_follows_how_each_answer_was_obtained(enrollment: RawTable, tmp_path: Path) -> None:
    cassettes = tmp_path / "cassettes"
    [fresh] = [i for i in items_for(enrollment, tmp_path / "a", record_client(cassettes, False))
               if i.header == BIRTH]  # fmt: skip
    assert fresh.origin == "jev_record"  # paid for now, through the API
    [again] = [i for i in items_for(enrollment, tmp_path / "b", record_client(cassettes, True))
               if i.header == BIRTH]  # fmt: skip
    assert again.origin == "jev_replay"  # record mode, but read from the saved cassette

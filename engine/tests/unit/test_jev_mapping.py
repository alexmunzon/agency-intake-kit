"""PR 7: Jev header mapping and enum normalization, all in replay or a mock transport."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import polars as pl
import pytest
from typer.testing import CliRunner

from agency_schema.formats import parse_date_loose
from agency_schema.outputs import JevMode
from intake import cli
from intake.config import ENUM_AUTO, MAP_AUTO, MAP_SUGGEST
from intake.ingest import ingest
from intake.mapping.enums import decide_value, fill_drop, normalize_column
from intake.mapping.headers import map_table
from intake.mapping.jev_mapping import (
    MAPPING_CASSETTES,
    Asker,
    decide_header,
    header_request,
    map_with_jev,
    route,
    sample_values,
)
from intake.mapping.synonyms import Target
from jev_client import CassetteMiss, JevClient, canonical_json, request_hash
from jev_client.cassettes import cassette_path

DROP = Path(__file__).parents[3] / "fixtures" / "agency-a" / "drop"
NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
BIRTH = "Birth Dt (mm/dd/yy)"
STATUS = Target("policies", "status")


@pytest.fixture(scope="module")
def tables() -> dict[str, Any]:
    return {t.source: t for t in ingest(DROP, run_id="t").tables}


@pytest.fixture(scope="module")
def planned(tmp_path_factory: pytest.TempPathFactory) -> Asker:
    asker = Asker(None)
    fill_drop(DROP, tmp_path_factory.mktemp("plan"), NOW, asker)
    return asker


def replay() -> Asker:
    return Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=MAPPING_CASSETTES))


def mock(answer: Any) -> tuple[httpx.MockTransport, list[dict[str, Any]]]:
    """A mock transport, so nothing reaches the network. answer(body) gives (choice, confidence)."""
    sent: list[dict[str, Any]] = []

    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        sent.append(body)
        qid = next(iter(body["questions"]))
        choice, confidence = answer(body)
        reply = {"type": "choice", "choice": choice, "probabilities": {choice: confidence}}
        return httpx.Response(
            200,
            json={
                "model": "jev-mock",
                "answers": {qid: {**reply, "confidence": confidence}},
                "usage": {"input_tokens": 100, "output_tokens": 1},
            },
        )

    return httpx.MockTransport(handle), sent


def live(answer: Any) -> tuple[Asker, list[dict[str, Any]]]:
    transport, sent = mock(answer)
    client = JevClient(mode=JevMode.LIVE, api_key="k-test", allow_spend=True, transport=transport)
    return Asker(client), sent


def test_example_2_birth_dt_maps_to_dob_in_replay(tables: dict[str, Any], tmp_path: Path) -> None:
    table = tables["enrollment"]
    result, decisions = map_with_jev(
        table, map_table(table, tmp_path, NOW), tmp_path, NOW, replay()
    )
    body = header_request("enrollment", BIRTH, table.frame[BIRTH]).body()
    cassette = json.loads(cassette_path(MAPPING_CASSETTES, body).read_text(encoding="utf-8"))
    recorded = cassette["response"]["answers"]["field"]["confidence"]
    entry = result.mapping.entry(BIRTH)
    assert entry is not None
    assert (entry.table, entry.field, entry.method) == ("clients", "dob", "jev")
    assert entry.confidence == recorded == decisions[0].confidence
    assert recorded >= MAP_AUTO
    assert not [e for e in result.exceptions if "Birth" in e.message]
    assert all(parse_date_loose(v) for v in table.frame[BIRTH].drop_nulls())


def test_paid_routes_by_its_sample_values(tables: dict[str, Any]) -> None:
    for source in ("statement_northwind_health", "statement_cardinal_mutual"):
        decision = decide_header(source, "Paid", tables[source].frame["Paid"], replay())
        assert (decision.choice, decision.route) == ("commission_lines.paid_date", "auto")

    def by_shape(body: dict[str, Any]) -> tuple[str, float]:
        dated = "-" in body["state"]["sample_values"][0]
        return ("commission_lines.paid_date" if dated else "commission_lines.amount"), 0.9

    asker, sent = live(by_shape)
    money = pl.Series(["61.05", "8.40", "120.00"])
    dates = pl.Series(["2026-07-15", "2026-08-15"])
    assert decide_header("statement_x", "Paid", money, asker).choice == "commission_lines.amount"
    assert decide_header("statement_x", "Paid", dates, asker).choice == "commission_lines.paid_date"
    assert len(sent) == 2


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (1.0, "auto"),
        (MAP_AUTO, "auto"),
        (0.8499, "suggest"),
        (MAP_SUGGEST, "suggest"),
        (0.5999, "unmapped"),
    ],
)
def test_header_thresholds_route_at_the_boundaries(confidence: float, expected: str) -> None:
    assert route("clients.dob", confidence) == expected
    assert route(None, 0.99) == "unmapped"


def test_mid_confidence_maps_with_map_002_and_low_stays_unmapped(
    tables: dict[str, Any], tmp_path: Path
) -> None:
    table = tables["enrollment"]
    for confidence, method, codes in ((0.7, "jev", {"MAP-002"}), (0.4, "unmapped", {"MAP-001"})):
        asker, _ = live(lambda body, c=confidence: ("clients.dob", c))
        folder = tmp_path / str(confidence)
        result, _ = map_with_jev(table, map_table(table, folder, NOW), folder, NOW, asker)
        entry = result.mapping.entry(BIRTH)
        assert entry is not None and entry.method == method
        assert {e.rule_id for e in result.exceptions if "Birth" in e.message} == codes


@pytest.mark.parametrize(
    ("choice", "confidence", "normalized"),
    [
        ("TERMINATED", ENUM_AUTO, "TERMINATED"),
        ("TERMINATED", 0.8499, None),
        ("unknown", 0.99, None),
    ],
)
def test_enum_thresholds(choice: str, confidence: float, normalized: str | None) -> None:
    asker, sent = live(lambda body: (choice, confidence))
    decision = decide_value(STATUS, "XFER", asker)
    assert decision.normalized == normalized
    assert decision.method == ("jev" if normalized else "person")
    assert sent[0]["state"] == {"field": "status", "value": "XFER"}


def test_enum_table_first_then_jev_for_leftovers_only() -> None:
    asker, sent = live(lambda body: ("unknown", 0.95))
    values = pl.Series(["active", "Term'd", "XFER", "ACTIVE", None, "XFER", "Withdrawn"])
    normalized, decisions = normalize_column(values, STATUS, asker)
    assert normalized.to_list() == [
        "ACTIVE",
        "TERMINATED",
        "XFER",
        "ACTIVE",
        None,
        "XFER",
        "CANCELLED",
    ]
    assert [d.value for d in decisions if d.method == "person"] == ["XFER"]
    assert len(sent) == 1
    assert decide_value(Target("clients", "state"), " tx ", asker).normalized == "TX"
    assert (
        decide_value(Target("policies", "line_of_business"), "Med Supp", asker).normalized
        == "MEDSUPP"
    )


def test_samples_are_minimized() -> None:
    assert sample_values(pl.Series(["03/14/51", "11/02/48", "03/14/51"])) == [
        "03/**/**",
        "11/**/**",
    ]
    assert sample_values(pl.Series(["123456789", "x"])) == []
    assert sample_values(pl.Series(["123-45-6789"])) == []
    assert sample_values(pl.Series(["called the client about her new plan today"])) == []
    long = sample_values(pl.Series(["A" * 30]))  # cut to 24, then masked
    assert long == ["AA" + "*" * 22]
    assert len(sample_values(pl.Series([f"{n:02d}/01/50" for n in range(1, 13)]))) == 5


def test_no_raw_value_in_any_agency_a_request(planned: Asker, tables: dict[str, Any]) -> None:
    bodies = [canonical_json(r.body()) for r in planned.requests.values()]
    raw = set(tables["enrollment"].frame[BIRTH].drop_nulls()) | set(
        tables["crm"].frame["Mbr DOB"].drop_nulls()
    )
    notes = {n for n in tables["crm"].frame["Notes"].drop_nulls() if len(n) > 8}
    assert notes
    for body in bodies:
        assert not any(v in body for v in raw | notes)
        assert '"notes"' not in body.casefold() or "clients.notes" in body


def test_agency_a_call_count_and_dedup(planned: Asker) -> None:
    states = [r.state for r in planned.requests.values()]
    headers = sorted(s["header"] for s in states if isinstance(s, dict) and "header" in s)
    values = sorted(s["value"] for s in states if isinstance(s, dict) and "value" in s)
    assert headers == [BIRTH, "Paid"]
    assert values == ["??", "N/A", "See notes", "XFER", "chk w/ carrier"]
    assert (len(planned.requests), planned.asked) == (7, 8)


def test_identical_requests_are_sent_once() -> None:
    asker, sent = live(lambda body: ("commission_lines.paid_date", 0.9))
    series = pl.Series(["2026-07-15"])
    for source in ("statement_a", "statement_b", "statement_c"):
        decide_header(source, "Paid", series, asker)
    assert (len(sent), asker.asked) == (1, 3)


def test_cassette_miss_raises_with_the_hash(tmp_path: Path) -> None:
    asker = Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=tmp_path))
    series = pl.Series(["2026-07-15"])
    expected = request_hash(header_request("statement_x", "Paid", series).body())
    with pytest.raises(CassetteMiss, match=expected):
        decide_header("statement_x", "Paid", series, asker)


def test_notes_are_never_sent() -> None:
    asker, sent = live(lambda body: ("clients.notes", 0.99))
    series = pl.Series(["Member said her diagnosis changed last week"])
    for header in ("Notes", "Agent Notes", "comments"):
        assert decide_header("crm", header, series, asker).route == "person"
    assert sent == []


def test_off_mode_routes_everything_to_a_person(tables: dict[str, Any], tmp_path: Path) -> None:
    asker = Asker(JevClient(mode=JevMode.OFF, api_key=None))
    table = tables["enrollment"]
    result, [decision] = map_with_jev(table, map_table(table, tmp_path, NOW), tmp_path, NOW, asker)
    assert (decision.route, decision.reason) == ("person", "mode_off")
    entry = result.mapping.entry(BIRTH)
    assert entry is not None and entry.method == "unmapped"
    assert {e.rule_id for e in result.exceptions if "Birth" in e.message} == {"MAP-001", "MAP-002"}
    values, [status] = normalize_column(pl.Series(["XFER"]), STATUS, asker)
    assert values.to_list() == ["XFER"] and status.reason == "mode_off"


def test_hand_made_cassettes_match_the_requests_byte_for_byte(planned: Asker) -> None:
    on_disk = {p.stem for p in MAPPING_CASSETTES.glob("*.json")}
    assert on_disk == set(planned.requests)
    for key, request in planned.requests.items():
        stored = json.loads((MAPPING_CASSETTES / f"{key}.json").read_text(encoding="utf-8"))
        assert canonical_json(stored["request"]) == canonical_json(request.body())


def test_agency_a_replays_end_to_end(tmp_path: Path) -> None:
    results = {r.mapping.source: r for r in fill_drop(DROP, tmp_path, NOW, replay())}
    for source in ("statement_northwind_health", "statement_cardinal_mutual"):
        paid = results[source].mapping.entry("Paid")
        assert paid is not None and paid.field == "paid_date"


def test_record_mapping_refuses_without_record_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JEV_MODE", "replay")
    called: list[Path] = []
    monkeypatch.setattr(cli, "_record_client", lambda c: called.append(c))
    out = CliRunner().invoke(cli.app, ["jev", "record-mapping", "--drop", str(DROP.parent)])
    assert out.exit_code == 2 and "Refusing" in out.output and called == []


def test_record_mapping_prints_count_and_estimate_first(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for path in MAPPING_CASSETTES.glob("*.json"):
        (tmp_path / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    monkeypatch.setenv("JEV_MODE", "record")
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-test-key-NEVER-PRINT")

    def answer(body: dict[str, Any]) -> tuple[str, float]:
        if "value" in body["state"]:
            return "unknown", 0.95
        is_paid = body["state"]["header"] == "Paid"
        return ("commission_lines.paid_date" if is_paid else "clients.dob"), 0.9

    transport, sent = mock(answer)

    def client(cassettes: Path) -> JevClient:
        return JevClient.from_env(allow_spend=True, cassette_dir=cassettes, transport=transport)

    monkeypatch.setattr(cli, "_record_client", client)
    args = ["jev", "record-mapping", "--drop", str(DROP.parent), "--cassettes", str(tmp_path)]
    out = CliRunner().invoke(cli.app, args)
    assert out.exit_code == 0, out.output
    first = out.output.splitlines()[0]
    assert first.startswith("7 requests (8 asked") and "estimated cost $0.0000" in first
    assert "NEVER-PRINT" not in out.output
    assert len(sent) == 7
    assert not [p for p in tmp_path.glob("*.json") if "handmade" in p.read_text(encoding="utf-8")]

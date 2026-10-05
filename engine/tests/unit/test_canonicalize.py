"""intake/run/canonicalize.py: the raw-to-canonical builder (#58), on small reader tables."""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from agency_schema.outputs import JevMode
from intake.mapping.enums import enum_request
from intake.mapping.headers import map_table
from intake.mapping.jev_mapping import Asker
from intake.mapping.synonyms import Target
from intake.readers import table_from_rows
from intake.rules.address import state_code
from intake.rules.frames import client_frame, policy_frame
from intake.rules.status import status_unknown
from intake.run.canonicalize import Canonical, MappedSource, canonicalize, statement_carrier
from jev_client import JevClient
from jev_client.cassettes import save_cassette

NOW = datetime(2026, 10, 1, 9, tzinfo=UTC)
CRM = ["Client ID", "Client Name", "Mbr DOB", "Address", "City", "State", "Zip", "Policy #"]
CRM += ["Carrier Name", "Plan", "Product", "Eff Date", "Term Date", "Status"]
CRM += ["Writing Agent NPN", "Premium", "Notes"]
ROWS = [
    ["C-1", "Lee, Ann", "21269", "1 Main", "Austin", "Tex.", "78701", "P-1", "Bluepeak"]
    + ["H1234-001", "MA", "01/31/26", "", "In Force", "123", "$1,061.05", "call back"],
    ["C-1", "Lee, Ann", "21269", "1 Main", "Austin", "Tex.", "78701", "P-2", "Bluepeak"]
    + ["S1234-001", "PDP", "2026-02-01", "12/31/26", "XFER", "123", "9.80", ""],
    ["C-9", "", "", "", "", "", "", "P-3", "Bluepeak"]  # an orphan: no client details
    + ["H1234-001", "MA", "02/01/26", "", "active", "123", "1.00", ""],
    ["C-2", "Bo Diaz", "05/01/1949", "2 Elm", "Reno", "NV", "89501"] + [""] * 10,
]


def mapped(
    tmp: Path, header: list[str], rows: list[list[str]], source: str, sheet: str | None = None
) -> MappedSource:
    table = table_from_rows(
        [header, *rows],
        source=source,
        source_file=f"{source}.csv",
        sheet=sheet,
        run_id="r",
        mapping_version="unmapped",
    )
    return MappedSource(table, map_table(table, tmp, NOW))


def crm(tmp: Path, asker: Asker) -> Canonical:
    return canonicalize([mapped(tmp, CRM, ROWS, "crm")], asker)


def replay_with(tmp: Path, answers: dict[tuple[Target, str], str]) -> Asker:
    """A replay client whose cassettes say what Jev picks for each messy value."""
    cassettes = tmp / "cassettes"
    for (target, value), choice in answers.items():
        answer = {
            "choice": choice,
            "confidence": 0.95,
            "probabilities": {choice: 0.95},
            "type": "choice",
        }
        response = {
            "answers": {"value": answer},
            "model": "test",
            "usage": {"input_tokens": 10, "output_tokens": 1},
        }
        save_cassette(cassettes, enum_request(target, value).body(), response)
    return Asker(JevClient(mode=JevMode.REPLAY, api_key=None, cassette_dir=cassettes))


def test_the_crm_splits_into_clients_and_policies(tmp_path: Path) -> None:
    tables = crm(tmp_path, Asker(None)).tables
    assert tables["policies"]["policy_id"].to_list() == ["P-1", "P-2", "P-3"]
    assert tables["policies"]["client_id"].to_list() == ["C-1", "C-1", "C-9"]
    # One client per id from its first row; the policy-less row is a client only; the
    # orphan row carries no client details, so it is no client (REF-001 finds it).
    assert tables["clients"]["client_id"].to_list() == ["C-1", "C-2"]
    assert tables["clients"]["first_name"].to_list() == ["Ann", "Bo"]
    assert tables["clients"]["last_name"].to_list() == ["Lee", "Diaz"]
    lineage = tables["clients"]["lineage"].to_list()
    assert [lin["row_number"] for lin in lineage] == [2, 5]
    assert lineage[0]["mapping_version"].startswith("crm-")


def test_values_normalize_only_where_the_meaning_is_certain(tmp_path: Path) -> None:
    tables = crm(tmp_path, Asker(None)).tables
    policies, clients = tables["policies"], tables["clients"]
    assert policies["effective_date"].to_list() == ["2026-01-31", "2026-02-01", "2026-02-01"]
    assert policies["termination_date"].to_list() == [None, "2026-12-31", None]
    assert policies["monthly_premium"].to_list() == ["1061.05", "9.80", "1.00"]
    assert clients["dob"].to_list() == ["1958-03-25", "1949-05-01"]
    assert policies["status"].to_list() == [
        "ACTIVE",
        "XFER",
        "ACTIVE",
    ]  # table word, as written, case


def test_roster_lists_flags_and_statement_carrier(tmp_path: Path) -> None:
    agents = mapped(
        tmp_path,
        ["NPN #", "Agent Name", "Licensed States", "Status"],
        [["123", "Ann Lee", "fl, GA | tx", "Active"]],
        "roster",
        "Agents",
    )
    rts = mapped(
        tmp_path,
        [
            "NPN",
            "Carrier",
            "State",
            "Plan Yr",
            "Line",
            "Appointed?",
            "Certified?",
            "RTS Start",
            "RTS End",
        ],
        [["123", "Bluepeak", "TX", "2026", "MA", "Y", "n", "2026-01-01", ""]],
        "roster",
        "RTS",
    )
    tables = canonicalize([agents, rts], Asker(None)).tables
    assert tables["agents"]["license_states"].to_list() == ["FL|GA|TX"]
    assert tables["rts"].select("appointed", "certified").row(0) == ("true", "false")
    assert statement_carrier("statement_summit_health_plans") == "Summit Health Plans"


@pytest.mark.parametrize("mode", ["off", "replay"])
def test_sta_001_and_adr_003_judge_the_raw_value_even_when_normalized(
    tmp_path: Path, mode: str
) -> None:
    """The word table maps "In Force" to ACTIVE; in replay Jev maps "XFER" and "Tex." too.
    Normalizing never hides that the source was non-standard: the rules read the raw column."""
    if mode == "off":
        asker = Asker(JevClient(mode=JevMode.OFF, api_key=None))
    else:
        asker = replay_with(
            tmp_path,
            {
                (Target("policies", "status"), "XFER"): "TERMINATED",
                (Target("clients", "state"), "Tex."): "TX",
            },
        )
    tables = crm(tmp_path, asker).tables
    policies, clients = tables["policies"], tables["clients"]
    assert policies["status_raw"].to_list() == ["In Force", "XFER", "active"]
    expected_status = ["ACTIVE", "TERMINATED" if mode == "replay" else "XFER", "ACTIVE"]
    assert policies["status"].to_list() == expected_status
    assert clients["state"].to_list() == (["TX", "NV"] if mode == "replay" else ["Tex.", "NV"])
    client_rows = client_frame(clients, NOW.date())
    rules_frame = policy_frame(
        policies,
        client_rows,
        tables.get("agents", clients.head(0).select(npn="client_id")),
        NOW.date(),
    )
    sta = status_unknown(rules_frame)
    assert [r.row_number for r in sta] == [2, 3]  # "In Force" and "XFER", as written
    assert [r.value_minimized for r in sta] == ["In *****", "X***"]
    adr = state_code(client_rows)
    assert [r.row_number for r in adr] == [2]


def test_notes_are_collected_for_the_pii_gate_from_every_row(tmp_path: Path) -> None:
    notes = crm(tmp_path, Asker(None)).notes
    assert [(n.lineage.row_number, n.text) for n in notes] == [(2, "call back")]

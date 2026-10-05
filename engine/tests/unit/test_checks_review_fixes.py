"""Review fixes for the cross-record checks: dates (#42), lists (#43), lineage (#49, #53)."""

from decimal import Decimal

import polars as pl
import pytest

from intake.checks import run_cross_record_checks
from intake.normalize import NotMoney, parse_money, split_list
from intake.readers import build_frame

RTS_HEAD = "npn carrier state plan_year line_of_business appointed certified end_date".split()
POLICY_HEAD = "policy_id client_id carrier line_of_business state effective_date writing_agent_npn"


def frame(
    rows: list[list[str | None]],
    header: list[str],
    *,
    file: str,
    sheet: str | None = None,
    first_row: int = 2,
    version: str = "canonical",
) -> pl.DataFrame:
    numbered = [(first_row + i, r) for i, r in enumerate(rows)]
    return build_frame(
        header, numbered, source_file=file, sheet=sheet, run_id="r1", mapping_version=version
    )


def world(
    effective: list[str], licenses: str = "TX", rts_rows: list[list[str | None]] | None = None
) -> dict[str, pl.DataFrame]:
    policies: list[list[str | None]] = [
        [f"P{i}", "C-1", "Harborline", "MA", "TX", eff, "111"] for i, eff in enumerate(effective)
    ]
    return {
        "clients": frame([["C-1", "TX"]], ["client_id", "state"], file="crm.csv"),
        "agents": frame(
            [["111", licenses]], ["npn", "license_states"], file="roster.xlsx", sheet="Agents"
        ),
        "rts": frame(rts_rows or [], RTS_HEAD, file="roster.xlsx", sheet="RTS"),
        "policies": frame(
            policies, POLICY_HEAD.split(), file="crm.xlsx", sheet="Policies", version="v3"
        ),
    }


def test_rts_reads_every_date_style_and_counts_unreadable_dates() -> None:
    """#42: ISO, US, and two-digit-year dates are all checked; an unreadable one is counted."""
    result = run_cross_record_checks(world(["2026-05-01", "05/01/2026", "05/01/26", "someday"]))
    gaps = sorted(r.row_number or 0 for r in result.records if r.rule_id == "RTS-001")
    assert gaps == [2, 3, 4]
    assert result.skipped == {"policies.effective_date": 1}


def test_rts_end_date_in_us_style_still_expires() -> None:
    rts: list[list[str | None]] = [
        ["111", "Harborline", "TX", "2026", "MA", "true", "true", "01/31/26"]
    ]
    result = run_cross_record_checks(world(["05/01/2026"], rts_rows=rts))
    assert [r.rule_id for r in result.records] == ["RTS-002"]


def test_roster_comma_license_list_is_read() -> None:
    """#43: the roster writes "FL, GA, TX"; a TX policy is licensed."""
    rts: list[list[str | None]] = [["111", "Harborline", "TX", "2026", "MA", "yes", "yes", None]]
    result = run_cross_record_checks(world(["2026-05-01"], licenses="FL, GA, TX", rts_rows=rts))
    assert result.records == []
    result = run_cross_record_checks(world(["2026-05-01"], licenses="FL | GA", rts_rows=rts))
    assert [r.rule_id for r in result.records] == ["LIC-001"]


def test_exceptions_carry_the_incoming_lineage() -> None:
    """#49: sheet and mapping_version come from the row, not constants."""
    result = run_cross_record_checks(world(["2026-05-01"]))
    lineage = result.records[0].lineage
    assert lineage is not None
    assert (lineage.source_file, lineage.sheet, lineage.mapping_version) == (
        "crm.xlsx",
        "Policies",
        "v3",
    )


def test_row_numbers_repeating_across_files_are_never_keys() -> None:
    """#53: two policy files both start at row 2; every gap gets its own id and cell entry."""
    tables = world([])
    head = POLICY_HEAD.split()
    a = frame([["P1", "C-1", "Harborline", "MA", "TX", "2026-05-01", "111"]], head, file="a.csv")
    b = frame([["P2", "C-1", "Harborline", "MA", "TX", "2026-06-01", "111"]], head, file="b.csv")
    tables["policies"] = pl.concat([a, b])
    result = run_cross_record_checks(tables)
    assert sorted(r.rule_id for r in result.records) == ["RTS-001", "RTS-001"]
    ids = {r.id for r in result.records}
    assert len(ids) == 2
    (cell,) = result.coverage.cells
    assert set(cell.exception_ids) == ids and cell.policy_count == 2


@pytest.mark.parametrize(
    ("text", "parts"),
    [("FL, GA, TX", ["FL", "GA", "TX"]), ("tx|ok", ["TX", "OK"]), (" ", []), (None, [])],
)
def test_split_list(text: str | None, parts: list[str]) -> None:
    assert split_list(text) == parts


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("$61.05", Decimal("61.05")),
        ("1,061.05", Decimal("1061.05")),
        ("(61.05)", Decimal("-61.05")),
        (" -52.50 ", Decimal("-52.50")),
        ("", None),
        (None, None),
    ],
)
def test_parse_money(text: str | None, amount: Decimal | None) -> None:
    assert parse_money(text) == amount


@pytest.mark.parametrize("text", ["abc", "12.3.4", "NaN", "99999999999"])
def test_parse_money_refuses_non_numbers(text: str) -> None:
    with pytest.raises(NotMoney):
        parse_money(text)

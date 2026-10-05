"""SSN-001 decision rule (#39): header hints, id-field exclusions, and value shapes."""

import json
from pathlib import Path

import pytest

from agency_schema.enums import Severity
from intake.gates.refusal import check_ssn
from intake.ingest import ingest

FIXTURES = Path(__file__).parents[3] / "fixtures"


def gate(tmp_path: Path, header: str, values: list[str]) -> list[str]:
    """Run SSN-001 on a one-file drop with an Agent Name column plus the column under test."""
    lines = [f"Agent Name,{header}"] + [f"Agent {i},{v}" for i, v in enumerate(values)]
    (tmp_path / "roster.csv").write_text("\n".join(lines) + "\n")
    return [r.rule_id for r in check_ssn(ingest(tmp_path, run_id="r").tables)]


NINE_DIGIT_NPNS = [str(123456789 + 7919 * i) for i in range(20)]


def test_the_ssn_fixture_still_blocks_once_and_echoes_no_value() -> None:
    result = ingest(FIXTURES / "agency-a-ssn" / "drop", run_id="r")
    records = check_ssn(result.tables)
    assert [r.rule_id for r in records] == ["SSN-001"]
    (record,) = records
    assert record.blocks_load and record.severity == Severity.BLOCKER
    assert record.row_number is None and record.lineage is None
    truth = json.loads((FIXTURES / "agency-a-ssn" / "ground_truth.json").read_text())
    (defect,) = [d for d in truth["defects"] if d["defect_type"] == "ssn_column"]
    text = json.dumps([r.model_dump(mode="json") for r in records])
    values = defect["injected_values"]["values"]
    assert not any(v in text or v.replace("-", "") in text for v in values)


def test_the_clean_fixture_never_fires() -> None:
    assert check_ssn(ingest(FIXTURES / "agency-a" / "drop", run_id="r").tables) == []


@pytest.mark.parametrize("header", ["NPN", "NPN #", "Writing Agent NPN", "Upline NPN"])
def test_a_nine_digit_npn_column_does_not_block(tmp_path: Path, header: str) -> None:
    assert gate(tmp_path, header, NINE_DIGIT_NPNS) == []


def test_nine_digit_npns_under_a_neutral_header_do_not_block(tmp_path: Path) -> None:
    assert gate(tmp_path, "Number", NINE_DIGIT_NPNS) == []


@pytest.mark.parametrize(
    "header", ["Member ID", "Policy #", "Medicare ID", "Zip", "Phone", "Subscriber ID"]
)
def test_known_id_headers_never_block_on_nine_digits(tmp_path: Path, header: str) -> None:
    assert gate(tmp_path, header, [f"0{v[1:]}" for v in NINE_DIGIT_NPNS]) == []


def test_header_ssn_with_bare_nine_digit_values_blocks(tmp_path: Path) -> None:
    assert gate(tmp_path, "SSN", NINE_DIGIT_NPNS) == ["SSN-001"]


@pytest.mark.parametrize("header", ["Tax ID", "Soc Sec #", "TIN", "Social Security"])
def test_strong_headers_with_dashed_values_block(tmp_path: Path, header: str) -> None:
    values = [f"000-{i:02d}-{1000 + i}" for i in range(20)]
    assert gate(tmp_path, header, values) == ["SSN-001"]


def test_phone_with_ten_digit_values_does_not_block(tmp_path: Path) -> None:
    assert gate(tmp_path, "Phone", [f"555{7000000 + i}" for i in range(20)]) == []


def test_free_text_with_a_tenth_dashed_ssns_blocks(tmp_path: Path) -> None:
    values = [f"called on 2026-0{i % 9 + 1}-15 about plan" for i in range(18)]
    values += ["client gave 000-12-3456 on the call", "000-98-7654"]
    assert gate(tmp_path, "Notes", values) == ["SSN-001"]


def test_zero_led_bare_nine_digits_that_cannot_be_npns_block(tmp_path: Path) -> None:
    assert gate(tmp_path, "Number", [f"0{v[1:]}" for v in NINE_DIGIT_NPNS]) == ["SSN-001"]

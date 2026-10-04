from typing import Any

import pytest
from pydantic import ValidationError

from agency_schema.exceptions import BLOCKER_RULE_IDS, ExceptionRecord, minimize_value


@pytest.mark.parametrize(
    ("raw", "masked"),
    [
        ("1958-03-12", "19**-**-**"),  # the example shape from the build guide
        ("1EG4TE5MK73", "1E*********"),  # MBI
        ("HL-998213", "HL-******"),
        ("O'Brien", "O'*****"),
        ("TX", "**"),  # short values keep at most a third of their characters
        ("12345", "1****"),
        ("7", "*"),
        ("", None),
        (None, None),
    ],
)
def test_minimize_value(raw: str | None, masked: str | None) -> None:
    assert minimize_value(raw) == masked


def test_minimize_value_caps_long_text() -> None:
    masked = minimize_value("a" * 500)
    assert masked is not None
    assert len(masked) <= 35
    assert masked.endswith("...")


def test_minimized_value_never_shows_three_digits_in_a_row() -> None:
    for raw in ["123456789", "1958-03-12", "12/31/1958 1EG4TE5MK73", "61.05"]:
        masked = minimize_value(raw)
        assert masked is not None
        assert not any(masked[i : i + 3].isdigit() for i in range(len(masked) - 2))


def test_record_accepts_a_valid_error(exception_kwargs: dict[str, Any]) -> None:
    record = ExceptionRecord(**exception_kwargs)
    assert record.lane == "UNREVIEWED"


def test_record_refuses_a_raw_value(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["value_minimized"] = "1958-03-12"
    with pytest.raises(ValidationError, match="minimize_value"):
        ExceptionRecord(**exception_kwargs)


@pytest.mark.parametrize("raw", ["Smith", "1 9 5 8", "x" * 500, "ab*c", "TX", "12", "1E*"])
def test_record_refuses_anything_minimize_value_would_not_produce(
    exception_kwargs: dict[str, Any], raw: str
) -> None:
    exception_kwargs["value_minimized"] = raw
    with pytest.raises(ValidationError, match="minimize_value"):
        ExceptionRecord(**exception_kwargs)


@pytest.mark.parametrize("ssn", ["123-45-6789", "123 45 6789"])
@pytest.mark.parametrize("field", ["message", "suggested_fix"])
def test_record_refuses_an_ssn_in_text(
    exception_kwargs: dict[str, Any], field: str, ssn: str
) -> None:
    exception_kwargs[field] = f"SSN {ssn} found"
    with pytest.raises(ValidationError, match="SSN"):
        ExceptionRecord(**exception_kwargs)


def test_record_allows_a_nine_digit_npn_in_text(exception_kwargs: dict[str, Any]) -> None:
    # NPN-002's message names the NPN, and NPNs can be 9 digits long.
    exception_kwargs["message"] = "NPN 188441234 unknown"
    assert ExceptionRecord(**exception_kwargs).message == "NPN 188441234 unknown"


@pytest.mark.parametrize(
    "raw", ["TX", "7", "12345", "1958-03-12", "1EG4TE5MK73", "HL-998213", "z" * 500]
)
def test_record_accepts_every_minimize_value_output(
    exception_kwargs: dict[str, Any], raw: str
) -> None:
    exception_kwargs["value_minimized"] = minimize_value(raw)
    assert ExceptionRecord(**exception_kwargs).value_minimized == minimize_value(raw)


def test_record_blocks_load_must_be_a_real_bool(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["blocks_load"] = "no"
    with pytest.raises(ValidationError):
        ExceptionRecord(**exception_kwargs)


def test_record_rule_id_must_match_family(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["family"] = "MBI"
    with pytest.raises(ValidationError, match="family"):
        ExceptionRecord(**exception_kwargs)


def test_record_rule_id_format(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["rule_id"] = "DOB1"
    with pytest.raises(ValidationError):
        ExceptionRecord(**exception_kwargs)


def test_exactly_three_blockers() -> None:
    assert BLOCKER_RULE_IDS == frozenset({"MAP-003", "CMP-001", "SSN-001"})


def test_only_the_three_blockers_may_be_blockers(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs.update(severity="BLOCKER", blocks_load=True)
    with pytest.raises(ValidationError, match="blocker"):
        ExceptionRecord(**exception_kwargs)


def test_blocker_must_block_load(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs.update(
        rule_id="CMP-001", family="CMP", severity="BLOCKER", blocks_load=False, row_number=None
    )
    with pytest.raises(ValidationError, match="blocks_load"):
        ExceptionRecord(**exception_kwargs)


def test_error_may_not_block_load(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["blocks_load"] = True
    with pytest.raises(ValidationError, match="blocks_load"):
        ExceptionRecord(**exception_kwargs)


def test_file_level_blocker_has_no_row(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs.update(
        rule_id="CMP-001",
        family="CMP",
        severity="BLOCKER",
        blocks_load=True,
        row_number=None,
        raw_hash=None,
        field=None,
        value_minimized=None,
        lineage=None,
    )
    assert ExceptionRecord(**exception_kwargs).row_number is None


def test_row_level_record_needs_lineage(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["lineage"] = None
    with pytest.raises(ValidationError, match="lineage"):
        ExceptionRecord(**exception_kwargs)


def test_record_lineage_must_match_its_row(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["lineage"] = {**exception_kwargs["lineage"], "row_number": 3}
    with pytest.raises(ValidationError, match="lineage"):
        ExceptionRecord(**exception_kwargs)


def test_file_level_record_has_no_lineage(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs.update(row_number=None, raw_hash=None)
    with pytest.raises(ValidationError, match="lineage"):
        ExceptionRecord(**exception_kwargs)


def test_jev_scores_are_probabilities(exception_kwargs: dict[str, Any]) -> None:
    exception_kwargs["jev"] = {
        "entry_error_probability": 1.5,
        "impact_score": None,
        "pii_probability": None,
    }
    with pytest.raises(ValidationError):
        ExceptionRecord(**exception_kwargs)


def test_record_has_no_defaults() -> None:
    assert all(f.is_required() for f in ExceptionRecord.model_fields.values())

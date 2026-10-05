from datetime import date

import pytest
from hypothesis import given
from hypothesis import strategies as st

from agency_schema.enums import LineOfBusiness
from agency_schema.formats import (
    is_valid_hios_plan_id,
    is_valid_mbi,
    is_valid_medigap_letter,
    is_valid_npn,
    normalize_email,
    normalize_name,
    normalize_phone,
    parse_date_loose,
    parse_medicare_plan_id,
    zip3_matches_state,
    zip3_table,
)

MBI_LETTERS = "ACDEFGHJKMNPQRTUVWXY"  # A to Z without S L O I B Z
DIGITS = "0123456789"


def _chars(alphabet: str, n: int = 1) -> st.SearchStrategy[str]:
    return st.text(alphabet=alphabet, min_size=n, max_size=n)


letter = _chars(MBI_LETTERS)
digit = _chars(DIGITS)
alnum = _chars(MBI_LETTERS + DIGITS)

valid_mbis = st.tuples(
    _chars("123456789"), letter, alnum, digit, letter, alnum, digit, letter, letter, digit, digit
).map("".join)
valid_npns = st.integers(min_value=1, max_value=9_999_999_999).map(str)
valid_plan_ids = st.tuples(
    st.sampled_from("HRS"),
    _chars(DIGITS, 4),
    _chars(DIGITS, 3),
    st.one_of(st.just(""), st.text(alphabet=DIGITS, min_size=1, max_size=3).map("-{}".format)),
).map(lambda t: f"{t[0]}{t[1]}-{t[2]}{t[3]}")
valid_hios = st.tuples(
    _chars(DIGITS, 5),
    _chars("ABCDEFGHIJKLMNOPQRSTUVWXYZ", 2),
    _chars(DIGITS, 7),
    st.one_of(st.just(""), _chars(DIGITS, 2).map("-{}".format)),
).map("".join)


@given(valid_mbis)
def test_valid_mbis_accepted(mbi: str) -> None:
    assert is_valid_mbi(mbi)
    assert is_valid_mbi(f"{mbi[:4]}-{mbi[4:7]}-{mbi[7:]}".lower())  # dashes and case allowed


@pytest.mark.parametrize(
    "mbi",
    ["1SG4TE5MK73", "0EG4TE5MK73", "1EG4TE5MK7", "1EG4TE5MK733", "11G4TE5MK73", "", "1EG4TE5MKZ3"],
)
def test_invalid_mbis_refused(mbi: str) -> None:
    # S in position 2, zero first, too short, too long, digit where a letter goes, empty, Z
    assert not is_valid_mbi(mbi)


@given(valid_npns)
def test_valid_npns_accepted(npn: str) -> None:
    assert is_valid_npn(npn)


@pytest.mark.parametrize("npn", ["0123456", "12345678901", "12a45", "", "-12", "1.5"])
def test_invalid_npns_refused(npn: str) -> None:
    assert not is_valid_npn(npn)


@given(valid_plan_ids)
def test_valid_plan_ids_parse(plan_id: str) -> None:
    parsed = parse_medicare_plan_id(plan_id)
    assert parsed is not None
    assert parsed.contract == plan_id[:5]
    assert parsed.plan == plan_id[6:9]
    expected = LineOfBusiness.PDP if plan_id[0] == "S" else LineOfBusiness.MA
    assert parsed.line_of_business == expected


def test_plan_id_parts() -> None:
    parsed = parse_medicare_plan_id("H1234-005-002")
    assert parsed is not None
    assert (parsed.prefix, parsed.contract, parsed.plan, parsed.segment) == (
        "H",
        "H1234",
        "005",
        "002",
    )
    assert parse_medicare_plan_id("S5678-001") == ("S", "S5678", "001", None)


@pytest.mark.parametrize("plan_id", ["E1234-005", "H123-005", "H1234-05", "H1234-005-0001", ""])
def test_invalid_plan_ids_refused(plan_id: str) -> None:
    assert parse_medicare_plan_id(plan_id) is None


@pytest.mark.parametrize(
    "value", ["G", "Plan N", "plan f", "F High Deductible", "Plan G High Deductible"]
)
def test_valid_medigap_letters(value: str) -> None:
    assert is_valid_medigap_letter(value)


@pytest.mark.parametrize("value", ["E", "H", "Plan", "GG", "", "Plan E"])
def test_invalid_medigap_letters(value: str) -> None:
    assert not is_valid_medigap_letter(value)


@given(valid_hios)
def test_valid_hios_accepted(hios: str) -> None:
    assert is_valid_hios_plan_id(hios)


@pytest.mark.parametrize(
    "hios", ["12345TX123456", "12345TX12345678", "12345tx1234567", "12345TX1234567-1"]
)
def test_invalid_hios_refused(hios: str) -> None:
    # the first is 13 characters
    assert not is_valid_hios_plan_id(hios)


@pytest.mark.parametrize(
    ("zip_code", "state"),
    [("90012", "CA"), ("10001", "NY"), ("78701-1234", "TX"), ("41011", "KY"), ("96910", "GU")],
)
def test_zip_spot_checks(zip_code: str, state: str) -> None:
    assert zip3_matches_state(zip_code, state)


@pytest.mark.parametrize(
    ("zip_code", "state"),
    [
        ("90012", "NV"),
        ("41011", "OH"),
        ("9001", "CA"),
        ("900123", "CA"),
        ("ABCDE", "CA"),
        ("00001", "NY"),
    ],
)
def test_zip_mismatches(zip_code: str, state: str) -> None:
    assert not zip3_matches_state(zip_code, state)


@given(st.sampled_from(sorted({(z, s) for z, states in zip3_table().items() for s in states})))
def test_every_table_prefix_matches_its_state(pair: tuple[str, str]) -> None:
    zip3, state = pair
    assert zip3_matches_state(f"{zip3}01", state)


def test_every_state_in_zip_table() -> None:
    states = {s for row in zip3_table().values() for s in row}
    expected = set(
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ "
        "NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY "
        "DC PR VI GU AS MP FM MH PW AA AE AP".split()
    )
    assert states == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("(555) 123-4567", "5551234567"),
        ("+1 555.123.4567", "5551234567"),
        ("555-123-4567 ext. 12", "5551234567"),
        ("123-4567", None),
        ("", None),
    ],
)
def test_normalize_phone(raw: str, expected: str | None) -> None:
    assert normalize_phone(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(" Jane.Doe@Example.COM ", "jane.doe@example.com"), ("jane@", None), ("a b@c.com", None)],
)
def test_normalize_email(raw: str, expected: str | None) -> None:
    assert normalize_email(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("O'Brien, Jr.", "obrien"),
        ("DE LA CRUZ", "de la cruz"),
        ("  Smith-Jones  III ", "smith jones"),
        ("Sr. Mary", "mary"),
        ("Jr", "jr"),  # a bare suffix is kept, so the name never becomes empty
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("45901", date(2025, 9, 1)),
        ("2025-09-01", date(2025, 9, 1)),
        ("2025-09-01T00:00:00", date(2025, 9, 1)),
        ("09/01/2025", date(2025, 9, 1)),
        ("9/1/2025", date(2025, 9, 1)),
        ("01-Sep-25", date(2025, 9, 1)),
        ("01-SEP-1958", date(1958, 9, 1)),
        ("03/12/58", date(1958, 3, 12)),
        ("05/01/29", date(2029, 5, 1)),  # pivot: 00 to 29 are 2000s
        ("05/01/30", date(1930, 5, 1)),
        ("20260501", date(2026, 5, 1)),  # compact yyyymmdd, as the enrollment export writes it
        ("19000101", date(1900, 1, 1)),
        ("20991231", date(2099, 12, 31)),
        (" 20240229 ", date(2024, 2, 29)),
    ],
)
def test_parse_date_loose(raw: str, expected: date) -> None:
    assert parse_date_loose(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "19999",
        "60001",
        "02/30/2025",
        "2025-13-01",
        "next week",
        "",
        "13/01/2025",
        "18991231",  # compact dates: year before 1900
        "21000101",  # year after 2099
        "20261301",  # month 13
        "20260230",  # no 30 February
        "20250229",  # 2025 is not a leap year
        "01052026",  # day-first eight digits is not yyyymmdd
        "2026051",  # seven digits: neither a serial nor yyyymmdd
        "202605010",  # nine digits
    ],
)
def test_parse_date_loose_refuses(raw: str) -> None:
    assert parse_date_loose(raw) is None


def test_compact_dates_and_excel_serials_never_collide() -> None:
    # Serials are five digits (20000 to 60000); compact dates are exactly eight.
    assert parse_date_loose("45901") == date(2025, 9, 1)
    assert parse_date_loose("00045901") is None  # zero-padded serial is not a valid yyyymmdd

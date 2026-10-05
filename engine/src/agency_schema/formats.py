"""Pure format helpers. Models do not call these; the row rules (PR 8) do.

Each validator takes a raw string and answers yes or no, or returns the parsed parts.
None of them raise on bad input.
"""

import csv
import re
from datetime import date, datetime, timedelta
from functools import cache
from importlib.resources import files
from typing import NamedTuple

from agency_schema.enums import LineOfBusiness

# MBI letters exclude S L O I B Z. Positions: C A AN N A AN N A A N N.
_MBI_A = "[AC-HJKMNP-RT-Y]"
_MBI_AN = "[AC-HJKMNP-RT-Y0-9]"
MBI_PATTERN = re.compile(
    rf"[1-9]{_MBI_A}{_MBI_AN}[0-9]{_MBI_A}{_MBI_AN}[0-9]{_MBI_A}{_MBI_A}[0-9]{{2}}"
)
NPN_PATTERN = re.compile(r"[1-9][0-9]{0,9}")
MEDICARE_PLAN_PATTERN = re.compile(r"([HRS])(\d{4})-(\d{3})(?:-(\d{1,3}))?")
MEDIGAP_PATTERN = re.compile(r"(?:PLAN\s+)?[ABCDFGKLMN](?:\s+HIGH\s+DEDUCTIBLE)?", re.IGNORECASE)
HIOS_PATTERN = re.compile(r"\d{5}[A-Z]{2}\d{7}(?:-\d{2})?")
ZIP_PATTERN = re.compile(r"(\d{3})\d{2}(?:-\d{4})?")
EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_EXTENSION = re.compile(r"\s*(?:x|ext\.?)\s*\d+\s*$", re.IGNORECASE)

NAME_SUFFIXES = frozenset({"jr", "sr", "ii", "iii"})

# Two-digit years: 30 to 99 are 1930 to 1999, 00 to 29 are 2000 to 2029.
# So "05/01/29" is 2029, a future date that the date rules must flag.
TWO_DIGIT_YEAR_PIVOT = 30
EXCEL_SERIAL_MIN = 20000  # 1954-10-03
EXCEL_SERIAL_MAX = 60000  # 2064-04-08
COMPACT_DATE_DIGITS = 8  # 20260501 is 1 May 2026
COMPACT_YEAR_MIN = 1900
COMPACT_YEAR_MAX = 2099
EXCEL_EPOCH = date(1899, 12, 30)  # Excel's day zero, which absorbs its 1900 leap-year bug
MONTHS = {
    m: i for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split(), start=1)
}
_US_DATE = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})")
_DAY_MON_YEAR = re.compile(r"(\d{1,2})-([A-Za-z]{3})-(\d{2}|\d{4})")
_ISO_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})(?:[T ][\d:.]+)?")


class MedicarePlanId(NamedTuple):
    prefix: str  # H or R is Medicare Advantage, S is a drug plan
    contract: str  # prefix plus four digits, for example H1234
    plan: str  # three digits
    segment: str | None  # one to three digits, or None

    @property
    def line_of_business(self) -> LineOfBusiness:
        return LineOfBusiness.PDP if self.prefix == "S" else LineOfBusiness.MA


def is_valid_mbi(value: str) -> bool:
    """Medicare Beneficiary Identifier. Dashes, spaces at the ends, and lowercase are allowed."""
    return MBI_PATTERN.fullmatch(value.strip().replace("-", "").upper()) is not None


def is_valid_npn(value: str) -> bool:
    """National Producer Number: 1 to 10 digits with no leading zero."""
    return NPN_PATTERN.fullmatch(value.strip()) is not None


def parse_medicare_plan_id(value: str) -> MedicarePlanId | None:
    """Split an MA or PDP contract-plan ID such as H1234-005-002. None if it is not one."""
    match = MEDICARE_PLAN_PATTERN.fullmatch(value.strip().upper())
    if match is None:
        return None
    prefix, digits, plan, segment = match.groups()
    return MedicarePlanId(prefix, prefix + digits, plan, segment)


def is_valid_medigap_letter(value: str) -> bool:
    """A Medigap plan letter, optionally written "Plan G" or "F High Deductible"."""
    return MEDIGAP_PATTERN.fullmatch(value.strip()) is not None


def is_valid_hios_plan_id(value: str) -> bool:
    """ACA marketplace HIOS plan ID: 5 digits, 2 capital letters, 7 digits, optional -NN."""
    return HIOS_PATTERN.fullmatch(value.strip()) is not None


@cache
def zip3_table() -> dict[str, frozenset[str]]:
    """3-digit ZIP prefix to the state codes that use it, from data/zip3_state.csv."""
    table: dict[str, set[str]] = {}
    text = files("agency_schema").joinpath("data/zip3_state.csv").read_text(encoding="utf-8")
    for row in csv.DictReader(text.splitlines()):
        table.setdefault(row["zip3"], set()).add(row["state"])
    return {zip3: frozenset(states) for zip3, states in table.items()}


def zip3_matches_state(zip_code: str, state: str) -> bool:
    """True when the ZIP is 5 digits or ZIP+4 and its prefix belongs to the state."""
    match = ZIP_PATTERN.fullmatch(zip_code.strip())
    if match is None:
        return False
    return state.strip().upper() in zip3_table().get(match.group(1), frozenset())


def normalize_phone(value: str) -> str | None:
    """Ten digits with no punctuation, dropping a leading 1 and any extension. None if not ten."""
    digits = re.sub(r"\D", "", PHONE_EXTENSION.sub("", value))
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def normalize_email(value: str) -> str | None:
    """Trimmed and lowercased. None if it does not look like name@domain.tld."""
    email = value.strip().lower()
    return email if EMAIL_PATTERN.fullmatch(email) else None


def normalize_name(value: str) -> str:
    """For matching: casefold, drop apostrophes, other punctuation becomes a space,
    collapse spaces, and drop Jr, Sr, II, III unless that would leave nothing."""
    text = re.sub(r"[^\w\s]", " ", value.casefold().replace("'", "").replace("’", ""))
    words = text.split()
    kept = [w for w in words if w not in NAME_SUFFIXES]
    return " ".join(kept or words)


def _full_year(year: str) -> int:
    if len(year) == 4:
        return int(year)
    two = int(year)
    return 1900 + two if two >= TWO_DIGIT_YEAR_PIVOT else 2000 + two


def _make_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def parse_date_loose(value: str) -> date | None:
    """Read ISO, MM/DD/YYYY, MM/DD/YY, DD-Mon-YY, compact YYYYMMDD, or an Excel serial.

    Returns None for anything else, including impossible dates like 02/30/2025.
    Day-first slash dates are not accepted, so 13/01/2025 is None. Exactly eight digits are
    always read as YYYYMMDD with a year from 1900 to 2099 (never as a serial, which has five).
    """
    text = value.strip()
    if text.isdigit() and len(text) == COMPACT_DATE_DIGITS:
        year = int(text[:4])
        if not COMPACT_YEAR_MIN <= year <= COMPACT_YEAR_MAX:
            return None
        return _make_date(year, int(text[4:6]), int(text[6:]))
    if text.isdigit():
        serial = int(text)
        if EXCEL_SERIAL_MIN <= serial <= EXCEL_SERIAL_MAX:
            return EXCEL_EPOCH + timedelta(days=serial)
        return None
    if match := _ISO_DATE.fullmatch(text):
        if "T" in text or " " in text:
            try:
                return datetime.fromisoformat(text).date()
            except ValueError:
                return None
        return _make_date(int(match[1]), int(match[2]), int(match[3]))
    if match := _US_DATE.fullmatch(text):
        return _make_date(_full_year(match[3]), int(match[1]), int(match[2]))
    if match := _DAY_MON_YEAR.fullmatch(text):
        month = MONTHS.get(match[2].upper())
        return _make_date(_full_year(match[3]), month, int(match[1])) if month else None
    return None

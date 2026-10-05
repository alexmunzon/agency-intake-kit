"""Shared value normalizers for the cross-record checks and the tie-out.

Readers keep every cell as raw text, so dates, money, and lists arrive in whatever style the
source wrote. These helpers read them one way everywhere: dates through parse_date_loose, money
to Decimal, and list fields split on any common separator.
"""

import re
from decimal import Decimal, InvalidOperation

import polars as pl

from agency_schema.formats import parse_date_loose
from intake.config import LIST_SPLIT_PATTERN

MONEY_LIMIT = Decimal("10000000000")  # DECIMAL(12, 2) holds less than ten billion
_MONEY_JUNK = re.compile(r"[\s$,]")


class NotMoney(ValueError):
    """A non-blank amount that is not a number."""


def split_list(value: str | None) -> list[str]:
    """ "FL, GA | tx" -> ["FL", "GA", "TX"]. Blank gives an empty list."""
    return [part.upper() for part in re.split(LIST_SPLIT_PATTERN, value or "") if part]


def parse_money(value: str | None) -> Decimal | None:
    """ "$1,061.05" -> 1061.05 and "(61.05)" -> -61.05. Blank is None; anything else NotMoney."""
    text = _MONEY_JUNK.sub("", value or "")
    if not text:
        return None
    negative = text.startswith("(") and text.endswith(")")
    if negative:
        text = text[1:-1]
    try:
        amount = Decimal(text)
    except InvalidOperation as error:
        raise NotMoney(value) from error
    if not amount.is_finite() or abs(amount) >= MONEY_LIMIT:
        raise NotMoney(value)
    return -amount if negative else amount


def loose_date(column: str) -> pl.Expr:
    """A text column as a Date, read with parse_date_loose (null when blank or unreadable)."""
    return pl.col(column).map_elements(parse_date_loose, return_dtype=pl.Date, skip_nulls=True)


def unreadable_dates(frame: pl.DataFrame, column: str) -> int:
    """How many non-blank cells in column parse_date_loose cannot read."""
    if column not in frame.columns:
        return 0
    text = pl.col(column).str.strip_chars()
    return frame.filter((text != "") & loose_date(column).is_null()).height

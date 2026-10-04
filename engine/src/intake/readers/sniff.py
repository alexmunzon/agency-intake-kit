"""Guess how a file was written: encoding, delimiter, header row, and trailing total rows."""

import csv
import io
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass

from intake.config import (
    HEADER_MIN_TEXT_SHARE,
    HEADER_SCAN_ROWS,
    READER_DELIMITERS,
    READER_ENCODINGS,
    SNIFF_SAMPLE_LINES,
    TOTAL_ROW_WORDS,
)

UTF8_BOM = b"\xef\xbb\xbf"
_NUMBER = re.compile(r"^[-+$]?[\d,]*\.?\d+%?$")


def decode(data: bytes) -> tuple[str, str]:
    """Return (text, encoding name). A UTF-8 byte order mark is stripped but not trusted.

    Some exports write the UTF-8 marker and then latin-1 text, so the body is decoded on its
    own: each READER_ENCODINGS entry is tried strictly, in order, and the last one never fails.
    """
    body = data.removeprefix(UTF8_BOM)
    for encoding in READER_ENCODINGS[:-1]:
        try:
            return body.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return body.decode(READER_ENCODINGS[-1]), READER_ENCODINGS[-1]


@dataclass(frozen=True)
class DelimiterGuess:
    delimiter: str
    confident: bool


def sniff_delimiter(text: str) -> DelimiterGuess:
    """Pick the delimiter that splits the first lines into the same number of fields.

    Each candidate is scored by how many sample lines share its most common field count (at
    least two fields). The guess is confident when every sample line agrees.
    """
    lines = [line for line in text.splitlines()[:SNIFF_SAMPLE_LINES] if line.strip()]
    best: tuple[float, int, str] | None = None
    for delim in READER_DELIMITERS:
        counts = [len(row) for row in csv.reader(lines, delimiter=delim)]
        if not counts:
            continue
        width, hits = Counter(counts).most_common(1)[0]
        if width < 2:
            continue
        score = (hits / len(counts), width, delim)
        if best is None or score[:2] > best[:2]:
            best = score
    if best is None:
        return DelimiterGuess(READER_DELIMITERS[0], confident=False)
    return DelimiterGuess(best[2], confident=best[0] == 1.0)


def split_rows(text: str, delimiter: str) -> list[list[str]]:
    return list(csv.reader(io.StringIO(text, newline=""), delimiter=delimiter))


def _is_text(cell: object) -> bool:
    return isinstance(cell, str) and cell.strip() != "" and not _NUMBER.match(cell.strip())


def find_header_row(rows: Sequence[Sequence[object]]) -> int:
    """0-based index of the first row whose cells are mostly words, past any title rows.

    A merged title row has one filled cell out of many, so it fails the HEADER_MIN_TEXT_SHARE
    test against the widest row. Falls back to the first row when nothing qualifies.
    """
    scan = rows[:HEADER_SCAN_ROWS]
    width = max((len(r) for r in scan), default=0)
    for i, row in enumerate(scan):
        if width and sum(_is_text(c) for c in row) / width >= HEADER_MIN_TEXT_SHARE:
            return i
    return 0


def is_trailer(row: Sequence[str | None]) -> bool:
    """A total, subtotal, or blank row at the end of a file."""
    filled = [c for c in row if c not in (None, "")]
    if not filled:
        return True
    first = (row[0] or "").strip().lower()
    return first in TOTAL_ROW_WORDS


def count_trailers(rows: Sequence[Sequence[str | None]]) -> int:
    """How many rows at the end are total or blank rows."""
    n = 0
    while n < len(rows) and is_trailer(rows[len(rows) - 1 - n]):
        n += 1
    return n


def total_row_count(rows: Sequence[Sequence[str | None]]) -> int | None:
    """The data row count a total row prints in its second cell, when it prints one."""
    for row in rows:
        first = (row[0] or "").strip().lower() if row else ""
        if first in TOTAL_ROW_WORDS and len(row) > 1 and (row[1] or "").strip().isdigit():
            return int((row[1] or "").strip())
    return None

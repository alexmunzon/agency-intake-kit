"""Small helpers the four source writers share: cell text, date formats, deterministic xlsx."""

import io
import re
import zipfile
from datetime import date
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any

from openpyxl import Workbook

EXCEL_EPOCH = date(1899, 12, 30)
SERIAL_RANGE = (20000, 60000)  # the serials the date rules accept (see CLAUDE.md)
FROZEN_ZIP_TIME = (2026, 10, 1, 0, 0, 0)
FROZEN_STAMP = "2026-10-01T00:00:00Z"
Location = tuple[str, str | None, int]  # source file, sheet (None for CSV), 1-based row


def text(value: Any) -> str:
    """Cell text: blank for None, enum values, money as exact two-decimal text."""
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def excel_serial(d: date) -> int:
    return (d - EXCEL_EPOCH).days


def fmt_date(d: date | None, style: str) -> str:
    """One of: iso, mdy (01/31/2026), mdy2 (01/31/26), compact (20260131), serial."""
    if d is None:
        return ""
    if style == "serial":
        return str(excel_serial(d))
    pattern = {"iso": "%Y-%m-%d", "mdy": "%m/%d/%Y", "mdy2": "%m/%d/%y", "compact": "%Y%m%d"}
    return d.strftime(pattern[style])


def save_xlsx(wb: Workbook, path: Path) -> None:
    """Save with frozen timestamps (zip entries and docProps), so the bytes never churn."""
    buffer = io.BytesIO()
    wb.save(buffer)
    with (
        zipfile.ZipFile(buffer) as src,
        zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as dst,
    ):
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "docProps/core.xml":
                stamp = rb"(<dcterms:(?:created|modified)[^>]*>)[^<]*"
                data = re.sub(stamp, rb"\g<1>" + FROZEN_STAMP.encode(), data)
            info = zipfile.ZipInfo(item.filename, FROZEN_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            dst.writestr(info, data)

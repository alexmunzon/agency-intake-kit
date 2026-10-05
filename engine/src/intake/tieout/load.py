"""Register the prepared frames, the rate table, and the tolerances as DuckDB tables.

No SQL lives here: frames go in through the Arrow stream interface (no pyarrow needed), and
every query is in sql/*.sql. All values arrive as text (dates ISO, amounts plain decimals, see
prepare.py), so money is never a float. A missing clients table arrives empty, which only
switches off the weak name plus DOB match.
"""

from collections.abc import Mapping
from decimal import Decimal
from typing import Any

import duckdb
import polars as pl

from intake import config


class _ArrowStream:
    """Hands DuckDB a polars frame through the Arrow C stream, so pyarrow is not needed."""

    def __init__(self, frame: pl.DataFrame) -> None:
        self._frame = frame

    def __arrow_c_stream__(self, requested_schema: Any = None) -> Any:
        return self._frame.__arrow_c_stream__(requested_schema)


def _register(con: duckdb.DuckDBPyConnection, name: str, frame: pl.DataFrame) -> None:
    con.from_arrow(_ArrowStream(frame)).create(name)


def _text(values: Mapping[str, list[str]]) -> pl.DataFrame:
    return pl.DataFrame(dict(values), schema=dict.fromkeys(values, pl.String))


def connect(
    frames: Mapping[str, pl.DataFrame],
    rates: Mapping[tuple[str, str], Decimal],
    new_business_months: int,
) -> duckdb.DuckDBPyConnection:
    """An in-memory database with raw_<table>, rates, and settings ready for the views."""
    con = duckdb.connect()
    for name, frame in frames.items():
        _register(con, f"raw_{name}", frame)
    _register(
        con,
        "rates",
        _text(
            {
                "line_of_business": [lob for lob, _ in rates],
                "commission_type": [kind for _, kind in rates],
                "monthly_amount": [str(amount) for amount in rates.values()],
            }
        ),
    )
    settings = {
        "line_tolerance_usd": config.TIE_LINE_TOLERANCE_USD,
        "line_tolerance_pct": config.TIE_LINE_TOLERANCE_PCT,
        "total_tolerance_pct": config.TIE_TOTAL_TOLERANCE_PCT,
        "new_business_months": new_business_months,
    }
    _register(con, "settings", _text({k: [str(v)] for k, v in settings.items()}))
    return con

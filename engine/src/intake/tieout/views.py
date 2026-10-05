"""Run the tie-out SQL files, in name order. The files are the documentation of the logic."""

from pathlib import Path
from typing import Any

import duckdb

SQL_DIR = Path(__file__).parent / "sql"


def sql_files() -> list[Path]:
    return sorted(SQL_DIR.glob("*.sql"))


def create_views(con: duckdb.DuckDBPyConnection) -> None:
    for path in sql_files():
        con.execute(path.read_text(encoding="utf-8"))


def rows(con: duckdb.DuckDBPyConnection, view: str) -> list[dict[str, Any]]:
    """Every row of a view as a dict, in the view's own order."""
    relation = con.table(view)
    return [dict(zip(relation.columns, row, strict=True)) for row in relation.fetchall()]

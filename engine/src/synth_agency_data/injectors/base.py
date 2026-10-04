"""Shared pieces for the injectors.

An injector is a function (world, rng, rate) -> (world, defects). It copies the rows it
changes and never mutates its input. `rate` is a share of the table the defect lives in.
Each defect is labeled with a stable record key, so PR 12 can score by key, not row position.
"""

import random
from collections.abc import Callable
from dataclasses import replace
from datetime import date
from decimal import Decimal
from typing import Any

from synth_agency_data.world import Row, World

Defect = dict[str, Any]
Injector = Callable[[World, random.Random, float], tuple[World, list[Defect]]]


def lock_key(record_key: dict[str, Any]) -> str:
    return "|".join(f"{k}={v}" for k, v in record_key.items())


def line_key(line: Row) -> dict[str, Any]:
    return {k: line[k] for k in ("carrier", "statement_period", "line_no")}


def _json(value: Any) -> Any:
    return str(value) if isinstance(value, date | Decimal) else value


def defect(
    defect_type: str,
    source: str,
    record_key: dict[str, Any],
    rule_id: str | None,
    **injected: Any,
) -> Defect:
    """A labeled defect. Scored exactly when it names a rule; unscored ones are for bob-resolve."""
    return {
        "source": source,
        "record_key": record_key,
        "row_ref": None,  # set by the writer: the row in the defected canonical CSV
        "defect_type": defect_type,
        "expected_rule_ids": [rule_id] if rule_id else [],
        "scored": rule_id is not None,
        "injected_values": {k: _json(v) for k, v in injected.items()},
    }


def _key_fn(key: str | Callable[[Row], dict[str, Any]]) -> Callable[[Row], dict[str, Any]]:
    return (lambda r: {key: r[key]}) if isinstance(key, str) else key


def pick(
    rng: random.Random,
    world: World,
    table: str,
    rate: float,
    key: str | Callable[[Row], dict[str, Any]],
    keep: Callable[[Row], bool] = lambda row: True,
) -> list[int]:
    """Row indexes to defect: rate times the table size (at least one), unlocked rows only."""
    rows = world.tables[table]
    record_key = _key_fn(key)
    eligible = [
        i for i, r in enumerate(rows) if keep(r) and lock_key(record_key(r)) not in world.locked
    ]
    return sorted(rng.sample(eligible, min(max(1, round(rate * len(rows))), len(eligible))))


def edit(
    world: World,
    table: str,
    indexes: list[int],
    change: Callable[[Row], dict[str, Any]],
    defect_type: str,
    rule_id: str | None,
    key: str | Callable[[Row], dict[str, Any]],
) -> tuple[World, list[Defect]]:
    """Set one field per picked row. `change` returns {field: new value}."""
    tables = {**world.tables, table: list(world.tables[table])}
    defects = []
    for i in indexes:
        row = tables[table][i]
        ((field, new),) = change(row).items()
        tables[table][i] = {**row, field: new}
        defects.append(
            defect(
                defect_type,
                table,
                _key_fn(key)(row),
                rule_id,
                field=field,
                to=new,
                **{"from": row[field]},
            )
        )
    return replace(world, tables=tables), defects

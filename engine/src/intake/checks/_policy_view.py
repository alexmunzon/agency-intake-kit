"""One row per policy with everything the REF, RTS, and LIC rules need, joined on normalized keys.

Added columns: _client_found, _agent_known, _state (policy state, else the client's address
state), _plan_year (effective year; see PLAN_YEAR_DECEMBER_ROLLS_FORWARD), _licensed, and
_rts ("HELD", "EXPIRED" when every matching RTS row ended before the effective date, "MISSING"
when no row matches, null when the policy cannot be evaluated) with _ended.
"""

import polars as pl

from intake.config import LIST_SEPARATOR, PLAN_YEAR_DECEMBER_ROLLS_FORWARD, RTS_TRUE_VALUES

RTS_COLUMNS = "npn carrier state plan_year line_of_business appointed certified end_date".split()
RTS_KEY = ["_npn", "_carrier", "_state", "_plan_year", "_lob"]


def _empty(*columns: str) -> pl.DataFrame:
    return pl.DataFrame(schema=dict.fromkeys(columns, pl.String))


def _text(name: str, upper: bool = False) -> pl.Expr:
    col = pl.col(name).str.strip_chars()
    return col.str.to_uppercase() if upper else col


def _date(name: str) -> pl.Expr:
    return pl.col(name).str.strip_chars().str.to_date("%Y-%m-%d", strict=False)


def held_rts(rts: pl.DataFrame) -> pl.DataFrame:
    """RTS rows that are appointed and certified, grouped by key with their latest end date."""
    yes = list(RTS_TRUE_VALUES)
    return (
        rts.filter(
            pl.col("appointed").str.strip_chars().str.to_lowercase().is_in(yes)
            & pl.col("certified").str.strip_chars().str.to_lowercase().is_in(yes)
        )
        .select(
            _text("npn").alias("_npn"),
            _text("carrier").str.to_lowercase().alias("_carrier"),
            _text("state", upper=True).alias("_state"),
            pl.col("plan_year").str.strip_chars().cast(pl.Int32, strict=False).alias("_plan_year"),
            _text("line_of_business", upper=True).alias("_lob"),
            _date("end_date").alias("_end"),
        )
        .group_by(RTS_KEY)
        .agg(pl.col("_end").is_null().any().alias("_open"), pl.col("_end").max().alias("_ended"))
    )


def policy_view(tables: dict[str, pl.DataFrame]) -> pl.DataFrame:
    clients = tables.get("clients", _empty("client_id", "state"))
    agents = tables.get("agents", _empty("npn", "license_states"))
    rts = tables.get("rts", _empty(*RTS_COLUMNS))
    known = clients.select(
        _text("client_id").alias("_cid"),
        _text("state", upper=True).alias("_client_state"),
        pl.lit(True).alias("_client_found"),
    ).unique("_cid", keep="first")
    roster = agents.select(
        _text("npn").alias("_npn"),
        pl.col("license_states").str.split(LIST_SEPARATOR).alias("_licenses"),
        pl.lit(True).alias("_agent_known"),
    ).unique("_npn", keep="first")
    eff = _date("effective_date")
    rollover = pl.lit(PLAN_YEAR_DECEMBER_ROLLS_FORWARD) & (eff.dt.month() == 12)
    view = (
        tables["policies"]
        .with_columns(
            _text("client_id").alias("_cid"),
            _text("writing_agent_npn").alias("_npn"),
            _text("carrier").str.to_lowercase().alias("_carrier"),
            _text("line_of_business", upper=True).alias("_lob"),
            eff.alias("_eff"),
            (eff.dt.year() + rollover.cast(pl.Int32)).cast(pl.Int32).alias("_plan_year"),
        )
        .join(known, on="_cid", how="left")
        .join(roster, on="_npn", how="left")
        .with_columns(
            pl.col("_client_found", "_agent_known").fill_null(False),
            pl.coalesce(_text("state", upper=True), pl.col("_client_state")).alias("_state"),
        )
        .with_columns(
            pl.col("_licenses")
            .list.eval(pl.element().str.strip_chars().str.to_uppercase())
            .list.contains(pl.col("_state"))
            .fill_null(False)
            .alias("_licensed")
        )
    )
    view = view.join(held_rts(rts), on=RTS_KEY, how="left", nulls_equal=False)
    evaluable = pl.col("_agent_known") & pl.all_horizontal(pl.col(c).is_not_null() for c in RTS_KEY)
    covered = pl.col("_open").fill_null(False) | (pl.col("_ended") >= pl.col("_eff"))
    return view.with_columns(
        pl.when(~evaluable)
        .then(None)
        .when(pl.col("_open").is_null())
        .then(pl.lit("MISSING"))
        .when(covered)
        .then(pl.lit("HELD"))
        .otherwise(pl.lit("EXPIRED"))
        .alias("_rts")
    )

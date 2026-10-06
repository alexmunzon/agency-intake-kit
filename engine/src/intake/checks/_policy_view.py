"""One row per policy with everything the REF, RTS, and LIC rules need, joined on normalized keys.

Added columns: _client_found, _agent_known, _state (policy state, else the client's address
state), _plan_year (effective year; see PLAN_YEAR_DECEMBER_ROLLS_FORWARD), _licensed, and
_rts ("HELD", "EXPIRED" when every matching RTS row ended before the effective date, "MISSING"
when no row matches, null when the policy cannot be evaluated) with _ended.
"""

import polars as pl

from intake.config import PLAN_YEAR_DECEMBER_ROLLS_FORWARD, RTS_TRUE_VALUES
from intake.normalize import loose_date, split_list

RTS_COLUMNS = (
    "npn carrier state plan_year line_of_business appointed certified effective_date end_date"
).split()
RTS_KEY = ["_npn", "_carrier", "_state", "_plan_year", "_lob"]


def _empty(*columns: str) -> pl.DataFrame:
    return pl.DataFrame(schema=dict.fromkeys(columns, pl.String))


def _text(name: str, upper: bool = False) -> pl.Expr:
    col = pl.col(name).str.strip_chars()
    return col.str.to_uppercase() if upper else col


def _date(name: str) -> pl.Expr:
    """Every date goes through parse_date_loose: the CRM rotates ISO, US, and two-digit years."""
    return loose_date(name)


def _rts_intervals(rts: pl.DataFrame) -> pl.DataFrame:
    """Readable appointed/certified intervals. An invalid end is never an open interval."""
    if "effective_date" not in rts.columns:
        rts = rts.with_columns(pl.lit(None, dtype=pl.String).alias("effective_date"))
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
            _date("effective_date").alias("_start"),
            _date("end_date").alias("_end"),
            (pl.col("end_date").is_null() | (_text("end_date") == "")).alias("_open"),
        )
        .filter(pl.col("_start").is_not_null() & (pl.col("_open") | pl.col("_end").is_not_null()))
    )


def held_rts(rts: pl.DataFrame) -> pl.DataFrame:
    """Readable RTS records held by key; policy eligibility checks each interval separately."""
    return (
        _rts_intervals(rts)
        .group_by(RTS_KEY)
        .agg(pl.col("_open").any(), pl.col("_end").max().alias("_ended"))
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
        pl.col("license_states")
        .map_elements(split_list, return_dtype=pl.List(pl.String), skip_nulls=True)
        .alias("_licenses"),
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
            pl.col("_licenses").list.contains(pl.col("_state")).fill_null(False).alias("_licensed")
        )
    )
    intervals = view.select("_rec", "_eff", *RTS_KEY).join(
        _rts_intervals(rts), on=RTS_KEY, how="left", nulls_equal=False
    )
    eligible = pl.col("_start") <= pl.col("_eff")
    covered = eligible & (pl.col("_open") | (pl.col("_end") >= pl.col("_eff")))
    states = intervals.group_by("_rec").agg(
        eligible.fill_null(False).any().alias("_eligible"),
        covered.fill_null(False).any().alias("_covered"),
        pl.when(eligible).then(pl.col("_end")).max().alias("_ended"),
    )
    view = view.join(states, on="_rec", how="left")
    evaluable = pl.col("_agent_known") & pl.all_horizontal(pl.col(c).is_not_null() for c in RTS_KEY)
    return view.with_columns(
        pl.when(~evaluable)
        .then(None)
        .when(~pl.col("_eligible"))
        .then(pl.lit("MISSING"))
        .when(pl.col("_covered"))
        .then(pl.lit("HELD"))
        .otherwise(pl.lit("EXPIRED"))
        .alias("_rts")
    )

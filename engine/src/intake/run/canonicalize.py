"""Turn mapped raw tables into the canonical tables every later stage reads (#58).

The one row shape after mapping: a polars frame per canonical table with one text column per
model field (blank is null), the reader's `lineage` struct carrying this run's mapping version,
and, for status, line of business, and state, a `<field>_raw` column holding the value exactly
as the source wrote it. Rules that judge the source's wording (STA-001, ADR-003) read the raw
column, so normalizing a value never hides that the source was non-standard.

Values change only where the meaning is certain: dates that parse_date_loose reads become ISO,
money read by parse_money becomes a plain decimal, list fields are split by the shared splitter
and joined with "|", yes and no flags become true and false, and enum words go through the PR 7
word table and Jev. Anything else stays exactly as read, so the row rules still see and flag it.

The CRM is one row per policy with the client repeated, so it splits in two: every row with a
policy id is a policy, and the first row of each client id that carries client details is the
client (the 46 trailing rows with blank policy columns are clients only). Statements name no
carrier, so the carrier comes from the source name. The enrollment export is canonicalized too,
but only to cross-check birth dates against the CRM; it loads no table of its own.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from agency_schema.enums import EligibilityReason
from agency_schema.formats import parse_date_loose
from agency_schema.lineage import Lineage
from agency_schema.models import TABLE_MODELS
from intake.config import CARRIED_FIELDS, LIST_SEPARATOR, RTS_TRUE_VALUES
from intake.exceptions.pii import FreeText
from intake.mapping.enums import ENUM_OPTIONS, normalize_column
from intake.mapping.headers import MappingResult, mapping_key
from intake.mapping.jev_mapping import Asker
from intake.mapping.synonyms import Target
from intake.normalize import NotMoney, parse_money, split_list
from intake.readers import LINEAGE_COLUMN, RawTable, raw_hash

FIELDS = {t: [f for f in m.model_fields if f != "lineage"] for t, m in TABLE_MODELS.items()}
DATES = frozenset({"dob", "effective_date", "termination_date", "end_date", "member_dob"})
DATES |= {"paid_date"}
MONEY = frozenset({"monthly_premium", "amount"})
FLAGS = frozenset({"appointed", "certified"})
RAW_KEPT = ("status", "line_of_business", "state")  # judged on the source's own wording
FALSE_VALUES = frozenset({"false", "no", "n", "0"})
CLIENT_DETAIL = ("first_name", "last_name", "dob", "address_line1", "city", "state", "zip")
NOTES = "notes"
_PERIOD = re.compile(r"(\d{4})-(\d{1,2})")


@dataclass(frozen=True)
class MappedSource:
    table: RawTable
    result: MappingResult

    @property
    def key(self) -> str:
        return mapping_key(self.table.source, self.table.sheet)

    def targets(self) -> dict[str, Target]:
        """header -> canonical field, for headers mapped to a field and present in the file."""
        return {
            e.header: Target(e.table, e.field)
            for e in self.result.mapping.entries
            if e.table and e.field and e.header in self.table.frame.columns
        }


@dataclass(frozen=True)
class Canonical:
    tables: dict[str, pl.DataFrame]  # canonical tables the drop supplies, in model order
    enrollment: pl.DataFrame | None  # enrollment rows by field, for the CRM cross-check
    notes: list[FreeText]  # every non-blank notes cell, for the PII gate


def statement_carrier(source: str) -> str:
    """statement_summit_health_plans -> "Summit Health Plans": statements name no carrier."""
    return source.removeprefix("statement_").replace("_", " ").title()


def split_name(value: str) -> tuple[str | None, str | None]:
    """ "Lee, Ann" or "Ann Lee" -> ("Ann", "Lee")."""
    if "," in value:
        last, first = (part.strip() or None for part in value.split(",", 1))
        return first, last
    parts = value.split(None, 1)
    return (parts[0] if parts else None), (parts[1].strip() if len(parts) > 1 else None)


def period(value: str) -> str:
    """'2026-8' or any date inside the month -> '2026-08'; anything else as read."""
    text = value.strip()
    if match := _PERIOD.fullmatch(text):
        if 1 <= int(match[2]) <= 12:
            return f"{int(match[1]):04d}-{int(match[2]):02d}"
    parsed = parse_date_loose(text)
    return f"{parsed.year:04d}-{parsed.month:02d}" if parsed else value


def clean_value(field: str, value: str | None) -> str | None:
    """One cell, normalized only where its meaning is certain; else exactly as read."""
    if value is None or not value.strip():
        return None
    text = value.strip()
    if field in DATES:
        parsed = parse_date_loose(text)
        return parsed.isoformat() if parsed else value
    if field in MONEY:
        try:
            amount = parse_money(text)
        except NotMoney:
            return value
        return None if amount is None else str(amount)
    if field in FLAGS:
        flag = text.casefold()
        return "true" if flag in RTS_TRUE_VALUES else "false" if flag in FALSE_VALUES else value
    if field == "license_states":
        return LIST_SEPARATOR.join(split_list(text))
    if field == "statement_period":
        return period(text)
    if field == "eligibility_reason" and text.upper() in set(EligibilityReason):
        return text.upper()
    return text if field in ("line_no", "plan_year", "npn", "writing_agent_npn") else value


def _columns(source: MappedSource, table: str, asker: Asker) -> dict[str, list[str | None]]:
    frame = source.table.frame
    targets = source.targets()
    by_field = {t.field: h for h, t in targets.items() if t.table == table}
    for carried, origin in CARRIED_FIELDS.items():
        to_table, to_field = carried.split(".")
        from_target = Target(*origin.split("."))
        header = next((h for h, t in targets.items() if t == from_target), None)
        if to_table == table and to_field not in by_field and header is not None:
            by_field[to_field] = header
    cols: dict[str, list[str | None]] = {}
    for field, header in by_field.items():
        raw = frame[header]
        target = Target(table, field)
        if target in ENUM_OPTIONS:
            normalized, _ = normalize_column(raw, target, asker)  # PR 7's exact requests
            cols[field] = [None if v is None or not v.strip() else v.strip() for v in normalized]
            if field in RAW_KEPT:
                cols[f"{field}_raw"] = raw.to_list()
        else:
            cols[field] = [clean_value(field, v) for v in raw.to_list()]
    if "full_name" in cols:
        names = [split_name(v) if v else (None, None) for v in cols.pop("full_name")]
        cols.setdefault("first_name", [n[0] for n in names])
        cols.setdefault("last_name", [n[1] for n in names])
    if table == "commission_lines" and "carrier" not in cols:
        cols["carrier"] = [statement_carrier(source.table.source)] * frame.height
    return cols


def _frame(source: MappedSource, tables: Sequence[str], asker: Asker) -> pl.DataFrame:
    """One canonical frame from the fields of `tables` this source supplies (enrollment: two)."""
    cols: dict[str, list[str | None]] = {}
    for table in tables:
        cols |= {f: v for f, v in _columns(source, table, asker).items() if f not in cols}
    height = source.table.frame.height
    fields = [f for t in tables for f in FIELDS[t]]
    data = {f: cols.get(f, [None] * height) for f in dict.fromkeys(fields)}
    data |= {c: v for c, v in cols.items() if c.endswith("_raw")}
    version = pl.lit(source.result.version).alias("mapping_version")
    lineage = source.table.frame.select(pl.col(LINEAGE_COLUMN).struct.with_fields(version))
    return pl.DataFrame(data, schema=dict.fromkeys(data, pl.String)).hstack(lineage)


def _clients(frame: pl.DataFrame) -> pl.DataFrame:
    """The first row of each client id that carries client details (orphan rows carry none)."""
    has_detail = pl.any_horizontal(pl.col(c).is_not_null() for c in CLIENT_DETAIL)
    rows = frame.filter(pl.col("client_id").is_not_null() & has_detail)
    return rows.unique("client_id", keep="first", maintain_order=True)


def households(clients: pl.DataFrame) -> pl.DataFrame:
    """One household per household_id, from its clients in file order; first is primary."""
    rows = clients.filter(pl.col("household_id").is_not_null())
    grouped = rows.group_by("household_id", maintain_order=True).agg(
        pl.col("client_id").first().alias("primary_client_id"),
        pl.col("client_id").str.join(LIST_SEPARATOR).alias("members"),
        pl.col(LINEAGE_COLUMN).first(),
    )
    return grouped.select("household_id", "primary_client_id", "members", LINEAGE_COLUMN)


def _notes(source: MappedSource) -> list[FreeText]:
    header = next((h for h, t in source.targets().items() if t.field == NOTES), None)
    if header is None:
        return []
    frame = source.table.frame
    return [
        FreeText(field=NOTES, text=text, lineage=Lineage(**lin))
        for text, lin in zip(frame[header].to_list(), frame[LINEAGE_COLUMN].to_list(), strict=True)
        if text and text.strip()
    ]


def canonicalize(sources: Sequence[MappedSource], asker: Asker) -> Canonical:
    parts: dict[str, list[pl.DataFrame]] = {}
    enrollment: list[pl.DataFrame] = []
    notes: list[FreeText] = []
    for source in sources:
        fed = sorted({t.table for t in source.targets().values()})
        notes += _notes(source)
        if source.key == "enrollment":
            enrollment.append(_frame(source, fed, asker))
            continue
        for table in fed:
            frame = _frame(source, [table], asker)
            if table == "policies":
                frame = frame.filter(pl.col("policy_id").is_not_null())
            elif table == "clients":
                frame = _clients(frame)
            parts.setdefault(table, []).append(frame)
    built = {name: pl.concat(frames, how="diagonal") for name, frames in parts.items()}
    if "clients" in built:
        built["households"] = households(built["clients"])
    tables = {name: built[name] for name in TABLE_MODELS if name in built}
    joined = pl.concat(enrollment, how="diagonal") if enrollment else None
    return Canonical(tables, joined, notes)


@dataclass(frozen=True)
class EnrollmentCheck:
    """Enrollment birth dates against the CRM client of the same policy (#62)."""

    compared: int  # enrollment rows whose policy is in the CRM and both dates read
    agree: int
    disagree: tuple[str, ...]  # policy ids whose enrollment birth date differs from the CRM's
    unreadable: int  # enrollment birth dates parse_date_loose cannot read


def check_enrollment(
    enrollment: pl.DataFrame | None, tables: Mapping[str, pl.DataFrame]
) -> EnrollmentCheck | None:
    """No catalog rule covers an enrollment vs CRM disagreement, so it is counted, not raised."""
    if enrollment is None or "policies" not in tables or "clients" not in tables:
        return None
    if not {"policy_id", "dob"} <= set(enrollment.columns):
        return None
    crm = (
        tables["policies"]
        .select("policy_id", "client_id")
        .unique("policy_id", keep="first")
        .join(tables["clients"].select("client_id", crm_dob="dob"), on="client_id", how="left")
    )
    rows = enrollment.select("policy_id", "dob").join(crm, on="policy_id", how="inner")
    compared = agree = unreadable = 0
    disagree: list[str] = []
    for pid, dob, crm_dob in rows.select("policy_id", "dob", "crm_dob").iter_rows():
        ours, theirs = parse_date_loose(dob or ""), parse_date_loose(crm_dob or "")
        if dob and ours is None:
            unreadable += 1
        if ours is None or theirs is None:
            continue
        compared += 1
        if ours == theirs:
            agree += 1
        else:
            disagree.append(pid)
    return EnrollmentCheck(compared, agree, tuple(sorted(disagree)), unreadable)


def frame_from_rows(
    source_file: str,
    rows: Sequence[Mapping[str, Any]],
    *,
    sheet: str | None = None,
    run_id: str = "test-run",
    mapping_version: str = "test",
    first_row: int = 2,
) -> pl.DataFrame:
    """A small canonical frame in the pipeline's shape, for tests: text cells plus lineage.

    Row numbers start at first_row (row 1 is the header). raw_hash uses the readers' recipe.
    """
    header = list(dict.fromkeys(key for row in rows for key in row))
    cells = [[_text(row.get(h)) for h in header] for row in rows]
    lineage = pl.DataFrame(
        {
            "source_file": [source_file] * len(rows),
            "sheet": [sheet] * len(rows),
            "row_number": list(range(first_row, len(rows) + first_row)),
            "raw_hash": [raw_hash(c) for c in cells],
            "run_id": [run_id] * len(rows),
            "mapping_version": [mapping_version] * len(rows),
        },
        schema={"source_file": pl.String, "sheet": pl.String, "row_number": pl.Int64}
        | dict.fromkeys(("raw_hash", "run_id", "mapping_version"), pl.String),
    )
    data = {h: [c[i] for c in cells] for i, h in enumerate(header)}
    frame = pl.DataFrame(data, schema=dict.fromkeys(header, pl.String))
    return frame.with_columns(lineage.to_struct(LINEAGE_COLUMN))


def _text(value: Any) -> str | None:
    return None if value is None or str(value) == "" else str(value)

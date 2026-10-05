"""DUP rules: exact duplicate rows, name plus DOB collisions, and duplicate policy ids."""

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import normalize_name, parse_date_loose
from agency_schema.registry import rule
from intake.checks._records import record


@rule("DUP-001", Severity.WARNING, Family.DUP, "Exact duplicate row")
def exact_duplicate_rows(frame: pl.DataFrame) -> list[ExceptionRecord]:
    """Flag every later row whose raw_hash equals an earlier row's in the same source."""
    first = frame.group_by("_hash").agg(
        pl.col("_rec").min().alias("_first_rec"),
        pl.col("_row").sort_by("_rec").first().alias("_first"),
    )
    later = frame.join(first, on="_hash").filter(pl.col("_rec") > pl.col("_first_rec"))
    return [
        record(
            "DUP-001",
            Severity.WARNING,
            row,
            f"Row {row['_row']} duplicates row {row['_first']}",
            "Drop one",
        )
        for row in later.sort("_rec").iter_rows(named=True)
    ]


@rule(
    "DUP-002",
    Severity.WARNING,
    Family.DUP,
    "Same normalized name and DOB on two or more clients (exact after normalization; fuzzy "
    "identity matching belongs to bob-resolve)",
)
def name_dob_collisions(clients: pl.DataFrame) -> list[ExceptionRecord]:
    """Flag every client in a group of two or more distinct client ids sharing a person key.

    The group id is the group's first client id, so bob-resolve can pick the group up later.
    Only the clients table is compared: a commission line naming its own client is expected.
    """
    rows = [
        r
        for r in clients.sort("_rec").iter_rows(named=True)
        if all(r.get(c) for c in ("first_name", "last_name", "dob", "client_id"))
    ]
    groups: dict[tuple[str, str, str], list[dict[str, object]]] = {}
    for r in rows:
        born = parse_date_loose(r["dob"])
        dob = born.isoformat() if born else r["dob"].strip()
        key = (normalize_name(r["first_name"]), normalize_name(r["last_name"]), dob)
        groups.setdefault(key, []).append(r)
    out: list[tuple[int, ExceptionRecord]] = []
    for members in groups.values():
        ids = sorted({str(m["client_id"]).strip() for m in members})
        if len(ids) < 2:
            continue
        out += [
            (
                int(str(m["_rec"])),
                record(
                    "DUP-002",
                    Severity.WARNING,
                    m,
                    f"Possible duplicate person (group {ids[0]})",
                    "Resolve (handled fully in bob-resolve)",
                ),
            )
            for m in members
        ]
    return [r for _, r in sorted(out, key=lambda pair: pair[0])]


@rule("DUP-003", Severity.ERROR, Family.DUP, "Duplicate policy ID with different content")
def duplicate_policy_ids(policies: pl.DataFrame) -> list[ExceptionRecord]:
    """Flag rows whose policy_id repeats with content that differs from its first row."""
    keyed = policies.with_columns(pl.col("policy_id").str.strip_chars().alias("_pid"))
    stats = keyed.group_by("_pid").agg(
        pl.col("_hash").sort_by("_rec").first().alias("_first_hash"), pl.len().alias("_n")
    )
    hits = keyed.join(stats, on="_pid").filter(
        pl.col("_pid").is_not_null()
        & (pl.col("_n") > 1)
        & (pl.col("_hash") != pl.col("_first_hash"))
    )
    return [
        record(
            "DUP-003",
            Severity.ERROR,
            row,
            f"{row['_pid']} appears {row['_n']} times",
            "Keep the correct row",
            field="policy_id",
        )
        for row in hits.sort("_rec").iter_rows(named=True)
    ]

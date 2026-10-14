"""REF rules: policies pointing at a client the book does not have, or at the wrong one.

Orphan commission lines are TIE-002 (PR 10) and unknown writing agents are NPN-002 (PR 8).
REF-001 finds a policy whose client is missing; REF-002 finds a policy whose carrier names
a different client the book does have.
"""

import re
from collections.abc import Iterable
from datetime import date
from typing import TYPE_CHECKING, Any

import polars as pl

from agency_schema.enums import Family, Severity
from agency_schema.exceptions import ExceptionRecord
from agency_schema.formats import parse_date_loose
from agency_schema.registry import rule
from intake.checks._records import record, with_lineage
from intake.exceptions.policy import CATALOG_FIXES

if TYPE_CHECKING:
    from intake.tieout.link_evidence import LinkEvidence

STRONG_KEYS = frozenset({"MEMBER_ID", "POLICY_REF"})
Where = tuple[str, str | None, int]  # source_file, sheet, row_number
Person = tuple[str, date]  # name key, date of birth


@rule("REF-001", Severity.ERROR, Family.REF, "Policy references unknown client")
def orphan_policies(view: pl.DataFrame) -> list[ExceptionRecord]:
    """Anti-join of policies to clients, on the trimmed client id. Reads the policy view."""
    return [
        record(
            "REF-001",
            Severity.ERROR,
            row,
            f"{row['_pid'] or 'A policy'} has no client",
            "Add client or fix client_id",
            field="client_id",
        )
        for row in view.filter(~pl.col("_client_found"))
        .with_columns(pl.col("policy_id").str.strip_chars().alias("_pid"))
        .sort("_rec")
        .iter_rows(named=True)
    ]


def _name_key(full_name: str | None) -> str | None:
    """Lower case letters only, as name_key in tieout/sql/01_match_keys.sql. Empty is no key."""
    key = re.sub("[^a-z]", "", (full_name or "").lower())
    return key or None


def _person(full_name: str | None, dob: Any) -> Person | None:
    key = _name_key(full_name)
    born = parse_date_loose(dob) if isinstance(dob, str) else None
    return (key, born) if key and born else None


def _where(row: dict[str, Any]) -> Where:
    return row["_file"], row["_sheet"], row["_row"]


def _text(value: Any) -> str:
    return str(value or "").strip()


def _client_people(clients: pl.DataFrame) -> tuple[dict[str, set[Person]], dict[str, set[str]]]:
    """Each trimmed client id with every person its rows name, and its last name keys.

    A blank first or last name is no person, as in the SQL, where a NULL part makes the whole
    name NULL. Client ids are trimmed here while the SQL's book_people joins them untrimmed;
    that only matters for an id with stray spaces, and then this side errs toward a match.
    """
    people: dict[str, set[Person]] = {}
    surnames: dict[str, set[str]] = {}
    for r in clients.iter_rows(named=True):
        cid = _text(r.get("client_id"))
        if not cid:
            continue
        found = people.setdefault(cid, set())
        if r.get("first_name") is not None and r.get("last_name") is not None:
            person = _person(f"{r['first_name']} {r['last_name']}", r.get("dob"))
            if person:
                found.add(person)
        if last := _name_key(r.get("last_name")):
            surnames.setdefault(cid, set()).add(last)
    return people, surnames


def _copies(policies: dict[Where, dict[str, Any]]) -> dict[tuple[str, str, str], list[Where]]:
    """CRM rows by trimmed (carrier, policy_id, client_id), in file order.

    The tie-out links only the first copy of a carrier's policy, so an exact copy (DUP-001)
    gets no link of its own; it must share the flag or it reaches clean/ misfiled.
    """
    out: dict[tuple[str, str, str], list[Where]] = {}
    for where, r in sorted(policies.items(), key=lambda item: item[1]["_rec"]):
        key = (_text(r.get("carrier")), _text(r.get("policy_id")), _text(r.get("client_id")))
        out.setdefault(key, []).append(where)
    return out


def misfiled_policies(
    tables: dict[str, pl.DataFrame], links: Iterable["LinkEvidence"]
) -> list[ExceptionRecord]:
    """REF-002: one record per policy, on its CRM row, when its carrier names another client.

    It needs the tie-out's links, so it runs after the tie-out and registers in
    intake/rules/catalog.py, like the TIE rules.

    Evidence is a statement line, in any link state, whose only strong candidate is the policy
    and matched it by both member ID and policy number (one key alone could be a keying slip).
    A misfiled line is usually held ambiguous (conflicting_name_dob), so confirmed-only would
    never fire. The line's name and DOB must not be the filed client's and must be exactly one
    other client's, across the whole client list. Silent when: the filed client row is missing
    (REF-001) or has no readable name and DOB, the person matches nobody (a typo or nickname)
    or two or more clients, or the policy's lines disagree (some name the filed client, or
    they name different clients).
    """
    if not {"policies", "clients", "commission_lines"} <= tables.keys():
        return []
    policies = {
        _where(r): r for r in with_lineage("policies", tables["policies"]).iter_rows(named=True)
    }
    lines = {
        _where(r): r
        for r in with_lineage("commission_lines", tables["commission_lines"]).iter_rows(named=True)
    }
    owners: dict[Person, set[str]] = {}
    people, surnames = _client_people(tables["clients"])
    for cid, persons in people.items():
        for person in persons:
            owners.setdefault(person, set()).add(cid)

    named: dict[Where, list[str | None]] = {}  # policy row -> other client per line (None: A)
    for link in links:
        strong = [c for c in link.candidates if STRONG_KEYS & set(c.methods)]
        if len(strong) != 1 or not STRONG_KEYS <= set(strong[0].methods):
            continue
        lin = strong[0].lineage
        policy = policies.get((lin.source_file, lin.sheet, lin.row_number))
        line = lines.get((link.lineage.source_file, link.lineage.sheet, link.lineage.row_number))
        if policy is None or line is None:
            continue
        filed = _text(policy.get("client_id"))
        # An orphan (REF-001 reports it) or a filed client with no readable name and DOB:
        # without a known person, a line cannot be said to name someone else.
        if not people.get(filed):
            continue
        said = _person(line.get("member_name"), line.get("member_dob"))
        if said is None:
            continue
        if said in people[filed]:
            named.setdefault(_where(policy), []).append(None)
            continue
        others = owners.get(said, set()) - {filed}
        if len(others) == 1:  # zero (typo, nickname) or several (shared name) prove nothing
            named.setdefault(_where(policy), []).append(next(iter(others)))

    copies = _copies(policies)
    flagged: dict[Where, str] = {}  # CRM row -> message; one record per row
    for where, owners_named in named.items():
        if None in owners_named or len(set(owners_named)) != 1:
            continue
        row, other = policies[where], str(owners_named[0])  # never None here
        filed = _text(row.get("client_id"))
        n = len(owners_named)
        lines_text = "1 carrier statement line" if n == 1 else f"{n} carrier statement lines"
        message = (
            f"Policy {_text(row['policy_id'])} is filed under client {filed}, but {lines_text} "
            f"matched by member ID and policy number name client {other}"
        )
        if surnames.get(filed, set()) & surnames.get(other, set()):
            message += (
                ". They share a last name, so this may be a household member listed as the "
                "subscriber"
            )
        key = (_text(row.get("carrier")), _text(row.get("policy_id")), filed)
        for copy in copies.get(key, [where]):
            flagged.setdefault(copy, message)
    return [
        record("REF-002", Severity.ERROR, policies[w], m, CATALOG_FIXES["REF-002"], "client_id")
        for w, m in sorted(flagged.items(), key=lambda item: policies[item[0]]["_rec"])
    ]

# ADR 0001: DuckDB SQL for the three-way tie-out

- Status: Accepted
- Date: 2026-10-04

## Context

The tie-out proves that three sources agree: the book of business, the carrier commission statements, and the CRM. A tie-out is a line-by-line match of what should have been paid against what was paid, with every dollar difference explained. The person who checks it is often a finance or M&A analyst, not a Python developer.

The Deployment Specialist and M&A Analyst job descriptions both ask for SQL. Matching rows across sources, finding the ones with no partner, and adding up totals by carrier and agent are exactly what SQL reads best at.

Options considered:

1. Python only, with polars. Polars is a fast table library for Python. It works, but the matching logic would be spread across Python functions that an analyst cannot easily read.
2. A database server such as Postgres. It needs a running server, a password, and setup on every machine and in CI.
3. DuckDB. DuckDB is a database that runs inside the Python process, with no server to install. It reads polars tables directly and speaks standard SQL.

## Decision

The tie-out is written as DuckDB SQL views in `engine/src/intake/tieout/sql/*.sql`. Each file is loaded by name, never pasted into Python as a string, and carries comments, so the SQL files are the documentation of the matching logic. Polars still does reading and row checks. Tolerances (per line 1 percent or 1 dollar, totals 0.5 percent) live in `engine/src/intake/config.py`, not in the SQL.

Money stays exact the whole way. The models store money as an exact decimal to the cent, never a floating-point number, and the SQL must use a matching decimal type (CHANGELOG, PR 1a-i). A floating-point number is the computer's approximate way to store fractions; it can turn 0.10 into 0.1000000001, which is enough to make a tie-out drift.

## Consequences

- An analyst can open one `.sql` file and follow how a statement line is matched to a policy.
- No server, no credentials, nothing extra in CI. DuckDB installs with `uv sync`.
- Two query styles live in one engine (polars and SQL). The boundary is fixed: SQL only for the tie-out.
- A check that did not run is reported as "not run" with a reason, never as zero (CHANGELOG, PR 1b). The SQL must keep that difference.
- The tie-out itself is not built yet. It lands in PR 10. The output files it writes, and the dashboard page that reads them, already exist (PR 1b and PR 15).

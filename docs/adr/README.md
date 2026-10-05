# Architecture decision records

An architecture decision record (ADR) is a short note that says what we decided, why, and what it costs us. Each one is written once and kept, so a reader can see why the project looks the way it does without asking.

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-duckdb-for-reconciliation.md) | DuckDB SQL for the three-way tie-out | Accepted |
| [0002](0002-jev-as-a-gate-not-a-judge.md) | Jev is a gate, not a judge: rules decide | Accepted |
| [0003](0003-static-first-dashboard.md) | Static-first dashboard | Accepted |
| [0004](0004-synthetic-data-only.md) | Synthetic data only | Accepted |
| [0005](0005-separate-repos-per-project.md) | Separate repos per project, shared code extracted later | Accepted |

A new decision gets a new number. An old ADR is never rewritten; if a decision changes, a new ADR replaces it and the old one is marked "Superseded".

When a decision stays but the facts around it move, the ADR gains a dated "Update" section at the end. The original text above it is not changed.

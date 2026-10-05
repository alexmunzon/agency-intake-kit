# agency-intake-kit v1.0.0 release notes

Draft for v1.0.0. The tag is created only after Alex approves it and the final review sweeps are done.

## In one paragraph

agency-intake-kit takes the files a newly acquired insurance agency hands over (a CRM export, an enrollment export, carrier commission statements, and an agent roster) and, in one command, answers three questions: can this book go live, does the money agree, and was every policy sold by an agent allowed to sell it. It reads the files as they come, maps their columns to one standard format, checks every row against 46 named rules, reconciles the money three ways, and shows what to fix first on a dashboard and in a one-page report. Every record in the repo is synthetic.

## Scorecard (synthetic)

Measured on the committed demo run of the synthetic agency (seed 42), in `dashboard/public/demo-run/scorecard.json`:

- **All 717 planted mistakes found across 22 scored mistake types**, recall 1.00 for every type. Recall is the share of planted mistakes found.
- **0 false alarms on 11,234 clean rows** (printed by `npm run demo`). A false alarm is a problem raised on a row with no planted mistake.
- Status passed with warnings: 14,879 rows read, 12,836 clean, 0 blockers, 308 errors, 423 warnings, 13 info.
- The tie-out matched 6,400 book policies, 6,520 statement lines, and 2,177 CRM statuses, and explained $5,085.55 in differences across 239 items.
- Both "must block" examples block: a CRM file cut to 2,574 of 2,680 rows fails on CMP-001 before any model call, and a roster with an SSN column fails on SSN-001 with none of the 25 values in any output file.
- The end-to-end test fails if recall drops below 0.95 for any type or false alarms rise above 0.5 percent, so these numbers cannot quietly go stale.

These are synthetic results. Real agency files will hold mistakes the generator does not make.

## Jev cost

Jev is TypeSafe's decision model; it answers small yes-or-no and pick-one questions, only where rules run out, and never overrides a rule. Every answer the demo needs is recorded in the repo: 7 mapping answers ($0.000136) and 164 triage answers ($0.002961), about $0.003 in total, with the $0.50 spend cap never reached. A replay run, the default, costs $0 and needs no key.

## What shipped, by pull request

| PR | What it added |
|---|---|
| SPEC (#1) | The contract: outcome, six examples that became tests, the PR plan |
| 1a-i, 1a-ii, 1b (#2 to #4) | The standard data models, format checks, and the run output files the dashboard reads |
| 2, 3a, 3b (#5, #8, #33) | The synthetic agency: a clean world, 877 planted mistakes with an answer key, and four messy source files |
| 4 (#38) | Readers for messy CSV and spreadsheet files, plus the SSN and row-count gates |
| 5, 7 (#40, #64) | Column mapping by dictionary, then Jev, then a person; messy values to standard words |
| 6 (#6) | The Jev client: replay, off, live, and record modes, retries, and the $0.50 spend cap |
| 8, 9 (#30, #31) | The row rules and the cross-record checks (duplicates, broken references, ready-to-sell, licenses) |
| 10 (#32) | The three-way money tie-out in DuckDB SQL, exact to the cent |
| 11 (#36) | Exception policy, Jev triage, and the personal-details filter for notes |
| 12 (#72) | One command runs everything, writes the run folder and report, and the end-to-end tests |
| 13 to 16 (#7, #9, #10, #68) | The dashboard: Overview, Sources, Exceptions, Tie-out, Agents, Runs, dark mode, accessibility checks |
| 17 (#67) | The header mapping benchmark: dictionary alone, then Jev, then Sonnet |
| 18a, 18 (#21, this PR) | Decision records, README, screenshots, demo GIF, these notes |
| Review fixes (#34, #35, #46, #65, #66, #69, #70, #71) | Fixes from code reviews and the first sweep, and the real recorded Jev answers |

Full detail per PR is in [CHANGELOG.md](../CHANGELOG.md).

## Known issues and limits

- Synthetic data and one agency shape. The readers know these four file layouts only.
- A state written as "Tex." is held out of the load files even though Jev reads it as TX, because the address rule judges the value as written. This is on purpose; a person decides.
- Birth dates that differ between the enrollment export and the CRM are counted and printed, but no catalog rule raises them yet (all 1,838 compared agree in the demo).
- The build guide still names the old CLI flags `--now` and `--run-id`; they do not exist. SPEC and `intake run --help` are correct.
- Open GitHub issue #19: the dashboard repeats a few small helpers across pages, plus some dead code. Cleanup only; no wrong numbers.

## What comes next: bob-resolve

bob-resolve is the next project in the series. It matches the same person across agency files when there is no SSN to join on: one golden record per person, households grouped, every merge explained, and a benchmark of rules alone against rules plus Jev against rules plus Jev plus a reasoning model. It starts by moving the shared code from this repo (the data models, the synthetic generator, and the Jev client) into a shared package, `agency-data-commons`. [ADR 0005](adr/0005-separate-repos-per-project.md) lists what must be cut first.

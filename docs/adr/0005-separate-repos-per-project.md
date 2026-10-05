# ADR 0005: Separate repos per project, shared code extracted later

- Status: Accepted
- Date: 2026-10-04

## Context

This kit is one of three projects in the Agency Data Trust Series (ROADMAP.md, section 4). The others are bob-resolve (matching the same person across files without an SSN) and plan-diff (comparing plan documents across carriers). All three need the same building blocks: the canonical schema (`agency_schema`), the synthetic data generator (`synth_agency_data`), and the Jev client (`jev_client`).

Options considered:

1. **One repo for all three (a monorepo).** Sharing is easy, but each project is harder to read on its own, and a reader scanning one problem has to wade through the others.
2. **A shared package first, then the projects.** Clean on paper, but it means designing shared code before any project has proven what it needs.
3. **Separate repos, shared code born in the first one and extracted later.**

## Decision

Option 3. Each project is its own GitHub repo with its own README, SPEC, CHANGELOG, and live dashboard. agency-intake-kit is built first and holds the first copy of the shared packages. Once bob-resolve and plan-diff show which parts are truly shared, those parts move into a fourth repo, `agency-data-commons`, and the three projects depend on it.

Rules that keep extraction cheap:

- Each shared package lives in its own folder under `engine/src/` and should not import from `intake`. One known exception today: `jev_client` reads its model name, price, and limits from `intake/config.py` (CHANGELOG, PR 6). Those constants must move into `jev_client` before extraction.
- The exception model (`ExceptionRecord`), lineage, and rule registry live in `agency_schema`, not in this kit's pipeline code.
- The README standard, CLAUDE.md template, `npm run verify` command, and Stop hook are the same in every repo.

## Consequences

- Each repo reads as one finished project, which is what a hiring manager scans.
- Until extraction, a fix to a shared package must be copied by hand. The CHANGELOG records each shared-package change so nothing is missed.
- Extraction is a later, separate piece of work. Nothing in this repo depends on `agency-data-commons` yet.
- The generator already plants defects meant for bob-resolve (name typos, nicknames, swapped birth dates). This kit does not score them (SPEC, "Out of scope").

## Update 2026-10-05

The original text above is kept as written. What changed since, and what bob-resolve's extraction (its PR 0) must cut:

- `jev_client` still imports from this repo's pipeline: `client.py` reads `JEV_API_URL`, `JEV_BUDGET_USD`, `JEV_MAX_TRIES`, `JEV_TIMEOUT_S`, and `JEV_BACKOFF_BASE_S` from `intake/config.py`; `types.py` reads `JEV_MODEL`; `cost.py` reads `JEV_USD_PER_MTOK_IN`. These must move into `jev_client` (or be passed in) before extraction.
- `jev_client/client.py` sets `DEFAULT_CASSETTE_DIR` to this repo's `engine/tests/cassettes` by file path. The extracted package must take the cassette folder as an argument instead. This repo then passes `engine/tests/cassettes/mapping` and `engine/tests/cassettes/run`, as `intake/run/jev.py` already does.
- The pipeline's own run wrapper (`intake/run/jev.py`, one client and one budget per run, "not recorded" answers go to a person) stays in this repo. It is pipeline code, not shared code.

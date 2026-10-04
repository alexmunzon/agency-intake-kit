# Changelog

One entry per PR.

## PR 0: Scaffold (2026-10-04)

- Repo layout per BUILD-GUIDE section 1.3. No feature code yet.
- Engine: Python 3.12 with uv. Four packages (agency_schema, synth_agency_data, jev_client, intake), ruff, mypy strict, pytest. Console scripts `intake` and `synth` with a placeholder `version` command.
- Dashboard: Next.js 16 (App Router, TypeScript, Tailwind), shadcn/ui, vitest, Playwright config.
- Root `npm run verify` runs every check. CI runs it on every push and PR.
- `.claude/settings.json` permissions and a Stop hook that runs verify before Claude can end a turn with uncommitted changes.
- Change from the build guide: Node is pinned to 24, not 20. Node 20 reached end of life on 2026-04-30.
- `typecheck` runs `next typegen` first, because Next 16 generates some page types at build time.

## SPEC: the contract for every PR (2026-10-04)

- SPEC.md written from the SPEC interview. It now overrides the build guide where they disagree.
- PR plan gains "Lane" and "Needs merged first" columns for running lanes in parallel.
- PR 1 splits into 1a (models) and 1b (sample runs that act as the engine-to-dashboard contract).
- PR 3 splits into 3a (defects, planted example records, a canonical-shape copy) and 3b (source files), so rule PRs can start before readers and mapping exist.
- New run output `rts_coverage.json` feeds the Agents page RTS matrix (the guide had no data source for it). `intake/config.py` skeleton moves to PR 1a so lanes don't both create it. PR 11 records the triage and PII cassettes.
- Second review: triage and PII cassettes recorded in PR 12 against real pipeline requests; PR 11 deduplicates triage calls and states the expected call count; ground truth uses stable record keys; PR 13 copies the sample run into dashboard/public/demo-run.
- Jev spend capped at $0.50 per run. Missing an accuracy target in the end-to-end test fails verify.

## PR 1a-i: Canonical models, exception model, registry skeleton (2026-10-04)

- PR 1a split into 1a-i (this PR) and 1a-ii (format functions and the ZIP table), because together they ran about twice the 400-line limit. 1a-ii runs alongside 1b. SPEC.md PR plan updated.
- `agency_schema`: the six table models, closed enums (Carrier stays open text), `Lineage`, `ExceptionRecord`, and `json_schema()`. No field has a default, unknown fields are refused, and Lineage is required on every table.
- Money (`monthly_premium`, `amount`) is an exact decimal to the cent, not a float, so tie-out tolerances do not drift.
- `minimize_value()` is the one shared masking function. ExceptionRecord refuses a `value_minimized` with three digits in a row, and refuses any blocker other than MAP-003, CMP-001, SSN-001.
- Fresh-eyes review fixes: value_minimized must have exactly the masked shape; short values keep at most a third of their characters; SSN-shaped text refused in message and suggested_fix; whole-number and yes/no fields refuse text; blank strings refused where `None` is meant; list fields are tuples.
- `/code-review` fixes: ExceptionRecord carries full `lineage` (SPEC: exceptions.jsonl rows have lineage), matching row_number and raw_hash; spaced SSNs refused in text too; the masked-shape check uses the same "at most a third" rule as minimize_value.
- Rule registry: `@rule`, `catalog()`, `run_rules()`. It applies the same identity checks and refuses duplicate ids.
- `intake/config.py` skeleton with one commented section per PR.
- New enum not named in the guide: `AgentStatus` (ACTIVE, INACTIVE, UNKNOWN) for the agents table.
- Guardrail checks left open by PR 0:
  - Stop hook: it fired but never ran the tests. Hooks run in a bare shell without nvm, so `npm` was not found and every stop with uncommitted changes was blocked regardless of test results. Fixed in `.claude/hooks/stop-verify.sh` (Alex approved): it adds `~/.local/bin` for uv, loads nvm and Node 24 when npm is missing, and blocks with a clear message if npm still cannot be found. Retested live: a deliberately broken test was blocked with the real failure shown.
  - Mid-string ask rule (`Bash(*--jev live*)`): `echo "--jev live"` ran without asking. Either the version matches prefixes only, or auto mode approved it. Protection falls back to `JEV_MODE=replay` in `.env`.

## PR 1a-ii: Format functions and ZIP table (2026-10-04)

- `agency_schema.formats`: MBI, NPN, Medicare plan ID, Medigap letter, and HIOS checks; ZIP prefix to state; phone, email, and name normalizers; `parse_date_loose`. Pure helpers that never raise. Models do not call them; PR 8's rules do.
- Two-digit years pivot at 1930 to 2029 (`05/01/29` is 2029). Excel serials from 20000 to 60000 are dates. Day-first slash dates are refused.
- `data/zip3_state.csv`: 939 rows covering the 50 states, DC, five Pacific territories, PR, VI, and AA, AE, AP. Built from USPS list L002 (2011, the newest readable copy). L002 names sorting facilities, so 32 prefixes were corrected by hand to the state the addresses are in (VA 201 among them). The planned second-source cross-check was dropped because no second list could be read reliably; docs/schema.md says so.
- Tests: Hypothesis for MBI, NPN, Medicare plan IDs, HIOS IDs, and every row of the ZIP table; the guide's invalid cases; every state present.

## PR 1b: Output models and sample-run contract (2026-10-04)

- `agency_schema.outputs`: Manifest, Scorecard, tie-out legs, variances, totals, RTS coverage, and the status enums (RunStatus, LegStatus, TieOutLeg, RtsCellState, JevMode). `RUN_FILE_MODELS` maps each run file to its model. Documented in the new `docs/outputs.md`.
- A tie-out leg that did not run has empty counts, not zeros, so a missing check can never look clean.
- Decisions with Alex: money is text in JSON and the dashboard formats it with one helper; Jev estimated cost keeps six decimals; tie-out variances show the full carrier_member_id; one PR despite running over 400 lines, because the extra is tests and docs.
- `intake schema --json` prints the JSON Schema (serialization mode, the shape of files as written). `intake schema --ts` writes `dashboard/lib/types.ts` with a small built-in generator. `json_schema()` now covers the output files and takes a mode.
- Three sample runs in `fixtures/`: sample-run (PASSED_WITH_WARNINGS, examples 3 and 4), sample-run-failed (CMP-001, all legs NOT_RUN), sample-run-passed. Written through the models with `minimize_value()` and a frozen clock.
- `agency_schema.run_dir.check_run_dir()` validates a whole run directory and checks that its files agree. PR 12 runs it on real output.
- Tests: every sample passes `check_run_dir` and round-trips byte for byte; all statuses and severities appear; each model rule refuses a file broken in exactly that way; the committed `types.ts` matches the generator.
- Review fixes (fresh-eyes subagent and `/code-review`): a PASSED run cannot have a leg that did not run; each TIE rule is tied to its leg; cross-file checks moved from the test into `check_run_dir`; Jev `off` makes no calls; RTS gaps list one exception per policy; duplicate totals rows and RTS cells refused; totals carry a not_run_reason; variance dollars cannot be negative; recall dropped (computed from detected and planted); sample messages no longer repeat raw values; the TS generator handles literals and non-string enums and refuses unknown shapes.
- Open question for PR 6 and PR 12: what the $0.50 budget guard does to a run (see the PR description).

## PR 2: Synthetic clean world (2026-10-04)

- `synth generate --seed 42 --clients 2000 --out ../fixtures/agency-a` writes six canonical CSVs under `canonical/` plus a `ground_truth.json` with no defects. Same seed, same bytes. Fixtures are committed in PR 3b, not here.
- Seed 42 gives 2,000 clients in 1,400 households, 25 agents (one top, four managers, twenty producers), 2,600 policies (MA 1,430, PDP 390, MEDSUPP 260, ACA 520), 3,740 RTS rows, and 6,651 commission lines for 2026-06 to 2026-08. About 1.4 MB.
- Six fictional carriers only. `rates.py` amounts are illustrative, not CMS maxima. Money is Decimal.
- The clean world is built to raise nothing above info: every value passes the 1a-ii format helpers, ZIPs come from the ZIP table for the client's state, age-based Medicare clients were 65 when their policy started, Medicare starts fall on the 1st, every writing agent is licensed and RTS for what they sold, every active policy is paid once per period at the rate-table amount, and no two clients share a normalized name and birth date.
- Choices to know: the world's "today" is 2026-10-01 (the demo clock). Policies start from 2022 on and each agent sells in two to four states, which keeps the RTS table small. CSVs carry no lineage columns, because SPEC adds lineage when a file is read. List fields are joined with "|".
- CI: `astral-sh/setup-uv` bumped from v6 to v10.2.0 (Alex approved), which runs on Node 24. From v10 on, setup-uv publishes only exact version tags, so a bare `@v10` does not resolve.
- Size: about 690 changed lines against a plan of 380, mostly because the formatter puts one field per line. Alex chose to ship it as one PR.

## PR 6: Jev client (2026-10-04)

- `jev_client`: typed requests and answers for noul, choice, and score; four modes (`replay` default, `off`, `live`, `record`); `off` and a tripped budget return a typed `Unresolved`; a replay miss raises `CassetteMiss` with the request hash.
- Cassettes hold the request body and response only, never headers, keyed by the public `request_hash` (sorted keys, fixed separators, SHA-256). `record` reuses an existing cassette instead of paying twice.
- Retries on 429 and 529 with doubling waits and jitter, 5 tries in all. 401, 422, and other errors raise at once with the body.
- `live` and `record` are refused unless the caller passes `allow_spend=True`.
- Usage per run: calls, tokens, estimated cost (six decimals), budget, and `budget_tripped`. `minimize_state` keeps allowlisted fields and drops notes before PII clearance; the client refuses notes too.
- API shape and price checked on docs.typesafe.ai on 2026-10-04 and written up in the new `docs/jev.md`. Price confirmed at $0.042 per million input tokens. The official `typesafe-sdk` exists but is not wrapped; no new dependency.
- Constants in the `# PR 6` section of `config.py`.
- SPEC change: the spend cap no longer "stops any run". A trip switches Jev to `off` for the rest of the run, the run completes, and remaining questions go to the human queue (decision made before this PR, following guide 7.6). The 1b `JevUsage` model is unchanged.
- SPEC: the 'to be verified' note on the API shape now records what PR 6 checked.

## PR 13: Dashboard shell and Overview (2026-10-04)

- The Overview answers "Can this agency go live?" for one run: a status banner (yes, yes with fixes, or no, with the engine's reason and any file whose row count came up short), tiles for blockers, errors, warnings, info, and clean rows, then tie-out differences in dollars, RTS gaps, Jev calls and estimated cost, and run time. A stacked bar shows exceptions by source file, with the counts written next to each bar.
- A check that did not run shows "Not checked", never 0. On the failed sample that covers errors, warnings, the tie-out, and RTS gaps, because the blocker stopped the run before those checks.
- `lib/money.ts` is the one money helper. It formats decimal text and adds amounts in whole cents with BigInt, so money never becomes a float. A lint rule refuses `parseFloat` anywhere in the dashboard.
- `lib/run-loader.ts` reads a run folder (manifest, scorecard, exceptions, RTS coverage) and checks its basic shape: same run in manifest and scorecard, known severities, money written as text. The page reads `public/demo-run` at build time, so the deployed site is static and makes no network calls.
- `public/demo-run` is a copy of `fixtures/sample-run` until PR 12's `npm run demo` replaces it.
- App shell: title "Agency Intake Kit" with a real description, a left nav at desktop width and a scrolling top bar on phones. Pages not built yet show as "(soon)" instead of links. Fonts: Inter, and the system mono face for ids.
- Dark mode follows the system setting. The manual toggle waits for PR 16.
- `npm run shots` writes `overview-<width>-<theme>.png` to `docs/screenshots` and checks the Overview fits one screen at 1440 by 900.

## PR 3a: Error injectors, planted cases, defected canonical copy (2026-10-04)

- `synth_agency_data/injectors/`: 25 injectors at the guide 7.3 default rates, grouped by what they touch (`clients.py`, `policies.py`, `commissions.py`, `roster.py`). Each is `(world, rng, rate) -> (world, defects)`, copies the rows it changes, and never mutates its input. 20 are scored; name typos, nicknames, DOB transposition, DOB month-day swap, and near-duplicate clients are unscored (`expected_rule_ids: []`, for bob-resolve).
- Every defect has a stable `record_key` (`policy_id`, `client_id`, or carrier plus statement_period plus line_no) and a `row_ref` into the defected CSV (row 1 is the header). A defected record is locked, so no record carries two defects.
- `planted.py`: SPEC example 3 (P-00417 is Harborline, TX, MA, plan year 2026, written by NPN 1884412, no RTS row) and example 4 (Harborline 2026-08 line 212 pays 61.05 to HL-998213, no policy). Supporting edits: producer `32227216` (agent06, Jeffery Wagner) is renamed to `1884412` everywhere and gets a TX license, P-00417 moves to TX client C-00452 (a 65+ PDP-only client), and line 212 is inserted so later lines shift down by one. Random injectors never touch the planted policy, its client, or line 212.
- `synth generate` now injects by default and writes `canonical-defected/` plus a filled `ground_truth.json`. `--no-inject` writes the clean world to `canonical/` with no defects. Planting needs seed 42 at 2,000 clients and says so if the world is too small.
- Committed `fixtures/agency-a/canonical-defected/` and `fixtures/agency-a/ground_truth.json` (793 defects, about 1.7 MB). A test regenerates them and fails if the bytes drift.
- PII in notes is left to PR 3b, which writes the CRM `Notes` column.
- Size: about 1,350 changed lines against a plan of 340, not counting fixture data. Shipped as one PR on the orchestrator's instruction.

## PR 10: Three-way tie-out in DuckDB (2026-10-04)

- `intake/tieout/sql/01` to `07`: the tie-out as commented DuckDB views. Lines match the book on carrier plus carrier_member_id, then policy_ref, then name plus DOB (a weak match, TIE-006). Leg A finds active policies with no line in a period (TIE-001), leg B finds orphan payments (TIE-002), leg C finds paid policies the CRM does not show as ACTIVE (TIE-004). Dollar checks: each line vs the rate table within the larger of $1 or 1 percent (TIE-003), carrier and agent totals within 0.5 percent (TIE-005). Money is DECIMAL(12,2) in SQL and Decimal in Python, never a float.
- `load.py` hands polars frames to DuckDB through the Arrow stream interface, so no pyarrow dependency. `views.py` runs the SQL files in name order. `variances.py` builds the six `tie_out/*.json` models and one TIE ExceptionRecord per finding.
- A missing commission or policy source makes every leg and both totals NOT_RUN with a reason and no counts.
- `_canonical_io.py` is a small private canonical CSV reader that PR 4's readers replace.
- `config.py` PR 10 section: `TIE_LINE_TOLERANCE_USD`, `TIE_LINE_TOLERANCE_PCT`, `TIE_TOTAL_TOLERANCE_PCT`.
- On agency-a every planted TIE-001 to TIE-004 defect is found with no extras. The clean world has zero variances and totals tie to the cent. TIE-005 fires on the defected world as expected.

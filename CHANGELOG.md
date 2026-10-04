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

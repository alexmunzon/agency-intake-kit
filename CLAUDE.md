# agency-intake-kit

Agency intake toolkit for the Agency Data Trust Series. Synthetic data only. See ROADMAP.md (why) and SPEC.md (what).

## Commands
- `npm run verify`            all checks: ruff, mypy, pytest, eslint, tsc, vitest, next build. Must pass before any commit.
- `npm run demo`              regenerate the committed demo run into dashboard/public/demo-run (uses Jev replay cassettes).
- `npm run shots`             Playwright screenshots to docs/screenshots at 1440 and 375, light and dark.
- `cd engine && uv run intake run --in ../fixtures/agency-a/drop --out ../runs/agency-a --jev replay --as-of 2026-10-01T09:00:00Z`   the out folder is the run (its name is the run_id); add --overwrite to redo it. ground_truth.json beside drop/ is auto-detected.
- `cd engine && uv run synth generate --seed 42 --clients 2000 --out ../fixtures/agency-a`
- `cd engine && uv run pytest -q tests/unit/test_rules_dob.py -k age`   run one test file or test.

## Invariants (never break these)
- A deterministic verdict is never overridden by Jev or an LLM. Models fill gaps and order queues; rules decide.
- Every output row carries Lineage (source_file, sheet, row_number, raw_hash, run_id, mapping_version).
- Runs are immutable directories. An existing run_id is refused unless --overwrite is passed. Corrections are new rows.
- Raw gates run before any model call: SSN refusal (SSN-001) and completeness (CMP-001, CMP-002) operate on raw frames right after reading.
- Exactly three blockers: MAP-003, CMP-001, SSN-001. Blockers stop clean/ from being written and set FAILED. Errors exclude their rows. Warnings pass with a flag. Info logs only.
- No PHI, no real data, no SSNs. Free text passes the PII gate before any log or model call.
- Thresholds (Jev confidence cutoffs, tie-out tolerances, required fields) live in engine/src/intake/config.py, not inline.
- Jev calls send minimized fields only. Sample values for mapping skip free-text-looking columns and anything matching a 9-digit pattern. Never send notes fields to any model before the PII gate.
- JEV_MODE defaults to replay. live and record spend money and require explicit approval. CI is always replay.
- The exception model is ExceptionRecord in agency_schema. Never name a class Exception.

## Gotchas
- Use uv, not pip. Use polars, not pandas. DuckDB SQL lives in engine/src/intake/tieout/sql/*.sql, loaded by name, never inline strings.
- Readers keep raw values exactly as read. The one exception: cells openpyxl already returns as datetime become ISO strings, because the raw cell was a date. Numeric Excel serials that arrive as text or in CSVs are parsed by the date rules, which accept serials in the 20000 to 60000 range.
- Commission XLSX files have a merged title row and a trailing total row. Header row detection must handle both.
- The CRM export is one row per policy (client fields repeated), so fixtures/agency-a has 2,680 CRM rows, not 2,000: 2,600 policies, 34 planted duplicate rows, and 46 clients with no policy (policy columns blank).
- Hypothesis tests for MBI, NPN, plan IDs are in tests/unit/test_formats.py; extend them when changing formats.
- Dashboard reads JSON from public/demo-run by default; types in dashboard/lib/types.ts are generated from engine JSON schema by `uv run intake schema --ts`. Regenerate after changing output models.
- Docs and UI strings: plain language, no em dashes.
- Node 24 (the guide's Node 20 is end of life). Dashboard is Next 16: read dashboard/AGENTS.md before writing dashboard code.
- The repo path contains a space ("Data intake"). Quote every absolute path in shell commands and scripts.

## Workflow
- One PR per session per worktree. Branch names pr-NN-short-name. Under 400 changed lines.
- Tests first from SPEC examples, then implementation, then `npm run verify`, then show the output.
- Update CHANGELOG.md in every PR.

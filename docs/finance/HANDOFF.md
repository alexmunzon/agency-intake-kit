# Finance durable ledger handoff

Status: local, uncommitted finance work on `finance/durable-ledger-20261007`.
Verified base: Intake `275be53afdc6aecd33ac65defd9c980835127b49`
(`origin/main` verified by Session 1 on 2026-10-07). No commit, push, PR,
merge, or deployment has been performed for this slice.

## Scope ready for integration

- `engine/src/intake/finance_adapter.py`, `finance_store.py`, and `finance_cli.py`
  implement explicit synthetic statement layouts, local immutable receipt storage,
  and a module-scoped CLI. The CLI stages and syncs complete import/export JSON
  before exclusive publication; if post-publication directory syncing fails,
  the complete output may already exist. The existing `revenue.py` and
  `revenue_ledger.py` remain the classification and receipt-decision authority.
- `fixtures/finance-durable/`, `scripts/finance/sample.py`, and
  `dashboard/public/demo-ledger.json` supply repeatable synthetic examples. The
  provenance sidecar pins exact artifact bytes and links each source data row to
  its ledger revision entry. `engine/tests/unit/test_finance_provenance.py` checks
  pins, source hashes, raw row hashes, revision positions, and the public copy.
- `dashboard/lib/finance-ledger.ts`, the `/ledger` page, and their tests provide
  a browser-memory neutral review of an exported ledger. The existing finance
  review helper has a small cents-export change. See `README.md` and
  `test-evidence.txt`.

The finance sidecar borrows Session 1 contract 1.0.0 artifact-pin and provenance
terms. It is deliberately identified as `finance_provenance`, not a client/policy
Packet. Its run ID identifies this synthetic finance run and does not assert an
Intake run, client identity, policy link, human approval, or financial posting.

## Session 7 integration proposal

Session 7 exclusively owns shared CLI registration, shared navigation, final
combined verification, merge, and deployment. Register the finance module as
`from intake.finance_cli import app as finance_app` then
`app.add_typer(finance_app, name="finance-local")`. Add the shared dashboard
navigation link to `/ledger`. Review the exact combined diff and run required
repository gates after integration. Preserve the current user authorization
boundaries for push, PR, merge, and deployment.

The team rule is explicit: Astra coordinates planning, delegation, review, and
integration; explicitly assigned Sol workers implement, debug, write tests, and
verify. Do not assign implementation to Astra workers or silently substitute one.

## Verification state

The provenance sample passed its focused test, Ruff checks, and a two-run
exact-hash comparison across all generated fixture files and the public ledger.
The final focused engine regression run passed 66 tests, including failed-write
and concurrent-publication cases; the focused dashboard run passed 15 tests,
including the landmark structure check. Engine Ruff, formatting, and mypy
checks passed; focused dashboard ESLint passed. Exact logs are in
`test-evidence.txt` where available.
The initial full dashboard attempt had five failures: two
borrowed-install-path assertions and three UI timeouts; `npm ci` has since
installed the 449 locked packages in this worktree. The initial engine wrapper
stopped at an inaccessible default `uv` cache before running its checks. Those
failed attempts remain in the evidence. A final combined full gate is pending
Session 7's slot. No full-green result is claimed.

The local `/ledger` route returned HTTP 200, but desktop rendering, 375px
rendering, and browser console checks are still unverified because the numeric
in-app browser session timed out and subsequent inventories showed only Chrome.

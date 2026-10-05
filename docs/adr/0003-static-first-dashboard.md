# ADR 0003: Static-first dashboard

- Status: Accepted
- Date: 2026-10-04

## Context

The dashboard has two kinds of readers: an agency owner who wants one answer ("can this agency go live?") and a hiring manager who clicks the live link from the README. Both need a page that always works and always shows a full result.

A dashboard backed by a server and a database would need hosting, credentials, auth, and a way to keep data private. The project rules forbid real data and put auth out of scope (SPEC, "Out of scope").

## Decision

The dashboard is a static site. A static site is a set of files built once and served as is, with no server code running when someone visits. It is built with Next.js 16 and deployed on Vercel.

- It reads one committed run folder, `dashboard/public/demo-run`, at build time. It makes no API calls and needs no environment variables.
- Until PR 12 ships, that folder is a copy of the hand-built sample run in `fixtures/sample-run`. After PR 12, `npm run demo` regenerates it from a real engine run with a frozen clock, so the numbers do not change between builds.
- The engine and the dashboard share one contract. The engine's output models generate the dashboard's TypeScript types (`intake schema --ts`), and a test fails if they drift (CHANGELOG, PR 1b).
- Money is text in the JSON and is added in whole cents with one helper, `lib/money.ts`. A lint rule refuses `parseFloat` anywhere in the dashboard (CHANGELOG, PR 13).
- Loading your own run happens in the browser only, with no upload (PR 16, not shipped yet).

The build guide named Node 20. We pinned Node 24 instead, because Node 20 reached end of life on 2026-04-30. Next 16 generates some page types at build time, so `typecheck` runs `next typegen` first (CHANGELOG, PR 0). Next 16 also changed enough that `dashboard/AGENTS.md` must be read before writing dashboard code.

## Consequences

- Every preview and production URL shows a complete, real-looking result. Nothing can go down because a server or database is down.
- No data leaves the visitor's browser, and there is nothing to log in to.
- The deployed site shows one fixed run. Seeing a new run means rebuilding or loading it locally.
- Today the live demo shows a hand-built sample, not engine output. The README says so.

## Update 2026-10-05

The original text above is kept as written. What changed since:

- The live demo now shows real engine output, not the hand-built sample. `npm run demo` runs fixtures/agency-a in replay with a frozen clock (`--as-of 2026-10-01T09:00:00Z`) and copies the dashboard files and `report.html` into `dashboard/public/demo-run` (PR 12). Two runs of the same drop are byte-identical, so screenshots do not churn.
- The CLI flags are `--in`, `--out`, `--jev`, `--as-of`, and `--overwrite`. The `--now` and `--run-id` flags named in the build guide do not exist; the out folder's name is the run id (PR 12).
- The manifest gained `as_of` and `budget_tripped`, and `dashboard/lib/types.ts` was regenerated from the engine's schema, so engine and dashboard still share one contract.
- Loading your own run in the browser, with no upload, shipped in PR 16.

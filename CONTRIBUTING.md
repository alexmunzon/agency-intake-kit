# Contributing

This repository is a frozen, synthetic-data recruiting demo. Keep fixes small and reviewable. The broader [roadmap](ROADMAP.md) is background, not approval to add features or integrate the three demos.

## Setup and verification

Use Node 24, Python 3.12 and uv. From the repository root:

```sh
(cd engine && uv sync --locked)
(cd dashboard && npm ci)
JEV_MODE=replay npm run verify
```

The root package is scripts-only; install dependencies in the two subprojects, not at the root. Both lockfiles are committed. Dashboard builds require development dependencies, including Tailwind. Do not use `npm ci --omit=dev` for a build environment.

`verify` runs engine Ruff lint and formatting, mypy and pytest, then dashboard ESLint, type checking, Vitest and a Next.js production build. Smaller loops are `npm run verify:engine` and `npm run verify:dashboard`; a focused pass does not replace full verification. The committed demo is sufficient for `cd dashboard && npm run dev`.

## Change checklist

- Read [CLAUDE.md](CLAUDE.md), the relevant spec and existing tests. Dashboard changes also require [dashboard/AGENTS.md](dashboard/AGENTS.md) and the installed Next.js documentation.
- Preserve deterministic rule verdicts, source lineage, raw SSN/completeness gates, unavailable states and exact decimal money. [Data trust rules](README.md#data-trust-rules) and [SECURITY.md](SECURITY.md) describe the boundary.
- Use synthetic inputs only. Do not commit client data, PHI, credentials, environment files or local generated runs. See the security checklist before sharing diffs or logs.
- Keep `JEV_MODE=replay` in checks. Live and record model calls require explicit approval; never change mode to make a test pass.
- Add or update tests and a [CHANGELOG.md](CHANGELOG.md) entry. Keep docs in plain language, without em dashes, and qualify benchmark claims.
- Run `git diff --check` and full verification before proposing the change. State exactly which checks passed, failed or were not run. Screenshots and browser checks are separate evidence; do not claim them from unit tests.

## Dependency and CI changes

Update dependencies intentionally, through npm or uv, with the corresponding lockfile. Review version, source and integrity changes rather than running forced audit fixes. Keep the existing Actions permissions read-only and Actions references pinned to full upstream commit SHAs with readable version comments.

Run both npm audit scopes described in [SECURITY.md](SECURITY.md#local-review-checklist). A production-only pass does not remove the known development-tool advisory. Submit one focused PR with purpose, scope, verification evidence and residual risks. Do not merge or deploy as a side effect of preparing a contribution.

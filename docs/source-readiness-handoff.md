# Source readiness handoff

Status: implementation and Sol review fixes complete; focused checks pass. Frozen candidate for Session 7 combined verification. Not yet committed, merged or deployed.

## Orchestration rule from Alex (2026-10-07)

Use Astra as the orchestrator for planning, delegation, reviewing results and integration decisions. Delegate implementation, debugging, test-writing and routine verification to explicitly selected Sol subagents. Do not spawn Astra workers for those tasks. If Sol cannot be selected, tell Alex; never silently substitute Astra or claim Sol is running. Run independent work in parallel with clear deliverables, owned files or isolated branches, dependencies and acceptance tests. Avoid concurrent edits to the same files and reuse completed work.

Follow the shared GYDE roadmap and Session 1’s versioned data contract. Session 7 remains the only merge and deployment owner. Other sessions deliver tested commits and clear handoffs. Verify worker results before accepting them. Distinguish implemented, tested, merged and deployed; report blockers promptly and never claim tests or deployment passed without evidence. Preserve this rule in replacement-session handoffs.

The current user request explicitly authorizes the source-readiness slice beyond historical frozen v1 scope, but prohibits merge and deployment. Workspace CLAUDE.md remains the source for other applicable rules. Preserve unrelated checkouts, stashes and primary SPEC.md edits.

## Ownership and integration

Worktree: `/Users/alexmunzon/Data intake/aik-source-readiness`. Branch: `pr-source-readiness`, from fetched main `275be53afdc6aecd33ac65defd9c980835127b49`.

- Engine Sol: `readiness_engine_review`, explicit `gpt-6.1-sol`, owns `engine/src/intake/source_readiness*.py` and the focused Python test.
- Dashboard Sol: `readiness_dashboard_review`, explicit `gpt-6.1-sol`, owns the readiness route, component, TypeScript parser/evaluator and focused frontend tests.
- Browser Sol: `readiness_browser_verify`, explicit `gpt-6.1-sol`, owns browser evidence only.
- Astra parent reviews results, accepts changes, makes the local commit and coordinates Session 7.

Session 7 integration requirements: add `/readiness` to shared navigation and register `intake.source_readiness_cli:app` as `intake readiness`. Neither shared file is modified in this branch. The scoped module works immediately with `uv run python -m intake.source_readiness_cli`. No changes to the existing source totals, finance, demo package or theme.

Read `docs/source-readiness.md` for schema semantics, commands, examples, storage limits and reconciliation. Session 1 contract was read from `aik-contract-adapters/docs/contracts/agency-integration-v1.md`, version 1.0.0. The onboarding manifest uses compatible artifact byte pins; readiness is an explicit pre-intake extension, not a fabricated clean-record Packet.

## Verification and remaining work

Final focused evidence from explicit Sol workers: 68 Python tests and 57 Vitest tests passed after the continuity repair. Targeted Ruff, mypy (all three readiness modules), ESLint and fresh tsc --noEmit passed. Astra inspected engine grouping, timestamp/hash validation, frontend parity, import cancellation and download tests before acceptance. The full local gate started before review fixes and was terminated at Session 7’s request (exit 143); it is not a pass. Its log remains `/private/tmp/readiness-verify.log`. Session 7 will run the combined exact-file full gate before integration commit. No hosted gate, merge or deployment is claimed.

Desktop IAB passed initial unknown, all five states, duplicate retention, owner/action typing and no overflow at 1440px. IAB then disconnected. Mobile, console, remaining browser actions and final hot reload are explicitly unverified; see `source-readiness-browser-verification.md`. Component tests cover failed imports, clear/races and download preservation. The browser viewport override could not be reset after IAB disconnected; reset on recovery.

Usable sample: `fixtures/source-readiness/onboarding-corrected.zip`, 3864 bytes, SHA-256 `151ea6c11ec32a863510f3254d44167ef381b12ab16a142b7b6b0c4f81f8e13b`. Sol verified all four member pins, original/superseded evidence, recomputed summary and refusal to overwrite.

Session 1 approved the separate named readiness extension via Session 7: `source_readiness` and `source_readiness_onboarding`, version 1.0.0; nullable pre-intake intake_run_id; safe relative artifact pins; explicit agency and not_reviewed. A supersedes_version_id points to the exact immutable prior version and its file_sha256/evidence in the same validated package, not invented row lineage. It must not be loaded as a clean-record Packet.

Next actions: transfer frozen file hashes to Session 7; obtain final combined full-gate evidence before the requested verified commit; retry remaining IAB checks when available. Session 7 alone owns shared CLI/navigation, merge and deployment. This session has no merge or deployment authorization.

## Post-freeze continuity repair

Astra found that a stand-alone valid replacement could silently remove same-run receipts. The candidate was reopened before final acceptance and Session 7 was notified. Sol added same agency/run continuity checks on browser and CLI import: preserve prior versions, receipts and evidence unchanged, prevent clock rollback and changed established Intake links, allow idempotence and append-only corrections/deliveries. Different agency/run imports remain explicit package switches. Expected inventory planning metadata stays editable. Corrupt prior local stores refuse overwrite. Rejected imports preserve ownership/action edits and all earlier state. Wire format and the verified ZIP are unchanged. Final incremental patch/hashes are supplied to Session 7 for renewed acceptance.

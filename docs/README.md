# Documentation

Start with the [repository overview](../README.md), [live demo](https://agency-intake-kit.vercel.app) and [three-demo walkthrough](demo-walkthrough.md). The public demonstrations are separate sites with synthetic or public inputs. No client data moves between them.

## Review the evidence

- [Demo scorecard](../dashboard/public/demo-run/scorecard.json) and [manifest](../dashboard/public/demo-run/manifest.json): committed synthetic results and run provenance.
- [End-to-end test](../engine/tests/e2e/test_agency_a.py): recall and false-alarm assertions on the seeded agency.
- [Header-mapping benchmark](benchmark-header-mapping.md): method, seen-set limitations, replay coverage and pipeline differences.
- [Clean-row validation](clean-validation.md): declared schema validation and excluded rows.
- [Synthetic data](synthetic-data.md): generator, planted mistakes and limits.

## Understand the design

- [SPEC](../SPEC.md): contracts and examples. [Architecture decision records](adr/README.md): rationale for the major choices.
- [Rules](rules.md), [schema](schema.md) and [outputs](outputs.md): verdicts, data shapes, lineage and run artifacts.
- [Jev](jev.md): bounded model questions, confidence gates, replay and budgets.
- [Dashboard design](design.md) and [screenshots](screenshots/): presentation and recorded visual evidence. Existing images are evidence from their capture time, not an assertion of current browser coverage.

## Develop and maintain

- [Contributing](../CONTRIBUTING.md): locked setup, checks and small-change workflow.
- [Security](../SECURITY.md): threat boundaries, reporting, known dependency risk and audit limits.
- [Changelog](../CHANGELOG.md) and [v1.0.0 release notes](release-notes-v1.0.0.md): historical changes and release scope.
- [Roadmap](../ROADMAP.md) and [build guide](../BUILD-GUIDE-agency-intake-kit.md): historical planning and reference. The broader roadmap remains deferred; use the README and contributor guide for current setup.

Finance review and receipt-ledger candidates are described in the [README](../README.md#neutral-finance-review-and-receipt-ledger-synthetic-development-candidate). They retain synthetic-only and unauthenticated-approval caveats and are not production accounting integrations.

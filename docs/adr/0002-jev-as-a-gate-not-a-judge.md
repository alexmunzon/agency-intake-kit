# ADR 0002: Jev is a gate, not a judge

- Status: Accepted
- Date: 2026-10-04

## Context

Some intake questions have no clean rule. Which standard field does the header "Birth Dt (mm/dd/yy)" hold? Does "Termed" mean terminated? Is this exception a typo or a real business event? Does this free-text note contain health or identity details?

Jev is TypeSafe's decision model. It answers small, bounded questions (yes or no, pick one of N, score on a scale) with a probability instead of free text, at about four cents per million input tokens (docs/jev.md, checked 2026-10-04). A model that is sometimes wrong cannot be allowed to override a check that is always right, or nobody can trust the result.

## Decision

Rules decide. Models fill gaps and order queues. In practice:

1. **Deterministic rules run first and have the last word.** A rule verdict or a severity is never changed by Jev or any other model.
2. **Jev answers exactly four questions** (SPEC, "Jev usage"): header mapping, messy enum values, exception triage, and the PII gate. Each answer is routed by a threshold in `config.py`. Below the threshold, the item goes to a human.
3. **Raw gates run before any model call.** The SSN refusal (SSN-001) and completeness checks (CMP-001, CMP-002) run on the raw files right after reading.
4. **Payloads are minimized.** Jev sees only the fields a question needs. Notes never reach a model before the PII gate.
5. **Four modes, replay by default** (CHANGELOG, PR 6). `replay` reads recorded answers, called cassettes, from files in the repo. A cassette is one saved question and answer, keyed by a hash of the exact request; cassettes are committed, so CI never calls the network. `off` sends every question to the human queue and the run still completes. `live` and `record` spend money and are refused unless the caller passes `allow_spend=True`, and each use needs Alex's approval.
6. **Spend cap of $0.50 per run.** When it trips, Jev switches to `off` for the rest of the run. The run completes and the remaining questions go to the human queue.

## Consequences

- The pipeline works with no API key and no network. Anyone can clone the repo and run the checks.
- Every Jev answer is reproducible in CI, because it comes from a committed cassette.
- A cassette must be recorded against the exact requests the real pipeline sends, or replay misses. So recording waits for the real source files (PR 7) and the full pipeline (PR 12).
- Some items a model could have settled go to a human instead. That is the intended trade.
- Shipped so far: the Jev client with its modes, cassettes, retries, and spend accounting (PR 6). The four questions are wired in by PR 7 and PR 11, which have not shipped.

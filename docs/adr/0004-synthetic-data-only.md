# ADR 0004: Synthetic data only

- Status: Accepted
- Date: 2026-10-04

## Context

Insurance agency files hold names, birth dates, Medicare numbers, and sometimes health details. That is PHI, protected health information, which US law (HIPAA) strictly limits who may hold and share. A public portfolio repo must never contain it, and the builder has no lawful access to real agency files anyway.

The project also needs to prove its checks work. That needs data where every mistake is known in advance, so detection can be measured, not guessed.

## Decision

Every record in this repo is synthetic, made by a seeded generator (`synth_agency_data`).

- **Seeded means repeatable.** The same seed always gives the same bytes. Seed 42 with 2,000 clients gives 1,400 households, 25 agents, 2,600 policies, and 6,651 commission lines (CHANGELOG, PR 2).
- **Clean world first, then planted mistakes.** The generator builds a clean world that raises nothing above info, then injects 25 kinds of labeled defects and writes `ground_truth.json` listing every one, with a stable record key (CHANGELOG, PR 3a). That file is the answer key the checks are scored against.
- **Named examples are planted on purpose.** Policy P-00417 (an agent selling without ready-to-sell status) and Harborline statement line 212 (a $61.05 payment for no policy) are placed by code, so they exist in every regeneration.
- **Fake but realistic.** Six fictional carriers. Medicare numbers and plan IDs pass the format checks but are made up. Rate amounts are illustrative, not official figures.
- **No SSNs, ever.** A file with an SSN column is refused before any other step (SSN-001), and its values never reach a log, exception, or output. The exception model already refuses SSN-shaped text (PR 1a-i). The file-level gate ships in PR 4, and the end-to-end test that searches the run folder for each planted SSN value ships in PR 12.
- **Masking.** Exceptions show a masked value, never the raw one, through one shared function, `minimize_value()` (CHANGELOG, PR 1a-i).

## Consequences

- The repo is safe to make public, and so is the live dashboard.
- Detection rates are measured against a known answer key. The README labels them as measured on synthetic data, not real agency files.
- Synthetic data is cleaner and more regular than real exports. Real files will have mistakes the generator does not make. The README says so.
- This is a demonstration of privacy habits, not a HIPAA compliance certification.

# agency-intake-kit

Validate, reconcile, and show the health of a newly acquired insurance agency's book of business. All data in this project is synthetic.

**Work in progress.** Part of the engine is built and part is not; the [status](#status) section lists both. Live demo: https://agency-intake-kit.vercel.app

## What this is

When an insurance agency is bought, its records arrive as a pile of mismatched files: a CRM export, an enrollment platform export, carrier commission statements, and an agent roster kept by hand. Someone then checks them by hand for weeks. This kit is being built to take that pile and, in one command, answer three questions: can this book go live in our systems, does the money agree, and was every policy sold by an agent allowed to sell it. Today the data models, the synthetic data generator with its answer key, the Jev client, the row checks, the cross-record checks, the three-way money tie-out, and all five dashboard pages are built. The piece that reads the messy source files and runs everything as one command is landing now, so until it does the live demo shows a hand-built sample run, not engine output.

## Why this exists

I am Alex Munzon, a UCLA business economics student, and I built this as a working answer to a question I kept running into while studying insurance agency acquisitions: when an agency changes hands, how do you know its data can be trusted? This kit is the job of an AI deployment specialist written as code. It makes the checks explicit, scores them against planted mistakes with known answers, and keeps a person in charge of every judgment call. I wrote the spec, chose every rule and threshold, and reviewed and approved every change. AI coding agents did the typing, working one pull request at a time against that spec, with tests written first and every check run in CI before a merge. The commit history shows exactly which commits they co-authored. If you want to see how I think, start with [SPEC.md](SPEC.md) and the five decision records in [docs/adr/](docs/adr/README.md).

## Who it is for

- **Agency owner or acquirer:** one answer, can this agency go live, and if not, why not.
- **Integration specialist:** every problem, how serious it is, the exact source row, and how to fix it, in priority order.
- **Finance or M&A analyst:** commission differences in dollars by carrier and agent.
- **Compliance lead:** which agents wrote business they were not ready to sell or licensed for.

## What it does: five questions, one dashboard page each

| Page | Question it answers | Status |
|---|---|---|
| Overview | Can this agency go live? | Built (PR 13) |
| Sources | Did we receive every file, and did each one read cleanly? | Built (PR 14) |
| Exceptions | What needs fixing, in what order, and how? | Built (PR 14) |
| Tie-out | Does the money agree across the book, the statements, and the CRM? | Built (PR 15) |
| Agents | Did anyone sell something they were not ready to sell? | Built (PR 15) |

A sixth page, Runs ("what changed since the last run?"), comes in PR 16. Every page answers its question at the top before showing detail. A check that did not run says "Not checked", never 0, so a missing check can never look clean.

## Screenshots

From the live demo at 1440 pixels wide, made by `npm run shots`. Files are in [docs/screenshots/](docs/screenshots/).

![Overview page: a status banner answering whether the agency can go live, with counts of blockers, errors, and warnings](docs/screenshots/overview-1440.png)

![Exceptions page: a table of problems sorted by severity, with filters for severity, rule, and source file](docs/screenshots/exceptions-1440.png)

![Tie-out page: three cards comparing the book, the carrier statements, and the CRM, with a table of dollar differences](docs/screenshots/tie-out-1440.png)

![Agents page: writing agents and a ready-to-sell matrix by carrier, state, and plan year](docs/screenshots/agents-1440.png)

## What is synthetic, and why

Every record is made by a seeded generator. Seeded means the same seed always produces the same files, byte for byte. Seed 42 with 2,000 clients gives 1,400 households, 25 agents, 2,600 policies, and 6,651 commission lines across six fictional carriers.

The generator first builds a clean world, then plants 793 labeled mistakes and writes an answer key (`fixtures/agency-a/ground_truth.json`). That lets every check be scored against known truth instead of guessed. Synthetic data also means no real person's information is ever in this repo. Results measured on it are labeled as synthetic; real agency files will have mistakes the generator does not make. See [ADR 0004](docs/adr/0004-synthetic-data-only.md).

## Data trust rules

- **No PHI and no real data.** PHI is protected health information, which US law strictly limits. None of it enters the repo, a log, a test, or a model call.
- **No SSNs, ever.** A file with an SSN column blocks the run (rule SSN-001), and its values never appear in any output.
- **Lineage on every row.** Lineage is the record of where a row came from: source file, sheet, row number, a fingerprint of the raw row, the run, and the mapping version. Every output row carries it.
- **Three blockers, no more.** Only three rules can stop a run: MAP-003 (a required column is missing), CMP-001 (a file has fewer rows than promised), and SSN-001. Errors drop their rows, warnings pass with a flag, info is logged.
- **Rules decide, models never override.** Jev, TypeSafe's decision model, answers only small yes/no or pick-one questions, and only where rules run out. Below its confidence threshold the item goes to a person. See [ADR 0002](docs/adr/0002-jev-as-a-gate-not-a-judge.md).
- **Runs are never edited.** Each run is a folder that is never changed afterward; a correction is a new run.
- **Money is exact.** Amounts are stored to the cent as exact decimals and written as text, never as approximate floating-point numbers.

This is a demonstration of privacy habits, not a HIPAA compliance certification.

## How to run it locally

You need [uv](https://docs.astral.sh/uv/) (a Python package manager) and [nvm](https://github.com/nvm-sh/nvm) (a tool that installs the right Node version).

```bash
git clone https://github.com/alexmunzon/agency-intake-kit.git
cd agency-intake-kit
(cd engine && uv sync)                    # Python 3.12 and engine packages
nvm install 24 && nvm use 24              # Node 24
(cd dashboard && npm ci)                  # dashboard packages
npm run verify                            # every check: lint, types, tests, build
(cd dashboard && npm run dev)             # dashboard at http://localhost:3000
```

Also available now: `cd engine && uv run synth generate --seed 42 --clients 2000 --out ../fixtures/agency-a` regenerates the synthetic world.

Coming in PR 12: `npm run demo`, which runs the full pipeline on the synthetic agency and refreshes the dashboard's demo run. No API key is needed for any of this; Jev answers come from recordings committed to the repo.

## Status

What has shipped is in [CHANGELOG.md](CHANGELOG.md). The full plan and contract is [SPEC.md](SPEC.md).

**Built:**
- Data models for the six tables, lineage, exceptions, and every run output file (PR 1a-i, 1b).
- Format checks for Medicare numbers, agent IDs, plan IDs, and a ZIP-to-state table (PR 1a-ii).
- The synthetic generator, planted mistakes, and answer key (PR 2, 3a).
- The Jev client with replay, off, live, and record modes and a $0.50 spend cap per run (PR 6).
- Row checks for dates of birth, Medicare numbers, agent IDs, plan IDs, addresses, contacts, dates, and statuses (PR 8).
- Cross-record checks for duplicates, broken references, ready-to-sell gaps, and license gaps, plus the ready-to-sell coverage matrix (PR 9).
- The three-way money tie-out in DuckDB SQL, exact to the cent (PR 10).
- Dashboard pages Overview, Sources, Exceptions, Tie-out, and Agents, reading a sample run (PR 13 to 15), with screenshots and design notes.

**Not shipped yet:**
- The messy source files (CSV and spreadsheet versions of the agency's exports): PR 3b, in review.
- Readers that open those files and the raw-file gates: PR 4.
- Column mapping, by dictionary (PR 5) and by Jev (PR 7).
- Exception policy, Jev triage, and the PII filter: PR 11, in review.
- Running it all as one command, the HTML report, and `npm run demo`: PR 12.
- Load your own run, run comparison, dark mode toggle: PR 16.

No detection rates are published yet, because the pipeline that produces them is not built. They will come from the committed fixtures, not estimates. The one number published now is the header mapping benchmark (PR 17), refreshed by `cd engine && uv run intake bench header-mapping`:

<!-- benchmark:start -->
Header mapping benchmark on 134 labeled headers (79 from the fixture files, 55 synthetic variants), Jev in replay. Small synthetic set; method and caveats in [docs/benchmark-header-mapping.md](docs/benchmark-header-mapping.md).

| Approach | Accuracy | Coverage | Wrong mappings | Not recorded | Model calls | Est. cost per 1,000 headers |
|---|---|---|---|---|---|---|
| Synonyms only | 79.9% (107 of 134) | 71.6% | 0 | 0 | 0 | $0 |
| Synonyms then Jev | not measured: no recordings yet | n/a | 0 | 38 | 0 | n/a |
| Synonyms then Sonnet | skipped: no key | n/a | n/a | n/a | 0 | n/a |
<!-- benchmark:end -->

## Design decisions

Five short decision records in [docs/adr/](docs/adr/README.md): DuckDB for the tie-out, Jev as a gate, a static-first dashboard, synthetic data only, and separate repos per project. Data shapes are in [docs/schema.md](docs/schema.md) and [docs/outputs.md](docs/outputs.md); the Jev client is in [docs/jev.md](docs/jev.md).

## Glossary

- **Book of business (BoB):** the list of clients and policies an agency services.
- **RTS (ready to sell):** a broker is licensed, appointed with a carrier, and certified for a plan year in a state.
- **NPN:** National Producer Number, a broker's national ID.
- **MBI:** Medicare Beneficiary Identifier, the number on a Medicare card.
- **Carrier commission statement:** the monthly file a carrier sends listing what it paid the agency per policy.
- **Three-way tie-out:** proof that the book, the carrier statements, and the CRM agree with each other.
- **Jev:** TypeSafe's model that answers bounded questions with a probability.

## Part of a series

This is the first project built in the Agency Data Trust Series. bob-resolve (matching people across files without an SSN) and plan-diff (comparing plan documents across carriers) come next. See [ROADMAP.md](ROADMAP.md).

## License

MIT. See [LICENSE](LICENSE).

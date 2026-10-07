# Durable local finance ledger

This slice extends `revenue.py` and `revenue_ledger.py`. Their classification,
receipt duplicate, correction and conflict decisions remain authoritative. Synthetic
fixtures measure software behavior only. No ERP posting, customer attribution,
authenticated approval, hosted storage, paid services or credentials are provided.

## Local workflow

From `engine`, run these commands with `uv run python -m intake.finance_cli`.
Use fresh paths because `init`, `import-statement`, and `export` refuse to overwrite:

```
init /tmp/finance.sqlite ../fixtures/finance-review/mapping.json
import-statement ../fixtures/finance-durable/statement.csv ../fixtures/finance-durable/adapter.json /tmp/statement.json
append /tmp/finance.sqlite synthetic-operation-1 ../fixtures/finance-durable/batch.json
export /tmp/finance.sqlite /tmp/ledger.json
```

Each line is a separate command after the module prefix. XLSX uses the supplied
`adapter-xlsx.json` and `statement.xlsx`. Input layout configuration selects columns,
header row, last data row, delimiter, encoding and worksheet. No label normalization
or sign-based classification occurs. Unknown labels stay unclassified. Formula
cells in the selected header/data region, ambiguous worksheets, duplicate/missing
headers and malformed data rows refuse the entire import. A footer explicitly
excluded with `last_data_row` is not imported. XLSX numeric cells use openpyxl's
raw numeric value converted to text; display formatting such as trailing zeros
is not source evidence. CSV text is retained exactly. Original file SHA-256 and
raw-cell row hashes are separate.
Optional `source_sha256` pins refuse stale bytes before parsing.

`import-statement` and `export` stage complete JSON bytes beside the destination,
flush and sync them, then publish with an exclusive filesystem link. A reader
cannot see a partial output and a concurrent writer cannot replace an existing
output. If directory syncing fails after publication, the complete output may
already exist even though the command reports failure; inspect that path before
retrying with a fresh name.

SQLite uses FULL synchronous transactions and a write lock. Each store pins one
carrier mapping snapshot; use a separately identified store for another mapping
version or carrier. Existing stores, including empty or damaged files, are never
reinitialized. Batches validate in full before one journal insertion. Operation IDs
are scoped to a store. A byte-equivalent canonical request with the same ID returns
its original outcome, even after later corrections; changed content under that ID
is refused. Reusing a receipt ID in a different operation is refused. A new receipt
ID for duplicate evidence is retained without adding revenue. Receipt timestamps
must remain nondecreasing, as required by the existing ledger contract. Concurrent
writers serialize; an older timestamp submitted late is rejected rather than reordered.

The journal retains immutable operation payloads, original receipt packages and
mapping evidence. Correction decisions are replayed from this history. SQL triggers
block normal update/delete operations. Integrity checks and a hash chain refuse
malformed or altered entries. This is local accidental-corruption protection, not
an authenticated or tamper-proof audit system: a file owner can rewrite an entire
store or remove its tail. Back up the complete database only while no writer is
active; no cloud backup or network-filesystem durability is asserted. Store replay
currently scales with history and is intended for small local synthetic workloads.

## Provenance contract and integration ownership

Session 1's `aik-contract-adapters/docs/contracts/agency-integration-v1.md` version
1.0.0 supplies the ID, artifact-pin and provenance vocabulary. This finance extension
preserves `source_file`, `sheet`, original `row_number`, `raw_hash`, `run_id`, and
`mapping_version`. Adapter layout versions and revenue classification mapping
versions remain distinct. `provenance.json` is a finance sidecar rather than a
Session 1 client/policy Packet. Its `run_id` is the synthetic finance run; it does
not claim an Intake run. Each artifact pin records the exact file bytes and size.
Its nine row links cover all three ledger revision entries, including the duplicate
receipt: `artifact` and `artifact_row` point to a source CSV and its one-based data
row, while `ledger_artifact`, `ledger_revision_index`, and `ledger_row_index` point
to the exact ledger row. `receipt_id`, `revision_id`, and `row_id` identify that
revision. Byte pins establish consistency, never authenticity or approval. No
client, policy, enrollment or identity is manufactured.

Session 7 owns shared registration and navigation. The integration points are
`from intake.finance_cli import app as finance_app` followed by
`app.add_typer(finance_app, name="finance-local")`, and a navigation link to `/ledger`.
The module CLI works independently. Shared files are untouched in this branch.
The public ledger page validates exported totals with integer-cent arithmetic,
keeps a previous valid import on failure, and uses browser memory only. Reloading
clears the view; it never appends to or approves a local store.

## Samples and verification

`PYTHONPATH=engine/src engine/.venv/bin/python scripts/finance/sample.py` rebuilds
synthetic CSV/XLSX, receipt batches, neutral ledger and provenance pins. XLSX
archive metadata is fixed, so repeated generation produces identical bytes. The
sample has original 75.03, a duplicate, then an explicit correction to 85.03,
including 0.03 unclassified and a -25.00 reversal. JSON classification exports
retain full source labels and mapping snapshots; existing CSV neutral review
exports retain their spreadsheet formula guards.

See `test-evidence.txt` for full verification output and `HANDOFF.md` for remaining
integration and environment limitations. No merge or deployment was performed.

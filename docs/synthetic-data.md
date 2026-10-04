# Synthetic data

Everything in `fixtures/` is made up. The generator builds a fake agency book (seed 42: 2,000
clients, 2,600 policies, 25 agents, six fictional carriers), breaks it on purpose, writes it out
as the four messy files a real agency would hand over, and records every planted problem in
`ground_truth.json`, so the pipeline's catches can be scored.

```bash
cd engine
uv run synth generate --seed 42 --out ../fixtures/agency-a
uv run synth generate --seed 42 --out ../fixtures/agency-a-truncated --truncate-crm 2574 --no-canonical
uv run synth generate --seed 42 --out ../fixtures/agency-a-ssn --add-ssn-column --no-canonical
```

Same seed, same bytes. `tests/unit/test_writers.py` regenerates all three folders and fails if
any byte changes. Spreadsheets are saved with frozen timestamps for that reason.

## What is in a fixture folder

| Path | What it is |
|---|---|
| `drop/` | The four source shapes plus `manifest.json`. This is what `intake run` reads. |
| `canonical-defected/` | The same defected book as clean canonical CSVs (agency-a only). Rule PRs test against it. |
| `ground_truth.json` | Every planted defect: `source`, `record_key`, `row_ref` (row in the canonical CSV), `defect_type`, `expected_rule_ids`, `scored`, `injected_values`, and where it landed in `drop/`: `source_file`, `sheet` (blank for CSVs), `source_row` (1-based, as in the file). |

Scoring matches by `record_key`, never by row. Policy defects point at the policy's CRM row (the
later copy when an id is duplicated). Client defects point at the client's first CRM row. Line
defects point at the statement row. A missing commission line points at its policy's CRM row.

## The four source shapes and their quirks

| File | Shape | Quirks |
|---|---|---|
| `crm_export.csv` | One row per policy, client fields repeated (2,680 rows). Clients with no policy (46: re-keyed copies, and clients whose only policy was orphaned) get one row with the policy columns blank. | latin-1 text that starts with a UTF-8 byte order mark; "Client Name" as "Last, First"; "Mbr DOB" as Excel serial text when the serial is 20000 to 60000, else 01/31/1950; "Eff Date" and "Term Date" rotate 01/31/2026, 2026-01-31, 01/31/26 by row; status words in mixed case (Active, ACTIVE, active); a Notes column; CRLF line ends. |
| `enrollment_export.csv` | One row per MA or PDP policy row (1,847). | Semicolon delimiter, UTF-8, no BOM; snake_case headers plus "Birth Dt (mm/dd/yy)" (SPEC example 2); two-digit birth years (all 1930 or later); effective dates like 20260501; its own status words (Approved, Submitted, Disenrolled, Withdrawn, Unknown). |
| `commissions_<carrier>.xlsx` | One per carrier, all three periods on one sheet named Statement. | Row 1 is a merged title, row 2 a subtitle, row 3 the header, data from row 4, last row a total (column A "Total", column B the data row count, the last column the summed amount). Three header layouts. Amounts are two-decimal text. Northwind Health and Cardinal Mutual store dates as date cells; Bluepeak and Summit Health Plans as 01/31/2026 text; Harborline and Meridian Care as 2026-01-31 text. |
| `agent_roster.xlsx` | Sheet Agents (one row per agent) and sheet RTS (one row per agent, carrier, state, plan year, line of business). Header on row 1 of each. | Free-form headers ("NPN #", "Plan Yr", "Appointed?"); license states as one comma list; Y/N flags; RTS dates as date cells. |

`drop/manifest.json` lists each file (and sheet) with its full data row count. The truncated
fixture keeps the full count on purpose.

## The three fixtures

- **agency-a**: the full messy drop. Expected result: passes with warnings.
- **agency-a-truncated**: the CRM keeps only its first 2,574 data rows; the manifest still says
  2,680. Ground truth adds a `truncated_file` defect (CMP-001), and defects whose rows were cut
  off get `source_row: null`. Expected result: blocked.
- **agency-a-ssn**: the roster's Agents sheet gains an "SSN" column. Every value starts with
  area 000, which the Social Security Administration has never issued, so none can be a real
  number. The values are listed in ground truth (`ssn_column`, SSN-001) so the test can search
  the run folder for each one. Expected result: blocked.

## Injected defects (guide 7.3 default rates)

A rate is a share of the table the defect lives in. Each defected record carries one defect.

| Defect | Rate | Rule | Scored |
|---|---|---|---|
| ZIP does not match state | 1% of clients | ADR-002 | yes |
| Invalid MBI | 1% | MBI-001 | yes |
| Missing MBI | 2% | MBI-003 | yes |
| NPN malformed | 0.5% of policies | NPN-001 | yes |
| Unknown writing agent | 0.5% | NPN-002 | yes |
| Plan ID malformed | 1% | PLN-001, PLN-002, or PLN-004 | yes |
| Term date before effective date | 0.5% | DAT-002 | yes |
| Status conflicts with dates | 1% | DAT-003 | yes |
| Unrecognizable status word | 2% | STA-001 | yes |
| Exact duplicate row | 1% | DUP-001 | yes |
| Duplicate policy id, different values | 0.3% | DUP-003 | yes |
| Orphan policy (no such client) | 0.5% | REF-001 | yes |
| Orphan commission line | 1% of lines | TIE-002 | yes |
| Missing commission line | 2% | TIE-001 | yes |
| Commission off schedule | 1% | TIE-003 | yes |
| CRM says cancelled, carrier still pays | 1.5% of policies | TIE-004 | yes |
| RTS gap | 1% | RTS-001 | yes |
| RTS expired | 0.3% | RTS-002 | yes |
| License gap | 0.5% | LIC-001 | yes |
| Same name and birth date, two client ids | 0.5% of clients | DUP-002 | yes |
| PII sentence in CRM Notes | 1% of CRM policy rows | PII-001 | yes |
| Name typo | 2% | none | no |
| Nickname | 3% | none | no |
| Birth date digits transposed | 1% | none | no |
| Birth month and day swapped | 0.5% | none | no |
| Near-duplicate client | 1.5% | none | no |

Unscored defects are for the later bob-resolve project: they are reported but not gated.

Planted on purpose (SPEC examples 3 and 4): P-00417 has no RTS for Harborline, TX, 2026
(RTS-001), and Harborline 2026-08 line 212 pays 61.05 to member HL-998213, who has no policy
(TIE-002).

PII sentences use only fake specifics: 555 phone numbers, example.com emails, made-up last
names like Testperson, and short zero-led numbers that cannot look like an SSN. A few harmless
notes carry accented letters (español, café) so the latin-1 encoding is real.

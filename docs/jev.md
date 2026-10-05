# Jev (TypeSafe) client

Jev is TypeSafe's model. It answers small, bounded questions with probabilities instead of
free text. This kit asks it four questions (SPEC "Jev usage"), and rules always have the last word.

## What the docs say (checked 2026-10-04)

Read with WebFetch on 2026-10-04, before any recording. Real answers were recorded on 2026-10-05 (see Recording below and CHANGELOG).

| Fact | Value | Source |
|---|---|---|
| Endpoint | `POST https://api.typesafe.ai/v1/systemone` | https://docs.typesafe.ai/api.md, cross-checked on https://docs.typesafe.ai/introduction/quickstart.md |
| Auth | `Authorization: Bearer <API_KEY>`, `Content-Type: application/json` | api.md and quickstart.md |
| Request | `state` (text, object, or list), `model`, `questions` (map of id to question) | api.md |
| Model | `jev-latest` (alias; responses name the real model, `jev-1.13.0`). `jev-preview` also exists | https://docs.typesafe.ai/models.md |
| noul | request `criteria: {"true", "false"}` (both optional); answer `{"type": "noul", "noul": 0..1}` | api.md |
| choice | request `criteria: {option: description}`, up to 255 options; answer `choice`, `probabilities`, `confidence` | api.md |
| score | request `criteria: [level 0, level 1, ...]`, 2 to 10 levels; answer `score` (a float, the weighted mean of level numbers), `legend` and `probabilities` keyed by level number, `confidence` | api.md, https://docs.typesafe.ai/primitives/score.md |
| Usage | `usage.input_tokens`, `usage.output_tokens` (the Python SDK types both as possibly empty) | api.md, https://docs.typesafe.ai/sdk/python/api/types/responses.md |
| Errors | 401 bad or missing key, 422 bad body, 429 rate limit, 529 overloaded. Retry 429 and 529 with exponential backoff | api.md |
| Price | $0.042 per million input tokens ($42 per billion). Output tokens are free | models.md |
| Limits | 64k tokens per request; 32k for `state` plus the longest question | models.md |

The price and shape match BUILD-GUIDE section 8. One addition: answers carry a `type` field.

**Still assumed until the first approved recording (PR 7):**
- JSON keys inside `legend` and `probabilities` for score come back as text ("0", "1"). The example on score.md shows text keys; the SDK types them as numbers after parsing.
- A noul answer has no `confidence` field (api.md lists only `noul`).
- Error bodies are JSON or text. The client never shows them as is: it removes the key, its first 8
  characters, and anything after the word "Bearer", then keeps at most 200 characters.
- Whether the API accepts `"true": null` in noul criteria. Our client sends both keys when criteria are given.
- No `Retry-After` header is documented, so the client ignores it.

**Official SDK.** `typesafe-sdk` exists (`uv add typesafe-sdk`, Python 3.10 or newer). This PR does
not wrap it. The cassette hash must cover the exact body we send, the SDK has its own retries (which
would stack with ours), and a new dependency means a lockfile that cannot be hand-merged. httpx was
already a dependency. Revisit if the API shape changes often.

## Modes

Set by `JEV_MODE`, read by `JevClient.from_env()`. The default is `replay`.

| Mode | What happens | Spends money |
|---|---|---|
| `replay` | Reads the cassette for the request. A miss raises `CassetteMiss` with the request hash | No |
| `off` | Returns `Unresolved(reason="mode_off")`, never None. The questions go to the human queue | No |
| `live` | Always calls the API, even when a cassette exists. Reads and writes no cassettes | Yes |
| `record` | Uses an existing cassette if there is one, otherwise calls the API and saves a cassette. Delete a cassette to re-record it | Yes |

Only `replay` and `record` read cassettes. Use `live` to check what the real API says today.

The client refuses `live` and `record` unless the caller passes `allow_spend=True`. The repo's
permission rules do not catch these modes, so this check is the real lock. Alex approves each use.

## Retries

On 429 or 529 the client waits and tries again, up to 5 tries in all. The wait doubles each time
(1, 2, 4, 8 seconds, from `JEV_BACKOFF_BASE_S`) and is randomized between half and all of that
window, so many clients do not retry at the same moment ("jitter"). Any other error, including 401
and 422, raises `JevHTTPError` at once with the status and a short excerpt of the body. Network
errors are not retried.

The excerpt is redacted first: the key, the key's first 8 characters (some servers quote a
prefix), and any `Bearer ...` text become `[redacted]`, and it is cut at 200 characters so a 422
that echoes the request does not spill it into logs.

## Checking answers

Every answer must line up with the questions asked, or `ask` raises `JevBadReply` (a `ValueError`):

- One answer per question, with the same id and type.
- A choice answer must pick one of the options offered, and its probabilities may only name
  offered options. An off-list choice would otherwise become a column mapping or enum value that
  does not exist.
- A score must sit between level 0 and the top level, and its probabilities may only name level
  numbers that were offered ("0", "1", ...).

## Spend guard

Each reply adds its input tokens to the run's usage, counted before the reply is checked. A reply
that fails the checks was still billed, so it still counts; a missing or broken `usage` block
counts the call with 0 tokens and logs a warning. In `record`, a reply that fails the checks is
still saved as a cassette before the error is raised, and the error names the file. That way a
retry reads the saved reply instead of paying again. Delete the file to re-record it. The estimated cost is input tokens
times the price in `config.py`. It is an estimate, not a bill. When it reaches the budget ($0.50,
`JEV_BUDGET_USD`) the client logs a warning, sets `usage.budget_tripped`, and returns
`Unresolved(reason="budget_tripped")` for every later question. The run still completes; those
questions go to the human queue. `usage.mode` stays the configured mode, because the manifest's
`JevUsage` refuses `off` with real call counts. The manifest records the trip in `budget_tripped`.

The check runs after each call, so one call can go past the budget. At the published price a full
64k token call costs well under a cent. Replay counts recorded tokens too, so replay trips the
guard at the same point a live run would.

## Cassettes and the hash recipe

A cassette is `engine/tests/cassettes/<hash>.json` with two keys, `request` and `response`.
Headers are never stored, so the key cannot leak into one.

The hash (`jev_client.request_hash`, public so PR 11 can deduplicate with it):

1. Build the body with `JevRequest.body()`: `{"state", "model": "jev-latest", "questions"}`.
   A noul with no criteria leaves the `criteria` key out.
2. Serialize with `json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)`.
3. Encode as UTF-8 and take the SHA-256 hex digest.

Key order does not change the hash. Any change in content, including the model name, does, so
cassettes must be recorded against the exact requests the pipeline sends.

## Minimization

`minimize_state(record, allowlist)` keeps only allowlisted fields. A field named `notes` (any case,
any depth) is dropped unless `pii_cleared=True`, even if the allowlist names it. `JevClient.ask`
also refuses any request whose state still holds a notes field unless `pii_cleared=True` is passed.

## Recording (PR 7 and PR 12)

1. Ask Alex in words, stating the expected cost, before any `record` run.
2. Run with `JEV_MODE=record` and `allow_spend=True` set by the caller.
3. Commit the new cassettes and say so in the PR.

**In a run (PR 12).** One client and one $0.50 budget serve the whole run. Header and enum
questions read `engine/tests/cassettes/mapping/`; triage and PII questions read
`engine/tests/cassettes/run/`. In replay a question with no recording is answered "not recorded":
it goes to the human queue (lane UNREVIEWED, or MAP-002 for a header), is counted, and the run
still completes. The CLI prints how many. To record them, after Alex approves the spend:

```bash
cd engine && JEV_MODE=record uv run intake jev record-run --drop ../fixtures/agency-a
```

It refuses unless `JEV_MODE=record` is set. It first runs the drop in replay, prints the number of
unrecorded requests and the estimated cost, then runs again in record mode, which pays only for
requests with no cassette. The key is read from the environment and never printed. For agency-a
the estimate was 157 triage requests, about 31,768 input tokens by the cautious 3 characters per
token estimate, so about $0.0013. Recorded 2026-10-05 with Alex's approval: replay now answers
all 164 questions of an agency-a run (7 mapping, 157 triage), 70,509 input tokens, estimated
$0.002961, budget not tripped (CHANGELOG "Real triage cassettes"). The real token count is about
twice the estimate.

## Triage and the PII gate (PR 11)

**Triage** (`intake/exceptions/triage.py`) asks one request per error or warning with two
questions: `is_entry_error` (noul) and `impact` (score: cosmetic, affects reporting, affects
compliance or money). The state holds only the rule id, the field, the value's shape (`9999-99-99`,
digits become 9 and letters A), and the neighbor fields for the rule's family listed in
`TRIAGE_NEIGHBORS` in `config.py`. Closed-vocabulary neighbors (line of business, status, carrier,
state, and similar) are sent as is; anything else is sent as a shape. Notes are never sent.

| Entry-error probability | Lane |
|---|---|
| 0.80 or more (`TRIAGE_ENTRY_ERROR`) | SUGGESTED_FIX |
| 0.20 or less (`TRIAGE_BUSINESS_EVENT`) | BUSINESS_EVENT |
| in between | REVIEW |
| no answer (off mode or spend guard) | UNREVIEWED, the human queue |

Blockers go to REVIEW and info stays UNREVIEWED without a call. PII-001 is never triaged.

**Deduplication.** Two exceptions with the same rule, field, value shape, and neighbors build the
same body, so they have the same `request_hash`. Triage sends each hash once per run and reuses the
answer. `planned_requests(items)` returns the distinct requests; its length is the call count.

**PII gate** (`intake/exceptions/pii.py`) has two layers. The regex layer runs first and needs no
call: SSN shapes, emails, phone numbers (10 digits with separators, or labeled phone or cell),
dates of birth after a DOB label, card numbers after "card", bank and routing numbers (8 to 17
digits, or labeled account, acct, routing, IBAN), driver's license numbers (a state letter plus
digits, or labeled DL or license no), Medicare and member ids, anything labeled SSN, social,
password, or PIN, and a name after a relationship word (daughter, spouse, and so on). Each match
is replaced in place by a typed placeholder such as `[REDACTED:phone]`, and PII-001 fires
(warning, REVIEW lane) with `value_minimized` from `minimize_value` and the kinds in the message,
never the raw value. Text that still holds a date, a drug-like word, or a health word after that
goes to the noul question, already redacted and with every digit replaced by `#`. At or above
0.50 (`PII_REDACT`) the whole text becomes `[redacted]` and PII-001 fires. With no answer (off
mode or the spend guard) the text is redacted too: the gate fails closed. Identical texts are
asked once. The gate's returned text is what every output writes.

**Expected calls for fixtures/agency-a** (a real `intake run` in replay, asserted in
`tests/unit/test_triage.py`):

| Part | Exceptions | Calls |
|---|---|---|
| Header and enum mapping (PR 7, recorded) | 8 questions asked | 7 |
| Triage: row rules, cross-record checks, tie-out (PR 8, 9, 10) | 711 errors and warnings | 157 |
| PII gate (26 planted notes, all caught by the regex layer) | 26 | 0 |
| **Total** | | **164** |

Measured on the real drop path in PR 12 (readers, mapping, canonical tables), not the old
canonical copy. The savings come from grouping: requests with the same rule, field, value shape,
and neighbors are sent once, so 54 missing MBIs (MBI-003) cost one call. Without deduplication
the run would send 711 triage requests. The bounded link slice adds six exceptions for the
planted P-01324 identity conflict; the grouped call count remains unchanged.

**Test cassettes.** `engine/tests/cassettes/synthetic/` holds hand-made answers for the triage and
PII shapes (model `synthetic-hand-made`). They are not recordings. They sit in a subfolder so the
pipeline, which reads `engine/tests/cassettes/`, can never replay a made-up answer. The real ones
are in `engine/tests/cassettes/run/`, recorded 2026-10-05 (164 answers).

## Header mapping and enum values (PR 7)

**Question 1, header to field** (`intake/mapping/jev_mapping.py`), one per header the synonym
table left unmapped:

```json
{
  "state": {"header": "Birth Dt (mm/dd/yy)", "sample_values": ["10/**/**", "09/**/**"], "source_table": "clients, policies"},
  "model": "jev-latest",
  "questions": {"field": {"type": "choice",
    "instructions": "Which canonical field does `header` hold, judging by the header and `sample_values`? Sample values are masked: after the first characters, letters and digits are *.",
    "criteria": {"clients.client_id": null, "clients.dob": "date of birth of the client", "...": null, "none": "none of these"}}}
}
```

The options are every field of the source's tables (lineage left out, `full_name` added) as
`table.field`, so the enrollment export can pick a client or a policy field. Samples are up to 5
distinct values, cut to 24 characters, then masked with `minimize_value`. A column whose values
average over 40 characters, have more than 3 spaces, or hold any 9-digit number sends
`"sample_values": []`. A header with the word notes, note, comments, or memo is never sent.

| Confidence | Result |
|---|---|
| 0.85 or more (`MAP_AUTO`) | Mapped, method `jev`, confidence saved in `mapping/<key>.yaml` |
| 0.60 up to 0.85 (`MAP_SUGGEST`) | Mapped, plus MAP-002 each run until a person confirms it |
| Below 0.60, or `none` | Unmapped, PR 5's MAP-001 stays |
| No answer (off, spend guard) | Unmapped, MAP-001 plus MAP-002 in the REVIEW lane |

**Question 2, value to enum** (`intake/mapping/enums.py`), one per distinct value the word table
does not know:

```json
{"state": {"field": "status", "value": "XFER"}, "model": "jev-latest",
 "questions": {"value": {"type": "choice",
   "instructions": "Which of the allowed values does `value` mean for the field `field`?",
   "criteria": {"ACTIVE": "coverage is in force", "PENDING": "submitted, not yet in force", "TERMINATED": "coverage ended after it started", "CANCELLED": "stopped before coverage started", "unknown": "cannot tell from the value"}}}}
```

Fields covered: policy and agent status, line of business, commission type, and state. A pick of
0.85 or more (`ENUM_AUTO`) is used. Anything else stays as written, so STA-001 flags it. Values
over 24 characters, with more than 3 spaces, or with a 9-digit number are never sent.

**Expected calls for fixtures/agency-a: 7.** Mapping asks 3 header questions ("Birth Dt
(mm/dd/yy)" in the enrollment export, "Paid" in the Northwind and Cardinal statements). The two
"Paid" requests are identical (same header, same masked sample `20**-**-**`), so they are sent
once: 2 calls. The CRM status column has 5 values the word table leaves for Jev (`??`, `N/A`,
`See notes`, `XFER`, `chk w/ carrier`): 5 calls. Every other status, line of business, commission
type, and state value is decided by the table. The recording used 3,239 input tokens, about $0.000136.

**Recording.** The 7 cassettes in `engine/tests/cassettes/mapping/` are real TypeSafe answers,
recorded 2026-10-05 with Alex's approval (CHANGELOG "Real Jev mapping cassettes recorded"). To
re-record them, after Alex approves the spend, run from the repo root:

```bash
cd engine && uv run --env-file ../.env env JEV_MODE=record intake jev record-mapping --drop ../fixtures/agency-a
```

The command refuses unless `JEV_MODE=record`, prints the count and estimated cost before any call,
deletes only the hand-made cassettes it is about to replace, and never prints the key. Then run
`npm run verify`: example 2 needs the real answer for "Birth Dt (mm/dd/yy)" to be `clients.dob`
at 0.85 or more.

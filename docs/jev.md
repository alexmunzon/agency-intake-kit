# Jev (TypeSafe) client

Jev is TypeSafe's model. It answers small, bounded questions with probabilities instead of
free text. This kit asks it four questions (SPEC "Jev usage"), and rules always have the last word.

## What the docs say (checked 2026-10-04)

Read with WebFetch on 2026-10-04. No live call was made; nothing here was confirmed against the real API.

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
- Error bodies are JSON or text the client can show as is. The client keeps the first 500 characters.
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
| `live` | Calls the API. Writes nothing | Yes |
| `record` | Uses an existing cassette if there is one, otherwise calls the API and saves a cassette. Delete a cassette to re-record it | Yes |

The client refuses `live` and `record` unless the caller passes `allow_spend=True`. The repo's
permission rules do not catch these modes, so this check is the real lock. Alex approves each use.

## Retries

On 429 or 529 the client waits and tries again, up to 5 tries in all. The wait doubles each time
(1, 2, 4, 8 seconds, from `JEV_BACKOFF_BASE_S`) and is randomized between half and all of that
window, so many clients do not retry at the same moment ("jitter"). Any other error, including 401
and 422, raises `JevHTTPError` at once with the status and body. Network errors are not retried.

## Spend guard

Each answered request adds its input tokens to the run's usage. The estimated cost is input tokens
times the price in `config.py`. It is an estimate, not a bill. When it reaches the budget ($0.50,
`JEV_BUDGET_USD`) the client logs a warning, sets `usage.budget_tripped`, and returns
`Unresolved(reason="budget_tripped")` for every later question. The run still completes; those
questions go to the human queue. `usage.mode` stays the configured mode, because the manifest's
`JevUsage` refuses `off` with real call counts. PR 12 writes the trip into the manifest.

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

**PII gate** (`intake/exceptions/pii.py`): a regex pre-filter (dates, 9 to 11 digit numbers,
SSN-shaped text, drug-like words, and health words) picks the notes worth a look; the rest pass with
no call. Text holding an SSN-shaped value or a 9 to 11 digit number is redacted at once with no
call, so it never leaves the machine. Other flagged text goes to the noul question with every digit
replaced by `#`. At or above 0.50 (`PII_REDACT`) the text becomes `[redacted]` and PII-001 fires
(warning, REVIEW lane, no value shown). With no answer the text is redacted too: the gate fails
closed. Identical texts are asked once.

**Expected calls for fixtures/agency-a** (asserted in `tests/unit/test_triage.py`):

| Part | Exceptions | Calls |
|---|---|---|
| Triage, row rules (PR 8) on the defected canonical copy | 239 errors and warnings | **68** |
| PII gate (agency-a has no notes text) | 0 | **0** |
| Total today | | **68** |

The 68 come from grouping: 56 missing MBIs (MBI-003) on Medicare policies share one shape and
neighbor set, so they cost 1 call; 52 unknown statuses (STA-001) cost 11; 20 ZIP and state
mismatches (ADR-002) cost 14, one per state. Without deduplication the same run would make 239
calls. Cross-record and tie-out exceptions (PR 9 and PR 10) add at most 410 more, one per
planted defect in ground_truth.json, and far fewer after grouping. PR 12 runs the real pipeline
on the source files, which may shape values differently, so it replaces this number with the
exact count it asserts and records.

**Test cassettes.** `engine/tests/cassettes/synthetic/` holds hand-made answers for the triage and
PII shapes (model `synthetic-hand-made`). They are not recordings. They sit in a subfolder so the
pipeline, which reads `engine/tests/cassettes/`, can never replay a made-up answer. PR 12 records
the real ones.

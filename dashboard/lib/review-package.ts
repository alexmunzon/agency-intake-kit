import packetSchema from './contracts/agency-packet-v1.schema.json';
import { FILE_NAMES, parseRun, type Run, type RunFiles } from './run-loader';
import { parseReadiness, evaluateReadiness, type ReadinessPackage } from './source-readiness';
import { parseFinanceReview, type FinanceReview } from './finance-review';

type Obj = Record<string, unknown>;
export interface PinnedText { path: string; sha256: string; size_bytes: number; content: string }
interface Identity { state: string; review_state: string; record_ids: string[] }
export interface ReviewPackage {
  agency_id: string; intake_run_id: string; artifacts: PinnedText[]; run: Run;
  readiness: ReadinessPackage | null; finance: FinanceReview | null;
  identities: Identity[] | null;
}
function fail(reason: string): never { throw new Error(reason); }
function obj(x: unknown): Obj {
  if (!x || typeof x !== 'object' || Array.isArray(x)) fail('Expected an object');
  return x as Obj;
}
function exact(x: Obj, keys: string[]) {
  if (Object.keys(x).length !== keys.length || keys.some(k => !Object.hasOwn(x, k))) fail('Unsupported package fields');
}
function text(x: unknown): asserts x is string { if (typeof x !== 'string' || !x.trim()) fail('Missing scope'); }
function array(x: unknown): unknown[] { if (!Array.isArray(x)) fail('Expected a list'); return x; }
export function strictJson(source: string): unknown {
  const result: unknown = JSON.parse(source);
  let quoted = false, escaped = false, colons = 0;
  for (const c of source) {
    if (quoted) { if (escaped) escaped = false; else if (c === '\\') escaped = true; else if (c === '"') quoted = false; }
    else if (c === '"') quoted = true; else if (c === ':') colons++;
  }
  const count = (x: unknown): number => Array.isArray(x) ? x.reduce((n, v) => n + count(v), 0) : x && typeof x === 'object' ? Object.entries(x).reduce((n, [, v]) => n + 1 + count(v), 0) : 0;
  if (colons !== count(result)) fail('Duplicate JSON keys');
  return result;
}
// This validator consumes only the repository-owned contract schema, never an imported schema.
function contract(value: unknown, schema: Obj = packetSchema as Obj): void {
  if (schema.$ref) { contract(value, (packetSchema.$defs as unknown as Obj)[String(schema.$ref).split('/').pop()!] as Obj); return; }
  if (schema.anyOf) {
    if (!(schema.anyOf as Obj[]).some(s => { try { contract(value, s); return true; } catch { return false; } })) fail('Contract union mismatch');
    return;
  }
  if (Object.hasOwn(schema, 'const') && value !== schema.const) fail('Contract constant mismatch');
  if (schema.enum && !(schema.enum as unknown[]).includes(value)) fail('Contract enum mismatch');
  switch (schema.type) {
    case 'object': {
      const v = obj(value), properties = schema.properties as Obj;
      if ((schema.required as string[] ?? []).some(k => !Object.hasOwn(v, k))) fail('Missing contract field');
      for (const [k, x] of Object.entries(v)) {
        if (!Object.hasOwn(properties, k)) { if (schema.additionalProperties === false) fail('Unknown contract field'); }
        else contract(x, properties[k] as Obj);
      }
      break;
    }
    case 'array': for (const x of array(value)) contract(x, schema.items as Obj); break;
    case 'string':
      if (typeof value !== 'string' || (schema.minLength && value.length < Number(schema.minLength)) || (schema.pattern && !new RegExp(String(schema.pattern)).test(value))) fail('Invalid contract text');
      if (schema.format === 'date' && (value.startsWith('0000') || !/^\d{4}-\d{2}-\d{2}$/.test(value) || !Number.isFinite(Date.parse(value)) || new Date(value).toISOString().slice(0, 10) !== value)) fail('Invalid contract date');
      break;
    case 'integer': if (!Number.isSafeInteger(value) || (schema.minimum !== undefined && Number(value) < Number(schema.minimum))) fail('Invalid contract integer'); break;
    case 'null': if (value !== null) fail('Expected null'); break;
  }
}
// Strict CSV records for the native clean tables, including quoted newlines.
function csvRecords(source: string): Obj[] {
  const rows: string[][] = []; let row: string[] = [], field = '', quoted = false, closed = false;
  const input = source.replace(/^\uFEFF/, '');
  const endField = () => { row.push(field); field = ''; closed = false; };
  for (let i = 0; i < input.length; i++) {
    const c = input[i];
    if (quoted) {
      if (c === '"') { if (input[i + 1] === '"') { field += '"'; i++; } else { quoted = false; closed = true; } }
      else field += c;
    } else if (c === ',') endField();
    else if (c === '\n' || c === '\r') { if (c === '\r' && input[i + 1] === '\n') i++; endField(); rows.push(row); row = []; }
    else if (c === '"' && !field && !closed) quoted = true;
    else { if (closed || c === '"') fail('Malformed clean CSV'); field += c; }
  }
  if (quoted) fail('Unclosed clean CSV quote');
  if (field || row.length || closed) { endField(); rows.push(row); }
  const headers = rows.shift();
  if (!headers?.length || new Set(headers).size !== headers.length || headers.some(h => !h)) fail('Invalid clean CSV headers');
  return rows.map(values => { if (values.length !== headers.length) fail('Invalid clean CSV row width'); return Object.fromEntries(headers.map((h, i) => [h, values[i]])); });
}
async function validateNativeRows(rows: Obj[], table: 'clients' | 'policies', agency: string, run: string, artifacts: Map<string, PinnedText>) {
  if (!rows.length) return;
  const artifact = artifacts.get(`clean/${table}.csv`);
  if (!artifact) fail('Missing native clean table');
  const nativeRows = csvRecords(artifact.content);
  for (const r of rows) {
    const provenance = obj(r.provenance);
    if (provenance.artifact !== artifact.path) fail('Wrong native table provenance');
    const native = nativeRows[Number(provenance.artifact_row) - 1];
    if (!native) fail('Missing referenced native row');
    const parts = [agency, run, table, artifact.sha256, String(provenance.artifact_row)];
    const encoded = new TextEncoder().encode('[' + parts.map(x => JSON.stringify(x)).join(', ') + ']');
    const id = [...new Uint8Array(await crypto.subtle.digest('SHA-256', encoded))].map(x => x.toString(16).padStart(2, '0')).join('');
    if (id !== r.record_id) fail('Canonical record ID mismatch');
    for (const [key, value] of Object.entries(r)) {
      if (key === 'record_id' || key === 'provenance' || key === 'warnings') continue;
      if (!Object.hasOwn(native, key) || (native[key] || null) !== value) fail('Native row content mismatch');
    }
    for (const [key, value] of Object.entries(provenance)) {
      if (key === 'artifact' || key === 'artifact_row') continue;
      const nativeValue = native[`lineage_${key}`];
      if (key === 'row_number' ? !/^\d+$/.test(String(nativeValue)) || Number(nativeValue) !== value : (nativeValue || null) !== value) fail('Native lineage mismatch');
    }
    if (table === 'clients' && JSON.stringify(r.warnings ?? []) !== JSON.stringify(String(native.warnings ?? '').split('|').filter(Boolean))) fail('Native warnings mismatch');
  }
}
export async function parseReviewPackage(source: string): Promise<ReviewPackage> {
  if (source.length > 12_000_000) fail('Package exceeds 12 MB text limit');
  const root = obj(strictJson(source));
  exact(root, ['schema_version', 'data_kind', 'agency_id', 'intake_run_id', 'artifacts']);
  if (root.schema_version !== 'review-package-1' || root.data_kind !== 'synthetic') fail('Synthetic review-package-1 required');
  text(root.agency_id); text(root.intake_run_id);
  const artifacts: PinnedText[] = [];
  const paths = new Set<string>();
  for (const raw of array(root.artifacts)) {
    const a = obj(raw); exact(a, ['path', 'sha256', 'size_bytes', 'content']); text(a.path);
    if (a.path.startsWith('/') || a.path.split('/').some(x => !x || x === '.' || x === '..') || a.path.includes('\\') || paths.has(a.path)) fail('Unsafe or duplicate artifact path');
    if (typeof a.content !== 'string' || typeof a.sha256 !== 'string' || !/^[a-f0-9]{64}$/.test(a.sha256)) fail('Invalid pinned content');
    for (const c of a.content) { const n = c.codePointAt(0)!; if (n >= 0xd800 && n <= 0xdfff) fail('Invalid Unicode'); }
    const bytes = new TextEncoder().encode(a.content);
    if (a.size_bytes !== bytes.length) fail('Artifact size mismatch');
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(x => x.toString(16).padStart(2, '0')).join('');
    if (hash !== a.sha256) fail('Stale artifact hash');
    paths.add(a.path); artifacts.push(a as unknown as PinnedText);
  }
  const byPath = new Map(artifacts.map(a => [a.path, a]));
  const files = Object.fromEntries(Object.entries(FILE_NAMES).map(([key, name]) => {
    const a = byPath.get(name); if (!a) fail(`Missing ${name}`);
    if (key !== 'exceptions') strictJson(a.content); else for (const line of a.content.split('\n').filter(x => x.trim())) strictJson(line);
    return [key, a.content];
  })) as unknown as RunFiles;
  const run = parseRun(files);
  if (run.manifest.run_id !== root.intake_run_id) fail('Wrong Intake run');
  for (const input of run.manifest.inputs) {
    text(input.source); text(input.file_name);
    if (!/^[a-f0-9]{64}$/.test(input.sha256)) fail('Invalid input hash');
  }
  for (const e of run.exceptions) {
    text(e.source);
    if (e.row_number !== null && (!Number.isSafeInteger(e.row_number) || e.row_number < 1)) fail('Invalid exception row');
    if (e.raw_hash !== null && (typeof e.raw_hash !== 'string' || !/^[a-f0-9]{64}$/.test(e.raw_hash))) fail('Invalid exception hash');
  }
  for (const key of ['rows_in', 'rows_mapped', 'rows_clean'] as const) if (!Number.isSafeInteger(run.scorecard[key]) || run.scorecard[key] < 0) fail('Invalid row counts');
  const counts = run.scorecard.exceptions_by_severity;
  const failed = run.manifest.status === 'FAILED';
  if (failed !== (counts.blocker > 0) || (failed && run.scorecard.rows_clean !== 0)) fail('Blockers require failed status and no clean output');
  if ((run.manifest.status === 'PASSED') !== (counts.blocker + counts.error + counts.warning === 0)) fail('Status contradicts review evidence');
  if (run.scorecard.rows_clean > run.scorecard.rows_mapped || run.scorecard.rows_mapped > run.scorecard.rows_in) fail('Inconsistent row counts');
  let readiness: ReadinessPackage | null = null, finance: FinanceReview | null = null, identities: Identity[] | null = null;
  const readyText = byPath.get('source_readiness.json');
  if (readyText) {
    readiness = await parseReadiness(readyText.content);
    if (readiness.agency_id !== root.agency_id || readiness.intake_run_id !== root.intake_run_id) fail('Readiness scope mismatch');
    // At least one source pin must bind this readiness snapshot to actual Intake inputs.
    const inputHashes = new Set(run.manifest.inputs.map(i => i.sha256));
    const superseded = new Set(evaluateReadiness(readiness).superseded_version_ids);
    const active = readiness.versions.filter(v => !superseded.has(v.version_id));
    if (!active.length || active.some(v => !inputHashes.has(v.file_sha256))) fail('Readiness sources are not pinned Intake inputs');
  }
  const financeText = byPath.get('finance_review.json');
  if (financeText) {
    finance = parseFinanceReview(financeText.content);
    if (finance.agency_id !== root.agency_id || !finance.rows.length || finance.rows.some(r => r.lineage.run_id !== root.intake_run_id)) fail('Finance scope mismatch');
    if (!run.manifest.inputs.some(i => i.sha256 === finance!.content_sha256)) fail('Finance source is not a pinned Intake input');
  }
  const packetText = byPath.get('identity_packet.json');
  if (packetText) {
    const packet = obj(strictJson(packetText.content)); contract(packet);
    if (packet.agency_id !== root.agency_id || packet.intake_run_id !== root.intake_run_id) fail('Identity scope mismatch');
    const pins = array(packet.artifacts).map(obj);
    if (new Set(pins.map(p => p.path)).size !== pins.length || !pins.some(p => p.path === 'manifest.json')) fail('Missing or duplicate identity pins');
    for (const p of pins) { const a = byPath.get(String(p.path)); if (!a || a.sha256 !== p.sha256 || a.size_bytes !== p.size_bytes) fail('Identity evidence pin mismatch'); }
    const clients = array(packet.clients).map(obj), policies = array(packet.policies).map(obj);
    await validateNativeRows(clients, 'clients', root.agency_id, root.intake_run_id, byPath);
    await validateNativeRows(policies, 'policies', root.agency_id, root.intake_run_id, byPath);
    const rows = [...clients, ...policies];
    if (new Set(rows.map(r => r.record_id)).size !== rows.length) fail('Duplicate record ID');
    for (const r of rows) { const p = obj(r.provenance); if (p.run_id !== root.intake_run_id || !pins.some(a => a.path === p.artifact)) fail('Wrong row provenance'); }
    const ids = new Map(clients.map(c => [c.record_id, c.client_id]));
    const linked: string[] = [];
    for (const item of array(packet.identities)) {
      const i = obj(item), recordIds = i.record_ids as string[], clientIds = i.client_ids as string[];
      if (!recordIds.length || recordIds.some(r => !ids.has(r)) || new Set(clientIds).size !== new Set(recordIds.map(r => ids.get(r))).size || clientIds.some(c => !recordIds.some(r => ids.get(r) === c))) fail('Identity references mismatch');
      if (i.state === 'resolved' && (new Set(recordIds).size < 2 || i.person_id === null)) fail('Unsupported resolved identity');
      linked.push(...recordIds);
    }
    if (array(packet.identities).length && (new Set(linked).size !== linked.length || linked.length !== clients.length)) fail('Identity partition mismatch');
    identities = array(packet.identities).length ? packet.identities as Identity[] : null;
  }
  return { agency_id: root.agency_id, intake_run_id: root.intake_run_id, artifacts, run, readiness, finance, identities };
}
export function reviewSummary(p: ReviewPackage) {
  const rejected = new Set(p.run.exceptions.filter(e => e.severity === 'ERROR' && e.row_number !== null && e.raw_hash).map(e => JSON.stringify([e.source, e.row_number, e.raw_hash])));
  return {
    accepted: p.run.manifest.status === 'FAILED' ? null : p.run.scorecard.rows_clean,
    excludedEvidenceRows: rejected.size,
    unlocatedErrors: p.run.exceptions.filter(e => e.severity === 'ERROR' && (e.row_number === null || e.raw_hash === null)).length,
    readiness: p.readiness ? evaluateReadiness(p.readiness) : null,
    unresolvedIdentities: p.identities ? p.identities.filter(i => i.state !== 'resolved').length : null,
    pendingIdentityReviews: p.identities ? p.identities.filter(i => i.review_state !== 'approved').length : null,
  };
}

/** A run is immutable. Explicit Clear is required before replacing its evidence pins. */
export function assertReviewPackageContinuity(previous: ReviewPackage, next: ReviewPackage): void {
  if (previous.agency_id !== next.agency_id || previous.intake_run_id !== next.intake_run_id) return;
  const pins = new Map(next.artifacts.map(a => [a.path, a]));
  for (const artifact of previous.artifacts) {
    const replacement = pins.get(artifact.path);
    if (!replacement || replacement.sha256 !== artifact.sha256 || replacement.size_bytes !== artifact.size_bytes) fail('Existing snapshot evidence changed or disappeared; clear the view before loading a different snapshot');
  }
}

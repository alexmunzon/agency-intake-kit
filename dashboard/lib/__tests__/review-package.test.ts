import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { describe, expect, it } from 'vitest';
import { assertReviewPackageContinuity, parseReviewPackage, reviewSummary, strictJson } from '../review-package';

const pin = (path: string, content: string) => ({ path, content, size_bytes: new TextEncoder().encode(content).length, sha256: createHash('sha256').update(content).digest('hex') });
function bundle() {
  return { schema_version: 'review-package-1', data_kind: 'synthetic', agency_id: 'synthetic-agency-a', intake_run_id: 'demo', artifacts: ['manifest.json', 'scorecard.json', 'exceptions.jsonl', 'rts_coverage.json'].map(path => pin(path, readFileSync(`public/demo-run/${path}`, 'utf8'))) };
}
function change(b: ReturnType<typeof bundle>, path: string, fn: (x: Record<string, unknown>) => void) {
  const index = b.artifacts.findIndex(a => a.path === path), value = JSON.parse(b.artifacts[index].content); fn(value); b.artifacts[index] = pin(path, JSON.stringify(value));
}
describe('bound review package', () => {
  it('loads real synthetic run evidence without inventing other streams', async () => {
    const p = await parseReviewPackage(JSON.stringify(bundle()));
    const s = reviewSummary(p);
    expect(s.accepted).toBe(12833); expect(s.excludedEvidenceRows).toBeGreaterThan(0);
    expect(s.readiness).toBeNull(); expect(s.unresolvedIdentities).toBeNull(); expect(p.finance).toBeNull();
  });
  it('refuses a rehashed wrong run', async () => {
    const b = bundle(); b.intake_run_id = 'other';
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Wrong Intake run');
  });
  it('refuses altered bytes even when JSON is valid', async () => {
    const b = bundle(); b.artifacts[0].content += ' ';
    b.artifacts[0].size_bytes++;
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Stale artifact hash');
  });
  it.each(['../manifest.json', '/manifest.json', 'clean/../x'])('refuses unsafe path %s', async path => {
    const b = bundle(); b.artifacts[0].path = path;
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Unsafe');
  });
  it('refuses duplicate keys including escaped equivalents', () => {
    expect(() => strictJson('{"x":1,"\\u0078":2}')).toThrow('Duplicate');
  });
  it('refuses impossible accepted counts', async () => {
    const b = bundle(); change(b, 'scorecard.json', s => { s.rows_clean = 999999; });
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Inconsistent row counts');
  });
  it('refuses a separate readiness example even if caller relabels its agency and run', async () => {
    const b = bundle(), r = JSON.parse(readFileSync('../fixtures/source-readiness/current.json', 'utf8'));
    r.agency_id = b.agency_id; r.intake_run_id = b.intake_run_id;
    for (const x of [...r.expected_inventory, ...r.versions]) x.agency_id = b.agency_id;
    b.artifacts.push(pin('source_readiness.json', JSON.stringify(r)));
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('not pinned Intake inputs');
  });
  it('refuses missing evidence rather than substituting bundled demo artifacts', async () => {
    const b = bundle(); b.artifacts.pop();
    await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Missing rts_coverage');
  });
});

function withIdentity() {
 const b = bundle();
 const clients = ['a', 'b'].map(id => ({ record_id: id, client_id: id, first_name: null, last_name: null, dob: null, mbi: null, phone: null, email: null, address_line1: null, city: null, state: null, zip: null, household_id: null, warnings: [], provenance: { source_file: 'clients.csv', sheet: null, row_number: 1, raw_hash: 'a'.repeat(64), run_id: 'demo', mapping_version: '1', artifact: 'clean/clients.csv', artifact_row: 1 } }));
 const headers = [...Object.keys(clients[0]).filter(k => !['record_id', 'provenance', 'warnings'].includes(k)), ...Object.keys(clients[0].provenance).filter(k => !['artifact', 'artifact_row'].includes(k)).map(k => 'lineage_' + k), 'warnings'];
 const csv = headers.join(',') + '\n' + clients.map((c, i) => {
   c.provenance.artifact_row = i + 1;
   const values: Record<string, unknown> = {...c, ...Object.fromEntries(Object.entries(c.provenance).map(([k, v]) => ['lineage_' + k, v])), warnings: ''};
   return headers.map(k => values[k] ?? '').join(',');
 }).join('\n') + '\n';
 const native = pin('clean/clients.csv', csv); b.artifacts.push(native);
 for (const [i, c] of clients.entries()) c.record_id = createHash('sha256').update('[' + [b.agency_id, 'demo', 'clients', native.sha256, String(i + 1)].map(x => JSON.stringify(x)).join(', ') + ']').digest('hex');
 const p = { schema_version: '1.0.0', data_kind: 'synthetic', agency_id: b.agency_id, run_id: 'bob-1', intake_run_id: 'demo', artifacts: b.artifacts.filter(a => ['manifest.json', 'clean/clients.csv'].includes(a.path)).map(({path,sha256,size_bytes}) => ({path,sha256,size_bytes})), clients, policies: [], identities: [{ person_id: null, record_ids: [clients[0].record_id], client_ids: ['a'], state: 'unresolved', review_state: 'needs_review', reasons: [] }, { person_id: null, record_ids: [clients[1].record_id], client_ids: ['b'], state: 'unsupported', review_state: 'blocked', reasons: [] }], issues: [] };
 b.artifacts.push(pin('identity_packet.json', JSON.stringify(p))); return b;
}
describe('optional bound evidence', () => {
 it('counts a complete unresolved identity partition and preserves its review state', async () => {
  const summary = reviewSummary(await parseReviewPackage(JSON.stringify(withIdentity())));
  expect(summary.unresolvedIdentities).toBe(2); expect(summary.pendingIdentityReviews).toBe(2);
 });
 it('refuses an identity packet with changed evidence pins', async () => {
  const b = withIdentity(); change(b, 'identity_packet.json', p => { (p.artifacts as {sha256: string}[])[0].sha256 = '0'.repeat(64); });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('pin mismatch');
 });
 it('refuses identity references outside the bound client partition', async () => {
  const b = withIdentity(); change(b, 'identity_packet.json', p => { (p.identities as {record_ids: string[]}[])[0].record_ids = ['outside']; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('references mismatch');
 });
 it('refuses malformed native schema fields', async () => {
  const b = withIdentity(); change(b, 'identity_packet.json', p => { (p.clients as {dob: string}[])[0].dob = '2026-02-31'; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Contract union');
 });
 it('shows real signed finance totals only when source and lineage bind', async () => {
  const b = bundle(), f = JSON.parse(readFileSync('public/demo-finance.json', 'utf8'));
  f.agency_id = b.agency_id; for (const row of f.rows) row.lineage.run_id = 'demo';
  change(b, 'manifest.json', m => { (m.inputs as {sha256: string}[])[0].sha256 = f.content_sha256; });
  b.artifacts.push(pin('finance_review.json', JSON.stringify(f)));
  const parsed = await parseReviewPackage(JSON.stringify(b)); expect(parsed.finance?.statement_total).toBe(f.statement_total);
  change(b, 'finance_review.json', x => { (x.rows as {lineage: {run_id: string}}[])[0].lineage.run_id = 'wrong'; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Finance scope');
 });
 it('derives source freshness only from pinned input evidence', async () => {
  const b = bundle(), r = JSON.parse(readFileSync('../fixtures/source-readiness/current.json', 'utf8'));
  r.agency_id = b.agency_id; r.intake_run_id = b.intake_run_id;
  for (const x of [...r.expected_inventory, ...r.versions]) x.agency_id = b.agency_id;
  change(b, 'manifest.json', m => { (m.inputs as {sha256: string}[])[0].sha256 = r.versions[0].file_sha256; });
  b.artifacts.push(pin('source_readiness.json', JSON.stringify(r)));
  expect(reviewSummary(await parseReviewPackage(JSON.stringify(b))).readiness?.state).toBe('current');
 });
});

 it('preserves existing same-run pins until the user explicitly clears the view', async () => {
  const original = await parseReviewPackage(JSON.stringify(bundle()));
  const changed = bundle(); change(changed, 'manifest.json', m => { m.engine_version = 'changed'; });
  const parsed = await parseReviewPackage(JSON.stringify(changed));
  expect(() => assertReviewPackageContinuity(original, parsed)).toThrow('changed or disappeared');
  expect(() => assertReviewPackageContinuity(original, original)).not.toThrow();
 });

 it('refuses an identity packet whose claimed row points beyond native evidence', async () => {
  const b = withIdentity(); change(b, 'identity_packet.json', p => { (p.clients as {provenance: {artifact_row: number}}[])[0].provenance.artifact_row = 999999; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Missing referenced native row');
 });
 it('refuses changed native client claims even with valid envelope hashes', async () => {
  const b = withIdentity(); change(b, 'identity_packet.json', p => { (p.clients as {first_name: string}[])[0].first_name = 'Invented'; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Native row content mismatch');
 });

 it('refuses a passed run that contains blocker evidence', async () => {
  const b = bundle(), index = b.artifacts.findIndex(a => a.path === 'exceptions.jsonl');
  const rows = b.artifacts[index].content.split('\n').filter(Boolean).map(x => JSON.parse(x));
  const previous = rows[0].severity.toLowerCase(); rows[0].severity = 'BLOCKER';
  b.artifacts[index] = pin('exceptions.jsonl', rows.map(x => JSON.stringify(x)).join('\n') + '\n');
  change(b, 'scorecard.json', s => { const c = s.exceptions_by_severity as Record<string, number>; c[previous]--; c.blocker++; });
  await expect(parseReviewPackage(JSON.stringify(b))).rejects.toThrow('Blockers require');
 });
 it('retains superseded readiness evidence while binding the active source to Intake', async () => {
  const b = bundle(), r = JSON.parse(readFileSync('../fixtures/source-readiness/corrected.json', 'utf8'));
  r.agency_id = b.agency_id; r.intake_run_id = b.intake_run_id;
  for (const x of [...r.expected_inventory, ...r.versions]) x.agency_id = b.agency_id;
  const current = r.versions.find((v: {version_id: string}) => v.version_id === 'v2');
  change(b, 'manifest.json', m => { (m.inputs as {sha256: string}[])[0].sha256 = current.file_sha256; });
  b.artifacts.push(pin('source_readiness.json', JSON.stringify(r)));
  const p = await parseReviewPackage(JSON.stringify(b));
  expect(p.readiness?.versions).toHaveLength(2);
  expect(reviewSummary(p).readiness?.state).toBe('current');
 });

 it('keeps the browser contract mirror identical to the canonical adapter schema', () => {
  expect(readFileSync('lib/contracts/agency-packet-v1.schema.json', 'utf8')).toBe(readFileSync('../docs/contracts/agency-packet-v1.schema.json', 'utf8'));
 });

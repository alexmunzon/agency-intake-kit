import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { assertReadinessContinuity, evaluateReadiness, parseReadiness } from '../source-readiness';

const fixture = (name: string) => readFileSync(resolve('../fixtures/source-readiness', `${name}.json`), 'utf8');
describe('source readiness boundary', () => {
  it.each([
    ['current', 'current', true], ['missing', 'missing', false], ['stale', 'stale', false],
    ['unknown', 'unknown', false], ['wrong-period', 'missing', false],
    ['conflicting', 'conflicting', false], ['no-inventory', 'unknown', false],
  ])('%s', async (name, state, complete) => {
    const summary = evaluateReadiness(await parseReadiness(fixture(name as string)));
    expect(summary.state).toBe(state);
    expect(summary.complete).toBe(complete);
  });
  it('retains duplicates without increasing coverage', async () => {
    const data = await parseReadiness(fixture('duplicate'));
    expect(data.receipts).toHaveLength(2);
    const result = evaluateReadiness(data);
    expect(result.current_count).toBe(1);
    expect(result.duplicate_receipt_count).toBe(1);
  });
  it('retains original evidence and superseded reference', async () => {
    const data = await parseReadiness(fixture('corrected'));
    const result = evaluateReadiness(data);
    expect(data.evidence).toHaveLength(2);
    expect(result.superseded_version_ids).toEqual(['v1']);
    expect(result.entries[0].active_version_ids).toEqual(['v2']);
  });
  it('requires an explicit freshness cutoff even for a dated delivery', async () => {
    const data = JSON.parse(fixture('current'));
    data.expected_inventory[0].minimum_source_date = null;
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('unknown');
    expect(result.complete).toBe(false);
  });
  it('cannot establish completeness with an empty inventory', async () => {
    const data = JSON.parse(fixture('current'));
    data.expected_inventory = [];
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('unknown');
    expect(result.complete).toBe(false);
    expect(result.unexpected_version_ids).toEqual(['v1']);
  });
  it('keeps duplicate aliases of corrected evidence superseded', async () => {
    const data = JSON.parse(fixture('corrected'));
    data.versions.push({ ...data.versions[0], version_id: 'v1-copy', file_name: 'renamed.csv' });
    data.receipts.push({ ...data.receipts[0], receipt_id: 'r-copy', version_id: 'v1-copy' });
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('current');
    expect(result.superseded_version_ids).toEqual(['v1', 'v1-copy']);
    expect(result.entries[0].active_version_ids).toEqual(['v2']);
    expect(result.receipt_count).toBe(3);
    expect(result.duplicate_receipt_count).toBe(1);
  });
  it('recognizes correction aliases through equivalent parent aliases', async () => {
    const data = JSON.parse(fixture('corrected'));
    data.versions.push(
      { ...data.versions[0], version_id: 'alias-v1' },
      { ...data.versions[1], version_id: 'alias-v2', supersedes_version_id: 'alias-v1' },
      { ...data.versions[0], version_id: 'v3', supersedes_version_id: 'v2' },
    );
    for (const version_id of ['alias-v1', 'alias-v2', 'v3']) {
      data.receipts.push({ ...data.receipts[0], receipt_id: `r-${version_id}`, version_id });
    }
    // Parent references may precede their declarations in the imported JSON.
    data.versions.reverse();
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('current');
    expect(result.superseded_version_ids).toEqual(['alias-v1', 'alias-v2', 'v1', 'v2']);
    expect(result.entries[0].active_version_ids).toEqual(['v3']);
    expect(result.duplicate_receipt_count).toBe(2);
  });
  it('retains a delivered same-byte correction as a distinct generation', async () => {
    const data = JSON.parse(fixture('corrected'));
    data.versions[1].file_sha256 = data.versions[0].file_sha256;
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('current');
    expect(result.superseded_version_ids).toEqual(['v1']);
    expect(result.entries[0].active_version_ids).toEqual(['v2']);
    expect(result.duplicate_receipt_count).toBe(0);
  });
  it('keeps competing corrections conflicting and retains their original receipts', async () => {
    const data = JSON.parse(fixture('corrected'));
    data.versions.push({ ...data.versions[0], version_id: 'v3', supersedes_version_id: 'v1' });
    data.receipts.push({ ...data.receipts[1], receipt_id: 'r-v3', version_id: 'v3', received_at: '2026-10-03T12:00:00Z' });
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.state).toBe('conflicting');
    expect(result.entries[0].active_version_ids).toEqual(['v2', 'v3']);
    expect(result.entries[0].receipt_ids).toEqual(['r-v2', 'r-v3', 'r1']);
  });
  it('does not let an undelivered correction replace a delivery', async () => {
    const data = JSON.parse(fixture('corrected'));
    data.receipts = [data.receipts[0]];
    const result = evaluateReadiness(await parseReadiness(JSON.stringify(data)));
    expect(result.entries[0].active_version_ids).toEqual(['v1']);
    expect(result.superseded_version_ids).toEqual([]);
  });
  it.each(['BAD', 'g'.repeat(64), 'F'.repeat(64), 'f'.repeat(63)])('refuses malformed file hash %s', async hash => {
    const data = JSON.parse(fixture('current'));
    data.versions[0].file_sha256 = hash;
    await expect(parseReadiness(JSON.stringify(data))).rejects.toThrow();
  });
  it('compares receipt timestamps at contract microsecond precision', async () => {
    const data = JSON.parse(fixture('current'));
    data.as_of = '2026-10-07T12:00:00.000000Z';
    data.receipts[0].received_at = '2026-10-07T07:00:00.000001-05:00';
    await expect(parseReadiness(JSON.stringify(data))).rejects.toThrow();
    data.receipts[0].received_at = '2026-10-07T07:00:00.000000-05:00';
    await expect(parseReadiness(JSON.stringify(data))).resolves.toBeDefined();
  });
  it('refuses lone Unicode surrogates rather than hashing replacement bytes', async () => {
    const data = JSON.parse(fixture('current'));
    data.evidence[0].content = '\ud800';
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data.evidence[0].content));
    const replacementHash = [...new Uint8Array(digest)].map(v => v.toString(16).padStart(2, '0')).join('');
    data.evidence[0].sha256 = replacementHash;
    data.versions[0].file_sha256 = replacementHash;
    await expect(parseReadiness(JSON.stringify(data))).rejects.toThrow();
  });
  it.each(['2026-02-30', 'unknown', '', 1791381557])('refuses invalid date %s', async (date) => {
    const data = JSON.parse(fixture('current'));
    data.versions[0].source_date = date;
    await expect(parseReadiness(JSON.stringify(data))).rejects.toThrow();
  });
  it.each(['hash', 'duplicate-key', 'unknown-field', 'dangling', 'cycle', 'agency', 'receipt-id', 'time'])('refuses malformed %s', async kind => {
    const data = JSON.parse(fixture('current'));
    if (kind === 'hash') data.evidence[0].content = 'tampered';
    if (kind === 'unknown-field') data.complete = true;
    if (kind === 'dangling') data.versions[0].supersedes_version_id = 'missing';
    if (kind === 'cycle') data.versions[0].supersedes_version_id = 'v1';
    if (kind === 'agency') data.versions[0].agency_id = 'other';
    if (kind === 'receipt-id') data.receipts.push(data.receipts[0]);
    if (kind === 'time') data.receipts[0].received_at = '2026-10-01T12:00:00';
    const text = kind === 'duplicate-key' ? fixture('current').replace('"schema_version": "1.0.0"', '"schema_version": "1.0.0", "schema_version": "1.0.0"') : JSON.stringify(data);
    await expect(parseReadiness(text)).rejects.toThrow();
  });
});

describe('same-run readiness continuity', () => {
  it('accepts idempotent imports, appended corrections and duplicate receipts', async () => {
    const previous = await parseReadiness(fixture('current'));
    expect(() => assertReadinessContinuity(previous, structuredClone(previous))).not.toThrow();
    const incoming = await parseReadiness(fixture('corrected'));
    incoming.receipts.push({ ...incoming.receipts[0], receipt_id: 'duplicate-r1' });
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
  });
  it('accepts reordered fields/history and equivalent timestamp formatting', async () => {
    const previous = await parseReadiness(fixture('corrected'));
    const source = structuredClone(previous);
    source.versions.reverse(); source.receipts.reverse(); source.evidence.reverse();
    source.receipts[0].received_at = '2026-10-02T07:00:00.000000-05:00';
    source.receipts[1].received_at = '2026-10-01T12:00:00+00:00';
    const reordered = JSON.stringify(source, (_, value) => value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).reverse()) : value);
    const incoming = await parseReadiness(reordered);
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
    incoming.receipts[0].received_at = '2026-10-02T07:00:00.000001-05:00';
    expect(() => assertReadinessContinuity(previous, incoming)).toThrow(/retained history/);
  });
  it.each(['rewrite-version', 'rewrite-receipt', 'drop-version', 'drop-receipt', 'drop-evidence'])('refuses %s even when the package is independently valid', async kind => {
    const previous = await parseReadiness(fixture('current'));
    previous.evidence.push((await parseReadiness(fixture('corrected'))).evidence[1]);
    const source = structuredClone(previous);
    if (kind === 'rewrite-version') source.versions[0].file_name = 'renamed-history.csv';
    if (kind === 'rewrite-receipt') source.receipts[0].owner = 'Rewritten receipt owner';
    if (kind === 'drop-version') { source.versions = []; source.receipts = []; }
    if (kind === 'drop-receipt') source.receipts = [];
    if (kind === 'drop-evidence') source.evidence.pop();
    const incoming = await parseReadiness(JSON.stringify(source));
    expect(() => assertReadinessContinuity(previous, incoming)).toThrow(/retained history/);
  });
  it('allows changed expected planning metadata and inventory', async () => {
    const previous = await parseReadiness(fixture('current'));
    const incoming = structuredClone(previous);
    incoming.expected_inventory![0].owner = 'New planning owner';
    incoming.expected_inventory![0].next_action = 'New planning action';
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
    incoming.expected_inventory = [];
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
  });
  it('rejects backward clocks and changed existing Intake links', async () => {
    const previous = await parseReadiness(fixture('current'));
    const incoming = structuredClone(previous);
    incoming.as_of = '2026-10-06T12:00:00Z';
    expect(() => assertReadinessContinuity(previous, incoming)).toThrow(/snapshot backwards/);
    incoming.as_of = previous.as_of;
    incoming.intake_run_id = 'intake-linked';
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
    previous.intake_run_id = 'intake-linked';
    incoming.intake_run_id = 'other-intake';
    expect(() => assertReadinessContinuity(previous, incoming)).toThrow(/Intake link/);
    incoming.intake_run_id = null;
    expect(() => assertReadinessContinuity(previous, incoming)).toThrow(/Intake link/);
  });
  it('allows an explicit switch to a different run or agency', async () => {
    const previous = await parseReadiness(fixture('corrected'));
    const incoming = await parseReadiness(fixture('missing'));
    incoming.run_id = 'next-run';
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
    incoming.run_id = previous.run_id;
    incoming.agency_id = 'next-agency';
    expect(() => assertReadinessContinuity(previous, incoming)).not.toThrow();
  });
});

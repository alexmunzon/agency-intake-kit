// Readiness extension of Session 1's 1.0.0 artifact contract. File hashes are not row hashes.
export interface Scope { agency_id: string; carrier: string; file_type: string; period: string }
export interface ExpectedFile extends Scope { minimum_source_date: string | null; owner: string | null; next_action: string | null }
export interface FileVersion extends Scope { version_id: string; source_date: string | null; file_name: string; file_sha256: string; supersedes_version_id: string | null }
export interface Receipt { receipt_id: string; version_id: string; received_at: string; owner: string | null; next_action: string | null }
export interface ReadinessPackage {
  artifact_type: 'source_readiness'; schema_version: '1.0.0'; data_kind: 'synthetic';
  agency_id: string; run_id: string; intake_run_id: string | null; as_of: string;
  expected_inventory: ExpectedFile[] | null; versions: FileVersion[]; receipts: Receipt[];
  evidence: { sha256: string; content: string }[];
}
export type ReadinessState = 'missing' | 'stale' | 'current' | 'conflicting' | 'unknown';
export interface CoverageEntry { expected: ExpectedFile; state: ReadinessState; reason: string; active_version_ids: string[]; receipt_ids: string[] }
const scopeKey = (s: Scope) => JSON.stringify([s.agency_id, s.carrier, s.file_type, s.period]);
function refuse(): never { throw new Error('Invalid or unsupported readiness package. Previous package preserved.'); }
function object(value: unknown): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) refuse();
  return value as Record<string, unknown>;
}
function keys(o: Record<string, unknown>, required: string[]) {
  if (Object.keys(o).length !== required.length || required.some(k => !Object.hasOwn(o, k))) refuse();
}
function text(value: unknown): asserts value is string { if (typeof value !== 'string' || !value.trim()) refuse(); }
function optionalText(value: unknown) { if (value !== null) text(value); }
function hash(value: unknown) { if (typeof value !== 'string' || !/^[a-f0-9]{64}$/.test(value)) refuse(); }
function date(value: unknown) {
  if (value === null) return;
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith('0000')) refuse();
  const parsed = new Date(value + 'T00:00:00Z');
  if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== value) refuse();
}
function timestamp(value: unknown) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,6})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value) || !Number.isFinite(Date.parse(value))) refuse();
  date(value.slice(0, 10));
}
// Date.parse retains milliseconds; the contract accepts six fractional digits.
function timestampMicros(value: string): bigint {
  const fraction = /\.(\d{1,6})/.exec(value)?.[1] ?? '';
  return BigInt(Date.parse(value)) * BigInt(1000) + BigInt(fraction.padEnd(6, '0').slice(3));
}
function scope(value: Record<string, unknown>) {
  for (const k of ['agency_id', 'carrier', 'file_type']) text(value[k]);
  if (typeof value.period !== 'string' || !/^[0-9]{4}-(0[1-9]|1[0-2])$/.test(value.period)) refuse();
}
function array(value: unknown): unknown[] { if (!Array.isArray(value)) refuse(); return value; }
function unique(values: string[]) { if (new Set(values).size !== values.length) refuse(); }
// Count structural keys before parsing: JSON.parse alone silently discards duplicate keys.
function structuralKeys(source: string) {
  let quoted = false, escaped = false, count = 0;
  for (const char of source) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === ':') count++;
  }
  return count;
}
function countKeys(value: unknown): number {
  if (Array.isArray(value)) return value.reduce((n, v) => n + countKeys(v), 0);
  if (value && typeof value === 'object') return Object.keys(value).length + Object.values(value).reduce<number>((n, v) => n + countKeys(v), 0);
  return 0;
}
export async function parseReadiness(source: string): Promise<ReadinessPackage> {
  const raw: unknown = JSON.parse(source);
  if (structuralKeys(source) !== countKeys(raw)) refuse();
  const p = object(raw);
  keys(p, ['artifact_type', 'schema_version', 'data_kind', 'agency_id', 'run_id', 'intake_run_id', 'as_of', 'expected_inventory', 'versions', 'receipts', 'evidence']);
  if (p.artifact_type !== 'source_readiness' || p.schema_version !== '1.0.0' || p.data_kind !== 'synthetic') refuse();
  text(p.agency_id); text(p.run_id); optionalText(p.intake_run_id); timestamp(p.as_of);
  const scopeFields = ['agency_id', 'carrier', 'file_type', 'period'];
  for (const item of p.expected_inventory === null ? [] : array(p.expected_inventory)) {
    const v = object(item); keys(v, [...scopeFields, 'minimum_source_date', 'owner', 'next_action']);
    scope(v); date(v.minimum_source_date); optionalText(v.owner); optionalText(v.next_action);
  }
  for (const item of array(p.versions)) {
    const v = object(item); keys(v, [...scopeFields, 'version_id', 'source_date', 'file_name', 'file_sha256', 'supersedes_version_id']);
    scope(v); text(v.version_id); date(v.source_date); text(v.file_name); hash(v.file_sha256); optionalText(v.supersedes_version_id);
  }
  for (const item of array(p.receipts)) {
    const r = object(item); keys(r, ['receipt_id', 'version_id', 'received_at', 'owner', 'next_action']);
    text(r.receipt_id); text(r.version_id); timestamp(r.received_at); optionalText(r.owner); optionalText(r.next_action);
  }
  for (const item of array(p.evidence)) {
    const e = object(item); keys(e, ['sha256', 'content']); hash(e.sha256);
    if (typeof e.content !== 'string') refuse();
    // TextEncoder replaces lone surrogates. Refuse them instead of hashing bytes
    // different from the imported JSON string's claimed UTF-8 source evidence.
    for (const char of e.content) {
      const point = char.codePointAt(0)!;
      if (point >= 0xd800 && point <= 0xdfff) refuse();
    }
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(e.content));
    if ([...new Uint8Array(digest)].map(v => v.toString(16).padStart(2, '0')).join('') !== e.sha256) refuse();
  }
  const data = raw as ReadinessPackage;
  unique((data.expected_inventory ?? []).map(scopeKey)); unique(data.versions.map(v => v.version_id));
  unique(data.receipts.map(r => r.receipt_id)); unique(data.evidence.map(e => e.sha256));
  const versions = new Map(data.versions.map(v => [v.version_id, v]));
  const hashes = new Set(data.evidence.map(e => e.sha256));
  if ([...data.versions, ...(data.expected_inventory ?? [])].some(v => v.agency_id !== data.agency_id)) refuse();
  for (const v of data.versions) {
    if (!hashes.has(v.file_sha256) || (v.source_date !== null && v.source_date > data.as_of.slice(0, 10))) refuse();
    const seen = new Set([v.version_id]);
    let parent = v.supersedes_version_id;
    while (parent !== null) {
      if (seen.has(parent) || !versions.has(parent)) refuse();
      seen.add(parent);
      const previous = versions.get(parent)!;
      if (scopeKey(previous) !== scopeKey(v)) refuse();
      parent = previous.supersedes_version_id;
    }
  }
  for (const r of data.receipts) if (!versions.has(r.version_id) || timestampMicros(r.received_at) > timestampMicros(data.as_of)) refuse();
  return data;
}
export function assertReadinessContinuity(previous: ReadinessPackage, incoming: ReadinessPackage): void {
  if (previous.agency_id !== incoming.agency_id || previous.run_id !== incoming.run_id) return;
  function retained<T extends object>(before: T[], after: T[], identity: (item: T) => string,
    value: (item: T, key: keyof T) => unknown = (item, key) => item[key]) {
    const records = new Map(after.map(item => [identity(item), item]));
    for (const item of before) {
      const replacement = records.get(identity(item));
      if (!replacement || Object.keys(item).some(key => value(item, key as keyof T) !== value(replacement, key as keyof T))) {
        throw new Error('Same-run import deletes or rewrites retained history. Previous package preserved.');
      }
    }
  }
  retained(previous.versions, incoming.versions, v => v.version_id);
  retained(previous.receipts, incoming.receipts, r => r.receipt_id,
    (r, key) => key === 'received_at' ? timestampMicros(r.received_at) : r[key]);
  retained(previous.evidence, incoming.evidence, e => e.sha256);
  if (timestampMicros(incoming.as_of) < timestampMicros(previous.as_of) ||
      (previous.intake_run_id !== null && incoming.intake_run_id !== previous.intake_run_id)) {
    throw new Error('Same-run import moves the snapshot backwards or changes its Intake link. Previous package preserved.');
  }
}
export function evaluateReadiness(p: ReadinessPackage) {
  const delivered = new Set(p.receipts.map(r => r.version_id));
  const versions = new Map(p.versions.map(v => [v.version_id, v]));
  // Aliases share evidence and equivalent ancestry, even when parent IDs differ.
  // Including the parent group keeps a same-byte correction a new generation.
  const versionGroups = new Map<string, number>();
  const groups = new Map<string, number>();
  for (const version of p.versions) {
    const trail: FileVersion[] = [];
    let current: FileVersion | undefined = version;
    while (current && !versionGroups.has(current.version_id)) {
      trail.push(current);
      current = current.supersedes_version_id === null ? undefined : versions.get(current.supersedes_version_id);
    }
    while (trail.length) {
      const v = trail.pop()!;
      const parentGroup = v.supersedes_version_id === null ? null : versionGroups.get(v.supersedes_version_id)!;
      const signature = JSON.stringify([scopeKey(v), v.file_sha256, v.source_date, parentGroup]);
      if (!groups.has(signature)) groups.set(signature, groups.size);
      versionGroups.set(v.version_id, groups.get(signature)!);
    }
  }
  const superseded = new Set<string>();
  for (const id of delivered) {
    let parent = versions.get(id)!.supersedes_version_id;
    while (parent !== null) { superseded.add(parent); parent = versions.get(parent)!.supersedes_version_id; }
  }
  const replaced = new Set([...superseded].map(id => versionGroups.get(id)!));
  for (const v of p.versions) if (replaced.has(versionGroups.get(v.version_id)!)) superseded.add(v.version_id);
  const entries: CoverageEntry[] = (p.expected_inventory ?? []).map(expected => {
    const active = p.versions.filter(v => scopeKey(v) === scopeKey(expected) && delivered.has(v.version_id) && !superseded.has(v.version_id)).sort((a, b) => a.version_id < b.version_id ? -1 : a.version_id > b.version_id ? 1 : 0);
    const distinct = new Set(active.map(v => JSON.stringify([v.file_sha256, v.source_date])));
    let state: ReadinessState, reason: string;
    if (!active.length) { state = 'missing'; reason = 'No delivery for this exact agency, carrier, type and period.'; }
    else if (distinct.size > 1) { state = 'conflicting'; reason = 'Multiple active versions require an explicit correction.'; }
    else if (expected.minimum_source_date === null || active[0].source_date === null) { state = 'unknown'; reason = 'Source date or freshness cutoff is unknown.'; }
    else if (active[0].source_date < expected.minimum_source_date) { state = 'stale'; reason = 'Source date is earlier than the required cutoff.'; }
    else { state = 'current'; reason = 'Delivered source meets the explicit freshness cutoff.'; }
    return { expected, state, reason, active_version_ids: active.map(v => v.version_id), receipt_ids: p.receipts.filter(r => scopeKey(versions.get(r.version_id)!) === scopeKey(expected)).map(r => r.receipt_id).sort() };
  });
  const priority: ReadinessState[] = ['conflicting', 'missing', 'unknown', 'stale'];
  const state: ReadinessState = !entries.length ? 'unknown' : priority.find(s => entries.some(e => e.state === s)) ?? 'current';
  const scopes = new Set((p.expected_inventory ?? []).map(scopeKey));
  const distinctReceipts = new Set(p.receipts.map(r => versionGroups.get(r.version_id)!));
  return {
    state, complete: !!entries.length && state === 'current', expected_count: entries.length,
    current_count: entries.filter(e => e.state === 'current').length, receipt_count: p.receipts.length,
    duplicate_receipt_count: p.receipts.length - distinctReceipts.size, entries,
    unexpected_version_ids: p.versions.filter(v => !scopes.has(scopeKey(v))).map(v => v.version_id).sort(),
    superseded_version_ids: [...superseded].sort(),
  };
}

'use client';

import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { CARD } from '@/components/tiles';
import { assertReadinessContinuity, evaluateReadiness, parseReadiness, type ReadinessPackage } from '@/lib/source-readiness';

const FIELD = 'w-full rounded border border-input bg-background p-2 text-sm';
const WORDS = 'min-w-0 break-words [overflow-wrap:anywhere]';
const UNKNOWN = 'Not supplied';
export function SourceReadiness() {
  const [data, setData] = useState<ReadinessPackage | null>(null);
  const [source, setSource] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const currentData = useRef<ReadinessPackage | null>(null);
  const result = data ? evaluateReadiness(data) : null;
  function replaceData(next: ReadinessPackage | null) {
    currentData.current = next;
    setData(next);
  }
  async function load(read: () => Promise<string>) {
    const id = ++generation.current;
    setBusy(true); setError(null);
    try {
      const parsed = await parseReadiness(await read());
      if (generation.current === id) {
        if (currentData.current) assertReadinessContinuity(currentData.current, parsed);
        replaceData(parsed);
      }
    } catch {
      if (generation.current === id) setError('Import refused. Invalid JSON, schema, dates, correction references, evidence hash or changed/removed history. Previous package preserved.');
    } finally { if (generation.current === id) setBusy(false); }
  }
  function clear() {
    generation.current++; replaceData(null); setError(null); setBusy(false); setSource('');
  }
  function download() {
    if (!data) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2) + '\n'], { type: 'application/json' }));
    const link = document.createElement('a'); link.href = url; link.download = 'source_readiness.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function update(index: number, key: 'owner' | 'next_action', value: string) {
    const old = currentData.current;
    if (old?.expected_inventory) replaceData({ ...old, expected_inventory: old.expected_inventory.map((e, i) => i === index ? { ...e, [key]: value.trim() ? value : null } : e) });
  }
  return <div className={`space-y-6 ${WORDS}`}>
    <header className="space-y-2">
      <p className="text-sm text-muted-foreground">Synthetic data only · Source readiness</p>
      <h1 className="text-3xl font-semibold">Are the expected files ready?</h1>
      <p>Coverage matches agency, carrier, file type and period. Freshness uses the source date and an explicit cutoff, never the delivery time.</p>
      <p className="text-sm text-muted-foreground">Browser memory only. Refreshing or leaving this page clears the view and edits. Download a package to keep it on your device. There is no hosted storage or authenticated approval.</p>
    </header>
    <section aria-label="Load readiness package" className={`${CARD} space-y-3 p-4`}>
      <p className="text-sm">Imports into the same agency and readiness run must retain all version, receipt and evidence history. A different agency or run switches the package. Clearing the view allows a fresh snapshot.</p>
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm">Import synthetic package<input type="file" accept=".json,application/json" disabled={busy} className="block w-full max-w-72 text-sm" onChange={event => {
          const file = event.target.files?.[0]; event.target.value = '';
          if (file) void load(() => file.text());
        }} /></label>
        <Button variant="outline" disabled={busy} onClick={() => void load(async () => {
          const response = await fetch('/source-readiness/demo.json'); if (!response.ok) throw new Error(); return response.text();
        })}>Load synthetic example</Button>
        <Button variant="outline" onClick={clear}>Clear local view</Button>
        <Button disabled={!data || busy} onClick={download}>Download reusable package</Button>
      </div>
      <details><summary className="cursor-pointer text-sm">Paste or edit a package</summary>
        <label className="mt-3 block text-sm">Package JSON<textarea className={`${FIELD} mt-1 font-mono`} rows={6} value={source} onChange={e => setSource(e.target.value)} /></label>
        <Button className="mt-2" disabled={busy || !source.trim()} onClick={() => void load(async () => source)}>Validate and load JSON</Button>
      </details>
      {busy && <p role="status">Validating evidence and references…</p>}
      {error && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{error}</p>}
    </section>
    <section aria-label="Coverage summary" className={`${CARD} space-y-2 p-4`}>
      <h2 className="text-xl font-semibold">{result?.complete ? 'Expected coverage complete' : `Readiness ${result?.state ?? 'unknown'}`}</h2>
      <p>{result?.expected_count ? `${result.current_count} of ${result.expected_count} expected files are current.` : 'Expected-file inventory is absent or empty. Completeness cannot be established.'}</p>
      <p className="text-sm">Source coverage is separate from validation results, financial totals, identity resolution and a person’s approval.</p>
      {data && <div className={`space-y-1 text-sm ${WORDS}`}><p>Agency: {data.agency_id}</p><p>Readiness run: {data.run_id} · Intake run: {data.intake_run_id ?? 'Not linked yet'}</p><p>Evaluated as of {data.as_of}. This is a dated snapshot, not a live freshness check.</p><p>Receipts retained: {result!.receipt_count}</p><p>Duplicate deliveries retained: {result!.duplicate_receipt_count}</p><p>Unexpected versions: {result!.unexpected_version_ids.join(', ') || 'None'}</p></div>}
    </section>
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">{result?.entries.map((entry, index) => <section key={JSON.stringify([entry.expected.agency_id, entry.expected.carrier, entry.expected.file_type, entry.expected.period])} className={`${CARD} ${WORDS} space-y-3 p-4`}>
      <h2 className="text-lg font-semibold">{entry.state} · {entry.expected.carrier} · {entry.expected.file_type} · {entry.expected.period}</h2>
      <p className="text-sm">{entry.reason}</p>
      <p className="text-sm">Source date required: {entry.expected.minimum_source_date ?? 'Unknown cutoff'}</p>
      <p className="text-sm">Active versions: {entry.active_version_ids.join(', ') || 'None'}</p>
      <label className="block text-sm">Owner<input className={FIELD} disabled={busy} value={entry.expected.owner ?? ''} onChange={e => update(index, 'owner', e.target.value)} /></label>
      <label className="block text-sm">Next action<input className={FIELD} disabled={busy} value={entry.expected.next_action ?? ''} onChange={e => update(index, 'next_action', e.target.value)} /></label>
    </section>)}</div>
    {data && <section className="space-y-3" aria-label="Version and receipt evidence">
      <h2 className="text-xl font-semibold">Versions and delivery evidence</h2>
      <p className="text-sm">Superseded evidence remains in the reusable package. Multiple active contents require review; delivery order never chooses a winner.</p>
      {data.versions.map(v => <details key={v.version_id} className={`${CARD} ${WORDS} p-4`}>
        <summary className="cursor-pointer">{v.version_id} · {v.file_name} · {result!.superseded_version_ids.includes(v.version_id) ? 'Superseded' : 'Retained'}</summary>
        <dl className="mt-3 space-y-2 text-sm">
          <div><dt>Scope</dt><dd>{v.agency_id} · {v.carrier} · {v.file_type} · {v.period}</dd></div>
          <div><dt>Source date</dt><dd>{v.source_date ?? 'Unknown'}</dd></div>
          <div><dt>Supersedes version</dt><dd>{v.supersedes_version_id ?? 'None'}</dd></div>
          <div><dt>Exact source SHA-256</dt><dd className="font-mono text-xs">{v.file_sha256}</dd></div>
        </dl>
        <ul className="mt-3 space-y-2 text-sm">{data.receipts.filter(r => r.version_id === v.version_id).map(r => <li key={r.receipt_id}>{r.receipt_id} · Received {r.received_at}<br />Owner: {r.owner ?? UNKNOWN} · Next action: {r.next_action ?? UNKNOWN}</li>)}</ul>
        {!data.receipts.some(r => r.version_id === v.version_id) && <p className="mt-2 text-sm">No delivery recorded. This version contributes no coverage.</p>}
        <details className="mt-3"><summary className="cursor-pointer text-sm">Original synthetic file evidence</summary><pre className="mt-2 whitespace-pre-wrap break-all text-xs">{data.evidence.find(e => e.sha256 === v.file_sha256)?.content}</pre></details>
      </details>)}
    </section>}
  </div>;
}

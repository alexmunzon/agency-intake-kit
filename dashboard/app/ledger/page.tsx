"use client";

import { useRef, useState } from 'react';
import { FinanceReviewPanel } from '@/components/finance-review-panel';
import { parseFinanceLedger, type FinanceLedger } from '@/lib/finance-ledger';

export default function LedgerPage() {
  const [ledger, setLedger] = useState<FinanceLedger | null>(null);
  const [error, setError] = useState('');
  const request = useRef(0);
  const [page, setPage] = useState(0);
  async function load(file: File | undefined) {
    if (!file) return;
    const token = ++request.current;
    try {
      if (file.size > 10 * 1024 * 1024) throw new Error('Choose a ledger smaller than 10 MB.');
      const next = parseFinanceLedger(await file.text());
      if (token !== request.current) return;
      setLedger(next); setPage(0); setError('');
    } catch { if (token !== request.current) return; setError('Ledger refused. The previous valid ledger remains visible.'); }
  }
  async function example() {
    const token = ++request.current;
    try {
      const response = await fetch('/demo-ledger.json');
      if (!response.ok) throw new Error('Example unavailable');
      const next = parseFinanceLedger(await response.text());
      if (token !== request.current) return;
      setLedger(next); setPage(0); setError('');
    } catch { if (token === request.current) setError('Example unavailable. The previous valid ledger remains visible.'); }
  }
  return <section aria-labelledby="ledger-heading" className="mx-auto min-w-0 max-w-6xl space-y-6 break-words p-4 [overflow-wrap:anywhere]">
    <h1 id="ledger-heading" className="text-2xl font-semibold">Receipt ledger</h1>
    <p>Inspect a synthetic neutral ledger export. This page holds data only in browser memory; it does not provide hosted persistence, authenticated approval or accounting posting. Durable receipt storage runs locally through the finance command.</p>
    <label className="block">Open ledger JSON <input className="block max-w-full" type="file" accept=".json,application/json" onChange={e => void load(e.target.files?.[0])} /></label>
    <div className="flex flex-wrap items-center gap-4"><button className="rounded border px-3 py-2" onClick={() => void example()}>Load synthetic example</button>
    <a className="underline" href="/demo-ledger.json" download>Download synthetic ledger example</a></div>
    {error && <p role="alert">{error}</p>}
    {!ledger && <p>No ledger loaded. Download the example or open your local export.</p>}
    {ledger && <>
      <h2 className="text-xl font-semibold">Receipt history</h2>
      <p>{ledger.receipts.length} receipts. Duplicates and superseded revisions remain evidence; only active revisions contribute to active totals. Conflicts require review.</p>
      <nav aria-label="Receipt pages" className="flex gap-4"><button disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</button><span>Page {page + 1}</span><button disabled={(page + 1) * 25 >= ledger.receipts.length} onClick={() => setPage(page + 1)}>Next</button></nav>
      <div className="min-w-0 overflow-x-auto" role="region" aria-label="Receipt history" tabIndex={0}><table className="min-w-[44rem] w-full text-left text-sm"><thead><tr>{['Receipt', 'Received', 'Statement / revision', 'State', 'Replaces', 'Reason'].map(h => <th className="p-2" key={h}>{h}</th>)}</tr></thead><tbody>{ledger.receipts.slice(page * 25, (page + 1) * 25).map((r, i) => <tr key={r.receipt_id}><td className="p-2">{r.receipt_id}</td><td className="p-2">{r.received_at}</td><td className="p-2">{r.logical_key.join(' / ')} / {r.revision_id}<details><summary>Evidence hash</summary>{r.canonical_rows_sha256}</details></td><td className="p-2">{r.state}</td><td className="p-2">{r.replaces_revision_id ?? 'None'}</td><td className="p-2">{r.reason ?? 'None'}<details><summary>Original revision evidence</summary><pre className="max-w-sm whitespace-pre-wrap break-all">{JSON.stringify(ledger.revisions[page * 25 + i], null, 2)}</pre></details></td></tr>)}</tbody></table></div>
      <h2 className="text-xl font-semibold">Active totals by agency, carrier and period</h2>
      {ledger.grouped_totals.map(g => <p key={JSON.stringify([g.agency_id, g.carrier, g.period])}>{g.agency_id} / {g.carrier} / {g.period}: {g.statement_total}, including {g.category_totals.unclassified} unclassified.</p>)}
      <h2 className="text-xl font-semibold">Unresolved conflict totals, excluded from active revenue</h2>
      {ledger.unresolved_conflict_totals.length === 0 ? <p>No unresolved conflict amounts.</p> : ledger.unresolved_conflict_totals.map(g => <p key={JSON.stringify([g.agency_id, g.carrier, g.period])}>{g.agency_id} / {g.carrier} / {g.period}: {g.statement_total}</p>)}
      <FinanceReviewPanel statements={ledger.active_reviews} />
      <details><summary>Historical conflict reviews ({ledger.conflicts.length})</summary><FinanceReviewPanel statements={ledger.conflicts} /></details>
    </>}
  </section>;
}

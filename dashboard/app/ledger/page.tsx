"use client";

import { useRef, useState } from 'react';
import { EvidenceTime } from '@/components/evidence-time';
import { FinanceReviewPanel } from '@/components/finance-review-panel';
import { Button } from '@/components/ui/button';
import { CARD, Tile } from '@/components/tiles';
import { TABLE, TABLE_WRAP } from '@/components/tie-out';
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
  return <section aria-labelledby="ledger-heading" className="page-stack [overflow-wrap:anywhere]">
    <header className="page-header">
      <p className="eyebrow mb-3">Statement evidence</p>
      <h1 id="ledger-heading">Revenue breakdown</h1>
      <p className="page-description">Review signed totals, unclassified amounts and the source rows behind them. This ledger is a separate snapshot from the loaded Intake run.</p>
    </header>
    <div className={`${CARD} space-y-3 p-5`}>
      <div className="flex flex-wrap items-center gap-4">
        <Button onClick={() => void example()}>Load synthetic example</Button>
        <label className="block min-w-0 text-sm">Open ledger JSON <input className="mt-2 block max-w-full" type="file" accept=".json,application/json" onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; void load(file); }} /></label>
        <a className="inline-flex min-h-11 items-center underline" href="/demo-ledger.json" download>Download synthetic ledger example</a>
      </div>
      <p className="text-sm text-muted-foreground">Read-only review. No authenticated approval or accounting posting.</p>
      <details className="text-sm text-muted-foreground"><summary className="cursor-pointer font-medium">Storage and implementation details</summary>
        <p className="mt-2">This page holds data only in browser memory; it does not provide hosted persistence. Durable receipt storage runs locally through the finance command.</p>
      </details>
      {error && <p role="alert" className="status-error">{error}</p>}
      {!ledger && <p role="status">No ledger loaded. Load the example or open your local export.</p>}
    </div>
    {ledger && <>
      <section aria-labelledby="active-revenue" className="space-y-4">
        <h2 id="active-revenue" className="text-xl font-semibold">Active revenue by agency, carrier and period</h2>
        <p className="text-sm text-muted-foreground">Only active revisions contribute. Unclassified amounts remain included and need review.</p>
        {ledger.grouped_totals.length === 0 && <p>No active revenue supplied.</p>}
        {ledger.grouped_totals.map(g => <article className={`${CARD} min-w-0 space-y-3 p-5`} key={JSON.stringify([g.agency_id, g.carrier, g.period])}>
          <h3 className="font-semibold">{g.carrier} · {g.period}</h3>
          <p className="text-sm text-muted-foreground">Agency {g.agency_id}</p>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2 [&>div]:min-w-0">
            <Tile label="Signed active total" value={g.statement_total} context="Positive and negative amounts retained" />
            <Tile label="Unclassified amount" value={g.category_totals.unclassified} context="Included in the active total; classification unresolved" />
          </div>
        </article>)}
      </section>
      <section aria-labelledby="conflict-totals" className="space-y-2">
        <h2 id="conflict-totals" className="text-lg font-semibold">Unresolved conflicts, excluded from active revenue</h2>
        {ledger.unresolved_conflict_totals.length === 0 ? <p className="text-sm text-muted-foreground">No unresolved conflict amounts.</p> : ledger.unresolved_conflict_totals.map(g => <p key={JSON.stringify([g.agency_id, g.carrier, g.period])}>{g.agency_id} / {g.carrier} / {g.period}: {g.statement_total}</p>)}
      </section>
      <FinanceReviewPanel statements={ledger.active_reviews} />
      <details className={`${CARD} min-w-0 p-5`}>
        <summary className="cursor-pointer font-semibold">Receipt history and evidence ({ledger.receipts.length})</summary>
        <div className="mt-4 space-y-4">
          <p className="text-sm text-muted-foreground">Duplicates and superseded revisions remain evidence. They are excluded from active totals. Conflicts require review.</p>
          <nav aria-label="Receipt pages" className="flex flex-wrap items-center gap-4">
            <Button variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
            <span role="status">Page {page + 1} of {Math.max(1, Math.ceil(ledger.receipts.length / 25))}</span>
            <Button variant="outline" disabled={(page + 1) * 25 >= ledger.receipts.length} onClick={() => setPage(page + 1)}>Next</Button>
          </nav>
          <div className={TABLE_WRAP} role="region" aria-label="Receipt history" tabIndex={0}>
            <table className={TABLE}>
              <thead><tr>{['Receipt', 'Received (UTC)', 'Statement / revision', 'State', 'Replaces', 'Reason'].map(h => <th scope="col" key={h}>{h}</th>)}</tr></thead>
              <tbody>{ledger.receipts.slice(page * 25, (page + 1) * 25).map((r, i) => <tr key={r.receipt_id}>
                <th scope="row">{r.receipt_id}</th>
                <td><EvidenceTime value={r.received_at} /><details><summary className="cursor-pointer">Exact timestamp</summary>{r.received_at}</details></td>
                <td>{r.logical_key.join(' / ')} / {r.revision_id}<details><summary className="cursor-pointer">Evidence hash</summary>{r.canonical_rows_sha256}</details></td>
                <td>{r.state}</td><td>{r.replaces_revision_id ?? 'None'}</td>
                <td>{r.reason ?? 'None'}<details><summary className="cursor-pointer">Original revision evidence</summary><pre className="max-w-sm whitespace-pre-wrap break-all">{JSON.stringify(ledger.revisions[page * 25 + i], null, 2)}</pre></details></td>
              </tr>)}</tbody>
            </table>
          </div>
        </div>
      </details>
      <details className={`${CARD} min-w-0 p-5`}><summary className="cursor-pointer font-semibold">Historical conflict reviews ({ledger.conflicts.length})</summary><div className="mt-4"><FinanceReviewPanel statements={ledger.conflicts} /></div></details>
    </>}
  </section>;
}

'use client';

import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { assertReviewPackageContinuity, parseReviewPackage, reviewSummary, type ReviewPackage } from '@/lib/review-package';

const PANEL = 'consulting-panel min-w-0 rounded-lg border border-border bg-card p-5 [overflow-wrap:anywhere]';
export function ReviewPackageSummary() {
  const [data, setData] = useState<ReviewPackage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const generation = useRef(0);
  const current = useRef<ReviewPackage | null>(null);
  const summary = data ? reviewSummary(data) : null;
  async function load(file: File) {
    const id = ++generation.current; setBusy(true); setError(null);
    try {
      if (file.size > 12_000_000) throw new Error('Package exceeds 12 MB');
      const next = await parseReviewPackage(await file.text());
      if (generation.current === id) {
        if (current.current) assertReviewPackageContinuity(current.current, next);
        current.current = next; setData(next);
      }
    } catch (e) {
      if (generation.current === id) setError(`Import refused: ${e instanceof Error ? e.message : 'Invalid package'}. Previous valid package preserved.`);
    } finally { if (generation.current === id) setBusy(false); }
  }
  return <section aria-label="Validated review summary" className="space-y-4">
    <div className={PANEL}>
      <h2 className="text-xl font-semibold">One bound evidence snapshot</h2>
      <p className="mt-2 text-sm text-muted-foreground">Import a synthetic review package to see verified file consistency and run-scoped evidence. No automatic approval or go-live verdict. Hashes prove consistency, not authenticity. This view is read-only and clears on refresh. Same-run imports retain existing pins; clear the summary before changing a snapshot.</p>
      <div className="mt-4 flex flex-wrap items-center gap-4">
        <label className="block min-w-0 text-sm">Import review package<input className="mt-2 block w-full max-w-72" type="file" accept=".json,application/json" disabled={busy} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (file) void load(file); }} /></label>
        <Button variant="outline" onClick={() => { generation.current++; current.current = null; setData(null); setBusy(false); setError(null); }}>Clear summary</Button>
      </div>
      {busy && <p role="status" className="mt-3 text-sm">Verifying artifact hashes and scope…</p>}
      {error && <p role="alert" className="mt-3 text-sm status-error">{error}</p>}
      <p role="status" className="mt-3 text-sm">{data ? `Loaded agency ${data.agency_id} · Intake run ${data.intake_run_id} · ${data.artifacts.length} verified artifact pins` : 'No package loaded. Evidence is unavailable until imported.'}</p>
    </div>
    <div className="grid min-w-0 gap-4 md:grid-cols-2">
      <section className={PANEL} aria-label="Source freshness summary"><h3 className="font-semibold">Source freshness</h3>
        <p className="mt-2">{summary?.readiness && data?.readiness?.expected_inventory?.length ? `${summary.readiness.current_count} / ${summary.readiness.expected_count} expected files current · ${summary.readiness.state}` : 'Unavailable: no run-bound expected source inventory'}</p>
        {data?.readiness && <p className="mt-2 text-sm text-muted-foreground">As of {data.readiness.as_of}. This is a dated snapshot, not a live freshness check.</p>}
        {summary?.readiness?.entries.filter(e => e.state !== 'current').map((e, i) => <p key={i} className="mt-2 text-sm">{e.expected.carrier} · {e.state} · {e.expected.next_action ?? e.reason} · Owner: {e.expected.owner ?? 'Unassigned'}</p>)}
      </section>
      <section className={PANEL} aria-label="Records summary"><h3 className="font-semibold">Accepted and excluded records</h3>
        <p className="mt-2">Accepted clean output rows: {summary?.accepted ?? 'Unavailable'}</p>
        <p className="mt-2">Distinct source rows with error evidence: {summary?.excludedEvidenceRows ?? 'Unavailable'}</p>
        {summary && summary.unlocatedErrors > 0 && <p className="mt-2 text-sm">{summary.unlocatedErrors} error findings have no complete source-row pointer and are not included in the distinct-row count.</p>}
        <p className="mt-2 text-sm text-muted-foreground">Error rows are deduplicated by source, row number and raw hash. They are not subtracted from raw input counts: mapping changes row granularity. Blocked runs have no accepted output.</p>
        {data && <p className="mt-2 text-sm">Next: review {data.run.scorecard.exceptions_by_severity.error} errors and {data.run.scorecard.exceptions_by_severity.warning} warnings in the bound exception evidence.</p>}
      </section>
      <section className={PANEL} aria-label="Identity summary"><h3 className="font-semibold">Unresolved identities</h3>
        <p className="mt-2">{summary?.unresolvedIdentities === null || summary?.unresolvedIdentities === undefined ? 'Unavailable: no bound identity partition' : `${summary.unresolvedIdentities} unresolved, ambiguous or unsupported groups in the supplied identity packet`}</p>
        <p className="mt-2 text-sm text-muted-foreground">Counts cover only the supplied identity groups, not all agency records. Deterministic resolution is not human confirmation. Companion demo identities are never included automatically.</p>
      </section>
      <section className={PANEL} aria-label="Finance summary"><h3 className="font-semibold">Signed financial totals</h3>
        <p className="mt-2">{data?.finance ? `Statement total: ${data.finance.statement_total} · Control check: ${data.finance.total_check}` : 'Unavailable: no bound finance review'}</p>
        {data?.finance && <p className="mt-2 text-sm">{data.finance.carrier} · {data.finance.period} · {data.finance.statement_id} · {data.finance.revision_id}</p>}
        <p className="mt-2 text-sm text-muted-foreground">Signed means positive and negative amounts retained, not digitally signed. No ERP posting or authenticated financial approval.</p>
      </section>
      <section className={`${PANEL} md:col-span-2`} aria-label="Review state summary"><h3 className="font-semibold">Review state and next actions</h3>
        <p className="mt-2">Identity groups without declared approval: {summary?.pendingIdentityReviews ?? 'Unavailable'}</p>
        <p className="mt-2 text-sm text-muted-foreground">Declared reviewer states are unauthenticated evidence. Obtain a human decision after inspecting sources, exclusions, identities and totals. Missing evidence remains unresolved; this page never approves a release.</p>
      </section>
    </div>
    {data && <details className={PANEL}><summary className="cursor-pointer font-medium">Verified artifact provenance</summary><ul className="mt-3 space-y-3 text-xs">{data.artifacts.map(a => <li key={a.path}><strong>{a.path}</strong> · {a.size_bytes} bytes<br /><span className="font-mono">SHA-256 {a.sha256}</span></li>)}</ul></details>}
  </section>;
}

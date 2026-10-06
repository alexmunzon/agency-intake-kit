"use client";

import { useState } from "react";
import { formatMoney } from "@/lib/money";
import type { StatementGroup } from "@/lib/statement-groups";

export function StatementGroupsPanel({ groups }: { groups?: StatementGroup[] }) {
  const [previous, setPrevious] = useState(groups);
  const [page, setPage] = useState(0);
  if (previous !== groups) { setPrevious(groups); setPage(0); }
  const pages = Math.max(1, Math.ceil((groups?.length ?? 0) / 25));
  const current = Math.min(page, pages - 1);
  return <section aria-label="Statement carrier and period totals" className="space-y-3">
    <h2 className="text-lg font-semibold">Statement totals by carrier and period</h2>
    <p className="text-sm">Observed statement labels only. Unknown labels stay explicit. Received-row totals do not deduplicate receipts, establish policy attribution or confirm source readiness.</p>
    {groups === undefined ? <p className="text-sm">Grouping is unavailable. No statement_groups.json artifact is attached.</p>
      : groups.length === 0 ? <p className="text-sm">No statement rows are available for grouping. See statement evidence and run gates above.</p>
      : <ul className="grid gap-3 sm:grid-cols-2">{groups.slice(current * 25, (current + 1) * 25).map(group =>
        <li key={JSON.stringify([group.carrier, group.statement_period])} className="space-y-1 rounded-lg border border-slate-200 p-3 text-sm break-all dark:border-slate-800">
          <h3 className="font-medium">{group.carrier === null ? "Carrier unavailable" : `Carrier label: ${group.carrier}`}</h3>
          <p>{group.statement_period === null ? "Statement period unavailable" : `Statement period: ${group.statement_period}`}</p>
          <p>{group.total_paid === null ? "No valid amounts" : <strong>{formatMoney(group.total_paid)}</strong>}</p>
          <p>{group.valid_line_count} valid, {group.excluded_line_count} excluded rows</p>
        </li>)}</ul>}
    {pages > 1 && <nav aria-label="Statement group pages" className="flex flex-wrap items-center gap-3 text-sm">
      <button type="button" aria-label="Previous group page" disabled={current === 0} onClick={() => setPage(current - 1)} className="rounded border px-3 py-1 disabled:opacity-50">Previous</button>
      <span role="status">Group page {current + 1} of {pages}</span>
      <button type="button" aria-label="Next group page" disabled={current === pages - 1} onClick={() => setPage(current + 1)} className="rounded border px-3 py-1 disabled:opacity-50">Next</button>
    </nav>}
  </section>;
}

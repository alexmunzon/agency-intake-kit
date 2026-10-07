"use client";

import { useState } from "react";
import { formatMoney } from "@/lib/money";
import type { StatementLine, StatementTotals } from "@/lib/statement-totals";

const PAGE_SIZE = 25;
const REASONS = { valid: "Valid amount", amount_blank: "Amount blank",
  amount_malformed: "Amount could not be read", amount_mapping_unavailable: "Amount column unavailable" };

function Row({ line }: { line: StatementLine }) {
  const lin = line.lineage;
  return <li className="space-y-2 rounded-lg border border-border p-3 text-sm break-all">
    <p className="font-medium">{REASONS[line.reason]}: {line.amount === null ? "Not included" : formatMoney(line.amount)}</p>
    <p>{line.source}: {lin.source_file}{lin.sheet ? `, ${lin.sheet}` : ""}, row {lin.row_number}</p>
    <details><summary className="cursor-pointer text-primary underline underline-offset-4">Full source provenance</summary>
      <dl className="mt-2 space-y-1 text-xs">
        <div><dt className="font-medium">Run</dt><dd>{lin.run_id}</dd></div>
        <div><dt className="font-medium">Mapping version</dt><dd>{lin.mapping_version}</dd></div>
        <div><dt className="font-medium">Raw row hash</dt><dd className="font-mono">{lin.raw_hash}</dd></div>
      </dl>
    </details>
  </li>;
}

export function StatementTotalsPanel({ totals }: { totals?: StatementTotals }) {
  const [previous, setPrevious] = useState(totals);
  const [page, setPage] = useState(0);
  if (previous !== totals) { setPrevious(totals); setPage(0); }
  const lines = totals?.lines ?? [];
  const pages = Math.max(1, Math.ceil(lines.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  return <section aria-label="Statement totals" className="evidence-section space-y-3">
    <h2 className="text-lg font-semibold">Statement totals</h2>
    <p className="text-sm">Received statement row evidence. It does not deduplicate receipts or establish that the book agrees. Run status and tie-out checks remain separate.</p>
    {totals === undefined ? <p className="text-sm">No statement_totals.json artifact is attached to this run. Statement evidence is unavailable.</p>
      : totals.status === "BLOCKED" ? <p className="text-sm">Raw safety or completeness gate blocked statement totals. See run exceptions.</p>
      : totals.status === "UNAVAILABLE" ? <p className="text-sm">{totals.reason === "no_statements"
        ? "No commission statements were received." : "Commission statement sources contained no rows."}</p>
      : <>
        <p className="text-sm">{totals.total_paid === null ? "No valid statement amounts were recorded."
          : <>Valid received-row total: <strong>{formatMoney(totals.total_paid)}</strong>.</>}
          {" "}{totals.valid_line_count} valid, {totals.excluded_line_count} excluded rows. This is not book-expected revenue or a policy attribution.</p>
        <ul className="space-y-3">{lines.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE).map(line =>
          <Row key={JSON.stringify([line.lineage.source_file, line.lineage.sheet, line.lineage.row_number])} line={line} />)}</ul>
        {pages > 1 && <nav aria-label="Statement row pages" className="flex flex-wrap items-center gap-3 text-sm">
          <button type="button" aria-label="Previous statement page" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} className="rounded border px-3 py-1 disabled:opacity-50">Previous</button>
          <span role="status">Page {currentPage + 1} of {pages}</span>
          <button type="button" aria-label="Next statement page" disabled={currentPage === pages - 1} onClick={() => setPage(currentPage + 1)} className="rounded border px-3 py-1 disabled:opacity-50">Next</button>
        </nav>}
      </>}
  </section>;
}

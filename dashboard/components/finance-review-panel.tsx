"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CARD, Tile } from "@/components/tiles";
import { TABLE, TABLE_WRAP } from "@/components/tie-out";
import { CATEGORIES, type FinanceReview } from "@/lib/finance-review";

const ROWS_PER_PAGE = 25;

const MUTED = "text-sm text-muted-foreground";
const WORDS = "whitespace-normal break-words [overflow-wrap:anywhere]";
const label = (value: string) => value.replaceAll("_", " ");

/** Render parsed server decimals verbatim. No browser arithmetic or policy attribution. */
export function FinanceReviewPanel({ statements }: { statements: readonly FinanceReview[] }) {
  return (
    <section aria-label="Finance review" className="min-w-0 space-y-6">
      <header>
        <h2 className="text-[22px] font-semibold tracking-tight">Review statement revenue</h2>
        <p className={MUTED}>
          Neutral finance review. Amounts retain their signs and server precision.
          Mapping approval records supplied provenance, not an authenticated authorization. Statement control checks are separate. Customer and policy attribution remain unresolved.
        </p>
      </header>
      {statements.length === 0 && <p className={`${CARD} p-4`}>No finance statements supplied.</p>}
      {statements.map((statement) => (
        <StatementReview key={JSON.stringify([statement.agency_id, statement.statement_id, statement.revision_id, statement.content_sha256, statement.mapping_sha256])} statement={statement} />
      ))}
    </section>
  );
}

function StatementReview({ statement }: { statement: FinanceReview }) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(statement.rows.length / ROWS_PER_PAGE));
  const visibleRows = statement.rows.slice(page * ROWS_PER_PAGE, (page + 1) * ROWS_PER_PAGE);
  return (
        <article
          className={`${CARD} min-w-0 space-y-4 p-4`}>
          <header className={WORDS}>
            <h3 className="text-lg font-semibold">{statement.carrier} · {statement.period}</h3>
            <p className={MUTED}>Agency {statement.agency_id} · Statement {statement.statement_id} · Revision {statement.revision_id}</p>
          </header>
          <div className="grid min-w-0 gap-3 sm:grid-cols-2 lg:grid-cols-3 [&>div]:min-w-0 [&_p]:break-words [&_p]:[overflow-wrap:anywhere]">
            <Tile label="Statement total" value={statement.statement_total} />
            <Tile label="Source control total" value={statement.control_total ?? "Not supplied"} />
            <Tile label="Control check" value={statement.total_check === "NOT_RUN" ? "Not checked" : statement.total_check === "PASS" ? "Totals agree" : "Totals differ"}
              context="This check does not approve the package." />
          </div>
          <dl className={`grid min-w-0 grid-cols-1 gap-3 text-sm sm:grid-cols-2 [&>div]:min-w-0 ${WORDS}`}>
            <div><dt className={MUTED}>Mapping approval</dt><dd>{statement.mapping_approved ? `Approved by ${statement.approved_by} at ${statement.approved_at}` : "Awaiting a person's approval"}</dd></div>
            <div><dt className={MUTED}>Mapping</dt><dd>{statement.mapping_id} · Version {statement.mapping_version}</dd></div>
            <div><dt className={MUTED}>Mapping hash</dt><dd className="font-mono text-xs">{statement.mapping_sha256}</dd></div>
            <div><dt className={MUTED}>Statement content hash</dt><dd className="font-mono text-xs">{statement.content_sha256}</dd></div>
          </dl>
          <div role="region" aria-label={`Category totals for ${statement.statement_id}`} tabIndex={0} className={`min-w-0 ${TABLE_WRAP}`}>
            <table className={TABLE}>
              <caption className="p-3 text-left text-sm font-medium">Category totals for this statement revision</caption>
              <thead><tr><th scope="col">Category</th><th scope="col">Signed amount</th></tr></thead>
              <tbody>{CATEGORIES.map((category) => <tr key={category}><th scope="row">{label(category)}</th><td>{statement.category_totals[category]}</td></tr>)}</tbody>
            </table>
          </div>
          <p className={MUTED}>Unclassified amounts remain in the statement total. An approved mapping does not resolve unknown labels or authorize journal posting.</p>
          <nav aria-label={`Source row navigation for ${statement.statement_id}`} className="flex flex-wrap items-center gap-3 text-sm">
            <p role="status" aria-live="polite">Page {page + 1} of {pageCount} · Rows {statement.rows.length === 0 ? 0 : page * ROWS_PER_PAGE + 1}-{Math.min((page + 1) * ROWS_PER_PAGE, statement.rows.length)} of {statement.rows.length}</p>
            <Button type="button" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous rows</Button>
            <Button type="button" variant="outline" disabled={page + 1 >= pageCount} onClick={() => setPage(page + 1)}>Next rows</Button>
          </nav>
          <div role="region" aria-label={`Source rows for ${statement.statement_id}`} tabIndex={0} className={`min-w-0 ${TABLE_WRAP}`}>
            <table className={TABLE}>
              <caption className="p-3 text-left text-sm font-medium">Source rows and unresolved evidence</caption>
              <thead><tr>{["Row", "Signed amount", "Source labels", "Category and kind", "Review", "Source evidence"].map((heading) => <th scope="col" key={heading}>{heading}</th>)}</tr></thead>
              <tbody>{visibleRows.map((row) => (
                <tr key={row.row_id}>
                  <th scope="row" className="font-mono">{row.row_id}</th>
                  <td>{row.amount}<span className={`block ${MUTED}`}>Source: {row.raw_amount}</span></td>
                  <td className={`min-w-48 ${WORDS}`}>Category: {row.raw_category_label ?? "Not supplied"}<br />Kind: {row.raw_transaction_label ?? "Not supplied"}</td>
                  <td className={`min-w-40 ${WORDS}`}>{label(row.category)}<br />{row.transaction_kind === null ? "Kind unresolved" : label(row.transaction_kind)}</td>
                  <td className={`min-w-56 ${WORDS}`}>
                    <p>Method: {label(row.classification_method)}</p>
                    <p>Account: {row.account_code ?? "Unresolved"}</p>
                    <p>Policy attribution: Unresolved</p>
                    {row.unresolved_reasons.length > 0 ? <ul className="mt-1 list-inside list-disc">{row.unresolved_reasons.map((reason, index) => <li key={`${index}:${reason}`}>{label(reason)}</li>)}</ul> : <p>No classification issues reported.</p>}
                  </td>
                  <td className={`min-w-64 ${WORDS}`}>
                    <details><summary className="cursor-pointer">{row.lineage.source_file}, row {row.lineage.row_number}</summary>
                      <dl className="mt-2 space-y-1">
                        <div><dt>Sheet</dt><dd>{row.lineage.sheet ?? "CSV, no sheet"}</dd></div>
                        <div><dt>Run</dt><dd>{row.lineage.run_id}</dd></div>
                        <div><dt>Source mapping version</dt><dd>{row.lineage.mapping_version}</dd></div>
                        <div><dt>Raw row hash</dt><dd className="font-mono">{row.lineage.raw_hash}</dd></div>
                      </dl>
                    </details>
                  </td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        </article>
  );
}

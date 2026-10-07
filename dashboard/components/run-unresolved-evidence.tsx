"use client";

import { useState } from "react";
import { useLoadedRun } from "@/components/loaded-run";
import type { UnresolvedEvidence } from "@/lib/unresolved-evidence";

const REASONS = { crm_absent: "CRM file not received", dob_column_missing: "DOB column not found",
  dob_blank: "DOB is blank", dob_malformed: "DOB could not be read" };
const PAGE_SIZE = 25;
export function RunUnresolvedEvidence() {
  const { loaded } = useLoadedRun();
  const records = loaded?.unresolved;
  const [previous, setPrevious] = useState(records);
  const [page, setPage] = useState(0);
  // A newly imported artifact resets paging even when its run ID is unchanged.
  if (previous !== records) { setPrevious(records); setPage(0); }
  const count = records?.length ?? 0;
  const pages = Math.max(1, Math.ceil(count / PAGE_SIZE));
  return <section aria-label="Unresolved evidence" className="evidence-section mt-8 space-y-3 text-sm">
    <h2 className="text-lg font-semibold">Unresolved evidence</h2>
    <p>Recorded source and row references for absent CRM or missing, blank or unreadable date of birth (DOB). These are not load-ready customer records or resolved identities.</p>
    <p>Run status, exceptions and comparison status remain authoritative. This artifact does not establish completeness.</p>
    {records === undefined ? <p>No unresolved evidence artifact is attached to this run. Evidence is unavailable.</p>
      : count === 0 ? <p>The attached artifact contains no recorded cases. Raw safety blockers can leave it empty; consult the run status and exceptions.</p>
      : <>
        <p>{count} recorded cases, including any source summaries. This is not a count of people.</p>
        <ul className="space-y-3">
          {records.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE).map((record, index) => <EvidenceCase key={`${page}-${index}`} record={record} />)}
        </ul>
        {pages > 1 && <nav aria-label="Unresolved evidence pages" className="flex flex-wrap items-center gap-3">
          <button type="button" aria-label="Previous evidence page" disabled={page === 0} onClick={() => setPage(page - 1)} className="rounded border px-3 py-1 disabled:opacity-50">Previous</button>
          <span role="status">Page {page + 1} of {pages}</span>
          <button type="button" aria-label="Next evidence page" disabled={page === pages - 1} onClick={() => setPage(page + 1)} className="rounded border px-3 py-1 disabled:opacity-50">Next</button>
        </nav>}
      </>}
  </section>;
}
function EvidenceCase({ record }: { record: UnresolvedEvidence }) {
  const lin = record.lineage;
  return <li className="space-y-2 rounded-lg border border-border p-3 break-all">
    <p className="font-medium">{REASONS[record.reason]}</p>
    <p>Source: {record.source}</p>
    {lin ? <p>{lin.source_file}{lin.sheet === null ? "" : `, ${lin.sheet}`}, row {lin.row_number}</p>
      : <p>Source summary; no row reference recorded.</p>}
    {record.reason === "crm_absent" && lin && <p>Received source row awaiting CRM context; no customer or policy match is implied.</p>}
    <details><summary className="cursor-pointer text-primary underline underline-offset-4">Source provenance</summary>
      <dl className="mt-2 space-y-1 text-xs">
        <div><dt className="font-medium">Run</dt><dd>{record.run_id}</dd></div>
        {lin && <><div><dt className="font-medium">Mapping version</dt><dd>{lin.mapping_version}</dd></div>
          <div><dt className="font-medium">Raw row hash</dt><dd className="font-mono">{lin.raw_hash}</dd></div></>}
      </dl>
    </details>
  </li>;
}

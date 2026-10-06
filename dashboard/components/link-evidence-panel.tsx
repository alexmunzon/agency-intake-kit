"use client";

import { useState } from "react";

import { formatMoney } from "@/lib/money";
import type { LinkEvidence } from "@/lib/link-evidence";

const PAGE_SIZE = 25;
const METHODS = { MEMBER_ID: "carrier member ID", POLICY_REF: "policy reference", NAME_DOB: "name and date of birth" };
const STATES = ["confirmed", "provisional", "ambiguous", "unmatched"] as const;
const REASONS: Record<string, string> = {
  strong_key: "Consistent strong identifier",
  name_dob_only: "Name and date of birth only",
  multiple_candidates: "Multiple candidates",
  unmatched_strong_key: "Strong identifier has no candidate",
  conflicting_name_dob: "Conflicting name and date of birth evidence",
  no_candidate: "No candidate found",
};

function location(lineage: LinkEvidence["lineage"]): string {
  return `${lineage.source_file}${lineage.sheet ? `, ${lineage.sheet}` : ""}, row ${lineage.row_number}`;
}

function LineageDetails({ lineage }: { lineage: LinkEvidence["lineage"] }) {
  return (
    <dl className="grid gap-1 text-xs sm:grid-cols-2">
      <div><dt className="font-medium">Source</dt><dd className="break-all">{lineage.source_file}</dd></div>
      <div><dt className="font-medium">Sheet and row</dt><dd>{lineage.sheet ?? "No sheet"}, {lineage.row_number}</dd></div>
      <div><dt className="font-medium">Run</dt><dd className="break-all">{lineage.run_id}</dd></div>
      <div><dt className="font-medium">Mapping version</dt><dd className="break-all">{lineage.mapping_version}</dd></div>
      <div className="sm:col-span-2"><dt className="font-medium">Raw row hash</dt><dd className="break-all font-mono">{lineage.raw_hash}</dd></div>
    </dl>
  );
}

export function LinkEvidencePanel({ links }: { links?: LinkEvidence[] }) {
  const [page, setPage] = useState(0);
  const count = links?.length ?? 0;
  const lastPage = Math.max(0, Math.ceil(count / PAGE_SIZE) - 1);
  const currentPage = Math.min(page, lastPage);
  const shown = links?.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE) ?? [];

  return (
    <section aria-label="Policy link evidence" className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">Policy link evidence</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          These are supplied statement-line records. A confirmed link is a deterministic match, not a human approval or proof that the package is complete.
        </p>
      </div>
      {links === undefined ? (
        <p className="text-sm">No policy link evidence artifact is attached to this run.</p>
      ) : links.length === 0 ? (
        <p className="text-sm">The attached artifact contains no policy link records. It does not establish that all statements matched.</p>
      ) : (
        <>
          <dl className="grid grid-cols-2 gap-2 text-sm tabular-nums sm:grid-cols-4" aria-label="Link state counts">
            {STATES.map((state) => (
              <div key={state} className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
                <dt className="capitalize">{state}</dt>
                <dd className="text-lg font-semibold">{links.filter((link) => link.state === state).length.toLocaleString("en-US")}</dd>
              </div>
            ))}
          </dl>
          <div className="max-w-full overflow-x-auto rounded-lg border border-slate-200 dark:border-slate-800">
            <table className="w-full min-w-[44rem] text-left text-sm">
              <caption className="p-3 text-left font-medium">Statement lines and candidate policies</caption>
              <thead><tr className="border-b border-slate-200 dark:border-slate-800">
                <th className="p-3">Statement source</th><th className="p-3">State and reason</th>
                <th className="p-3">Amount</th><th className="p-3">Selected policy</th><th className="p-3">Evidence</th>
              </tr></thead>
              <tbody>
                {shown.map((link) => (
                  <tr key={JSON.stringify([link.lineage.source_file, link.lineage.sheet, link.lineage.row_number])} className="border-t border-slate-200 align-top dark:border-slate-800">
                    <td className="p-3 break-all">{location(link.lineage)}</td>
                    <td className="p-3"><span className="capitalize font-medium">{link.state}</span><span className="block">{REASONS[link.reason] ?? link.reason}</span></td>
                    <td className="p-3 tabular-nums whitespace-nowrap">{link.amount === null ? "Not reported" : formatMoney(link.amount)}</td>
                    <td className="p-3 font-mono break-all">{link.state === "confirmed" ? link.policy_id : "None confirmed"}</td>
                    <td className="p-3">
                      <details>
                        <summary className="cursor-pointer text-indigo-700 underline dark:text-indigo-300">Source and candidates</summary>
                        <div className="mt-2 space-y-3 min-w-64">
                          <div><p className="font-medium">Statement lineage</p><LineageDetails lineage={link.lineage} /></div>
                          {link.candidates.length === 0 ? <p>No candidate recorded.</p> : (
                            <ul className="space-y-3">
                              {link.candidates.map((candidate) => (
                                <li key={candidate.policy_id} className="border-t border-slate-200 pt-2 dark:border-slate-800">
                                  <p>Candidate <span className="font-mono break-all">{candidate.policy_id}</span> by {candidate.methods.map(method => METHODS[method]).join(", ")}</p>
                                  <LineageDetails lineage={candidate.lineage} />
                                </li>
                              ))}
                            </ul>
                          )}
                        </div>
                      </details>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {lastPage > 0 && (
            <nav aria-label="Policy link evidence pages" className="flex items-center gap-3 text-sm">
              <button type="button" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)} className="rounded border px-3 py-1 disabled:opacity-50">Previous</button>
              <span role="status">Page {currentPage + 1} of {lastPage + 1}; showing {shown.length} of {count} records</span>
              <button type="button" disabled={currentPage === lastPage} onClick={() => setPage(currentPage + 1)} className="rounded border px-3 py-1 disabled:opacity-50">Next</button>
            </nav>
          )}
        </>
      )}
    </section>
  );
}

import Link from "next/link";

import { SeverityBadge, TONES } from "@/components/severity-badge";
import { PageHeader } from "@/components/tie-out";
import { CARD } from "@/components/tiles";
import { toneOf } from "@/lib/exceptions";
import type { Run } from "@/lib/run-loader";
import { summarizeSources, type SourceSummary } from "@/lib/sources";
import { cn } from "@/lib/utils";

function Fact({ term, value }: { term: string; value: string }) {
  return (
    <div>
      <dt className="text-xs text-slate-600 dark:text-slate-400">{term}</dt>
      <dd className="tabular-nums">{value}</dd>
    </div>
  );
}

function SourceCard({ summary }: { summary: SourceSummary }) {
  const { file, tone, status, gates } = summary;
  const count = (n: number | null) => (n === null ? "Not stated" : n.toLocaleString("en-US"));
  return (
    <section aria-label={file.file_name} className={cn(CARD, "relative overflow-hidden p-4 pl-6")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1.5", TONES[tone].band)} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-mono text-sm font-medium break-all">{file.file_name}</h2>
        <SeverityBadge tone={tone} label={status} />
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-5">
        <Fact term="Rows expected" value={count(file.rows_expected)} />
        <Fact term="Rows received" value={count(file.rows_received)} />
        <Fact term="Encoding" value={summary.encoding} />
        <Fact term="Delimiter" value={summary.delimiter} />
        <Fact term="Header row" value={summary.headerRow} />
      </dl>
      <h3 className="mt-3 text-xs text-slate-600 dark:text-slate-400">Reading and mapping checks that fired</h3>
      {!summary.mapped && <p className="text-sm text-slate-600 dark:text-slate-400">Mapping not checked. The run stopped first.</p>}
      {gates.length === 0 ? (
        summary.mapped && <p className="text-sm">None</p>
      ) : (
        <ul className="mt-1 space-y-1 text-sm">
          {gates.map((record) => (
            <li key={record.id}>
              <SeverityBadge tone={toneOf(record.severity)} /> <span className="font-mono text-xs">{record.rule_id}</span> {record.message}
            </li>
          ))}
        </ul>
      )}
      {summary.rowIssues > 0 && (
        <p className="mt-2 text-sm">
          <Link href="/exceptions" className="text-indigo-700 underline dark:text-indigo-300">
            {summary.rowIssues.toLocaleString("en-US")} more found inside rows. See Exceptions.
          </Link>
        </p>
      )}
    </section>
  );
}

export function Sources({ run }: { run: Run }) {
  const summaries = summarizeSources(run);
  const clean = summaries.filter((summary) => summary.tone === "pass").length;
  // On a stopped run nothing was mapped, so count files read and say mapping was not checked.
  const read = summaries.filter((summary) => summary.tone !== "blocker" && summary.tone !== "error").length;
  const header = run.manifest.status === "FAILED"
    ? `${read} of ${summaries.length} files read. Mapping not checked, because the run stopped first.`
    : `${clean} of ${summaries.length} files read and mapped cleanly.`;
  return (
    <div className="space-y-4">
      <PageHeader run={run} question="What did we receive, and did it read cleanly?">{header}</PageHeader>
      {summaries.map((summary) => <SourceCard key={summary.file.source} summary={summary} />)}
    </div>
  );
}

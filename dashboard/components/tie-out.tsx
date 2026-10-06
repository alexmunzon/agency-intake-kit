import type { ReactNode } from "react";
import { LinkEvidencePanel } from "@/components/link-evidence-panel";
import type { LinkEvidence } from "@/lib/link-evidence";

import { SeverityBadge, SeverityIcon, TONES, type Tone } from "@/components/severity-badge";
import { CARD } from "@/components/tiles";
import { formatMoney } from "@/lib/money";
import { plural, tieOutSummary } from "@/lib/overview";
import type { Run } from "@/lib/run-loader";
import { LEGS, VARIANCE_SUM_NOTE, differenceText, otherDifferences, otherText, totalsSum, type TieOut } from "@/lib/tie-out";
import type { LegResult, Totals, Variance } from "@/lib/types";
import { cn } from "@/lib/utils";

export const TABLE_WRAP = "overflow-x-auto rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900";
export const TABLE = "w-full whitespace-nowrap text-left text-xs tabular-nums [&_td]:h-9 [&_td]:px-3 [&_th]:h-9 [&_th]:px-3 [&_th]:font-medium [&_tr]:border-t [&_tr]:border-slate-200 dark:[&_tr]:border-slate-800";
export const STICKY = "sticky left-0 bg-white dark:bg-slate-900";
const MUTED = "text-slate-600 dark:text-slate-400";

/** The run id, the page's one question, and an optional line under it. Shared by every page. */
export function PageHeader({ run, question, children }: { run: Run; question: string; children?: ReactNode }) {
  return (
    <header>
      <p className={cn("text-sm", MUTED)}>
        Run <span className="font-mono text-xs">{run.manifest.run_id}</span>. Synthetic data only.
      </p>
      <h1 className="text-2xl font-semibold tracking-tight">{question}</h1>
      {children && <p className="mt-1 text-sm">{children}</p>}
    </header>
  );
}

export function Answer({ tone, text, detail }: { tone: Tone; text: string; detail?: string | null }) {
  return (
    <section aria-label="Answer" className={cn(CARD, "relative overflow-hidden p-4 pl-6")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1.5", TONES[tone].band)} />
      <p className="flex items-center gap-2 text-lg font-semibold">
        <SeverityIcon tone={tone} className="size-5" />
        {text}
      </p>
      {detail && <p className="mt-1 text-sm">{detail}</p>}
    </section>
  );
}

function LegCard({ result, title, proves }: { result: LegResult; title: string; proves: string }) {
  const ran = result.status === "RAN";
  // The loader refuses a leg that ran with a count missing. If one gets here anyway, say so, never 0.
  const count = (n: number | null) => (n === null ? "Not reported" : n.toLocaleString("en-US"));
  const stats: [string, string][] = ran
    ? [
        ["Reported matches", count(result.matched)],
        ["Reported unmatched", count(result.unmatched)],
        ["Weak matches", count(result.weak_matched)],
        ["Differences", result.variance_dollars === null ? "Not reported" : formatMoney(result.variance_dollars)],
      ]
    : [];
  const clean = ran && result.variance_count === 0;
  return (
    <div role="group" aria-label={title} className={cn(CARD, "p-4", !ran && "border-dashed bg-slate-100 dark:bg-slate-950")}>
      <h2 className="text-sm font-medium">{title}</h2>
      <p className={cn("text-xs", MUTED)}>{proves}</p>
      <p className="mt-2">
        {ran ? (
          <SeverityBadge tone={clean ? "pass" : "warning"} label={clean ? "Checked, all agree" : `Checked, ${plural(result.variance_count ?? 0, "difference")}`} />
        ) : (
          <span className="text-lg font-semibold text-slate-600 dark:text-slate-400">Not checked</span>
        )}
      </p>
      {ran ? (
        <dl className="mt-3 grid grid-cols-2 gap-2 text-sm tabular-nums">
          {stats.map(([label, value]) => (
            <div key={label}>
              <dt className={cn("text-xs", MUTED)}>{label}</dt>
              <dd className="font-semibold">{value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className={cn("mt-1 text-xs", MUTED)}>{result.not_run_reason}</p>
      )}
    </div>
  );
}

function where(row: Variance): string {
  const place = [row.carrier, row.statement_period].filter(Boolean).join(" ");
  if (row.line_no !== null) return `${place}, line ${row.line_no}`;
  return row.policy_id ? `${place}, policy ${row.policy_id}` : place;
}

function VarianceTable({ rows, messages }: { rows: Variance[]; messages: Map<string, string> }) {
  return (
    <div className={TABLE_WRAP}>
      <table className={TABLE}>
        <caption className="p-3 text-left text-sm font-medium">Differences to review</caption>
        <thead>
          <tr>
            <th className={STICKY}>Member id</th><th>Where</th><th>Amount</th><th>Rule</th><th>Explanation</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.exception_id}>
              <td className={cn(STICKY, "font-mono")}>{row.carrier_member_id ?? "None"}</td>
              <td>{where(row)}</td>
              <td>
                {row.rule_id === "TIE-001" || row.rule_id === "TIE-002" ? (
                  <>
                    <span>{row.rule_id === "TIE-001" ? "No confirmed payment link" : "No confirmed policy link"}</span>
                    <span className={cn("block", MUTED)}>
                      {row.paid === null ? "Statement amount not attributed" : `Statement ${formatMoney(row.paid)}`}; {row.expected === null ? "policy expectation not calculated" : `book expectation ${formatMoney(row.expected)}`}
                    </span>
                  </>
                ) : row.paid === null && row.expected === null ? (
                  // A status disagreement (TIE-004) is not a money check, so there is no amount to show.
                  <span>Status only, no amount</span>
                ) : (
                  <>
                    <span>{differenceText(row.difference)}</span>
                    <span className={cn("block", MUTED)}>
                      Paid {row.paid ? formatMoney(row.paid) : "nothing"}, expected {row.expected ? formatMoney(row.expected) : "nothing"}
                    </span>
                  </>
                )}
              </td>
              <td className="font-mono">{row.rule_id}</td>
              <td className="min-w-64 whitespace-normal">{messages.get(row.exception_id) ?? `See ${row.exception_id}`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TotalsTable({ totals, title, all }: { totals: Totals; title: string; all: string }) {
  if (totals.status === "NOT_RUN") {
    return (
      <div role="group" aria-label={title} className={cn(CARD, "border-dashed p-4")}>
        <h2 className="text-sm font-medium">{title}</h2>
        <p className="text-lg font-semibold text-slate-600 dark:text-slate-400">Not checked</p>
        <p className={cn("text-xs", MUTED)}>{totals.not_run_reason}</p>
      </div>
    );
  }
  const sum = totalsSum(totals.rows);
  const rows = [...totals.rows.map((row) => ({ ...row, total: false })), { key: all, ...sum, within_tolerance: null, total: true }];
  return (
    <div className={TABLE_WRAP}>
      <table className={TABLE} aria-label={title}>
        <caption className="p-3 text-left text-sm font-medium">
          {title}<span className="block text-xs font-normal">Unattributed is the net statement amount without a policy link in this run, already included in Paid.</span>
        </caption>
        <thead>
          <tr>
            <th className={STICKY}>{all === "All agents" ? "Agent (NPN)" : "Carrier"}</th>
            <th>Expected</th><th>Paid</th><th>Difference</th><th>Unattributed (net)</th><th>Tolerance</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className={cn(row.total && "font-semibold")}>
              <th scope="row" className={cn(STICKY, all === "All agents" && !row.total && "font-mono")}>{row.key}</th>
              <td>{formatMoney(row.book_expected)}</td>
              <td>{formatMoney(row.statement_paid)}</td>
              <td>{differenceText(row.difference)}</td>
              <td>{formatMoney(row.unexplained_revenue)}</td>
              <td>
                {row.within_tolerance === null ? null : (
                  <SeverityBadge tone={row.within_tolerance ? "pass" : "error"} label={row.within_tolerance ? "Within" : "Outside"} />
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TieOutView({ run, tieOut, links }: { run: Run; tieOut: TieOut; links?: LinkEvidence[] }) {
  const summary = tieOutSummary(run);
  const other = otherDifferences(tieOut.variances);
  const messages = new Map(run.exceptions.map((record) => [record.id, record.message]));
  // The count matches the table below: leg differences plus the checks that belong to no leg.
  const total = summary.checked ? summary.count + other.count : 0;
  const answer: [Tone, string, string | null] = !summary.checked
    ? ["blocker", "Not checked. The run stopped before the tie-out.", summary.reason]
    : total === 0 && summary.ran === summary.legs
      ? ["pass", "Yes. Every check ran and the money agrees.", "Book, statements, and CRM match."]
      : total === 0
        ? ["warning", "Partly. The checks that ran agree.", `Only ${summary.ran} of ${summary.legs} checks ran.`]
        : ["warning", `Not fully. ${plural(total, "difference")} to review.`, `${formatMoney(summary.dollars)} in differences across ${summary.ran} of ${summary.legs} checks${otherText(other)}.`];
  return (
    <div className="space-y-4">
      <PageHeader run={run} question="Does the money agree?" />
      <Answer tone={answer[0]} text={answer[1]} detail={answer[2]} />
      {summary.checked && <p className="text-sm">{VARIANCE_SUM_NOTE}</p>}
      <LinkEvidencePanel links={links} />
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        {LEGS.map(({ leg, title, proves }) => {
          const result = tieOut.legs.find((item) => item.leg === leg);
          return result && <LegCard key={leg} result={result} title={title} proves={proves} />;
        })}
      </div>
      {summary.checked &&
        (tieOut.variances.length > 0 ? (
          <VarianceTable rows={tieOut.variances} messages={messages} />
        ) : (
          <p className={cn(CARD, "p-4 text-sm")}>No differences found.</p>
        ))}
      <div className="space-y-4">
        <TotalsTable totals={tieOut.byCarrier} title="Totals by carrier" all="All carriers" />
        <TotalsTable totals={tieOut.byAgent} title="Totals by agent" all="All agents" />
      </div>
    </div>
  );
}

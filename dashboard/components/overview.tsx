import Link from "next/link";

import { SeverityBadge, SeverityIcon, TONES, type Tone } from "@/components/severity-badge";
import { PageHeader } from "@/components/tie-out";
import { CARD, Tile } from "@/components/tiles";
import { rtsMatrix } from "@/lib/agents";
import { formatMoney } from "@/lib/money";
import {
  countsBySource, durationText, frozenClock, plural, rtsChecked, runDateText, shortFiles, tieOutSummary,
  type SourceCounts,
} from "@/lib/overview";
import type { Run } from "@/lib/run-loader";
import { otherDifferences, otherText, VARIANCE_SUM_NOTE, type TieOut } from "@/lib/tie-out";
import type { RunStatus, SeverityCounts } from "@/lib/types";
import { cn } from "@/lib/utils";

const ANSWERS: Record<RunStatus, { tone: Tone; answer: string; word: string; fallback: string }> = {
  PASSED: { tone: "pass", answer: "Yes. Every check passed.", word: "Passed", fallback: "No errors, warnings, or blockers." },
  PASSED_WITH_WARNINGS: { tone: "warning", answer: "Yes, with fixes to review.", word: "Passed with warnings", fallback: "" },
  FAILED: { tone: "blocker", answer: "No. A blocker stopped the run.", word: "Failed", fallback: "" },
};

const SEVERITY_TILES: { key: keyof SeverityCounts; tone: Tone; label: string; context: string }[] = [
  { key: "blocker", tone: "blocker", label: "Blockers", context: "Stop the whole load" },
  { key: "error", tone: "error", label: "Errors", context: "Rows kept out of the load files" },
  { key: "warning", tone: "warning", label: "Warnings", context: "Rows load with a flag" },
  { key: "info", tone: "info", label: "Info", context: "Notes only, nothing to fix" },
];

function StatusBanner({ run }: { run: Run }) {
  const { status, status_reason } = run.manifest;
  const { tone, answer, word, fallback } = ANSWERS[status];
  return (
    <section aria-label="Run status" data-tone={tone} className={cn(CARD, "decision-panel relative overflow-hidden")}>
      <span aria-hidden className={cn("absolute inset-y-0 left-0 w-1", TONES[tone].band)} />
      <div className="decision-content">
        <div className="min-w-0">
          <p className="eyebrow mb-2">Readiness decision</p>
          <p className="decision-title flex items-start gap-2 font-semibold">
            <SeverityIcon tone={tone} className="mt-0.5 size-5" />
            {answer}
          </p>
          <p className="decision-detail mt-2 text-sm">
            <SeverityBadge tone={tone} label={word} /> <span>{status_reason ?? fallback}</span>
          </p>
          <ul className="mt-2 text-sm tabular-nums">
            {shortFiles(run).map((file) => (
              <li key={file.source}>
                {`${file.file_name}: expected ${file.rows_expected?.toLocaleString("en-US")} rows, received ${file.rows_received.toLocaleString("en-US")}.`}
              </li>
            ))}
          </ul>
        </div>
        {run.exceptions.length > 0 && (
          <Link href="/exceptions" className="review-action">See the exceptions <span aria-hidden>→</span></Link>
        )}
      </div>
    </section>
  );
}

function SourceBars({ rows }: { rows: SourceCounts[] }) {
  const widest = Math.max(1, ...rows.map((row) => row.total));
  return (
    <section aria-labelledby="by-source" className={cn(CARD, "source-evidence p-5")}>
      <div className="panel-heading"><h2 id="by-source">Exceptions by source file</h2><span className="text-xs text-muted-foreground">Severity distribution</span></div>
      {rows.length === 0 && <p className="mt-2 text-sm text-muted-foreground">No exceptions.</p>}
      <ul className="mt-3 space-y-1">
        {rows.map(({ source, counts, total }) => (
          <li key={source} className="source-evidence-row grid min-w-0 grid-cols-[minmax(0,1fr)_1fr] items-center gap-x-4 gap-y-1 text-sm sm:grid-cols-[11rem_1fr_15rem]">
            <span className="truncate font-mono text-xs" title={source}>{source}</span>
            <span aria-hidden className="flex h-3 overflow-hidden rounded bg-muted">
              <span className="flex" style={{ width: `${(100 * total) / widest}%` }}>
                {SEVERITY_TILES.filter(({ key }) => counts[key] > 0).map(({ key, tone }) => (
                  <span key={key} className={TONES[tone].band} style={{ flexGrow: counts[key] }} />
                ))}
              </span>
            </span>
            <span className="col-span-2 text-xs text-muted-foreground tabular-nums sm:col-span-1">
              {SEVERITY_TILES.filter(({ key }) => counts[key] > 0)
                .map(({ key }) => plural(counts[key], key))
                .join(", ")}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

const STOPPED = "Found before the run stopped. Row checks did not run.";

export function Overview({ run, tieOut: tieFiles }: { run: Run; tieOut: TieOut }) {
  const { manifest, scorecard } = run;
  const failed = manifest.status === "FAILED";
  const tieOut = tieOutSummary(run);
  const rts = rtsChecked(run);
  const jevOff = manifest.jev.mode === "off";
  return (
    <div className="page-stack">
      <PageHeader run={run} question="Can this agency go live?">Validate the incoming book, prioritize fixes, and trace the evidence before release.</PageHeader>
      <StatusBanner run={run} />
      <section aria-label="Load quality" className="metric-strip">
        {SEVERITY_TILES.map(({ key, tone, label, context }) => {
          // A blocker stops the run before row checks. Raw-stage checks (like a missing file) still ran,
          // so a count found before the stop is shown with that context. Zero there means not checked.
          const count = scorecard.exceptions_by_severity[key];
          if (failed && key !== "blocker" && count === 0) {
            return <Tile key={key} label={label} value="Not checked" context="The run stopped before row checks" muted />;
          }
          return (
            <Tile key={key} label={label} tone={tone} value={count.toLocaleString("en-US")} context={failed && key !== "blocker" ? STOPPED : context} />
          );
        })}
        <Tile
          label="Clean rows"
          tone="pass"
          muted={failed}
          value={failed ? "None" : scorecard.rows_clean.toLocaleString("en-US")}
          context={failed ? "No load files written" : `of ${scorecard.rows_in.toLocaleString("en-US")} rows read`}
        />
      </section>
      <section aria-label="Financial and operational checks" className="space-y-3">
        <h2 className="section-eyebrow">Financial and operational checks</h2>
        <div className="overview-check-grid grid min-w-0 grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {tieOut.checked ? (
            <Tile
              label="Check variance sum"
              note={VARIANCE_SUM_NOTE}
              value={formatMoney(tieOut.dollars)}
              context={`${plural(tieOut.count, "item")}, ${tieOut.ran === tieOut.legs ? `all ${tieOut.legs}` : `${tieOut.ran} of ${tieOut.legs}`} checks ran${otherText(otherDifferences(tieFiles.variances))}`}
            />
          ) : (
            <Tile label="Check variance sum" value="Not checked" context={tieOut.reason} muted />
          )}
          <Tile
            label="RTS gaps"
            value={rts ? rtsMatrix(run.rts).gapPolicies.toLocaleString("en-US") : "Not checked"}
            context={rts ? "Policies sold without ready-to-sell status" : "The run stopped before this check"}
            muted={!rts}
          />
          <Tile
            label="Jev AI review"
            value={jevOff ? "Off" : plural(manifest.jev.calls, "call")}
            context={`${formatMoney(manifest.jev.estimated_cost_usd)} estimated, ${manifest.jev.mode} mode`}
          />
          <Tile
            label="Run time"
            value={durationText(run)}
            context={frozenClock(run) ? `Frozen clock, run on ${runDateText(run)}` : `Run on ${runDateText(run)}`}
          />
        </div>
      </section>
      <SourceBars rows={countsBySource(run)} />
    </div>
  );
}

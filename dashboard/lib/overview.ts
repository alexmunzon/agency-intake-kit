import { sumMoney } from "@/lib/money";
import type { Run } from "@/lib/run-loader";
import type { InputFile, SeverityCounts } from "@/lib/types";

// Turns a run into the facts the Overview shows. A check that did not run is "not checked",
// never zero, because a zero would read as "checked, nothing wrong".
export type TieOutSummary =
  | { checked: false; reason: string }
  | { checked: true; ran: number; legs: number; dollars: string; count: number };

export interface SourceCounts {
  source: string;
  counts: SeverityCounts;
  total: number;
}

export function tieOutSummary(run: Run): TieOutSummary {
  const legs = run.scorecard.tie_out;
  const ran = legs.filter((leg) => leg.status === "RAN");
  if (ran.length === 0) {
    return { checked: false, reason: legs[0]?.not_run_reason ?? "The tie-out did not run." };
  }
  return {
    checked: true,
    ran: ran.length,
    legs: legs.length,
    dollars: sumMoney(ran.map((leg) => leg.variance_dollars ?? "0.00")),
    count: ran.reduce((sum, leg) => sum + (leg.variance_count ?? 0), 0),
  };
}

/** RTS coverage is built after mapping, so a run stopped by a blocker never checked it. */
export function rtsChecked(run: Run): boolean {
  return !(run.manifest.status === "FAILED" && run.rts.cells.length === 0);
}

export function countsBySource(run: Run): SourceCounts[] {
  const bySource = new Map<string, SeverityCounts>();
  for (const record of run.exceptions) {
    const counts = bySource.get(record.source) ?? { blocker: 0, error: 0, warning: 0, info: 0 };
    counts[record.severity.toLowerCase() as keyof SeverityCounts] += 1;
    bySource.set(record.source, counts);
  }
  return [...bySource]
    .map(([source, counts]) => ({ source, counts, total: Object.values(counts).reduce((a, b) => a + b, 0) }))
    .sort((a, b) => b.total - a.total || a.source.localeCompare(b.source));
}

export function shortFiles(run: Run): InputFile[] {
  return run.manifest.inputs.filter(
    (file) => file.rows_expected !== null && file.rows_received !== file.rows_expected,
  );
}

/** A frozen clock (--as-of) pins both times, so the difference is not a measurement (#77). */
export function frozenClock(run: Run): boolean {
  return run.manifest.as_of !== null;
}

export function durationText(run: Run): string {
  if (frozenClock(run)) return "Not measured";
  const ms = Date.parse(run.manifest.finished_at) - Date.parse(run.manifest.started_at);
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return plural(seconds, "second");
  return `${Math.floor(seconds / 60)} min ${seconds % 60} sec`;
}

export function runDateText(run: Run): string {
  const date = new Date(run.manifest.started_at);
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function plural(count: number, word: string): string {
  return `${count.toLocaleString("en-US")} ${word}${count === 1 || word === "info" ? "" : "s"}`;
}

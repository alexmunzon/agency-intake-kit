import type { Tone } from "@/components/severity-badge";
import type { ExceptionRecord, Severity } from "@/lib/types";

// The Exceptions page's queue logic, kept out of the components so tests can check it directly.
export const SEVERITY_ORDER: Severity[] = ["BLOCKER", "ERROR", "WARNING", "INFO"];

export interface ExceptionFilters {
  severity: Severity | "";
  rule: string;
  source: string;
}

export const NO_FILTERS: ExceptionFilters = { severity: "", rule: "", source: "" };

export function toneOf(severity: Severity): Tone {
  return severity.toLowerCase() as Tone;
}

/** Blockers first, then errors, warnings, and info. File order within each severity. */
export function orderExceptions(records: ExceptionRecord[]): ExceptionRecord[] {
  const rank = (record: ExceptionRecord) => SEVERITY_ORDER.indexOf(record.severity);
  return [...records].sort((a, b) => rank(a) - rank(b) || a.id.localeCompare(b.id));
}

export function filterExceptions(records: ExceptionRecord[], filters: ExceptionFilters): ExceptionRecord[] {
  return records.filter(
    (record) =>
      (!filters.severity || record.severity === filters.severity) &&
      (!filters.rule || record.rule_id === filters.rule) &&
      (!filters.source || record.source === filters.source),
  );
}

/** The distinct values a filter can take, sorted, so the dropdowns only offer what exists. */
export function choices(records: ExceptionRecord[], key: "rule_id" | "source"): string[] {
  return [...new Set(records.map((record) => record[key]))].sort();
}

export function percent(probability: number): string {
  return `${Math.round(probability * 100)}%`;
}

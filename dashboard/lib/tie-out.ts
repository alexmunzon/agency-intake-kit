import { formatMoney, sumMoney } from "@/lib/money";
import { plural } from "@/lib/overview";
import { parseJson, type Run } from "@/lib/run-loader";
import type { LegResult, TieOutLeg, TotalRow, Totals, Variance } from "@/lib/types";

// Parses tie_out/*.json from one run. Like run-loader, it checks shape only (the engine's models
// validate for real), and refuses money written as a number so no cents can be lost to floats.
export interface TieOut {
  legs: LegResult[];
  variances: Variance[];
  byCarrier: Totals;
  byAgent: Totals;
}
export const VARIANCE_SUM_NOTE = "Sum across checks; a line can appear more than once. This is not a missing-revenue total.";

export const LEGS: { leg: TieOutLeg; file: string; title: string; proves: string }[] = [
  { leg: "BOOK_VS_STATEMENT", file: "leg_book_vs_statement", title: "A. Book vs statement", proves: "Policy payment links reported by the run" },
  { leg: "STATEMENT_VS_BOOK", file: "leg_statement_vs_book", title: "B. Statement vs book", proves: "Statement policy links reported by the run" },
  { leg: "CRM_VS_STATEMENT", file: "leg_crm_vs_statement", title: "C. CRM vs statement", proves: "CRM status comparison for linked policies" },
];
/** File stems in tie_out/, legs first. */
export const TIE_OUT_FILES = [...LEGS.map((leg) => leg.file), "variances", "totals_by_carrier", "totals_by_agent"];
const MONEY_FIELDS = ["paid", "expected", "difference", "variance_dollars", "book_expected", "statement_paid", "unexplained_revenue"];
const ZERO = /^-?0+(\.0+)?$/;
const COUNTS = ["matched", "unmatched", "weak_matched", "variance_count", "variance_dollars"] as const;

function checkMoney(value: unknown, where: string): void {
  if (Array.isArray(value)) return value.forEach((item) => checkMoney(item, where));
  if (typeof value !== "object" || value === null) return;
  for (const [key, field] of Object.entries(value)) {
    if (MONEY_FIELDS.includes(key) && field !== null && typeof field !== "string") {
      throw new Error(`${where}: ${key} must be text`);
    }
    checkMoney(field, where);
  }
}

function parse<T>(files: Record<string, string>, name: string, key: string): T {
  const value = parseJson(files[name], `tie_out/${name}.json`) as Record<string, unknown>;
  if (typeof value !== "object" || value === null || !(key in value)) {
    throw new Error(`${name}.json: missing ${key}`);
  }
  checkMoney(value, `${name}.json`);
  return value as T;
}

// Each leg file must hold its own leg. A leg that ran has every count; a leg that did not run has
// none, because a zero would read as "checked, nothing wrong".
function checkLeg(result: LegResult, leg: TieOutLeg, where: string): void {
  if (result.leg !== leg) throw new Error(`${where}: holds ${result.leg}, expected ${leg}`);
  for (const key of COUNTS) {
    if (result.status === "RAN" && result[key] === null) throw new Error(`${where}: ran but ${key} is missing`);
    if (result.status !== "RAN" && result[key] !== null) throw new Error(`${where}: did not run but ${key} is set`);
  }
}

/** With a run, also checks that the leg files agree with that run's scorecard. */
export function parseTieOut(files: Record<string, string>, run?: Run): TieOut {
  const legs = LEGS.map(({ file, leg }) => {
    const result = parse<LegResult>(files, file, "status");
    checkLeg(result, leg, `tie_out/${file}.json`);
    const summary = run?.scorecard.tie_out.find((item) => item.leg === leg);
    if (run && (summary?.status !== result.status || summary.variance_count !== result.variance_count || summary.variance_dollars !== result.variance_dollars)) {
      throw new Error(`tie_out/${file}.json: not from the same run as scorecard.json`);
    }
    return result;
  });
  return {
    legs,
    variances: parse<{ variances: Variance[] }>(files, "variances", "variances").variances,
    byCarrier: parse<Totals>(files, "totals_by_carrier", "rows"),
    byAgent: parse<Totals>(files, "totals_by_agent", "rows"),
  };
}

/** Dollar checks that belong to no leg (TIE-003 rate table, TIE-005 totals), summed as positive amounts. */
export function otherDifferences(variances: Variance[]): { count: number; dollars: string } {
  const rows = variances.filter((row) => row.leg === null);
  return { count: rows.length, dollars: sumMoney(rows.map((row) => row.difference.replace(/^-/, ""))) };
}

/** "61.05" becomes "$61.05 more paid". Direction is in words, never only in color. */
export function differenceText(difference: string): string {
  if (ZERO.test(difference)) return "Even";
  const negative = difference.startsWith("-");
  return `${formatMoney(negative ? difference.slice(1) : difference)} ${negative ? "less" : "more"} paid`;
}

export function totalsSum(rows: TotalRow[]): Omit<TotalRow, "key" | "within_tolerance"> {
  const sum = (field: "book_expected" | "statement_paid" | "difference" | "unexplained_revenue") =>
    sumMoney(rows.map((row) => row[field]));
  return {
    book_expected: sum("book_expected"),
    statement_paid: sum("statement_paid"),
    difference: sum("difference"),
    unexplained_revenue: sum("unexplained_revenue"),
  };
}

export function isZero(amount: string): boolean {
  return ZERO.test(amount);
}

/** ", plus 1 commission off the rate table or totals ($6.50)", or "" when there are none. */
export function otherText(other: { count: number; dollars: string }): string {
  return other.count === 0 ? "" : `, plus ${plural(other.count, "commission")} off the rate table or totals (${formatMoney(other.dollars)})`;
}

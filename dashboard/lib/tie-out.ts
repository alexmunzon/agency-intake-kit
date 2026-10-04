import { readFile } from "node:fs/promises";
import path from "node:path";

import { formatMoney, sumMoney } from "@/lib/money";
import type { LegResult, TieOutLeg, TotalRow, Totals, Variance } from "@/lib/types";

// Loads tie_out/*.json from one run. Like run-loader, it checks shape only (the engine's models
// validate for real), and refuses money written as a number so no cents can be lost to floats.
export interface TieOut {
  legs: LegResult[];
  variances: Variance[];
  byCarrier: Totals;
  byAgent: Totals;
}

export const LEGS: { leg: TieOutLeg; file: string; title: string; proves: string }[] = [
  { leg: "BOOK_VS_STATEMENT", file: "leg_book_vs_statement", title: "A. Book vs statement", proves: "Every active policy has a commission line" },
  { leg: "STATEMENT_VS_BOOK", file: "leg_statement_vs_book", title: "B. Statement vs book", proves: "Every commission line matches a policy in the book" },
  { leg: "CRM_VS_STATEMENT", file: "leg_crm_vs_statement", title: "C. CRM vs statement", proves: "CRM status agrees with the carrier" },
];
const OTHER_FILES = ["variances", "totals_by_carrier", "totals_by_agent"];
const MONEY_FIELDS = ["paid", "expected", "difference", "variance_dollars", "book_expected", "statement_paid", "unexplained_revenue"];
const ZERO = /^-?0+(\.0+)?$/;

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
  const value = JSON.parse(files[name]) as Record<string, unknown>;
  if (typeof value !== "object" || value === null || !(key in value)) {
    throw new Error(`${name}.json: missing ${key}`);
  }
  checkMoney(value, `${name}.json`);
  return value as T;
}

export function parseTieOut(files: Record<string, string>): TieOut {
  return {
    legs: LEGS.map(({ file }) => parse<LegResult>(files, file, "status")),
    variances: parse<{ variances: Variance[] }>(files, "variances", "variances").variances,
    byCarrier: parse<Totals>(files, "totals_by_carrier", "rows"),
    byAgent: parse<Totals>(files, "totals_by_agent", "rows"),
  };
}

export async function loadTieOut(runDir: string): Promise<TieOut> {
  const files: Record<string, string> = {};
  for (const name of [...LEGS.map((leg) => leg.file), ...OTHER_FILES]) {
    try {
      files[name] = await readFile(path.join(runDir, "tie_out", `${name}.json`), "utf8");
    } catch {
      throw new Error(`Could not read tie_out/${name}.json in ${runDir}`);
    }
  }
  return parseTieOut(files);
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

import { expect, it } from "vitest";
import { parseStatementGroups } from "@/lib/statement-groups";
import type { StatementTotals } from "@/lib/statement-totals";

const lineage = { source_file: "s.csv", sheet: null, row_number: 2, raw_hash: "a".repeat(64), run_id: "run", mapping_version: "unmapped" };
const amounts = ["12.50", "-12.50", null, null, "2.01"];
const totals: StatementTotals = { schema_version: 1, run_id: "run", status: "PARTIAL", reason: "excluded_rows",
  valid_line_count: 3, excluded_line_count: 2, total_paid: "2.01", lines: amounts.map((amount, i) => ({
    source: "statement_s", lineage: { ...lineage, row_number: i + 2 }, amount, reason: amount === null ? "amount_blank" : "valid" })) };
const artifact = () => ({ schema_version: 1, run_id: "run", lines: totals.lines.map((line, i) => ({ lineage: line.lineage,
  carrier: i < 3 ? "Carrier A" : null, statement_period: i < 3 ? "2026-09" : i === 3 ? null : "2026-08" })) });
const parse = (value: unknown, evidence: StatementTotals | undefined = totals) => parseStatementGroups(JSON.stringify(value), evidence);

it("groups signed exact amounts, exclusions, explicit unknowns, null and genuine zero", () => {
  expect(parse(artifact())).toEqual([
    { carrier: "Carrier A", statement_period: "2026-09", valid_line_count: 2, excluded_line_count: 1, total_paid: "0.00" },
    { carrier: null, statement_period: "2026-08", valid_line_count: 1, excluded_line_count: 0, total_paid: "2.01" },
    { carrier: null, statement_period: null, valid_line_count: 0, excluded_line_count: 1, total_paid: null },
  ]);
  const shuffled = artifact(); shuffled.lines.reverse();
  expect(parse(shuffled)).toEqual(parse(artifact()));
});
it("accepts empty blocked and unavailable evidence without manufacturing groups", () => {
  for (const status of ["BLOCKED", "UNAVAILABLE"] as const) {
    expect(parse({ schema_version: 1, run_id: "run", lines: [] }, { ...totals, status, lines: [] })).toEqual([]);
  }
  expect(() => parseStatementGroups(JSON.stringify(artifact()), undefined)).toThrow(/statement_groups.json/);
});
it.each(["missing", "extra", "duplicate", "wrong-run", "hash", "mapping", "row", "sheet", "file", "shape", "nested-shape", "carrier", "blank", "period", "year", "month"])("rejects inconsistent %s metadata", kind => {
  const value = artifact();
  if (kind === "missing") value.lines.pop();
  if (kind === "extra") value.lines.push(value.lines[0]);
  if (kind === "duplicate") value.lines[1] = value.lines[0];
  if (kind === "wrong-run") value.run_id = "other";
  if (kind === "hash") value.lines[0].lineage = { ...lineage, raw_hash: "b".repeat(64) };
  if (kind === "mapping") value.lines[0].lineage = { ...lineage, mapping_version: "other" };
  if (kind === "row") value.lines[0].lineage = { ...lineage, row_number: 99 };
  if (kind === "sheet") Object.assign(value.lines[0].lineage = { ...lineage }, { sheet: "other" });
  if (kind === "file") value.lines[0].lineage = { ...lineage, source_file: "other.csv" };
  if (kind === "shape") Object.assign(value, { extra: true });
  if (kind === "nested-shape") Object.assign(value.lines[0], { extra: true });
  if (kind === "carrier") value.lines[0].carrier = " Carrier A ";
  if (kind === "blank") value.lines[0].carrier = "";
  if (kind === "period") value.lines[0].statement_period = "2026-9";
  if (kind === "year") value.lines[0].statement_period = "0000-09";
  if (kind === "month") value.lines[0].statement_period = "2026-13";
  expect(() => parse(value)).toThrow(/statement_groups.json/);
});
it("rejects duplicate JSON keys, numeric lineage syntax and malformed JSON without echoing input", () => {
  const text = JSON.stringify(artifact());
  for (const invalid of [text.replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
    text.replace('"carrier":"Carrier A"', '"carrier":"Carrier A","carrier":"Carrier A"'),
    text.replace('"row_number":2', '"row_number":2e0'), '{PRIVATE']) {
    expect(() => parseStatementGroups(invalid, totals)).toThrow(/statement_groups.json/);
    expect(() => parseStatementGroups(invalid, totals)).not.toThrow(/PRIVATE/);
  }
});

import { describe, expect, it } from "vitest";
import { parseStatementTotals } from "@/lib/statement-totals";

const lineage = { source_file: "statement.csv", sheet: null, row_number: 2, raw_hash: "a".repeat(64), run_id: "run-1", mapping_version: "unmapped" };
const valid = { source: "statement_harborline", lineage, amount: "12.50", reason: "valid" };
const excluded = { ...valid, lineage: { ...lineage, row_number: 3 }, amount: null, reason: "amount_blank" };
const artifact = { schema_version: 1, run_id: "run-1", status: "PARTIAL", reason: "excluded_rows", valid_line_count: 1, excluded_line_count: 1, total_paid: "12.50", lines: [valid, excluded] };
const parse = (value: unknown) => parseStatementTotals(JSON.stringify(value), "run-1");

describe("statement totals attachment", () => {
  it("retains signed valid and excluded received-row evidence", () => {
    expect(parse(artifact)).toEqual(artifact);
    expect(parse({ ...artifact, status: "AVAILABLE", reason: null, excluded_line_count: 0, lines: [{ ...valid, amount: "0.00" }], total_paid: "0.00" }).total_paid).toBe("0.00");
    expect(parse({ ...artifact, status: "AVAILABLE", reason: null, valid_line_count: 2, excluded_line_count: 0,
      lines: [{ ...valid, amount: "9999999999.99" }, { ...valid, lineage: { ...lineage, row_number: 3 }, amount: "9999999999.99" }],
      total_paid: "19999999999.98" }).total_paid).toBe("19999999999.98");
  });

  it.each([
    { ...artifact, run_id: "other" },
    { ...artifact, lines: [{ ...valid, lineage: { ...lineage, run_id: "other" } }], excluded_line_count: 0 },
    { ...artifact, lines: [valid, { ...excluded, lineage }] },
    { ...artifact, total_paid: "12.51" },
    { ...artifact, valid_line_count: 2 },
    { ...artifact, status: "AVAILABLE" },
    { ...artifact, lines: [{ ...valid, amount: "12.501" }, excluded] },
    { ...artifact, lines: [{ ...valid, amount: "10000000000.00" }, excluded] },
    { ...artifact, lines: [{ ...valid, amount: "-0.00" }, excluded] },
    { ...artifact, lines: [{ ...valid, source: "crm" }, excluded] },
    { ...artifact, lines: [{ ...valid, raw_name: "PRIVATE" }, excluded] },
  ])("rejects inconsistent shape, identity, totals and sources", (bad) => {
    expect(() => parse(bad)).toThrow(/statement_totals\.json/);
  });

  it("keeps blocked, unavailable, and all-excluded states distinct", () => {
    expect(parse({ ...artifact, status: "BLOCKED", reason: "raw_gate_blocked", lines: [], valid_line_count: 0, excluded_line_count: 0, total_paid: null }).status).toBe("BLOCKED");
    expect(parse({ ...artifact, status: "UNAVAILABLE", reason: "no_statements", lines: [], valid_line_count: 0, excluded_line_count: 0, total_paid: null }).status).toBe("UNAVAILABLE");
    expect(parse({ ...artifact, lines: [excluded], valid_line_count: 0, total_paid: null }).status).toBe("PARTIAL");
    expect(() => parse({ ...artifact, status: "BLOCKED", reason: "raw_gate_blocked" })).toThrow(/statement_totals\.json/);
  });

  it("rejects duplicate JSON keys without echoing private values", () => {
    const text = JSON.stringify(artifact).replace('"run_id":"run-1"', '"run_id":"run-1","run_id":"PRIVATE"');
    expect(() => parseStatementTotals(text, "run-1")).toThrow(/statement_totals\.json/);
    expect(() => parseStatementTotals(text, "run-1")).not.toThrow(/PRIVATE/);
    const sameTop = JSON.stringify(artifact).replace('"run_id":"run-1"', '"run_id":"run-1","run_id":"run-1"');
    const sameNested = JSON.stringify(artifact).replace('"row_number":2', '"row_number":2,"row_number":2');
    expect(() => parseStatementTotals(sameTop, "run-1")).toThrow(/statement_totals\.json/);
    expect(() => parseStatementTotals(sameNested, "run-1")).toThrow(/statement_totals\.json/);
  });

  it.each(['"schema_version":1.0', '"valid_line_count":1e0', '"row_number":2.0'])("rejects non-integer JSON token %s", (replacement) => {
    const key = replacement.split(":")[0];
    const text = JSON.stringify(artifact).replace(new RegExp(`${key}:\\d+`), replacement);
    expect(() => parseStatementTotals(text, "run-1")).toThrow(/statement_totals\.json/);
  });
});

import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { loadRunDir } from "@/lib/run-loader";
import { differenceText, loadTieOut, otherDifferences, parseTieOut, totalsSum } from "@/lib/tie-out";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const TIE_FILES = ["leg_book_vs_statement", "leg_statement_vs_book", "leg_crm_vs_statement", "variances", "totals_by_carrier", "totals_by_agent"];

async function tieFiles(name: string): Promise<Record<string, string>> {
  const files: Record<string, string> = {};
  for (const file of TIE_FILES) files[file] = await readFile(path.join(FIXTURES, name, "tie_out", `${file}.json`), "utf8");
  return files;
}

function edit(text: string, change: (value: Record<string, unknown>) => void): string {
  const value = JSON.parse(text);
  change(value);
  return JSON.stringify(value);
}

describe("loadTieOut", () => {
  it("reads all three legs in order A, B, C for the warnings sample", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run"));
    expect(tie.legs.map((leg) => [leg.leg, leg.status])).toEqual([
      ["BOOK_VS_STATEMENT", "RAN"],
      ["STATEMENT_VS_BOOK", "RAN"],
      ["CRM_VS_STATEMENT", "RAN"],
    ]);
    expect(tie.variances).toHaveLength(4);
  });

  it("keeps example 4, the Harborline orphan payment, exactly", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run"));
    const orphan = tie.variances.find((row) => row.carrier_member_id === "HL-998213");
    expect(orphan).toMatchObject({
      rule_id: "TIE-002",
      carrier: "Harborline",
      statement_period: "2026-08",
      line_no: 212,
      paid: "61.05",
      difference: "61.05",
    });
  });

  it("marks every leg and both totals NOT_RUN with no numbers for the failed sample", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run-failed"));
    for (const leg of tie.legs) {
      expect(leg.status).toBe("NOT_RUN");
      expect(leg.matched).toBeNull();
      expect(leg.variance_dollars).toBeNull();
      expect(leg.not_run_reason).toMatch(/CMP-001/);
    }
    expect(tie.byCarrier.status).toBe("NOT_RUN");
    expect(tie.byAgent.rows).toEqual([]);
    expect(tie.variances).toEqual([]);
  });

  it("has no variances for the passed sample", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run-passed"));
    expect(tie.variances).toEqual([]);
    expect(tie.legs.every((leg) => leg.variance_count === 0)).toBe(true);
  });

  it("refuses money written as a number", async () => {
    const dir = path.join(FIXTURES, "sample-run", "tie_out");
    const files: Record<string, string> = {};
    for (const name of ["leg_book_vs_statement", "leg_statement_vs_book", "leg_crm_vs_statement", "variances", "totals_by_carrier", "totals_by_agent"]) {
      files[name] = await readFile(path.join(dir, `${name}.json`), "utf8");
    }
    const bad = JSON.parse(files.variances);
    bad.variances[1].paid = 61.05;
    expect(() => parseTieOut({ ...files, variances: JSON.stringify(bad) })).toThrow(/paid must be text/);
  });

  it("names the file it could not read", async () => {
    await expect(loadTieOut(path.join(FIXTURES, "no-such-run"))).rejects.toThrow(/leg_book_vs_statement\.json/);
  });
});

describe("money words", () => {
  it("labels a difference with a direction word, not color only", () => {
    expect(differenceText("61.05")).toBe("$61.05 more paid");
    expect(differenceText("-31.00")).toBe("$31.00 less paid");
    expect(differenceText("0.00")).toBe("Even");
  });

  it("adds totals exactly", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run"));
    expect(totalsSum(tie.byCarrier.rows)).toEqual({
      book_expected: "28115.50",
      statement_paid: "28145.55",
      difference: "30.05",
      unexplained_revenue: "61.05",
    });
  });
});

describe("parseTieOut checks", () => {
  it("refuses a leg file that holds a different leg", async () => {
    const files = await tieFiles("sample-run");
    expect(() => parseTieOut({ ...files, leg_book_vs_statement: files.leg_statement_vs_book })).toThrow(
      /leg_book_vs_statement\.json: holds STATEMENT_VS_BOOK, expected BOOK_VS_STATEMENT/,
    );
  });

  it("refuses a leg that ran with a count missing", async () => {
    const files = await tieFiles("sample-run");
    const bad = edit(files.leg_statement_vs_book, (leg) => (leg.matched = null));
    expect(() => parseTieOut({ ...files, leg_statement_vs_book: bad })).toThrow(/leg_statement_vs_book\.json: ran but matched is missing/);
  });

  it("refuses a leg that did not run but has numbers", async () => {
    const files = await tieFiles("sample-run-failed");
    const bad = edit(files.leg_crm_vs_statement, (leg) => (leg.matched = 0));
    expect(() => parseTieOut({ ...files, leg_crm_vs_statement: bad })).toThrow(/leg_crm_vs_statement\.json: did not run but matched is set/);
  });

  it("refuses tie-out files from a different run than the scorecard", async () => {
    const run = await loadRunDir(path.join(FIXTURES, "sample-run"));
    const files = await tieFiles("sample-run-failed");
    expect(() => parseTieOut(files, run)).toThrow(/not from the same run as scorecard\.json/);
  });

  it("accepts each sample with its own scorecard", async () => {
    for (const name of ["sample-run", "sample-run-failed", "sample-run-passed"]) {
      const run = await loadRunDir(path.join(FIXTURES, name));
      const files = await tieFiles(name);
      expect(() => parseTieOut(files, run)).not.toThrow();
    }
  });

  it.each(TIE_FILES)("names tie_out/%s.json when it is not valid JSON", async (name) => {
    const files = await tieFiles("sample-run");
    expect(() => parseTieOut({ ...files, [name]: "{" })).toThrow(new RegExp(`tie_out/${name}\\.json: not valid JSON`));
  });
});

describe("other differences", () => {
  it("counts the rate-table check that belongs to no leg on the warnings sample", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run"));
    expect(otherDifferences(tie.variances)).toEqual({ count: 1, dollars: "6.50" });
  });

  it("is empty on the passed sample", async () => {
    const tie = await loadTieOut(path.join(FIXTURES, "sample-run-passed"));
    expect(otherDifferences(tie.variances)).toEqual({ count: 0, dollars: "0.00" });
  });
});


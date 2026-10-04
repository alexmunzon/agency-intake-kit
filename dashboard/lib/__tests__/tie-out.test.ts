import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { differenceText, loadTieOut, parseTieOut, totalsSum } from "@/lib/tie-out";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

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

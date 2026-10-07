import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

import {
  buildDecisions, DECISIONS_NOTE, decisionsFileName, parseMappingReview, readMappingReview,
} from "@/lib/mapping-review";

const TEXT = readFileSync(path.join(import.meta.dirname, "fixtures", "mapping-review.json"), "utf8");
const AT = "2026-10-06T12:00:00.000Z";
const mutate = (change: (value: Record<string, unknown>) => void) => {
  const value = JSON.parse(TEXT) as Record<string, unknown>;
  change(value);
  return JSON.stringify(value);
};
const firstItem = (value: Record<string, unknown>) => (value.items as Record<string, unknown>[])[0];

describe("parseMappingReview", () => {
  it("reads a well formed review for the matching run", () => {
    const review = parseMappingReview(TEXT, "demo");
    expect(review.items).toHaveLength(3);
    expect(review.items[1].proposed_field).toBe("policies.premium");
  });

  it.each([
    ["broken JSON", "{not json"],
    ["a different run", mutate((v) => { v.run_id = "other-run"; })],
    ["an unknown Jev mode", mutate((v) => { v.jev_mode = "turbo"; })],
    ["items that are not a list", mutate((v) => { v.items = {}; })],
    ["a bad item id", mutate((v) => { firstItem(v).item_id = "item-1"; })],
    ["a bad fingerprint", mutate((v) => { firstItem(v).format_fingerprint = "XYZ"; })],
    ["an unknown origin", mutate((v) => { firstItem(v).origin = "guess"; })],
    ["a proposal outside the allowed fields", mutate((v) => { firstItem(v).proposed_field = "clients.ssn"; })],
    ["withheld samples that are present", mutate((v) => { firstItem(v).samples = ["x"]; })],
    ["more than five samples", mutate((v) => {
      const item = (v.items as Record<string, unknown>[])[1];
      item.samples = ["a", "b", "c", "d", "e", "f"];
    })],
    ["confidence above 1", mutate((v) => { (v.items as Record<string, unknown>[])[1].confidence = 1.4; })],
    ["confidence with no model answer", mutate((v) => { firstItem(v).confidence = 0.5; })],
    ["negative rows", mutate((v) => { firstItem(v).rows_with_value = -1; })],
    ["a missing explanation", mutate((v) => { delete firstItem(v).explanation; })],
    ["a duplicate item", mutate((v) => { (v.items as unknown[]).push(firstItem(v)); })],
  ])("refuses %s with a plain message", (_label, text) => {
    expect(() => parseMappingReview(text, "demo")).toThrow(/^mapping_review\.json: /);
  });
});

describe("readMappingReview", () => {
  it("returns nothing when the run has no review file", () => {
    expect(readMappingReview(undefined, "demo")).toBeUndefined();
  });
  it("turns a malformed file into an error instead of throwing", () => {
    const state = readMappingReview("[]", "demo");
    expect(state).toEqual({ ok: false, error: expect.stringMatching(/^mapping_review\.json: /) });
  });
});

describe("buildDecisions", () => {
  const review = parseMappingReview(TEXT, "demo");
  const [notes, premium, paid] = review.items;

  it("writes exactly the interface fields with the fixed note", () => {
    const file = buildDecisions(review, {
      [premium.item_id]: { action: "approve" },
      [paid.item_id]: { action: "correct", field: "commission_lines.policy_id" },
      [notes.item_id]: { action: "ignore" },
    }, "  Dana Reviewer ", AT);
    expect(Object.keys(file)).toEqual(["run_id", "mapping_version", "reviewer", "decided_at", "note", "decisions"]);
    expect(file.note).toBe("a reviewer's note, not an authenticated approval");
    expect(file.note).toBe(DECISIONS_NOTE);
    expect(file.reviewer).toBe("Dana Reviewer");
    expect(file.decided_at).toBe(AT);
    expect(file.mapping_version).toBe(review.mapping_version);
    expect(file.decisions).toEqual([
      { item_id: notes.item_id, source: "crm", header: "Agent Remarks", format_fingerprint: "9f8e7d6c5b4a3921", action: "ignore", field: null },
      { item_id: premium.item_id, source: "crm", header: "Prem Amt", format_fingerprint: "9f8e7d6c5b4a3921", action: "approve", field: "policies.premium" },
      { item_id: paid.item_id, source: "statement_bluepeak", header: "Comm Pd", format_fingerprint: "0123456789abcdef", action: "correct", field: "commission_lines.policy_id" },
    ]);
    for (const decision of file.decisions) {
      expect(Object.keys(decision)).toEqual(["item_id", "source", "header", "format_fingerprint", "action", "field"]);
    }
  });

  it("leaves unresolved items and unfinished corrections out", () => {
    const file = buildDecisions(review, {
      [premium.item_id]: { action: "leave" },
      [paid.item_id]: { action: "correct", field: null },
    }, "Dana", AT);
    expect(file.decisions).toEqual([]);
  });

  it("refuses a blank reviewer name", () => {
    expect(() => buildDecisions(review, {}, "   ", AT)).toThrow(/name/);
  });

  it("refuses to approve an item with no proposal", () => {
    expect(() => buildDecisions(review, { [notes.item_id]: { action: "approve" } }, "Dana", AT)).toThrow(/proposal/);
  });

  it("refuses a correction outside the allowed fields or to none", () => {
    expect(() => buildDecisions(review, { [premium.item_id]: { action: "correct", field: "clients.ssn" } }, "Dana", AT)).toThrow(/allowed/);
    expect(() => buildDecisions(review, { [premium.item_id]: { action: "correct", field: "none" } }, "Dana", AT)).toThrow(/allowed/);
  });

  it("names the download after the run", () => {
    expect(decisionsFileName("demo")).toBe("mapping-decisions-demo.json");
  });
});

// fixtures/mapping-decisions-demo.json is what the dashboard downloads for the committed demo run.
// The engine's full-cycle test (engine/tests/e2e/test_mapping_apply_cycle.py) applies this exact file,
// so the two sides cannot drift. Regenerate with WRITE_DECISIONS_FIXTURE=1 after the demo run changes.
describe("shared decisions fixture", () => {
  const FIXTURE = path.resolve(import.meta.dirname, "../../../fixtures/mapping-decisions-demo.json");
  const demo = readFileSync(path.resolve(import.meta.dirname, "../../public/demo-run/mapping_review.json"), "utf8");

  it("is exactly what buildDecisions writes for the demo run", () => {
    const review = parseMappingReview(demo, "demo");
    const byHeader = (header: string, source: string) =>
      review.items.find((item) => item.header === header && item.source === source)!.item_id;
    const choices = {
      [byHeader("Birth Dt (mm/dd/yy)", "enrollment")]: { action: "approve" as const },
      [byHeader("Paid", "statement_northwind_health")]: { action: "ignore" as const },
    };
    const file = buildDecisions(review, choices, "Test Reviewer", new Date(Date.UTC(2026, 9, 2, 10)).toISOString());
    const text = `${JSON.stringify(file, null, 2)}\n`;
    if (process.env.WRITE_DECISIONS_FIXTURE === "1") writeFileSync(FIXTURE, text);
    expect(readFileSync(FIXTURE, "utf8")).toBe(text);
    expect(file.decided_at).toBe("2026-10-02T10:00:00.000Z");
    expect(Object.keys(file)).toEqual(["run_id", "mapping_version", "reviewer", "decided_at", "note", "decisions"]);
    expect(Object.keys(file.decisions[0])).toEqual(["item_id", "source", "header", "format_fingerprint", "action", "field"]);
  });
});

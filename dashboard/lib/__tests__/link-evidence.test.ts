import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { parseLinkEvidence } from "../link-evidence";
import type { LinkEvidence } from "../link-evidence";

const lineage = (overrides = {}) => ({
  source_file: "statement.xlsx", sheet: "Statement", row_number: 7,
  raw_hash: "a".repeat(64), run_id: "run-1", mapping_version: "map-v2", ...overrides,
});
const candidate = (policy_id = "P-1", methods = ["POLICY_REF"], lin = lineage()) => ({
  policy_id, methods, lineage: lin,
});
const record = (overrides = {}) => ({
  schema_version: 1, lineage: lineage(), state: "confirmed", reason: "strong_key",
  policy_id: "P-1", amount: "-12.30", candidates: [candidate()], ...overrides,
});
const input = (value: unknown) => `${JSON.stringify(value)}\n`;

describe("parseLinkEvidence", () => {
  it("reads the frozen engine-generated nine-line synthetic export", () => {
    const source = readFileSync(path.resolve(import.meta.dirname, "../../../fixtures/link-evidence.jsonl"), "utf8");
    const links = parseLinkEvidence(source, "run");
    expect(links).toHaveLength(9);
    expect(links.filter(link => link.state === "confirmed")).toHaveLength(8);
    expect(links.find(link => link.state === "provisional")?.policy_id).toBeNull();
  });
  it.each([
    record(),
    record({ state: "provisional", reason: "name_dob_only", policy_id: null,
      candidates: [candidate("P-1", ["NAME_DOB"])] }),
    record({ state: "ambiguous", reason: "unmatched_strong_key", policy_id: null,
      candidates: [candidate()] }),
    record({ state: "unmatched", reason: "no_candidate", policy_id: null, amount: null,
      candidates: [] }),
  ])("reads valid state and preserves complete lineage and signed/null amount", (value) => {
    const parsed: LinkEvidence = parseLinkEvidence(input(value), "run-1")[0];
    expect(parsed.lineage).toEqual(value.lineage);
    expect(parsed.amount).toBe(value.amount);
    expect(parsed.candidates).toEqual(value.candidates);
  });

  it("allows consistent strong plus weak evidence on confirmation", () => {
    const value = record({ candidates: [
      candidate("P-1", ["MEMBER_ID", "NAME_DOB"]), candidate("P-2", ["NAME_DOB"]),
    ] });
    expect(parseLinkEvidence(input(value), "run-1")[0].policy_id).toBe("P-1");
  });

  it("allows a confirmed orphan policy beside a name and DOB match on another policy", () => {
    const value = record({ candidates: [
      candidate("P-1", ["MEMBER_ID", "POLICY_REF"]), candidate("P-2", ["NAME_DOB"]),
    ] });
    expect(parseLinkEvidence(input(value), "run-1")[0].policy_id).toBe("P-1");
  });

  it.each([
    ["malformed JSON", "{bad"],
    ["duplicate JSON key", input(record()).replace('"schema_version":1', '"schema_version":1,"schema_version":1')],
    ["wrong run", input(record({ lineage: lineage({ run_id: "run-2" }) }))],
    ["invalid statement row", input(record({ lineage: lineage({ row_number: 0 }) }))],
    ["candidate identity mismatch", input(record({ candidates: [candidate("P-2")] }))],
    ["confirmed on one strong key beside other name and DOB", input(record({ candidates: [
      candidate("P-1", ["MEMBER_ID"]), candidate("P-2", ["NAME_DOB"]),
    ] }))],
    ["unknown match method", input(record({ candidates: [candidate("P-1", ["EMAIL"])] }))],
    ["duplicate method", input(record({ candidates: [candidate("P-1", ["POLICY_REF", "POLICY_REF"])] }))],
    ["duplicate candidate ID", input(record({ candidates: [candidate(), candidate()] }))],
    ["candidate wrong run", input(record({ candidates: [candidate("P-1", ["POLICY_REF"], lineage({ run_id: "run-2" }))] }))],
    ["impossible state/reason", input(record({ state: "unmatched" }))],
    ["object state", input(record({ state: { toString: null } }))],
    ["unknown reason", input(record({ reason: "maybe" }))],
    ["unknown field", input(record({ unexpected: true }))],
    ["numeric amount", input(record({ amount: 12.3 }))],
    ["overprecision", input(record({ amount: "12.345" }))],
    ["out of range", input(record({ amount: "10000000000.00" }))],
  ])("rejects %s", (_label, text) => {
    expect(() => parseLinkEvidence(text, "run-1")).toThrow(/links\.jsonl/);
  });

  it("rejects duplicate source locations even when their hashes differ", () => {
    const first = record();
    const second = record({ lineage: lineage({ raw_hash: "b".repeat(64) }) });
    expect(() => parseLinkEvidence(`${input(first)}${input(second)}`, "run-1")).toThrow(/line 2/i);
  });

  it("reports the line of malformed JSON", () => {
    expect(() => parseLinkEvidence(`${input(record())}{bad\n`, "run-1")).toThrow(/line 2/i);
  });
});

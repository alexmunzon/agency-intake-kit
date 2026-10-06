import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { expect, it } from "vitest";
import { parseUnresolvedEvidence } from "../unresolved-evidence";
import { MAX_FILE_BYTES, readRunFiles } from "../upload";

const lin = { source_file: "crm.csv", sheet: null, row_number: 3, raw_hash: "a".repeat(64), run_id: "sample-run", mapping_version: "v1" };
const row = { schema_version: 1, run_id: "sample-run", source: "crm", reason: "dob_blank", lineage: lin };
const json = (value: unknown) => JSON.stringify(value) + "\n";
const parse = (text: string) => parseUnresolvedEvidence(text, "sample-run");
const file = (text: string) => ({ name: "unresolved_evidence.jsonl", size: text.length, text: async () => text });

it("retains all producer reasons, summaries and complete lineage without identity values", () => {
  const values = [row, { ...row, reason: "dob_malformed", lineage: { ...lin, sheet: "Sheet 2" } },
    { ...row, reason: "dob_column_missing" }, { ...row, reason: "dob_column_missing", lineage: null },
    { ...row, reason: "crm_absent", lineage: null }, { ...row, reason: "crm_absent", source: "statement" }];
  expect(parse(values.map(json).join(""))).toEqual(values);
  expect(parse("")).toEqual([]);
});
it.each([
  { ...row, schema_version: 2 }, { ...row, run_id: "other" }, { ...row, source: "" },
  { ...row, reason: "unknown" }, { ...row, reason: "crm_absent" },
  { ...row, source: "statement" }, { ...row, lineage: null },
  { ...row, reason: "dob_malformed", lineage: null },
  { ...row, reason: "crm_absent", source: "statement", lineage: null },
  { ...row, raw_dob: "private" }, { ...row, lineage: { ...lin, run_id: "other" } },
  { ...row, lineage: { ...lin, row_number: true } }, { ...row, lineage: { ...lin, row_number: 0 } },
  { ...row, lineage: { ...lin, sheet: "" } }, { ...row, lineage: { ...lin, raw_hash: "bad" } },
  { ...row, lineage: { ...lin, extra: "private" } }, { ...row, lineage: { ...lin, mapping_version: "" } },
  { schema_version: 1 }, null,
])("rejects invalid scope, shape or run with file and line context", (value) => {
  expect(() => parse(json(value))).toThrow(/unresolved_evidence.jsonl line 1/);
});
it.each(["{bad", "\n", json(row).replace('"row_number":3', '"row_number":3.0'),
  json(row).replace('"row_number":3', '"row_number":3e0'), json(row).replace('"schema_version":1', '"schema_version":1,"schema_version":1'),
  json(row).replace('"sheet":null', '"sheet":null,"sheet":null'), json(row) + json({ ...row, lineage: { ...lin, raw_hash: "b".repeat(64) } })])(
  "rejects malformed JSON, duplicate keys and duplicate source/reason/location", (text) => expect(() => parse(text)).toThrow(/unresolved_evidence.jsonl/),
);
it("retains distinct sheets and reasons at the same row and identifies later bad lines", () => {
  expect(parse(json(row) + json({ ...row, lineage: { ...lin, sheet: "Other" } }))).toHaveLength(2);
  expect(() => parse(json(row) + "{bad")).toThrow(/line 2/);
});
async function packet() {
  const root = path.resolve(import.meta.dirname, "../../../fixtures/sample-run");
  const names = ["manifest.json", "scorecard.json", "exceptions.jsonl", "rts_coverage.json", ...(await readdir(path.join(root, "tie_out"))).map(n => `tie_out/${n}`)];
  return Promise.all(names.map(async n => ({ ...file(await readFile(path.join(root, n), "utf8")), name: path.basename(n) })));
}
it("keeps legacy absence distinct from empty and imported evidence without changing run or totals", async () => {
  const files = await packet();
  const legacy = await readRunFiles(files);
  for (const text of ["", json(row)]) {
    const result = await readRunFiles([...files, file(text)]);
    if (!result.ok || !legacy.ok) throw new Error("synthetic packet rejected");
    expect(legacy.loaded.unresolved).toBeUndefined();
    expect(result.loaded.unresolved).toEqual(text ? [row] : []);
    expect(result.loaded.run).toEqual(legacy.loaded.run);
    expect(result.loaded.tieOut).toEqual(legacy.loaded.tieOut);
  }
});
it("rejects optional duplicate, oversized, unreadable, malformed and wrong-run evidence", async () => {
  const files = await packet();
  for (const optional of [[file(""), file("")], [{ ...file(""), size: MAX_FILE_BYTES + 1 }],
    [{ ...file(""), text: async () => { throw new Error("private read error"); } }], [file("{bad")], [file(json({ ...row, run_id: "other" }))]]) {
    const result = await readRunFiles([...files, ...optional]);
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors.join(" ")).toMatch(/unresolved_evidence.jsonl/);
      expect(result.errors.join(" ")).not.toContain("private read error");
    }
  }
});

it.each([["absent-crm", 2], ["missing-dob-column", 3], ["valid-blank-malformed-dob", 2]] as const)("reads frozen engine output %s", async (scenario, count) => {
  const text = await readFile(path.resolve(import.meta.dirname, `../../../fixtures/unresolved-${scenario}.jsonl`), "utf8");
  const records = parseUnresolvedEvidence(text, "run");
  expect(records).toHaveLength(count);
  expect(records).toEqual(text.trim().split("\n").map(line => JSON.parse(line)));
});

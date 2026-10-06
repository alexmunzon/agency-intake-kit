import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";

import { MAX_FILE_BYTES, readRunFiles, type PickedFile } from "@/lib/upload";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

function picked(name: string, text: string): PickedFile {
  return { name, size: text.length, text: async () => text };
}

/** Every file in a fixture run, the way a folder pick hands them over. */
async function runFiles(sample: string): Promise<PickedFile[]> {
  const dir = path.join(FIXTURES, sample);
  const names = [...(await readdir(dir)).filter((n) => n.includes(".")), ...(await readdir(path.join(dir, "tie_out"))).map((n) => `tie_out/${n}`)];
  return Promise.all(names.map(async (name) => picked(path.basename(name), await readFile(path.join(dir, name), "utf8"))));
}

const swap = (files: PickedFile[], name: string, text: string) => files.map((f) => (f.name === name ? picked(name, text) : f));
async function noCrmFailedFiles(rawBlocked = true): Promise<PickedFile[]> {
  let files = await runFiles("sample-run-failed");
  const manifest = JSON.parse(await files.find(f => f.name === "manifest.json")!.text());
  manifest.inputs = manifest.inputs.filter((input: { source: string }) => input.source !== "crm");
  manifest.status_reason = rawBlocked ? "Statement file was truncated" : "No CRM file was received";
  files = swap(files, "manifest.json", JSON.stringify(manifest));
  const card = JSON.parse(await files.find(f => f.name === "scorecard.json")!.text());
  card.exceptions_by_severity = { blocker: 1, error: 0, warning: 0, info: 0 };
  card.exceptions_by_rule = { [rawBlocked ? "CMP-001" : "MAP-003"]: 1 };
  card.tie_out = card.tie_out.map((leg: Record<string, unknown>) => ({ ...leg, not_run_reason: rawBlocked ? "Raw completeness blocker" : "No policy book was received" }));
  files = swap(files, "scorecard.json", JSON.stringify(card));
  const original = JSON.parse((await files.find(f => f.name === "exceptions.jsonl")!.text()).split("\n")[0]);
  files = swap(files, "exceptions.jsonl", JSON.stringify({ ...original, rule_id: rawBlocked ? "CMP-001" : "MAP-003",
    family: rawBlocked ? "CMP" : "MAP", source: rawBlocked ? "statement_harborline" : "crm",
    message: rawBlocked ? "Statement file was truncated" : "CRM file absent" }));
  return files;
}

afterEach(() => vi.restoreAllMocks());

describe("readRunFiles", () => {
  it("retains an optional same-run statement total, keeping absent distinct from blocked", async () => {
    const files = await noCrmFailedFiles();
    const legacy = await readRunFiles(files);
    if (!legacy.ok) throw new Error(legacy.errors.join("; "));
    expect(legacy.loaded.statementTotals).toBeUndefined();
    const blocked = { schema_version: 1, run_id: "sample-run-failed", status: "BLOCKED", reason: "raw_gate_blocked",
      valid_line_count: 0, excluded_line_count: 0, total_paid: null, lines: [] };
    const attached = await readRunFiles([...files, picked("statement_totals.json", JSON.stringify(blocked))]);
    if (!attached.ok) throw new Error(attached.errors.join("; "));
    expect(attached.loaded.statementTotals?.status).toBe("BLOCKED");
    const wrong = await readRunFiles([...files, picked("statement_totals.json", JSON.stringify({ ...blocked, run_id: "other" }))]);
    expect(wrong.ok).toBe(false);
    if (!wrong.ok) expect(wrong.errors.join(" ")).toMatch(/statement_totals\.json/);
    const withCrm = await readRunFiles([...await runFiles("sample-run-failed"), picked("statement_totals.json", JSON.stringify(blocked))]);
    expect(withCrm.ok).toBe(false);
    if (!withCrm.ok) expect(withCrm.errors.join(" ")).toMatch(/statement_totals\.json/);
    const passed = await runFiles("sample-run");
    const passedManifest = JSON.parse(await passed.find(f => f.name === "manifest.json")!.text());
    passedManifest.inputs = passedManifest.inputs.filter((input: { source: string }) => input.source !== "crm");
    const nonfailed = await readRunFiles([...swap(passed, "manifest.json", JSON.stringify(passedManifest)),
      picked("statement_totals.json", JSON.stringify({ ...blocked, run_id: "sample-run" }))]);
    expect(nonfailed.ok).toBe(false);
    if (!nonfailed.ok) expect(nonfailed.errors.join(" ")).toMatch(/statement_totals\.json/);
    const noRawBlocker = await readRunFiles([...await noCrmFailedFiles(false), picked("statement_totals.json", JSON.stringify(blocked))]);
    expect(noRawBlocker.ok).toBe(false);
    if (!noRawBlocker.ok) expect(noRawBlocker.errors.join(" ")).toMatch(/statement_totals\.json/);
    const available = { ...blocked, status: "AVAILABLE", reason: null, valid_line_count: 1, total_paid: "12.50",
      lines: [{ source: "statement_harborline", lineage: { source_file: "s.csv", sheet: null, row_number: 2,
        raw_hash: "a".repeat(64), run_id: "sample-run-failed", mapping_version: "unmapped" }, amount: "12.50", reason: "valid" }] };
    const usableWithRawBlocker = await readRunFiles([...files, picked("statement_totals.json", JSON.stringify(available))]);
    expect(usableWithRawBlocker.ok).toBe(false);
    if (!usableWithRawBlocker.ok) expect(usableWithRawBlocker.errors.join(" ")).toMatch(/statement_totals\.json/);
  });

  it("loads a second run held in memory, ignoring files that are not run files", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    const files = [...(await runFiles("sample-run-partial")), picked("policies.csv", "policy_id\n")];
    const result = await readRunFiles(files);
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.label).toBe("sample-run-partial");
    expect(result.loaded.run.exceptions).toHaveLength(12);
    expect(result.loaded.tieOut.legs.map((leg) => leg.status)).toEqual(["RAN", "RAN", "NOT_RUN"]);
    expect(result.loaded.links).toBeUndefined();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("keeps a present empty links artifact distinct from a legacy run", async () => {
    const result = await readRunFiles([...await runFiles("sample-run"), picked("links.jsonl", "")]);
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.links).toEqual([]);
  });

  it("retains a same-run confirmed link", async () => {
    const lineage = { source_file: "statement.csv", sheet: null, row_number: 2, raw_hash: "a".repeat(64), run_id: "sample-run", mapping_version: "v1" };
    const record = { schema_version: 1, lineage, state: "confirmed", reason: "strong_key", policy_id: "P-1", amount: "12.50", candidates: [{ policy_id: "P-1", methods: ["POLICY_REF"], lineage: { ...lineage, source_file: "crm.csv" } }] };
    const result = await readRunFiles([...await runFiles("sample-run"), picked("links.jsonl", `${JSON.stringify(record)}\n`)]);
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.links).toEqual([record]);
  });

  it.each(["wrong-run", "malformed"])("rejects %s links with file context", async (kind) => {
    const text = kind === "malformed" ? "{oops\n" : JSON.stringify({ schema_version: 1, lineage: { source_file: "s.csv", sheet: null, row_number: 2, raw_hash: "a".repeat(64), run_id: "other-run", mapping_version: "v1" }, state: "unmatched", reason: "no_candidate", policy_id: null, amount: "1.00", candidates: [] });
    const result = await readRunFiles([...await runFiles("sample-run"), picked("links.jsonl", text)]);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.errors.join(" ")).toMatch(/links\.jsonl/);
  });

  it("rejects duplicate links files and names link read failures", async () => {
    const files = await runFiles("sample-run");
    const result = await readRunFiles([...files, picked("links.jsonl", ""), picked("links.jsonl", "")]);
    expect(result).toEqual({ ok: false, errors: ["tie_out/links.jsonl: picked twice. Pick one copy."] });
    const broken = { ...picked("links.jsonl", ""), text: async () => { throw new Error("read failed"); } };
    const failed = await readRunFiles([...files, broken]);
    expect(failed.ok).toBe(false);
    if (!failed.ok) expect(failed.errors.join(" ")).toMatch(/links\.jsonl/);
  });

  it("names every missing file", async () => {
    const files = (await runFiles("sample-run")).filter((f) => !["scorecard.json", "variances.json"].includes(f.name));
    const result = await readRunFiles(files);
    expect(result).toEqual({
      ok: false,
      errors: [
        "scorecard.json: missing. Pick it with the other run files.",
        "tie_out/variances.json: missing. Pick it with the other run files.",
      ],
    });
  });

  it("reports each broken file by name, not just the first", async () => {
    let files = swap(await runFiles("sample-run"), "manifest.json", "{");
    files = swap(files, "variances.json", "not json");
    files = swap(files, "exceptions.jsonl", '{"id": "EX-1"}\n{oops\n');
    const result = await readRunFiles(files);
    expect(result.ok).toBe(false);
    if (result.ok) return;
    expect(result.errors).toHaveLength(3);
    expect(result.errors[0]).toMatch(/^manifest\.json: not valid JSON/);
    expect(result.errors[1]).toMatch(/^exceptions\.jsonl line 2: not valid JSON/);
    expect(result.errors[2]).toMatch(/^tie_out\/variances\.json: not valid JSON/);
  });

  it("refuses files from two different runs", async () => {
    const other = await readFile(path.join(FIXTURES, "sample-run-passed", "scorecard.json"), "utf8");
    const result = await readRunFiles(swap(await runFiles("sample-run"), "scorecard.json", other));
    expect(result).toEqual({ ok: false, errors: ["scorecard.json: manifest and scorecard are not from the same run"] });
  });

  it("refuses a tie-out file from another run", async () => {
    const other = await readFile(path.join(FIXTURES, "sample-run-partial", "tie_out", "leg_crm_vs_statement.json"), "utf8");
    const result = await readRunFiles(swap(await runFiles("sample-run"), "leg_crm_vs_statement.json", other));
    expect(result).toEqual({ ok: false, errors: ["tie_out/leg_crm_vs_statement.json: not from the same run as scorecard.json"] });
  });

  it("refuses the same file picked twice", async () => {
    const files = await runFiles("sample-run");
    const manifest = files.find((f) => f.name === "manifest.json")!;
    const result = await readRunFiles([...files, manifest]);
    expect(result).toEqual({ ok: false, errors: ["manifest.json: picked twice. Pick one copy."] });
  });

  it("refuses a file that is too large without reading it", async () => {
    const files = (await runFiles("sample-run")).map((f) =>
      f.name === "exceptions.jsonl" ? { ...f, size: MAX_FILE_BYTES + 1, text: () => Promise.reject(new Error("read")) } : f,
    );
    const result = await readRunFiles(files);
    expect(result).toEqual({ ok: false, errors: ["exceptions.jsonl: larger than 50 MB, too large to open in the browser."] });
  });

  it("asks for files when none of them are run files", async () => {
    expect(await readRunFiles([picked("notes.txt", "hi")])).toEqual({
      ok: false,
      errors: ["None of these are run files. Pick manifest.json, scorecard.json, exceptions.jsonl, rts_coverage.json, and the tie_out files."],
    });
  });
});

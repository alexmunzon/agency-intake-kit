import path from "node:path";
import { describe, expect, it } from "vitest";

import { NO_FILTERS, choices, filterExceptions, orderExceptions } from "@/lib/exceptions";
import { loadRunDir } from "@/lib/run-dir";
import { summarizeSources } from "@/lib/sources";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const load = (name: string) => loadRunDir(path.join(FIXTURES, name));

describe("exception filters", () => {
  it("puts the CMP-001 blocker first on the failed sample", async () => {
    const ordered = orderExceptions((await load("sample-run-failed")).exceptions);
    expect(ordered.map((r) => r.rule_id)).toEqual(["CMP-001", "ING-001"]);
  });

  it("orders errors before warnings before info on the warnings sample", async () => {
    const ordered = orderExceptions((await load("sample-run")).exceptions);
    expect(ordered.map((r) => r.severity)).toEqual([
      ...Array(4).fill("ERROR"), ...Array(6).fill("WARNING"), ...Array(3).fill("INFO"),
    ]);
  });

  it("narrows by severity, rule, and source, and combines them", async () => {
    const records = (await load("sample-run")).exceptions;
    expect(filterExceptions(records, NO_FILTERS)).toHaveLength(13);
    expect(filterExceptions(records, { ...NO_FILTERS, severity: "ERROR" })).toHaveLength(4);
    expect(filterExceptions(records, { ...NO_FILTERS, rule: "RTS-001" }).map((r) => r.row_number)).toEqual([419]);
    expect(filterExceptions(records, { ...NO_FILTERS, source: "statement_harborline" })).toHaveLength(2);
    expect(filterExceptions(records, { severity: "ERROR", rule: "", source: "statement_harborline" }).map((r) => r.rule_id)).toEqual(["TIE-002"]);
    expect(filterExceptions(records, { severity: "BLOCKER", rule: "", source: "" })).toEqual([]);
  });

  it("offers only rules and sources that exist in the run", async () => {
    const records = (await load("sample-run-passed")).exceptions;
    expect(choices(records, "rule_id")).toEqual(["DAT-004", "ING-001"]);
    expect(choices(records, "source")).toEqual(["crm", "enrollment"]);
  });
});

describe("source summaries", () => {
  it("shows the CRM file blocked at 2,600 expected and 2,574 received on the failed sample", async () => {
    const [crm, ...rest] = summarizeSources(await load("sample-run-failed"));
    expect([crm.file.rows_expected, crm.file.rows_received]).toEqual([2600, 2574]);
    expect([crm.tone, crm.status]).toEqual(["blocker", "Blocked the run"]);
    expect(crm.gates.map((r) => r.rule_id)).toEqual(["CMP-001", "ING-001"]);
    expect(rest.every((s) => s.status === "Read, not mapped (run stopped)" && s.tone === "info")).toBe(true);
  });

  it("reads encoding, delimiter, and header row from the reading rules", async () => {
    const [crm, enrollment, harborline] = summarizeSources(await load("sample-run"));
    expect([crm.status, crm.encoding, crm.rowIssues]).toEqual(["Read with warnings", "cp1252", 7]);
    expect([enrollment.encoding, enrollment.delimiter, enrollment.headerRow]).toEqual(["UTF-8", "Detected with confidence", "Row 1"]);
    expect([harborline.status, harborline.delimiter]).toEqual(["Read cleanly", "Not needed (spreadsheet)"]);
  });

  it("shows a header found below row 1", async () => {
    const run = await load("sample-run-passed");
    const [info] = run.exceptions;
    run.exceptions.push({ ...info, id: "EX-000099", rule_id: "ING-002", message: "Header found on row 3" });
    expect(summarizeSources(run)[0].headerRow).toBe("Row 3");
  });

  it("marks every file clean on the passed sample", async () => {
    expect(summarizeSources(await load("sample-run-passed")).map((s) => s.tone)).toEqual(Array(5).fill("pass"));
  });
});

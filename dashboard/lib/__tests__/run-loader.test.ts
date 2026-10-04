import { readFile } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { DEMO_RUN_DIR, loadRunDir, parseRun, type RunFiles } from "@/lib/run-loader";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const SAMPLES = ["sample-run", "sample-run-failed", "sample-run-passed"];

async function rawFiles(name: string): Promise<RunFiles> {
  const read = (file: string) => readFile(path.join(FIXTURES, name, file), "utf8");
  return {
    manifest: await read("manifest.json"),
    scorecard: await read("scorecard.json"),
    exceptions: await read("exceptions.jsonl"),
    rts: await read("rts_coverage.json"),
  };
}

describe("loadRunDir", () => {
  it.each(SAMPLES)("loads %s with every exception the scorecard counts", async (name) => {
    const run = await loadRunDir(path.join(FIXTURES, name));
    const counts = Object.values(run.scorecard.exceptions_by_severity);
    expect(run.manifest.run_id).toBe(name);
    expect(run.exceptions).toHaveLength(counts.reduce((a, b) => a + b, 0));
  });

  it("loads the committed demo run by default", async () => {
    const run = await loadRunDir(DEMO_RUN_DIR);
    expect(run.manifest.status).toBe("PASSED_WITH_WARNINGS");
  });

  it("names the file it could not read", async () => {
    await expect(loadRunDir(path.join(FIXTURES, "no-such-run"))).rejects.toThrow(/manifest\.json/);
  });
});

describe("parseRun", () => {
  it("refuses money written as a number", async () => {
    const files = await rawFiles("sample-run");
    const manifest = JSON.parse(files.manifest);
    manifest.jev.estimated_cost_usd = 0.000901;
    expect(() => parseRun({ ...files, manifest: JSON.stringify(manifest) })).toThrow(
      /estimated_cost_usd/,
    );
  });

  it("refuses a manifest and scorecard from different runs", async () => {
    const files = await rawFiles("sample-run");
    const passed = await rawFiles("sample-run-passed");
    expect(() => parseRun({ ...files, scorecard: passed.scorecard })).toThrow(/same run/);
  });

  it("refuses an exception with an unknown severity", async () => {
    const files = await rawFiles("sample-run-passed");
    const bad = files.exceptions.replace('"severity":"INFO"', '"severity":"LOW"');
    expect(() => parseRun({ ...files, exceptions: bad })).toThrow(/exceptions\.jsonl line 1/);
  });
});

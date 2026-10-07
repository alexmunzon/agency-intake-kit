import { mkdtemp, readdir, readFile, rm, writeFile, cp } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { loadMappingReview } from "@/lib/run-dir";
import { readRunFiles, type PickedFile } from "@/lib/upload";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const REVIEW = path.join(import.meta.dirname, "fixtures", "mapping-review.json");

function picked(name: string, text: string): PickedFile {
  return { name, size: text.length, text: async () => text };
}
/** The sample run as an older engine wrote it: every file except mapping_review.json. */
async function runFiles(sample: string): Promise<PickedFile[]> {
  const dir = path.join(FIXTURES, sample);
  const names = [...(await readdir(dir)).filter((n) => n.includes(".") && n !== "mapping_review.json"), ...(await readdir(path.join(dir, "tie_out"))).map((n) => `tie_out/${n}`)];
  return Promise.all(names.map(async (name) => picked(path.basename(name), await readFile(path.join(dir, name), "utf8"))));
}
const forRun = async (runId: string) => (await readFile(REVIEW, "utf8")).replace('"run_id": "demo"', `"run_id": "${runId}"`);

describe("loadMappingReview (run folder on disk)", () => {
  it("returns nothing for an older run without the file", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "older-run-"));
    await cp(path.join(FIXTURES, "sample-run"), dir, { recursive: true });
    await rm(path.join(dir, "mapping_review.json"));
    expect(await loadMappingReview(dir, "sample-run")).toBeUndefined();
  });
  it("reads the committed sample run's review file", async () => {
    const state = await loadMappingReview(path.join(FIXTURES, "sample-run"), "sample-run");
    expect(state?.ok).toBe(true);
  });
  it("reads the file when present and reports a malformed one as an error", async () => {
    const dir = await mkdtemp(path.join(tmpdir(), "mapping-review-"));
    await cp(path.join(FIXTURES, "sample-run"), dir, { recursive: true });
    await writeFile(path.join(dir, "mapping_review.json"), await forRun("sample-run"));
    const state = await loadMappingReview(dir, "sample-run");
    expect(state?.ok && state.review.items).toHaveLength(3);
    await writeFile(path.join(dir, "mapping_review.json"), "{ broken");
    expect(await loadMappingReview(dir, "sample-run")).toEqual({ ok: false, error: expect.stringMatching(/^mapping_review\.json: /) });
  });
});

describe("readRunFiles with mapping_review.json", () => {
  it("leaves mappingReview out when the file is not picked", async () => {
    const result = await readRunFiles(await runFiles("sample-run"));
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.mappingReview).toBeUndefined();
  });
  it("attaches a valid review", async () => {
    const result = await readRunFiles([...(await runFiles("sample-run")), picked("mapping_review.json", await forRun("sample-run"))]);
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.mappingReview?.ok).toBe(true);
  });
  it("still opens the run when the review file is malformed, carrying a plain error", async () => {
    const result = await readRunFiles([...(await runFiles("sample-run")), picked("mapping_review.json", await forRun("someone-else"))]);
    if (!result.ok) throw new Error(result.errors.join("; "));
    expect(result.loaded.mappingReview).toEqual({ ok: false, error: expect.stringMatching(/different run/) });
  });
});

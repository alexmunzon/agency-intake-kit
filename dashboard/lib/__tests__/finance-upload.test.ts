import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { describe, expect, it } from "vitest";

import { readRunFiles, type PickedFile } from "@/lib/upload";
import { parseFinanceReview } from "@/lib/finance-review";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const DEMO_FINANCE = path.resolve(import.meta.dirname, "../../public/demo-finance.json");

function picked(name: string, text: string): PickedFile {
  return { name, size: text.length, text: async () => text };
}

/** Every core run file, in the shape returned by picking the run folder. */
async function runFiles(sample: string): Promise<PickedFile[]> {
  const dir = path.join(FIXTURES, sample);
  const names = [
    ...(await readdir(dir)).filter((name) => name.includes(".")),
    ...(await readdir(path.join(dir, "tie_out"))).map((name) => `tie_out/${name}`),
  ];
  return Promise.all(names.map(async (name) =>
    picked(path.basename(name), await readFile(path.join(dir, name), "utf8")),
  ));
}

async function financeText(): Promise<string> {
  return readFile(DEMO_FINANCE, "utf8");
}

describe("readRunFiles finance sidecar", () => {
  it("keeps older runs valid when finance.json is absent", async () => {
    const result = await readRunFiles(await runFiles("sample-run"));

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.loaded.label).toBe("sample-run");
    expect(result.loaded).not.toHaveProperty("finance");
  });

  it("preserves a valid finance review separately from the core run status", async () => {
    const coreFiles = await runFiles("sample-run");
    const manifest = JSON.parse(await coreFiles.find((file) => file.name === "manifest.json")!.text());
    const scorecard = JSON.parse(await coreFiles.find((file) => file.name === "scorecard.json")!.text());
    const rawFinance = await financeText();
    const expectedFinance = parseFinanceReview(rawFinance);
    const result = await readRunFiles([...coreFiles, picked("finance.json", rawFinance)]);

    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.loaded.finance).toEqual(expectedFinance);
    expect(result.loaded.run.manifest.status).toBe(manifest.status);
    expect(result.loaded.run.scorecard.status).toBe(scorecard.status);
  });

  it("rejects malformed finance.json with a file-specific error", async () => {
    const result = await readRunFiles([
      ...(await runFiles("sample-run")),
      picked("finance.json", "{ not json"),
    ]);

    expect(result).toEqual({
      ok: false,
      errors: ["finance.json: Invalid or unsupported finance review artifact"],
    });
  });

  it("rejects duplicate JSON keys in the raw finance sidecar", async () => {
    const duplicated = (await financeText()).replace(
      '"artifact_type": "neutral_finance_review"',
      '"artifact_type": "neutral_finance_review", "artifact_type": "neutral_finance_review"',
    );
    expect(duplicated).not.toBe(await financeText());

    const result = await readRunFiles([
      ...(await runFiles("sample-run")),
      picked("finance.json", duplicated),
    ]);

    expect(result).toEqual({
      ok: false,
      errors: ["finance.json: Invalid or unsupported finance review artifact"],
    });
  });

  it("rejects finance.json selected more than once", async () => {
    const sidecar = picked("finance.json", await financeText());
    const result = await readRunFiles([
      ...(await runFiles("sample-run")),
      sidecar,
      sidecar,
    ]);

    expect(result).toEqual({ ok: false, errors: ["finance.json: picked twice. Pick one copy."] });
  });
});

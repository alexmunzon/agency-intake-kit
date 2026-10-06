import { expect, it } from "vitest";
import { readRunFiles } from "@/lib/upload";

it("reports a failed File.text read by filename without rejecting the loader promise", async () => {
  const readError = new DOMException("The file could not be read", "NotReadableError");
  const result = await readRunFiles([
    { name: "manifest.json", size: 1, text: async () => { throw readError; } },
  ]);
  expect(result.ok).toBe(false);
  if (!result.ok) {
    expect(result.errors.some((error) => error.includes("manifest.json") && error.includes("read"))).toBe(true);
  }
});

it("reports a failed optional finance artifact read by filename", async () => {
  const result = await readRunFiles([
    { name: "finance.json", size: 1, text: async () => { throw new Error("unavailable"); } },
  ]);
  expect(result.ok).toBe(false);
  if (!result.ok) expect(result.errors).toContain("finance.json: could not read (unavailable)");
});

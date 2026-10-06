import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { LoadRun } from "@/components/load-run";
import { LoadedRunBanner, LoadedRunProvider, RunSwitch } from "@/components/loaded-run";
import type { LinkEvidence } from "@/lib/link-evidence";

const root = path.resolve(import.meta.dirname, "../../../fixtures/sample-run");
const lineage = (source_file: string, row_number: number) => ({
  source_file, sheet: null, row_number, raw_hash: "a".repeat(64),
  run_id: "sample-run", mapping_version: "map-v1",
});
const link: LinkEvidence = {
  schema_version: 1, state: "confirmed", reason: "strong_key",
  policy_id: "P-LINK-1", amount: "12.30", lineage: lineage("statement.csv", 7),
  candidates: [{
    policy_id: "P-LINK-1", methods: ["POLICY_REF"], lineage: lineage("book.csv", 2),
  }],
};
async function files(withLinks = false) {
  const names = (await readdir(root)).filter(name => name.includes("."));
  const tie = await readdir(path.join(root, "tie_out"));
  const all = await Promise.all([...names, ...tie].map(async (name) => {
    const text = await readFile(path.join(root, tie.includes(name) ? "tie_out" : "", name), "utf8");
    return new File([text], name);
  }));
  return withLinks ? [...all, new File([JSON.stringify(link)], "links.jsonl")] : all;
}
function pick(value: File[]) {
  const input = screen.getByLabelText("Pick the run files");
  Object.defineProperty(input, "files", { value, configurable: true });
  fireEvent.change(input);
}

it("switches link evidence with the loaded run and restores demo children when cleared", async () => {
  render(<LoadedRunProvider>
    <LoadedRunBanner /><LoadRun demoRunId="sample-run" />
    <RunSwitch page="tie-out"><p>Server demo tie-out</p></RunSwitch>
  </LoadedRunProvider>);
  pick(await files(true));
  const region = await screen.findByRole("region", { name: "Policy link evidence" });
  expect(within(region).getByRole("row", { name: /P-LINK-1/ })).toBeInTheDocument();
  pick(await files());
  expect(await screen.findByText("No policy link evidence artifact is attached to this run.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Back to the demo run" }));
  await waitFor(() => expect(screen.getByText("Server demo tie-out")).toBeInTheDocument());
});

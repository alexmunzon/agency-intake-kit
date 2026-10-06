import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { expect, it } from "vitest";
import { LoadRun } from "@/components/load-run";
import { LoadedRunBanner, LoadedRunProvider } from "@/components/loaded-run";
import { RunUnresolvedEvidence } from "@/components/run-unresolved-evidence";

const lin = { source_file: "crm.csv", sheet: "Clients", row_number: 3, raw_hash: "a".repeat(64), run_id: "sample-run", mapping_version: "v1" };
const row = { schema_version: 1, run_id: "sample-run", source: "crm", reason: "dob_blank", lineage: lin };
async function pick(records?: unknown[] | string) {
  const root = path.resolve(import.meta.dirname, "../../../fixtures/sample-run");
  const names = ["manifest.json", "scorecard.json", "exceptions.jsonl", "rts_coverage.json", ...(await readdir(path.join(root, "tie_out"))).map(n => `tie_out/${n}`)];
  const files = await Promise.all(names.map(async n => new File([await readFile(path.join(root, n), "utf8")], path.basename(n))));
  if (records !== undefined) files.push(new File([typeof records === "string" ? records : records.map(r => JSON.stringify(r)).join("\n")], "unresolved_evidence.jsonl"));
  const input = screen.getByLabelText("Pick the run files");
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
  await waitFor(() => expect(screen.queryByText(/Reading the files/)).not.toBeInTheDocument());
}
it("shows reasons and exact provenance, preserves prior evidence on failure, and clears on replacement/reset", async () => {
  render(<LoadedRunProvider><LoadedRunBanner /><LoadRun demoRunId="sample-run" /><RunUnresolvedEvidence /></LoadedRunProvider>);
  expect(screen.getByText(/No unresolved evidence artifact/)).toBeInTheDocument();
  await pick([row, { ...row, reason: "dob_malformed", lineage: { ...lin, row_number: 4 } },
    { ...row, reason: "dob_column_missing", lineage: null }, { ...row, reason: "crm_absent", lineage: null },
    { ...row, reason: "crm_absent", source: "statement", lineage: { ...lin, source_file: "statement.csv" } }]);
  const panel = screen.getByRole("region", { name: "Unresolved evidence" });
  for (const label of ["DOB is blank", "DOB could not be read", "DOB column not found", "CRM file not received"]) expect(within(panel).getAllByText(label).length).toBeGreaterThan(0);
  expect(within(panel).getByText("crm.csv, Clients, row 3")).toBeInTheDocument();
  expect(within(panel).getByText("statement.csv, Clients, row 3")).toBeInTheDocument();
  expect(within(panel).getAllByText(/Source summary/)).toHaveLength(2);
  expect(within(panel).getAllByText(lin.raw_hash)).toHaveLength(3);
  await pick("{bad");
  expect(screen.getByRole("alert")).toHaveTextContent("unresolved_evidence.jsonl");
  expect(within(panel).getByText("DOB is blank")).toBeInTheDocument();
  await pick([]);
  expect(within(panel).getByText(/contains no recorded cases/)).toBeInTheDocument();
  expect(within(panel).queryByText("DOB is blank")).not.toBeInTheDocument();
  await pick();
  expect(within(panel).getByText(/No unresolved evidence artifact/)).toBeInTheDocument();
  await pick([row]);
  fireEvent.click(screen.getByRole("button", { name: "Back to the demo run" }));
  expect(within(panel).getByText(/No unresolved evidence artifact/)).toBeInTheDocument();
});
it("paginates 26 cases and resets when same-ID run evidence is replaced", async () => {
  render(<LoadedRunProvider><LoadRun demoRunId="sample-run" /><RunUnresolvedEvidence /></LoadedRunProvider>);
  const rows = Array.from({ length: 26 }, (_, i) => ({ ...row, lineage: { ...lin, row_number: i + 2 } }));
  await pick(rows);
  expect(screen.queryByText("crm.csv, Clients, row 27")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Next evidence page" }));
  expect(screen.getByText("crm.csv, Clients, row 27")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next evidence page" })).toBeDisabled();
  await pick(rows.map(r => ({ ...r, lineage: { ...r.lineage, source_file: "replacement.csv" } })));
  expect(screen.queryByText("crm.csv, Clients, row 27")).not.toBeInTheDocument();
  expect(screen.getByText("replacement.csv, Clients, row 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Previous evidence page" })).toBeDisabled();
});

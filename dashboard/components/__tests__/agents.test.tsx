import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { AgentsView } from "@/components/agents";
import { loadRunDir } from "@/lib/run-loader";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

async function show(name: string) {
  render(<AgentsView run={await loadRunDir(path.join(FIXTURES, name))} />);
}

describe("AgentsView", () => {
  it("highlights example 3 in the RTS matrix", async () => {
    await show("sample-run");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Is every writing agent allowed to sell what they sold?",
    );
    expect(screen.getByText("No. 1 policy was sold without RTS.")).toBeInTheDocument();
    const gap = screen.getByRole("cell", { name: "1884412, Harborline TX 2026: Used without RTS, 1 policy" });
    expect(gap).toHaveAttribute("data-state", "USED_WITHOUT_RTS");
    expect(screen.getByRole("cell", { name: "1884412, Crestview Mutual TX 2026: Held but unused, 0 policies" })).toBeInTheDocument();
    expect(screen.getByRole("cell", { name: "1773019, Harborline TX 2026: Held and used, 88 policies" })).toBeInTheDocument();
    const fix = within(screen.getByRole("listitem", { name: "EX-000005" }));
    expect(fix.getByText("crm_export.csv row 419")).toBeInTheDocument();
    expect(fix.getByText(/Obtain RTS or reassign writing agent/)).toBeInTheDocument();
    const list = within(screen.getByRole("table", { name: "Writing agents" }));
    expect(list.getByRole("row", { name: /1884412/ })).toHaveTextContent("1 gap");
  });

  it("shows Not checked with no matrix for the failed sample", async () => {
    await show("sample-run-failed");
    expect(screen.getByText("Not checked. The run stopped before RTS was checked.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("answers yes for the passed sample", async () => {
    await show("sample-run-passed");
    expect(screen.getByText("Yes. Every policy was written by an agent ready to sell it.")).toBeInTheDocument();
    expect(screen.queryByText(/Used without RTS,/)).toBeNull();
  });
});

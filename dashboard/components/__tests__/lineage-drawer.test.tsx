import path from "node:path";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { LineageDrawer } from "@/components/lineage-drawer";
import { loadRunDir } from "@/lib/run-dir";

describe("LineageDrawer Jev scores", () => {
  it("shows impact as a weighted score on its 0-to-2 scale", async () => {
    const run = await loadRunDir(path.resolve(import.meta.dirname, "../../public/demo-run"));
    const record = run.exceptions.find((item) => item.rule_id === "REF-001" && item.jev?.impact_score === 1.43);
    expect(record).toBeDefined();
    render(<LineageDrawer record={record!} onClose={() => {}} />);

    const row = screen.getByText("Impact score on the load (0 to 2)").parentElement!;
    expect(within(row).getByText("1.43 / 2")).toBeInTheDocument();
    expect(row.querySelector('[data-score="impact_score"]')?.getAttribute("style")).toContain("width: 71.5%");
  });

  it.each([
    ["replay", "Jev review (replay of saved answers)"],
    ["live", "Jev review (live call)"],
    ["record", "Jev review (record mode)"],
  ] as const)("labels where the Jev scores came from in %s mode", async (mode, heading) => {
    const run = await loadRunDir(path.resolve(import.meta.dirname, "../../public/demo-run"));
    const record = run.exceptions.find((item) => item.jev !== null);
    expect(record).toBeDefined();
    render(<LineageDrawer record={record!} jevMode={mode} onClose={() => {}} />);

    expect(screen.getByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.queryByText("Jev AI review")).not.toBeInTheDocument();
    expect(screen.getByText("Scores are the model's own numbers, not measured accuracy.")).toBeInTheDocument();
  });

  it("falls back to a plain heading when the run mode is unknown or off", async () => {
    const run = await loadRunDir(path.resolve(import.meta.dirname, "../../public/demo-run"));
    const record = run.exceptions.find((item) => item.jev === null)!;
    render(<LineageDrawer record={record} onClose={() => {}} />);

    expect(screen.getByRole("heading", { name: "Jev review" })).toBeInTheDocument();
    expect(screen.getByText("Not reviewed by Jev.")).toBeInTheDocument();
  });
});

describe("Exceptions page passes the run's Jev mode to the detail panel", () => {
  it("shows the replay heading when a Jev-scored row is opened on the demo run", async () => {
    const { ExceptionsPage } = await import("@/components/exceptions-page");
    const { fireEvent } = await import("@testing-library/react");
    const run = await loadRunDir(path.resolve(import.meta.dirname, "../../public/demo-run"));
    expect(run.manifest.jev.mode).toBe("replay");
    const scored = run.exceptions.find((item) => item.jev !== null)!;
    render(<ExceptionsPage run={{ ...run, exceptions: [scored] }} />);

    fireEvent.click(within(screen.getByRole("table")).getAllByRole("row")[1]);
    const drawer = within(screen.getByRole("dialog"));
    expect(drawer.getByRole("heading", { name: "Jev review (replay of saved answers)" })).toBeInTheDocument();
  });
});

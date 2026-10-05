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
    expect(row.querySelector(".bg-indigo-600")?.getAttribute("style")).toContain("width: 71.5%");
  });
});

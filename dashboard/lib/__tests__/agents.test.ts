import path from "node:path";
import { describe, expect, it } from "vitest";

import { rtsMatrix } from "@/lib/agents";
import { loadRunDir } from "@/lib/run-dir";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");
const matrixFor = async (name: string) => rtsMatrix((await loadRunDir(path.join(FIXTURES, name))).rts);

describe("rtsMatrix", () => {
  it("puts example 3 in the Harborline TX 2026 column as used without RTS", async () => {
    const { columns, agents, gapPolicies } = await matrixFor("sample-run");
    expect(columns.map((column) => column.label)).toEqual([
      "Crestview Mutual TX 2026",
      "Harborline OK 2026",
      "Harborline TX 2026",
    ]);
    const agent = agents.find((row) => row.npn === "1884412");
    expect(agent?.cells.get("Harborline TX 2026")).toMatchObject({
      coverage: "USED_WITHOUT_RTS",
      policy_count: 1,
      exception_ids: ["EX-000005"],
    });
    expect(agent?.cells.get("Crestview Mutual TX 2026")?.coverage).toBe("HELD_UNUSED");
    expect(agent?.cells.get("Harborline OK 2026")?.coverage).toBe("HELD_AND_USED");
    expect(agent).toMatchObject({ policies: 42, gaps: 1 });
    expect(gapPolicies).toBe(1);
  });

  it("lists agents in NPN order with no cell where the roster has nothing", async () => {
    const { agents } = await matrixFor("sample-run");
    expect(agents.map((row) => row.npn)).toEqual(["1773019", "1884412", "2210457"]);
    expect(agents[0].cells.has("Crestview Mutual TX 2026")).toBe(false);
  });

  it("is empty for the failed sample", async () => {
    expect(await matrixFor("sample-run-failed")).toEqual({ columns: [], agents: [], gapPolicies: 0 });
  });

  it("has no gaps for the passed sample", async () => {
    const { agents, gapPolicies } = await matrixFor("sample-run-passed");
    expect(gapPolicies).toBe(0);
    expect(agents.every((row) => row.gaps === 0)).toBe(true);
  });
});

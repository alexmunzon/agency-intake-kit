import type { Metadata } from "next";

import { RunSwitch } from "@/components/loaded-run";
import { TieOutView } from "@/components/tie-out";
import { DEMO_RUN_DIR, loadRunDir, loadTieOut } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Tie-out | Agency Intake Kit" };

// Read at build time from public/demo-run, or swapped for a run you loaded. No network calls.
export default async function TieOutPage() {
  const run = await loadRunDir(DEMO_RUN_DIR);
  return (
    <RunSwitch page="tie-out">
      <TieOutView run={run} tieOut={await loadTieOut(DEMO_RUN_DIR, run)} />
    </RunSwitch>
  );
}

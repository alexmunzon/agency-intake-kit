import type { Metadata } from "next";

import { AgentsView } from "@/components/agents";
import { RunSwitch } from "@/components/loaded-run";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Agents | Agency Intake Kit" };

// Read at build time from public/demo-run, or swapped for a run you loaded. No network calls.
export default async function AgentsPage() {
  return (
    <RunSwitch page="agents">
      <AgentsView run={await loadRunDir(DEMO_RUN_DIR)} />
    </RunSwitch>
  );
}

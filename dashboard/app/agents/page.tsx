import type { Metadata } from "next";

import { AgentsView } from "@/components/agents";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";

export const metadata: Metadata = { title: "Agents | Agency Intake Kit" };

// Read at build time from public/demo-run. The dashboard makes no network calls.
export default async function AgentsPage() {
  return <AgentsView run={await loadRunDir(DEMO_RUN_DIR)} />;
}

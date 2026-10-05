import type { Metadata } from "next";

import { LoadRun } from "@/components/load-run";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Runs | Agency Intake Kit" };

export default async function RunsPage() {
  const demo = await loadRunDir(DEMO_RUN_DIR);
  return <LoadRun demoRunId={demo.manifest.run_id} />;
}

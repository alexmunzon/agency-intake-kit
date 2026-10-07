import type { Metadata } from "next";

import { RunSwitch } from "@/components/loaded-run";
import { Sources } from "@/components/sources";
import { DEMO_RUN_DIR, loadMappingReview, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Sources | Agency Intake Kit" };

export default async function SourcesPage() {
  const run = await loadRunDir(DEMO_RUN_DIR);
  return (
    <RunSwitch page="sources">
      <Sources run={run} mappingReview={await loadMappingReview(DEMO_RUN_DIR, run.manifest.run_id)} />
    </RunSwitch>
  );
}

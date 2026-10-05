import type { Metadata } from "next";

import { RunSwitch } from "@/components/loaded-run";
import { Sources } from "@/components/sources";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Sources | Agency Intake Kit" };

export default async function SourcesPage() {
  return (
    <RunSwitch page="sources">
      <Sources run={await loadRunDir(DEMO_RUN_DIR)} />
    </RunSwitch>
  );
}

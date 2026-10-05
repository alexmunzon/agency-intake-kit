import type { Metadata } from "next";

import { ExceptionsPage as Exceptions } from "@/components/exceptions-page";
import { RunSwitch } from "@/components/loaded-run";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-dir";

export const metadata: Metadata = { title: "Exceptions | Agency Intake Kit" };

// Read at build time. Filtering and the drawer run in the browser on data already on the page.
export default async function ExceptionsPage() {
  return (
    <RunSwitch page="exceptions">
      <Exceptions run={await loadRunDir(DEMO_RUN_DIR)} />
    </RunSwitch>
  );
}

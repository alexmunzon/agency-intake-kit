import { RunSwitch } from "@/components/loaded-run";
import { Overview } from "@/components/overview";
import { DEMO_RUN_DIR, loadRunDir, loadTieOut } from "@/lib/run-dir";

// The demo run is read at build time from public/demo-run. A run you load on the Runs page
// replaces it in the browser. The dashboard makes no network calls.
export default async function OverviewPage() {
  const run = await loadRunDir(DEMO_RUN_DIR);
  return (
    <RunSwitch page="overview">
      <Overview run={run} tieOut={await loadTieOut(DEMO_RUN_DIR, run)} />
    </RunSwitch>
  );
}

import { Overview } from "@/components/overview";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";

// Read at build time from public/demo-run. The dashboard makes no network calls.
export default async function OverviewPage() {
  return <Overview run={await loadRunDir(DEMO_RUN_DIR)} />;
}

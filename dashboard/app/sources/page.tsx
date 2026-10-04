import type { Metadata } from "next";

import { Sources } from "@/components/sources";
import { DEMO_RUN_DIR, loadRunDir } from "@/lib/run-loader";

export const metadata: Metadata = { title: "Sources | Agency Intake Kit" };

export default async function SourcesPage() {
  return <Sources run={await loadRunDir(DEMO_RUN_DIR)} />;
}

"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import { AgentsView } from "@/components/agents";
import { ExceptionsPage } from "@/components/exceptions-page";
import { Overview } from "@/components/overview";
import { Sources } from "@/components/sources";
import { TieOutView } from "@/components/tie-out";
import type { LoadedRun } from "@/lib/upload";

// A run you load lives only in this React state: never in storage, never sent anywhere.
// Moving between pages keeps it (the layout stays mounted); a reload or closing the tab clears it.
interface LoadedRunState {
  loaded: LoadedRun | null;
  setLoaded: (loaded: LoadedRun | null) => void;
}

const LoadedRunContext = createContext<LoadedRunState>({ loaded: null, setLoaded: () => {} });

export function LoadedRunProvider({ children }: { children: ReactNode }) {
  const [loaded, setLoaded] = useState<LoadedRun | null>(null);
  const value = useMemo(() => ({ loaded, setLoaded }), [loaded]);
  return <LoadedRunContext.Provider value={value}>{children}</LoadedRunContext.Provider>;
}

export function useLoadedRun(): LoadedRunState {
  return useContext(LoadedRunContext);
}

export function LoadedRunBanner() {
  const { loaded, setLoaded } = useLoadedRun();
  if (!loaded) return null;
  return (
    <section aria-label="Your run" className="mb-4 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm dark:border-indigo-900 dark:bg-indigo-950">
      <p>
        Showing your run <span className="font-mono text-xs break-all">{loaded.label}</span>. It stays in this tab only, and a reload clears it.
      </p>
      <button
        type="button"
        onClick={() => setLoaded(null)}
        className="rounded-md px-2 py-1 font-medium text-indigo-700 underline hover:bg-indigo-100 focus-visible:outline-2 focus-visible:outline-indigo-600 dark:text-indigo-300 dark:hover:bg-indigo-900"
      >
        Back to the demo run
      </button>
    </section>
  );
}

export type PageName = "overview" | "sources" | "exceptions" | "tie-out" | "agents";

/** Shows the server-rendered demo page, or the same page for a run you loaded. */
export function RunSwitch({ page, children }: { page: PageName; children: ReactNode }) {
  const { loaded } = useLoadedRun();
  if (!loaded) return children;
  const { run, tieOut } = loaded;
  switch (page) {
    case "overview":
      return <Overview run={run} tieOut={tieOut} />;
    case "sources":
      return <Sources run={run} />;
    case "exceptions":
      return <ExceptionsPage key={run.manifest.run_id} run={run} />;
    case "tie-out":
      return <TieOutView run={run} tieOut={tieOut} />;
    case "agents":
      return <AgentsView run={run} />;
  }
}

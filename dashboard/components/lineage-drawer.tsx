"use client";

import { useEffect, useRef, type ReactNode } from "react";

import { SeverityBadge } from "@/components/severity-badge";
import { percent, toneOf } from "@/lib/exceptions";
import type { ExceptionRecord } from "@/lib/types";

// One exception in full: what it is, where it came from, and how to fix it. Closes on Escape.
const JEV_SCORES = [
  ["entry_error_probability", "Chance this is a typing error"],
  ["impact_score", "Impact on the load"],
  ["pii_probability", "Chance this is private data"],
] as const;

function Row({ term, value }: { term: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1">
      <dt className="text-slate-600 dark:text-slate-400">{term}</dt>
      <dd className="break-all">{value ?? "None"}</dd>
    </div>
  );
}

export function LineageDrawer({ record, onClose }: { record: ExceptionRecord; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeButton.current?.focus();
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const { lineage, jev } = record;
  // The engine never writes raw notes, but a notes value is hidden here too, just in case.
  const value = record.field === "notes" && record.value_minimized ? "[redacted]" : record.value_minimized;
  const mono = (text: string | number | null) => (text === null ? null : <span className="font-mono">{text}</span>);
  return (
    <aside
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
      className="fixed inset-0 z-30 overflow-y-auto border-l border-slate-200 bg-white p-5 text-sm sm:left-auto sm:w-[480px] dark:border-slate-800 dark:bg-slate-900"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 id="drawer-title" className="text-base font-semibold">
          <span className="font-mono">{record.rule_id}</span> on <span className="font-mono">{record.id}</span>
        </h2>
        <button ref={closeButton} onClick={onClose} className="rounded-md border border-slate-200 px-2 py-1 text-xs focus-visible:outline-2 focus-visible:outline-indigo-600 dark:border-slate-800">
          Close
        </button>
      </div>
      <p className="mt-2"><SeverityBadge tone={toneOf(record.severity)} /> {record.message}</p>
      <h3 className="mt-4 font-medium">Suggested fix</h3>
      <p>{record.suggested_fix ?? "No fix needed. This is a note."}</p>
      <h3 className="mt-4 font-medium">Where it came from</h3>
      <dl>
        <Row term="Source file" value={mono(lineage?.source_file ?? record.source)} />
        {lineage?.sheet && <Row term="Sheet" value={lineage.sheet} />}
        <Row term="Row number" value={mono(lineage?.row_number ?? record.row_number)} />
        <Row term="Raw row hash" value={mono(lineage?.raw_hash ?? record.raw_hash)} />
        <Row term="Field" value={mono(record.field)} />
        <Row term="Value (masked)" value={mono(value)} />
        <Row term="Blocks the load" value={record.blocks_load ? "Yes" : "No"} />
      </dl>
      {!lineage && <p className="mt-1 text-xs text-slate-600 dark:text-slate-400">This is about the whole file, not one row.</p>}
      <h3 className="mt-4 font-medium">Jev AI review</h3>
      {jev ? (
        <dl>
          {JEV_SCORES.filter(([key]) => jev[key] !== null).map(([key, label]) => (
            <Row
              key={key}
              term={label}
              value={
                <span className="flex items-center gap-2 tabular-nums">
                  <span aria-hidden className="h-2 w-24 rounded bg-slate-100 dark:bg-slate-800">
                    <span className="block h-2 rounded bg-indigo-600 dark:bg-indigo-400" style={{ width: percent(jev[key] as number) }} />
                  </span>
                  {percent(jev[key] as number)}
                </span>
              }
            />
          ))}
        </dl>
      ) : (
        <p className="text-slate-600 dark:text-slate-400">Not reviewed by Jev.</p>
      )}
    </aside>
  );
}

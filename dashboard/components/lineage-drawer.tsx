"use client";

import { useEffect, useRef, type KeyboardEvent as ReactKeyboardEvent, type ReactNode } from "react";

import { SeverityBadge } from "@/components/severity-badge";
import { percent, toneOf } from "@/lib/exceptions";
import type { ExceptionRecord, JevMode } from "@/lib/types";

// One exception in full: what it is, where it came from, and how to fix it. Closes on Escape.
// It acts as a modal: the page behind it is inert, Tab stays inside, and focus returns on close.
const FOCUSABLE = 'summary, button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
const JEV_SCORES = [
  { key: "entry_error_probability", label: "Chance this is a typing error", max: 1, format: percent },
  { key: "impact_score", label: "Impact score on the load (0 to 2)", max: 2, format: (score: number) => `${score.toFixed(2)} / 2` },
  { key: "pii_probability", label: "Chance this is private data", max: 1, format: percent },
] as const;
// Say where the scores came from, the same way the mapping review panel does.
const JEV_HEADING: Partial<Record<JevMode, string>> = {
  replay: "Jev review (replay of saved answers)",
  live: "Jev review (live call)",
  record: "Jev review (record mode)",
};

function Row({ term, value }: { term: string; value: ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] gap-2 py-1">
      <dt className="text-muted-foreground">{term}</dt>
      <dd className="break-all">{value ?? "None"}</dd>
    </div>
  );
}

export function LineageDrawer({ record, jevMode, onClose }: { record: ExceptionRecord; jevMode?: JevMode; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    // Mark everything outside the drawer inert, walking up from the drawer to <body>.
    const inerted: Element[] = [];
    for (let node = panel.current as Element | null; node?.parentElement; node = node.parentElement) {
      for (const sibling of node.parentElement.children) {
        if (sibling !== node && !sibling.hasAttribute("inert")) {
          sibling.setAttribute("inert", "");
          inerted.push(sibling);
        }
      }
    }
    closeButton.current?.focus();
    return () => {
      inerted.forEach((element) => element.removeAttribute("inert"));
      opener?.focus();
    };
  }, []);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const trapTab = (event: ReactKeyboardEvent) => {
    if (event.key !== "Tab" || !panel.current) return;
    const items = [...panel.current.querySelectorAll<HTMLElement>(FOCUSABLE)];
    const [first, last] = [items[0], items[items.length - 1]];
    const edge = event.shiftKey ? first : last;
    if (document.activeElement === edge || !panel.current.contains(document.activeElement)) {
      event.preventDefault();
      (event.shiftKey ? last : first)?.focus();
    }
  };

  const { lineage, jev } = record;
  // The engine never writes raw notes, but a notes value is hidden here too, just in case.
  const value = record.field === "notes" && record.value_minimized ? "[redacted]" : record.value_minimized;
  const mono = (text: string | number | null) => (text === null ? null : <span className="font-mono">{text}</span>);
  return (
    <aside
      ref={panel}
      onKeyDown={trapTab}
      role="dialog"
      aria-modal="true"
      aria-labelledby="drawer-title"
      className="lineage-drawer fixed inset-0 z-30 overflow-y-auto border-l border-border bg-card text-sm sm:left-auto sm:w-[480px]"
    >
      <div className="flex items-start justify-between gap-2">
        <h2 id="drawer-title" className="text-base font-semibold">
          <span className="font-mono">{record.rule_id}</span> on <span className="font-mono">{record.id}</span>
        </h2>
        <button ref={closeButton} onClick={onClose} className="rounded-md border border-border px-2 py-1 text-xs focus-visible:outline-2 focus-visible:outline-ring">
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
      {!lineage && <p className="mt-1 text-xs text-muted-foreground">This is about the whole file, not one row.</p>}
      <details className="mt-4"><summary className="cursor-pointer font-medium">Model review details</summary>
      <h3 className="mt-2 font-medium">{(jevMode && JEV_HEADING[jevMode]) ?? "Jev review"}</h3>
      {jev ? (
        <>
          <p className="text-xs text-muted-foreground">Scores are the model&apos;s own numbers, not measured accuracy.</p>
          <dl>
          {JEV_SCORES.filter(({ key }) => jev[key] !== null).map(({ key, label, max, format }) => (
            <Row
              key={key}
              term={label}
              value={
                <span className="flex items-center gap-2 tabular-nums">
                  <span aria-hidden className="h-2 w-24 rounded bg-muted">
                    <span data-score={key} className="block h-2 rounded bg-muted-foreground" style={{ width: `${((jev[key] as number) / max) * 100}%` }} />
                  </span>
                  {format(jev[key] as number)}
                </span>
              }
            />
          ))}
          </dl>
        </>
      ) : (
        <p className="text-muted-foreground">Not reviewed by Jev.</p>
      )}
      </details>
    </aside>
  );
}

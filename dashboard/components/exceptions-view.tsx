"use client";

import { useCallback, useMemo, useState } from "react";
import { createColumnHelper } from "@tanstack/react-table";

import { LineageDrawer } from "@/components/lineage-drawer";
import { SeverityBadge, TONES } from "@/components/severity-badge";
import { DataTable, features, type Columns } from "@/components/tables";
import {
  NO_FILTERS, SEVERITY_ORDER, choices, filterExceptions, orderExceptions, toneOf, type ExceptionFilters,
} from "@/lib/exceptions";
import { plural } from "@/lib/overview";
import type { ExceptionRecord, Severity } from "@/lib/types";

const helper = createColumnHelper<typeof features, ExceptionRecord>();
const COLUMNS = helper.columns([
  helper.accessor("severity", { header: "Severity", cell: (info) => <SeverityBadge tone={toneOf(info.getValue())} /> }),
  helper.accessor("rule_id", { header: "Rule", cell: (info) => <span className="font-mono whitespace-nowrap">{info.getValue()}</span> }),
  helper.accessor("source", { header: "Source", cell: (info) => <span className="font-mono whitespace-nowrap">{info.getValue()}</span> }),
  helper.accessor("row_number", { header: "Row", cell: (info) => info.getValue()?.toLocaleString("en-US") ?? "Whole file" }),
  helper.accessor("message", { header: "What is wrong" }),
  helper.accessor("suggested_fix", { header: "How to fix it", cell: (info) => info.getValue() ?? "Nothing to fix" }),
]) as Columns<ExceptionRecord>;

const SELECT = "rounded-md border border-input bg-card px-2 py-1 text-sm text-foreground";

function Filter({ label, value, options, onChange }: { label: string; value: string; options: [string, string][]; onChange: (value: string) => void }) {
  return (
    <label className="flex flex-col gap-1.5 text-xs font-medium text-muted-foreground">
      {label}
      <select className={SELECT} value={value} onChange={(event) => onChange(event.target.value)}>
        <option value="">All</option>
        {options.map(([option, text]) => <option key={option} value={option}>{text}</option>)}
      </select>
    </label>
  );
}

export function ExceptionsView({ records }: { records: ExceptionRecord[] }) {
  const ordered = useMemo(() => orderExceptions(records), [records]);
  const [filters, setFilters] = useState<ExceptionFilters>(NO_FILTERS);
  const [open, setOpen] = useState<ExceptionRecord | null>(null);
  const shown = useMemo(() => filterExceptions(ordered, filters), [ordered, filters]);
  const close = useCallback(() => setOpen(null), []);
  const set = (key: keyof ExceptionFilters) => (value: string) => setFilters({ ...filters, [key]: value });
  const counts = SEVERITY_ORDER.map((severity) => [severity, records.filter((r) => r.severity === severity).length] as const);

  return (
    <div className="space-y-3">
      <p className="flex flex-wrap gap-2 text-sm tabular-nums" aria-label="Counts by severity">
        {counts.map(([severity, count]) => (
          <SeverityBadge key={severity} tone={toneOf(severity)} label={`${count.toLocaleString("en-US")} ${TONES[toneOf(severity)].label}`} />
        ))}
      </p>
      <div className="filter-bar flex flex-wrap items-end gap-3">
        <Filter label="Severity" value={filters.severity} onChange={set("severity")}
          options={SEVERITY_ORDER.map((s: Severity) => [s, TONES[toneOf(s)].label])} />
        <Filter label="Rule" value={filters.rule} onChange={set("rule")}
          options={choices(records, "rule_id").map((rule) => [rule, rule])} />
        <Filter label="Source" value={filters.source} onChange={set("source")}
          options={choices(records, "source").map((source) => [source, source])} />
        <p className="text-sm text-muted-foreground tabular-nums" role="status">
          Showing {shown.length.toLocaleString("en-US")} of {plural(records.length, "exception")}
        </p>
      </div>
      {shown.length === 0 ? (
        <p className="text-sm">No exceptions match these filters. Set a filter back to All to see more.</p>
      ) : (
        <DataTable
          label="Exceptions, blockers first"
          columns={COLUMNS}
          data={shown}
          rowLabel={(r) => `${r.severity.toLowerCase()} ${r.rule_id} in ${r.source}: ${r.message}. Open details.`}
          onRowClick={setOpen}
        />
      )}
      <p className="text-xs text-muted-foreground sm:hidden">Scroll the table sideways to see every column.</p>
      {open && <LineageDrawer record={open} onClose={close} />}
    </div>
  );
}

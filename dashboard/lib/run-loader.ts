import type { ExceptionRecord, Manifest, RtsCoverage, Scorecard } from "@/lib/types";

// Parses one run's files from text, so the server (demo run) and the browser (your run) share it. Basic shape checks only: the engine's models
// are the real validator. These catch a wrong folder, a mixed-up run, or money written as a number.
export interface Run {
  manifest: Manifest;
  scorecard: Scorecard;
  exceptions: ExceptionRecord[];
  rts: RtsCoverage;
}

export type RunFiles = Record<"manifest" | "scorecard" | "exceptions" | "rts", string>;

export const FILE_NAMES: RunFiles = {
  manifest: "manifest.json",
  scorecard: "scorecard.json",
  exceptions: "exceptions.jsonl",
  rts: "rts_coverage.json",
};
const STATUSES = ["PASSED", "PASSED_WITH_WARNINGS", "FAILED"];
const SEVERITIES = ["BLOCKER", "ERROR", "WARNING", "INFO"];

function check(ok: boolean, where: string, problem: string): void {
  if (!ok) throw new Error(`${where}: ${problem}`);
}

/** JSON.parse that names the file (and line) when the text is broken, so users know what to fix. */
export function parseJson(text: string, where: string): unknown {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${where}: not valid JSON (${(error as Error).message})`);
  }
}

function object(value: unknown, where: string, keys: string[]): Record<string, unknown> {
  check(typeof value === "object" && value !== null, where, "expected an object");
  const record = value as Record<string, unknown>;
  for (const key of keys) check(key in record, where, `missing ${key}`);
  return record;
}

export function parseRun(files: RunFiles): Run {
  const manifest = object(parseJson(files.manifest, FILE_NAMES.manifest), FILE_NAMES.manifest, [
    "run_id", "status", "started_at", "finished_at", "inputs", "jev",
  ]);
  check(STATUSES.includes(manifest.status as string), FILE_NAMES.manifest, "unknown status");
  const jev = object(manifest.jev, FILE_NAMES.manifest, ["calls", "estimated_cost_usd"]);
  check(typeof jev.estimated_cost_usd === "string", FILE_NAMES.manifest, "estimated_cost_usd must be text");

  const scorecard = object(parseJson(files.scorecard, FILE_NAMES.scorecard), FILE_NAMES.scorecard, [
    "run_id", "status", "rows_in", "rows_clean", "exceptions_by_severity", "tie_out", "rts_gaps",
  ]);
  check(
    scorecard.run_id === manifest.run_id && scorecard.status === manifest.status,
    FILE_NAMES.scorecard,
    "manifest and scorecard are not from the same run",
  );
  check(Array.isArray(manifest.inputs), FILE_NAMES.manifest, "inputs must be a list");
  check(Array.isArray(scorecard.tie_out), FILE_NAMES.scorecard, "tie_out must be a list");
  const severityCounts = object(scorecard.exceptions_by_severity, FILE_NAMES.scorecard, ["blocker", "error", "warning", "info"]);
  for (const leg of scorecard.tie_out as unknown[]) {
    const money = object(leg, FILE_NAMES.scorecard, ["variance_dollars"]).variance_dollars;
    check(money === null || typeof money === "string", FILE_NAMES.scorecard, "variance_dollars must be text");
  }

  const lines = files.exceptions.split("\n").filter((line) => line.trim() !== "");
  const exceptions = lines.map((line, index) => {
    const where = `${FILE_NAMES.exceptions} line ${index + 1}`;
    const record = object(parseJson(line, where), where, ["id", "rule_id", "severity", "source"]);
    check(SEVERITIES.includes(record.severity as string), where, "unknown severity");
    if (record.lineage !== null && record.lineage !== undefined) {
      const lineage = object(record.lineage, where, ["run_id"]);
      check(lineage.run_id === manifest.run_id, where, "lineage is not from the same run");
    }
    return record as unknown as ExceptionRecord;
  });

  const rts = object(parseJson(files.rts, FILE_NAMES.rts), FILE_NAMES.rts, ["cells"]);
  check(Array.isArray(rts.cells), FILE_NAMES.rts, "cells must be a list");
  check(new Set(exceptions.map((record) => record.id)).size === exceptions.length,
    FILE_NAMES.exceptions, "exception ids must be unique");
  for (const level of SEVERITIES) {
    check(severityCounts[level.toLowerCase()] === exceptions.filter((record) => record.severity === level).length,
      FILE_NAMES.exceptions, "severity counts disagree with scorecard.json");
  }
  const ruleCounts = object(scorecard.exceptions_by_rule, FILE_NAMES.scorecard, []);
  const observedRules = new Map<string, number>();
  for (const record of exceptions) observedRules.set(record.rule_id, (observedRules.get(record.rule_id) ?? 0) + 1);
  check(Object.keys(ruleCounts).length === observedRules.size &&
    [...observedRules].every(([rule, count]) => ruleCounts[rule] === count),
    FILE_NAMES.exceptions, "rule counts disagree with scorecard.json");
  const coverage = rts as unknown as RtsCoverage;
  const gaps = coverage.cells.filter((cell) => cell.coverage === "USED_WITHOUT_RTS");
  check(scorecard.rts_gaps === gaps.length, FILE_NAMES.rts, "gap count disagrees with scorecard.json");
  const exceptionRules = new Map(exceptions.map((record) => [record.id, record.rule_id]));
  for (const cell of gaps) {
    check(Array.isArray(cell.exception_ids), FILE_NAMES.rts, "exception_ids must be a list");
    for (const id of cell.exception_ids) check(exceptionRules.get(id) === "RTS-001",
      FILE_NAMES.rts, "gap references an unknown RTS-001 exception");
  }

  return {
    manifest: manifest as unknown as Manifest,
    scorecard: scorecard as unknown as Scorecard,
    exceptions,
    rts: rts as unknown as RtsCoverage,
  };
}

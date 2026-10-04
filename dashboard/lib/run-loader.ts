import { readFile } from "node:fs/promises";
import path from "node:path";

import type { ExceptionRecord, Manifest, RtsCoverage, Scorecard } from "@/lib/types";

// Loads one run directory written by the engine. Basic shape checks only: the engine's models
// are the real validator. These catch a wrong folder, a mixed-up run, or money written as a number.
export interface Run {
  manifest: Manifest;
  scorecard: Scorecard;
  exceptions: ExceptionRecord[];
  rts: RtsCoverage;
}

export type RunFiles = Record<"manifest" | "scorecard" | "exceptions" | "rts", string>;

const FILE_NAMES: RunFiles = {
  manifest: "manifest.json",
  scorecard: "scorecard.json",
  exceptions: "exceptions.jsonl",
  rts: "rts_coverage.json",
};
const STATUSES = ["PASSED", "PASSED_WITH_WARNINGS", "FAILED"];
const SEVERITIES = ["BLOCKER", "ERROR", "WARNING", "INFO"];

export const DEMO_RUN_DIR = path.join(process.cwd(), "public", "demo-run");

function check(ok: boolean, where: string, problem: string): void {
  if (!ok) throw new Error(`${where}: ${problem}`);
}

function object(value: unknown, where: string, keys: string[]): Record<string, unknown> {
  check(typeof value === "object" && value !== null, where, "expected an object");
  const record = value as Record<string, unknown>;
  for (const key of keys) check(key in record, where, `missing ${key}`);
  return record;
}

export function parseRun(files: RunFiles): Run {
  const manifest = object(JSON.parse(files.manifest), FILE_NAMES.manifest, [
    "run_id", "status", "started_at", "finished_at", "inputs", "jev",
  ]);
  check(STATUSES.includes(manifest.status as string), FILE_NAMES.manifest, "unknown status");
  const jev = object(manifest.jev, FILE_NAMES.manifest, ["calls", "estimated_cost_usd"]);
  check(typeof jev.estimated_cost_usd === "string", FILE_NAMES.manifest, "estimated_cost_usd must be text");

  const scorecard = object(JSON.parse(files.scorecard), FILE_NAMES.scorecard, [
    "run_id", "status", "rows_in", "rows_clean", "exceptions_by_severity", "tie_out", "rts_gaps",
  ]);
  check(
    scorecard.run_id === manifest.run_id && scorecard.status === manifest.status,
    FILE_NAMES.scorecard,
    "manifest and scorecard are not from the same run",
  );
  check(Array.isArray(manifest.inputs), FILE_NAMES.manifest, "inputs must be a list");
  check(Array.isArray(scorecard.tie_out), FILE_NAMES.scorecard, "tie_out must be a list");
  object(scorecard.exceptions_by_severity, FILE_NAMES.scorecard, ["blocker", "error", "warning", "info"]);
  for (const leg of scorecard.tie_out as unknown[]) {
    const money = object(leg, FILE_NAMES.scorecard, ["variance_dollars"]).variance_dollars;
    check(money === null || typeof money === "string", FILE_NAMES.scorecard, "variance_dollars must be text");
  }

  const lines = files.exceptions.split("\n").filter((line) => line.trim() !== "");
  const exceptions = lines.map((line, index) => {
    const where = `${FILE_NAMES.exceptions} line ${index + 1}`;
    const record = object(JSON.parse(line), where, ["id", "rule_id", "severity", "source"]);
    check(SEVERITIES.includes(record.severity as string), where, "unknown severity");
    return record as unknown as ExceptionRecord;
  });

  const rts = object(JSON.parse(files.rts), FILE_NAMES.rts, ["cells"]);
  check(Array.isArray(rts.cells), FILE_NAMES.rts, "cells must be a list");

  return {
    manifest: manifest as unknown as Manifest,
    scorecard: scorecard as unknown as Scorecard,
    exceptions,
    rts: rts as unknown as RtsCoverage,
  };
}

export async function loadRunDir(dir: string): Promise<Run> {
  const files = {} as RunFiles;
  for (const [key, name] of Object.entries(FILE_NAMES) as [keyof RunFiles, string][]) {
    try {
      files[key] = await readFile(path.join(dir, name), "utf8");
    } catch {
      throw new Error(`Could not read ${name} in ${dir}`);
    }
  }
  return parseRun(files);
}

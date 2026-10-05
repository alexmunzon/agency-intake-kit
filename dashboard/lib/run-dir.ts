import { readFile } from "node:fs/promises";
import path from "node:path";

import { FILE_NAMES, parseRun, type Run, type RunFiles } from "@/lib/run-loader";
import { parseTieOut, TIE_OUT_FILES, type TieOut } from "@/lib/tie-out";

// Server only: reads a run directory from disk. Pages call this at build time for the demo run.
// The parsing lives in run-loader and tie-out, so a run loaded in the browser is checked the same way.
export const DEMO_RUN_DIR = path.join(process.cwd(), "public", "demo-run");

async function read(dir: string, name: string): Promise<string> {
  try {
    return await readFile(path.join(dir, name), "utf8");
  } catch {
    throw new Error(`Could not read ${name} in ${dir}`);
  }
}

export async function loadRunDir(dir: string): Promise<Run> {
  const files = {} as RunFiles;
  for (const [key, name] of Object.entries(FILE_NAMES) as [keyof RunFiles, string][]) {
    files[key] = await read(dir, name);
  }
  return parseRun(files);
}

export async function loadTieOut(runDir: string, run?: Run): Promise<TieOut> {
  const files: Record<string, string> = {};
  for (const name of TIE_OUT_FILES) files[name] = await read(runDir, `tie_out/${name}.json`);
  return parseTieOut(files, run);
}

import { FILE_NAMES, parseJson, parseRun, type Run, type RunFiles } from "@/lib/run-loader";
import { parseTieOut, TIE_OUT_FILES, type TieOut } from "@/lib/tie-out";

// Reads a run you pick in the browser. Nothing is uploaded: the files are read into this tab's
// memory and checked with the same parsers the demo run uses. Every problem names its file.
export interface PickedFile {
  name: string;
  size: number;
  text(): Promise<string>;
}

export interface LoadedRun {
  label: string;
  run: Run;
  tieOut: TieOut;
}

export type UploadResult = { ok: true; loaded: LoadedRun } | { ok: false; errors: string[] };

export const MAX_FILE_BYTES = 50 * 1024 * 1024;

// The run file each picked name stands for. Matching by name lets you pick a whole run folder:
// tie_out names are unique, and anything else (clean/*.csv, for example) is never read.
const RUN_NAMES = Object.values(FILE_NAMES);
const WANTED = new Map<string, string>([
  ...RUN_NAMES.map((name): [string, string] => [name, name]),
  ...TIE_OUT_FILES.map((stem): [string, string] => [`${stem}.json`, `tie_out/${stem}.json`]),
]);

function checkJson(name: string, text: string): string[] {
  try {
    if (!name.endsWith(".jsonl")) parseJson(text, name);
    else text.split("\n").forEach((line, i) => line.trim() && parseJson(line, `${name} line ${i + 1}`));
    return [];
  } catch (error) {
    return [(error as Error).message];
  }
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function readRunFiles(files: PickedFile[]): Promise<UploadResult> {
  const picked = new Map<string, PickedFile>();
  const errors: string[] = [];
  for (const file of files) {
    const name = WANTED.get(file.name);
    if (!name) continue;
    if (picked.has(name)) errors.push(`${name}: picked twice. Pick one copy.`);
    else if (file.size > MAX_FILE_BYTES) errors.push(`${name}: larger than 50 MB, too large to open in the browser.`);
    picked.set(name, file);
  }
  if (picked.size === 0) {
    return { ok: false, errors: ["None of these are run files. Pick manifest.json, scorecard.json, exceptions.jsonl, rts_coverage.json, and the tie_out files."] };
  }
  if (errors.length > 0) return { ok: false, errors };

  const texts = new Map<string, string>();
  for (const name of WANTED.values()) {
    const file = picked.get(name);
    if (!file) {
      errors.push(`${name}: missing. Pick it with the other run files.`);
      continue;
    }
    const text = await file.text();
    texts.set(name, text);
    errors.push(...checkJson(name, text));
  }
  if (errors.length > 0) return { ok: false, errors };

  try {
    const runFiles = Object.fromEntries(
      (Object.entries(FILE_NAMES) as [keyof RunFiles, string][]).map(([key, name]) => [key, texts.get(name)!]),
    ) as RunFiles;
    const run = parseRun(runFiles);
    const tieFiles = Object.fromEntries(TIE_OUT_FILES.map((stem) => [stem, texts.get(`tie_out/${stem}.json`)!]));
    return { ok: true, loaded: { label: run.manifest.run_id, run, tieOut: parseTieOut(tieFiles, run) } };
  } catch (error) {
    return { ok: false, errors: [message(error)] };
  }
}

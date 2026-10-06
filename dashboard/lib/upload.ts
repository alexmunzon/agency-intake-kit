import { FILE_NAMES, parseJson, parseRun, type Run, type RunFiles } from "@/lib/run-loader";
import { parseTieOut, TIE_OUT_FILES, type TieOut } from "@/lib/tie-out";
import { parseFinanceReview, type FinanceReview } from "@/lib/finance-review";
import { parseLinkEvidence, type LinkEvidence } from "@/lib/link-evidence";

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
  finance?: FinanceReview;
  links?: LinkEvidence[];
}

export type UploadResult = { ok: true; loaded: LoadedRun } | { ok: false; errors: string[] };

export const MAX_FILE_BYTES = 50 * 1024 * 1024;

// The run file each picked name stands for. Matching by name lets you pick a whole run folder:
// tie_out names are unique, and anything else (clean/*.csv, for example) is never read.
const RUN_NAMES = Object.values(FILE_NAMES);
const FINANCE_FILE = "finance.json";
const LINKS_FILE = "tie_out/links.jsonl";
const WANTED = new Map<string, string>([
  ...RUN_NAMES.map((name): [string, string] => [name, name]),
  ...TIE_OUT_FILES.map((stem): [string, string] => [`${stem}.json`, `tie_out/${stem}.json`]),
  [FINANCE_FILE, FINANCE_FILE],
  ["links.jsonl", LINKS_FILE],
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
  const requiredNames = [...RUN_NAMES, ...TIE_OUT_FILES.map((stem) => `tie_out/${stem}.json`)];
  for (const name of requiredNames) {
    const file = picked.get(name);
    if (!file) {
      errors.push(`${name}: missing. Pick it with the other run files.`);
      continue;
    }
    try {
      const text = await file.text();
      texts.set(name, text);
      errors.push(...checkJson(name, text));
    } catch (error) {
      errors.push(`${name}: could not read (${message(error)})`);
    }
  }
  const financeFile = picked.get(FINANCE_FILE);
  if (financeFile) {
    try {
      texts.set(FINANCE_FILE, await financeFile.text());
    } catch (error) {
      errors.push(`${FINANCE_FILE}: could not read (${message(error)})`);
    }
  }
  const linksFile = picked.get(LINKS_FILE);
  if (linksFile) {
    try { texts.set(LINKS_FILE, await linksFile.text()); }
    catch { errors.push(`${LINKS_FILE}: could not read the file. Pick it again.`); }
  }
  if (errors.length > 0) return { ok: false, errors };

  try {
    let finance: FinanceReview | undefined;
    const financeText = texts.get(FINANCE_FILE);
    if (financeText !== undefined) {
      try {
        finance = parseFinanceReview(financeText);
      } catch {
        return { ok: false, errors: [`${FINANCE_FILE}: Invalid or unsupported finance review artifact`] };
      }
    }
    const runFiles = Object.fromEntries(
      (Object.entries(FILE_NAMES) as [keyof RunFiles, string][]).map(([key, name]) => [key, texts.get(name)!]),
    ) as RunFiles;
    const run = parseRun(runFiles);
    const linksText = texts.get(LINKS_FILE);
    const links = linksText === undefined ? undefined : parseLinkEvidence(linksText, run.manifest.run_id);
    const tieFiles = Object.fromEntries(TIE_OUT_FILES.map((stem) => [stem, texts.get(`tie_out/${stem}.json`)!]));
    return {
      ok: true,
      loaded: {
        label: run.manifest.run_id,
        run,
        tieOut: parseTieOut(tieFiles, run),
        ...(finance ? { finance } : {}),
        ...(links !== undefined ? { links } : {}),
      },
    };
  } catch (error) {
    return { ok: false, errors: [message(error)] };
  }
}

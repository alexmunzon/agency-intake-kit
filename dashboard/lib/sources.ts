import type { Tone } from "@/components/severity-badge";
import type { Run } from "@/lib/run-loader";
import type { ExceptionRecord, InputFile } from "@/lib/types";

// One summary per source file for the Sources page. Reading problems are the ING, MAP, CMP, and
// SSN rules. Everything else is a problem inside a row and belongs on the Exceptions page.
const READ_FAMILIES = ["ING", "MAP", "CMP", "SSN"];

export interface SourceSummary {
  file: InputFile;
  tone: Tone;
  status: string;
  encoding: string;
  delimiter: string;
  headerRow: string;
  gates: ExceptionRecord[];
  rowIssues: number;
  /** False when a blocker stopped the run before mapping, so mapping was never checked. */
  mapped: boolean;
}

function messageOf(records: ExceptionRecord[], rule: string): string | undefined {
  return records.find((record) => record.rule_id === rule)?.message;
}

// "Read crm.csv as cp1252" gives "cp1252". "Header found on row 3" gives "Row 3". If the wording
// ever changes, the full message shows instead, which is still true.
function lastWord(message: string | undefined): string | undefined {
  return message && (/ as (\S+)$/.exec(message)?.[1] ?? message);
}

function rowOf(message: string | undefined): string | undefined {
  const row = message && /row (\d+)$/.exec(message)?.[1];
  return row ? `Row ${row}` : message;
}

export function summarizeSource(run: Run, file: InputFile): SourceSummary {
  const records = run.exceptions.filter((record) => record.source === file.source);
  const gates = records.filter((record) => READ_FAMILIES.includes(record.family));
  const spreadsheet = /\.xlsx?$/i.test(file.file_name);
  let tone: Tone = "pass";
  let status = "Read cleanly";
  if (records.some((record) => record.severity === "BLOCKER")) {
    [tone, status] = ["blocker", "Blocked the run"];
  } else if (file.rows_expected !== null && file.rows_expected !== file.rows_received) {
    [tone, status] = ["error", "Rows missing"];
  } else if (gates.some((record) => record.severity !== "INFO")) {
    [tone, status] = ["warning", "Read with warnings"];
  }
  const mapped = run.manifest.status !== "FAILED";
  if (!mapped && tone === "pass") [tone, status] = ["info", "Read, not mapped (run stopped)"];
  return {
    file,
    tone,
    status,
    // No ING-001 means the file was UTF-8. No ING-002 means the header was on the first row.
    encoding: lastWord(messageOf(records, "ING-001")) ?? "UTF-8",
    delimiter: spreadsheet ? "Not needed (spreadsheet)" : (messageOf(records, "ING-004") ?? "Detected with confidence"),
    headerRow: rowOf(messageOf(records, "ING-002")) ?? "Row 1",
    gates,
    rowIssues: records.length - gates.length,
    mapped,
  };
}

export function summarizeSources(run: Run): SourceSummary[] {
  return run.manifest.inputs.map((file) => summarizeSource(run, file));
}

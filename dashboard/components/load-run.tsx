"use client";

import Link from "next/link";
import { useState, type DragEvent } from "react";

import { useLoadedRun } from "@/components/loaded-run";
import { CARD } from "@/components/tiles";
import { readRunFiles, type PickedFile } from "@/lib/upload";
import { cn } from "@/lib/utils";

const MUTED = "text-slate-600 dark:text-slate-400";
const INPUT = "block w-full max-w-full text-sm file:mr-3 file:rounded-md file:border-0 file:bg-indigo-600 file:px-3 file:py-1.5 file:text-white dark:file:bg-indigo-500 dark:file:text-slate-950";

/** Every file inside a dropped folder (and its tie_out folder). Only run files are read later. */
async function entryFiles(entry: FileSystemEntry): Promise<File[]> {
  if (entry.isFile) return [await new Promise<File>((ok, fail) => (entry as FileSystemFileEntry).file(ok, fail))];
  const reader = (entry as FileSystemDirectoryEntry).createReader();
  const files: File[] = [];
  for (;;) {
    const batch = await new Promise<FileSystemEntry[]>((ok, fail) => reader.readEntries(ok, fail));
    if (batch.length === 0) return files;
    for (const child of batch) files.push(...(await entryFiles(child)));
  }
}

async function droppedFiles(data: DataTransfer): Promise<File[]> {
  const entries = Array.from(data.items ?? [])
    .map((item) => item.webkitGetAsEntry?.())
    .filter((entry): entry is FileSystemEntry => Boolean(entry));
  if (entries.length === 0) return Array.from(data.files);
  return (await Promise.all(entries.map(entryFiles))).flat();
}

export function LoadRun({ demoRunId }: { demoRunId: string }) {
  const { loaded, setLoaded } = useLoadedRun();
  const [errors, setErrors] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);

  async function load(files: PickedFile[]) {
    setBusy(true);
    try {
      const result = await readRunFiles(files);
      if (result.ok) {
        setErrors([]);
        setLoaded(result.loaded);
      } else {
        setErrors(result.errors);
      }
    } catch {
      setErrors(["The files could not be read. Pick them again."]);
    } finally {
      setBusy(false);
    }
  }

  async function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    await load(await droppedFiles(event.dataTransfer));
  }

  return (
    <div className="space-y-4">
      <header>
        <p className={cn("text-sm", MUTED)}>Synthetic data only.</p>
        <h1 className="text-2xl font-semibold tracking-tight">Load your own run</h1>
        <p className="mt-1 text-sm">
          Pick the files from a run folder the engine wrote. They are read in this browser tab only. Nothing is uploaded, and reloading or closing the tab clears them.
        </p>
      </header>

      <p className={cn(CARD, "p-4 text-sm")} role="status" aria-label="Which run">
        {loaded ? (
          <>
            Loaded <span className="font-mono text-xs break-all">{loaded.label}</span>. Every page now shows it.{" "}
            <Link href="/" className="text-indigo-700 underline dark:text-indigo-300">Open the Overview</Link>
          </>
        ) : (
          <>
            Now showing the demo run <span className="font-mono text-xs">{demoRunId}</span>.
          </>
        )}
        {busy && " Reading the files..."}
      </p>

      <div
        role="group"
        aria-label="Drop run files here"
        onDragOver={(event) => event.preventDefault()}
        onDrop={onDrop}
        className={cn(CARD, "space-y-4 border-2 border-dashed p-4")}
      >
        <p className="text-sm font-medium">Drop the run folder or its files here, or pick them below.</p>
        <p className={cn("text-xs", MUTED)}>
          A run needs manifest.json, scorecard.json, exceptions.jsonl, rts_coverage.json, and the six JSON files in tie_out. Optional finance.json adds statement revenue review; links.jsonl retains policy candidate evidence. Other files in the folder are skipped and never read.
        </p>
        <div>
          <label htmlFor="run-files" className="mb-1 block text-sm">Pick the run files</label>
          <input
            id="run-files"
            type="file"
            multiple
            accept=".json,.jsonl"
            className={INPUT}
            onChange={(event) => load(Array.from(event.target.files ?? []))}
          />
        </div>
        <div>
          <label htmlFor="run-folder" className="mb-1 block text-sm">Or pick the whole run folder</label>
          <input
            id="run-folder"
            type="file"
            {...{ webkitdirectory: "" }}
            className={INPUT}
            onChange={(event) => load(Array.from(event.target.files ?? []))}
          />
        </div>
      </div>

      {errors.length > 0 && (
        <div role="alert" className={cn(CARD, "border-rose-300 p-4 text-sm dark:border-rose-800")}>
          <p className="font-medium">These files could not be loaded. The pages still show the run from before.</p>
          <ul className="mt-2 list-disc space-y-1 pl-5 break-words">
            {errors.map((error) => <li key={error}>{error}</li>)}
          </ul>
        </div>
      )}
    </div>
  );
}

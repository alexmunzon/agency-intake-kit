import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { LoadRun } from "@/components/load-run";
import { LoadedRunBanner, LoadedRunProvider, RunSwitch } from "@/components/loaded-run";

const FIXTURES = path.resolve(import.meta.dirname, "../../../fixtures");

async function fixtureFiles(sample: string): Promise<File[]> {
  const dir = path.join(FIXTURES, sample);
  const names = [...(await readdir(dir)).filter((n) => n.includes(".")), ...(await readdir(path.join(dir, "tie_out"))).map((n) => `tie_out/${n}`)];
  return Promise.all(names.map(async (name) => new File([await readFile(path.join(dir, name), "utf8")], path.basename(name))));
}

function setup() {
  render(
    <LoadedRunProvider>
      <LoadedRunBanner />
      <LoadRun demoRunId="sample-run" />
      <RunSwitch page="overview">
        <p>Demo overview</p>
      </RunSwitch>
    </LoadedRunProvider>,
  );
}

function pick(files: File[]) {
  const input = screen.getByLabelText("Pick the run files");
  Object.defineProperty(input, "files", { value: files, configurable: true });
  fireEvent.change(input);
}

describe("Load your own run", () => {
  it("says nothing leaves the browser and shows the demo run first", () => {
    setup();
    expect(screen.getByText(/Nothing is uploaded/)).toBeInTheDocument();
    expect(screen.getByText("Demo overview")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Back to the demo run" })).toBeNull();
  });

  it("loads a second run without the network and every page switches to it", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");
    setup();
    pick(await fixtureFiles("sample-run-partial"));
    await waitFor(() => expect(screen.getByRole("status", { name: "Which run" })).toHaveTextContent("Loaded sample-run-partial. Every page now shows it."));
    expect(screen.queryByText("Demo overview")).toBeNull();
    expect(screen.getByRole("heading", { level: 1, name: "What needs review before handoff?" })).toBeInTheDocument();
    expect(screen.getByText(/2 of 3 checks ran/)).toBeInTheDocument();
    const banner = within(screen.getByRole("region", { name: "Your run" }));
    expect(banner.getByText(/sample-run-partial/)).toBeInTheDocument();
    expect(fetchSpy).not.toHaveBeenCalled();

    fireEvent.click(banner.getByRole("button", { name: "Back to the demo run" }));
    expect(screen.getByText("Demo overview")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Your run" })).toBeNull();
  });

  it("lists each problem by file name and keeps the demo run", async () => {
    setup();
    const files = (await fixtureFiles("sample-run")).filter((file) => file.name !== "rts_coverage.json");
    pick(files);
    const alert = within(await screen.findByRole("alert"));
    expect(alert.getByText("rts_coverage.json: missing. Pick it with the other run files.")).toBeInTheDocument();
    expect(screen.getByText("Demo overview")).toBeInTheDocument();
  });

  it("accepts files dropped on the drop area", async () => {
    setup();
    const files = await fixtureFiles("sample-run-partial");
    fireEvent.drop(screen.getByRole("group", { name: "Drop run files here" }), { dataTransfer: { files, items: [] } });
    await waitFor(() => expect(screen.getByRole("status", { name: "Which run" })).toHaveTextContent("Loaded sample-run-partial. Every page now shows it."));
  });
});

import { mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, beforeAll, describe, expect, it } from "vitest";

// braces GHSA-vfj7-8cjw-p6xm has no patched release. Its last path into this project was Next's lint
// plugin -> fast-glob -> micromatch -> braces. An npm override swaps that fast-glob for a small local
// stand-in built on Node's own fs.globSync, so braces is no longer installed at all.
const root = path.resolve(import.meta.dirname, "../..");
const require = createRequire(path.join(root, "package.json"));
const pluginDir = path.dirname(require.resolve("@next/eslint-plugin-next/package.json"));
const { getRootDirs } = require(path.join(pluginDir, "dist/utils/get-root-dirs.js")) as {
  getRootDirs: (context: { cwd: string; settings: { next?: { rootDir?: string | string[] } } }) => string[];
};

describe("braces is gone from the install", () => {
  it("is absent from the lockfile, with micromatch", () => {
    const lock = JSON.parse(readFileSync(path.join(root, "package-lock.json"), "utf8"));
    const names = Object.keys(lock.packages);
    expect(names.filter((n) => /(^|\/)node_modules\/(braces|micromatch)$/.test(n))).toEqual([]);
  });

  it("gives Next's lint plugin the local stand-in instead of fast-glob", () => {
    const resolved = realpathSync(require.resolve("fast-glob", { paths: [pluginDir] }));
    expect(resolved).toBe(realpathSync(path.join(root, "vendor/fast-glob-shim/index.js")));
  });
});

describe("Next lint rootDir patterns behave as they did with fast-glob", () => {
  const cwd = process.cwd();
  let dir = "";
  beforeAll(() => {
    dir = mkdtempSync(path.join(tmpdir(), "rootdirs-"));
    for (const p of ["app/api", "lib/__tests__", "components/ui", "components/__tests__", ".hidden/x", "src/app"]) {
      mkdirSync(path.join(dir, p), { recursive: true });
    }
    writeFileSync(path.join(dir, "README.md"), "x");
    writeFileSync(path.join(dir, "lib/money.ts"), "x");
    process.chdir(dir);
  });
  afterAll(() => {
    process.chdir(cwd);
    rmSync(dir, { recursive: true, force: true });
  });
  const dirsFor = (rootDir?: string | string[]) =>
    getRootDirs({ cwd: dir, settings: rootDir === undefined ? {} : { next: { rootDir } } }).sort();

  // Expected values recorded from fast-glob 3.3.1 on this same fixture before the swap.
  it.each([
    ["app/", ["app/"]],
    ["app", ["app"]],
    ["./app/", ["./app/"]],
    ["*/", ["app", "components", "lib", "src"]],
    ["components/*/", ["components/__tests__", "components/ui"]],
    ["lib/**/", ["lib/__tests__"]],
    ["**/app/", ["app", "src/app"]],
    ["[al]*/", ["app", "lib"]],
    ["nope/", []],
    ["README.md", []],
    ["lib/*", ["lib/__tests__"]],
    ["src/*/", ["src/app"]],
  ])("%s", (pattern, expected) => {
    expect(dirsFor(pattern)).toEqual(expected);
  });

  it("handles a list of roots and the default", () => {
    expect(dirsFor(["app/", "lib/"])).toEqual(["app/", "lib/"]);
    expect(dirsFor()).toEqual([dir]);
  });

  it("refuses brace and extglob patterns loudly instead of expanding them", () => {
    expect(() => dirsFor("{app,lib}/")).toThrow(/not supported/);
    expect(() => dirsFor("{a,{b,{c}}}/")).toThrow(/not supported/);
    expect(() => dirsFor("@(app|lib)/")).toThrow(/not supported/);
  });
});

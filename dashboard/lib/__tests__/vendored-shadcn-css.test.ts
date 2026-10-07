import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

// The shadcn package pulled braces (GHSA-vfj7-8cjw-p6xm, no patched release) into the install
// tree. The only thing the app used from it was one stylesheet, so that file is now vendored
// byte for byte and the package is gone. These checks keep it that way.
const root = path.resolve(import.meta.dirname, "../..");
const read = (file: string) => readFileSync(path.join(root, file), "utf8");

// sha256 of shadcn@4.21.1 dist/tailwind.css as published to npm.
const UPSTREAM_SHA256 = "4c371f7a1ff5d219ae2f7ff28bd256b4346fd546fe46fbae22092e57db2f0fae";
const VENDORED = "app/vendor/shadcn/tailwind.css";

describe("Vendored shadcn stylesheet", () => {
  it("does not depend on the shadcn package", () => {
    const pkg = JSON.parse(read("package.json"));
    expect(pkg.dependencies ?? {}).not.toHaveProperty("shadcn");
    expect(pkg.devDependencies ?? {}).not.toHaveProperty("shadcn");
    expect(read("package-lock.json")).not.toContain('"node_modules/shadcn"');
  });

  it("imports the vendored copy instead of the package path", () => {
    const css = read("app/globals.css");
    expect(css).not.toContain('@import "shadcn/');
    expect(css).toContain('@import "./vendor/shadcn/tailwind.css";');
  });

  it("keeps the vendored copy identical to the published upstream file", () => {
    const hash = createHash("sha256").update(readFileSync(path.join(root, VENDORED))).digest("hex");
    expect(hash).toBe(UPSTREAM_SHA256);
  });

  it("ships the upstream MIT license next to the vendored copy", () => {
    expect(existsSync(path.join(root, "app/vendor/shadcn/LICENSE.md"))).toBe(true);
    expect(read("app/vendor/shadcn/LICENSE.md")).toContain("MIT License");
  });
});

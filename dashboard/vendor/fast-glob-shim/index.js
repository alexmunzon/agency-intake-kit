// Local stand-in for fast-glob, used only by @next/eslint-plugin-next (its get-root-dirs helper,
// which runs only when an ESLint config sets settings.next.rootDir). Real fast-glob pulls in braces,
// which has an unpatched advisory (GHSA-vfj7-8cjw-p6xm). This keeps the plugin's documented
// behavior for ordinary patterns with Node's own fs.globSync and refuses brace or extglob
// patterns instead of expanding them. Tests: dashboard/lib/__tests__/no-braces.test.ts.

import fs from "node:fs";

const MAGIC = /[*?[\]]/;
const UNSUPPORTED = /[{}()]/;

function isDirectory(p) {
  try {
    return fs.statSync(p).isDirectory();
  } catch {
    return false;
  }
}

function globOne(pattern, onlyDirectories) {
  if (UNSUPPORTED.test(pattern)) {
    throw new Error(`fast-glob stand-in: brace and extglob patterns are not supported: ${pattern}`);
  }
  // fast-glob returns a pattern without wildcards exactly as written when it exists.
  if (!MAGIC.test(pattern)) {
    const exists = onlyDirectories ? isDirectory(pattern) : fs.existsSync(pattern);
    return exists ? [pattern] : [];
  }
  let found = fs.globSync(pattern).map((p) => p.replace(/\\/g, "/"));
  if (onlyDirectories) found = found.filter(isDirectory);
  // Like fast-glob, hidden entries are skipped, and "base/**" does not match base itself.
  found = found.filter((p) => !p.split("/").some((part) => part.startsWith(".") && part !== "." && part !== ".."));
  const base = pattern.match(/^(.*?)\/\*\*\/?$/);
  if (base) found = found.filter((p) => p !== base[1].replace(/^\.\//, ""));
  return found;
}

export function globSync(patterns, options = {}) {
  const known = new Set(["onlyDirectories"]);
  for (const key of Object.keys(options)) {
    if (!known.has(key)) throw new Error(`fast-glob stand-in: option not supported: ${key}`);
  }
  const list = Array.isArray(patterns) ? patterns : [patterns];
  return [...new Set(list.flatMap((p) => globOne(p, Boolean(options.onlyDirectories))))];
}

export { globSync as sync };

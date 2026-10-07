import assert from "node:assert/strict";
import { test } from "node:test";

import { assess } from "./braces-advisory.mjs";

// Shape copied from GET /advisories/GHSA-vfj7-8cjw-p6xm on 2026-10-06.
const current = () => ({
  ghsa_id: "GHSA-vfj7-8cjw-p6xm",
  withdrawn_at: null,
  vulnerabilities: [
    {
      package: { ecosystem: "npm", name: "braces" },
      vulnerable_version_range: "<= 3.0.3",
      first_patched_version: null,
    },
  ],
});

test("no patch yet passes quietly", () => {
  const result = assess(current());
  assert.equal(result.ok, true);
  assert.match(result.message, /no patched release/);
});

test("a patched release fails so the owner is emailed", () => {
  const advisory = current();
  advisory.vulnerabilities[0].first_patched_version = "3.0.4";
  const result = assess(advisory);
  assert.equal(result.ok, false);
  assert.match(result.message, /3\.0\.4/);
});

test("a withdrawn advisory fails for a person to review", () => {
  const advisory = current();
  advisory.withdrawn_at = "2026-11-01T00:00:00Z";
  assert.equal(assess(advisory).ok, false);
});

test("a changed affected range fails for a person to review", () => {
  const advisory = current();
  advisory.vulnerabilities[0].vulnerable_version_range = "<= 3.0.4";
  const result = assess(advisory);
  assert.equal(result.ok, false);
  assert.match(result.message, /<= 3\.0\.4/);
});

test("a response without the npm braces entry fails instead of passing", () => {
  for (const advisory of [{}, { vulnerabilities: [] }, null, "not json"]) {
    assert.equal(assess(advisory).ok, false);
  }
});

test("a fix listed in a second braces entry still fails", () => {
  const advisory = current();
  advisory.vulnerabilities.push({
    package: { ecosystem: "npm", name: "braces" },
    vulnerable_version_range: ">= 4.0.0, <= 4.0.1",
    first_patched_version: "4.0.2",
  });
  const result = assess(advisory);
  assert.equal(result.ok, false);
  assert.match(result.message, /4\.0\.2/);
});

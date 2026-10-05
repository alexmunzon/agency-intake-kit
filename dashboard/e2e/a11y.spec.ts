import path from "node:path";
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

// Accessibility and layout checks on every page (#17). Run by hand: npx playwright test e2e/a11y.spec.ts
const PAGES = [
  { path: "/", question: "Can this agency go live?" },
  { path: "/sources", question: "What did we receive, and did it read cleanly?" },
  { path: "/exceptions", question: "What needs fixing, in what order, and how?" },
  { path: "/tie-out", question: "Does the money agree?" },
  { path: "/agents", question: "Is every writing agent allowed to sell what they sold?" },
  { path: "/runs", question: "Load your own run" },
] as const;
const SCHEMES = ["light", "dark"] as const;
const PARTIAL = path.resolve(__dirname, "../../fixtures/sample-run-partial");
const PARTIAL_FILES = [
  "manifest.json", "scorecard.json", "exceptions.jsonl", "rts_coverage.json",
  ...["leg_book_vs_statement", "leg_statement_vs_book", "leg_crm_vs_statement", "variances", "totals_by_carrier", "totals_by_agent"].map((stem) => `tie_out/${stem}.json`),
].map((name) => path.join(PARTIAL, name));

test.use({ reducedMotion: "reduce" });

/** Serious and critical axe findings, as "rule: target" lines so a failure says where to look. */
async function seriousViolations(page: Page): Promise<string[]> {
  const { violations } = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .flatMap((v) => v.nodes.map((node) => `${v.id}: ${node.target.join(" ")}`));
}

async function sidewaysScroll(page: Page): Promise<number> {
  return page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
}

async function open(page: Page, url: string, question: string) {
  await page.goto(url);
  await expect(page.getByRole("heading", { level: 1, name: question })).toBeVisible();
}

for (const scheme of SCHEMES) {
  for (const { path: url, question } of PAGES) {
    test(`${url} ${scheme}: axe has no serious or critical findings`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 1440, height: 900 });
      await open(page, url, question);
      await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /\bdark\b/ : /^(?!.*\bdark\b)/);
      expect(await seriousViolations(page)).toEqual([]);
    });

    test(`${url} ${scheme}: 375 wide has no sideways scroll`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme });
      await page.setViewportSize({ width: 375, height: 812 });
      await open(page, url, question);
      expect(await sidewaysScroll(page)).toBeLessThanOrEqual(0);
    });
  }

  test(`exceptions ${scheme}: axe passes with the lineage drawer open`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme });
    await open(page, "/exceptions", "What needs fixing, in what order, and how?");
    await page.getByRole("row", { name: /Open details/ }).first().click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(await seriousViolations(page)).toEqual([]);
  });
}

test("the dark mode toggle wins over the system setting and survives a reload", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await open(page, "/", "Can this agency go live?");
  await page.getByRole("button", { name: "Dark mode" }).click();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await page.reload();
  await expect(page.locator("html")).toHaveClass(/\bdark\b/);
  await expect(page.getByRole("button", { name: "Dark mode" })).toHaveAttribute("aria-pressed", "true");
});

test("a loaded run shows on every page with no network calls, and passes axe", async ({ page, baseURL }) => {
  const outside: string[] = [];
  page.on("request", (request) => {
    if (!request.url().startsWith(baseURL!)) outside.push(request.url());
  });
  await open(page, "/runs", "Load your own run");
  await page.getByLabel("Pick the run files").setInputFiles(PARTIAL_FILES);
  await expect(page.getByRole("status", { name: "Which run" })).toContainText("Loaded sample-run-partial");
  const sent = page.waitForRequest((request) => request.method() !== "GET", { timeout: 1000 }).catch(() => null);
  expect(await sent).toBeNull();

  for (const { path: url, question } of PAGES.slice(0, 5)) {
    await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: url === "/" ? "Overview" : new RegExp(url.slice(1), "i") }).click();
    await expect(page.getByRole("heading", { level: 1, name: question })).toBeVisible();
    await expect(page.getByRole("region", { name: "Your run" })).toContainText("sample-run-partial");
    expect(await seriousViolations(page)).toEqual([]);
  }
  await expect(page.getByRole("group", { name: "C. CRM vs statement" })).toHaveCount(0);
  await page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Tie-out" }).click();
  await expect(page.getByRole("group", { name: "C. CRM vs statement" })).toContainText("Not checked");

  await page.getByRole("button", { name: "Back to the demo run" }).click();
  await expect(page.getByRole("region", { name: "Your run" })).toHaveCount(0);
  await expect(page.getByRole("group", { name: "C. CRM vs statement" })).toContainText("Checked");
  expect(outside).toEqual([]);
});

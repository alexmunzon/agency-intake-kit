import { expect, test, type Page } from "@playwright/test";

// README screenshots of the demo run, written to docs/screenshots at the repo root.
// Run with `npm run shots` (from the repo root or dashboard/). The demo run is frozen
// (`npm run demo` uses --now), and animations are off, so the images do not churn.
const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 375, height: 812 };
const OUT = "../docs/screenshots";

const PAGES = [
  { name: "overview", path: "/", question: "Can this agency go live?" },
  { name: "sources", path: "/sources", question: "What did we receive, and did it read cleanly?" },
  { name: "exceptions", path: "/exceptions", question: "What needs fixing, in what order, and how?" },
  { name: "tie-out", path: "/tie-out", question: "Does the money agree?" },
  { name: "agents", path: "/agents", question: "Is every writing agent allowed to sell what they sold?" },
] as const;

test.use({ reducedMotion: "reduce" });

async function open(page: Page, path: string, question: string) {
  await page.goto(path);
  await expect(page.getByRole("heading", { level: 1, name: question })).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
}

async function expectNoSidewaysScroll(page: Page) {
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(0);
}

for (const { name, path, question } of PAGES) {
  test(`${name} 1440 light`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.setViewportSize(DESKTOP);
    await open(page, path, question);
    await expectNoSidewaysScroll(page);
    if (name === "overview") {
      // The answer and every tile fit on one screen at desktop width. The answer sits above
      // the tiles, so the lowest tile edge bounds both. Evidence tables below may scroll.
      const tiles = page.locator(".metric-tile");
      expect(await tiles.count()).toBeGreaterThanOrEqual(5);
      const bottoms = await tiles.evaluateAll((els) => els.map((el) => el.getBoundingClientRect().bottom));
      expect(Math.max(...bottoms)).toBeLessThanOrEqual(DESKTOP.height);
    }
    await page.screenshot({ path: `${OUT}/${name}-1440.png`, animations: "disabled" });
  });

  test(`${name} 375 has no sideways scroll`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.setViewportSize(PHONE);
    await open(page, path, question);
    await expectNoSidewaysScroll(page);
    if (name === "overview") {
      await page.screenshot({ path: `${OUT}/overview-375.png`, fullPage: true, animations: "disabled" });
    }
  });
}

test("overview 1440 dark", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "dark" });
  await page.setViewportSize(DESKTOP);
  await open(page, "/", "Can this agency go live?");
  await page.screenshot({ path: `${OUT}/overview-dark.png`, animations: "disabled" });
});

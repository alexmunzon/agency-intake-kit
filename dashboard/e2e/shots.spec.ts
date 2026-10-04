import { expect, test } from "@playwright/test";

// Overview screenshots for the README, written to docs/screenshots at the repo root.
// Run with `npm run shots` (from the repo root or dashboard/).
const HEIGHT = 900;

for (const width of [1440, 375]) {
  for (const theme of ["light", "dark"] as const) {
    test(`overview ${width} ${theme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: theme });
      await page.setViewportSize({ width, height: HEIGHT });
      await page.goto("/");
      await expect(page.getByRole("heading", { name: "Can this agency go live?" })).toBeVisible();
      if (width === 1440) {
        // The answer and every tile fit on one screen at desktop width.
        const height = await page.evaluate(() => document.documentElement.scrollHeight);
        expect(height).toBeLessThanOrEqual(HEIGHT);
      }
      await page.screenshot({ path: `../docs/screenshots/overview-${width}-${theme}.png`, fullPage: true });
    });
  }
}

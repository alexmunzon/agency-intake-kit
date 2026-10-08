import { mkdirSync, renameSync } from "node:fs";
import { expect, test } from "@playwright/test";

// Records the README demo: Overview, then Exceptions, then Tie-out, as a video.
// `npm run demo-gif` (repo root) runs this, then ffmpeg turns the video into
// docs/screenshots/demo.gif. The demo run is frozen, so the frames do not churn.
const SIZE = { width: 1280, height: 800 };
const OUT_DIR = "../docs/screenshots/.demo-video";

const STEPS = [
  { path: "/", question: "What needs review before handoff?" },
  { path: "/exceptions", question: "What needs fixing, in what order, and how?" },
  { path: "/tie-out", question: "Does the money agree?" },
] as const;

test("demo video: Overview, Exceptions, Tie-out", async ({ browser }) => {
  mkdirSync(OUT_DIR, { recursive: true });
  const context = await browser.newContext({
    viewport: SIZE,
    colorScheme: "light",
    reducedMotion: "reduce",
    recordVideo: { dir: OUT_DIR, size: SIZE },
  });
  const page = await context.newPage();
  for (const { path, question } of STEPS) {
    await page.goto(path);
    await expect(page.getByRole("heading", { level: 1, name: question })).toBeVisible();
    await page.evaluate(() => document.fonts.ready);
    await page.waitForTimeout(2500);
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(1500);
  }
  const video = page.video();
  await context.close();
  if (!video) throw new Error("Playwright did not record a video");
  renameSync(await video.path(), `${OUT_DIR}/demo.webm`);
});

import type { Browser } from "@playwright/test";

/**
 * Put a phone screenshot into a simple neutral device frame drawn in CSS (a dark bezel on a light
 * grey ground, no brand marks, no notch), rendered at scale 2.
 */
export async function framed(browser: Browser, screenshot: Buffer): Promise<Buffer> {
  const context = await browser.newContext({
    viewport: { width: 520, height: 1000 },
    deviceScaleFactor: 2,
  });
  const page = await context.newPage();
  await page.setContent(`<!doctype html><body style="margin:0;background:#E3E8EC;display:grid;place-items:center;height:100vh">
    <div id="frame" style="padding:16px;border-radius:64px;background:#1B242C;box-shadow:0 18px 40px rgba(28,43,54,.28), inset 0 0 0 2px #38454F">
      <img src="data:image/png;base64,${screenshot.toString("base64")}" width="390" height="844"
           style="display:block;border-radius:48px">
    </div></body>`);
  await page.waitForFunction(() => (document.querySelector("img") as HTMLImageElement).complete);
  const out = await page.screenshot({ type: "png" });
  await context.close();
  return out;
}

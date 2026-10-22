import { mkdir, writeFile } from "node:fs/promises";
import { join, resolve } from "node:path";

import { test, type Browser, type Page } from "@playwright/test";

import { LANG, MODE, REF_URL } from "../src/env.ts";
import { framed } from "../src/frame.ts";
import { expectChrome, settle, type Theme } from "../src/page.ts";
import { SCENES, type Scene } from "../src/scenes.ts";

// The package runs from scripts/screenshots: the repository root is two levels up.
const ROOT = resolve(process.cwd(), "../..");

async function write(path: string, data: Buffer): Promise<void> {
  await mkdir(resolve(path, ".."), { recursive: true });
  await writeFile(path, data);
}

/** One reference page per kind, loaded once: the canvas of iframes in design/reference/html. */
const refs = new Map<string, Page>();
async function reference(browser: Browser, scene: Scene, title: string): Promise<Buffer> {
  const url = `${REF_URL}/${scene.kind === "app" ? "mobile/staff-app.html" : "dashboard/planer-dashboard.html"}`;
  let page = refs.get(url);
  if (!page) {
    const context = await browser.newContext({ viewport: { width: 1600, height: 1000 } });
    page = await context.newPage();
    await page.goto(url);
    await page.waitForLoadState("load");
    await page.waitForTimeout(4000);
    refs.set(url, page);
  }
  const frame = page.locator(`iframe[title="${title}"]`);
  await frame.scrollIntoViewIfNeeded();
  await page.waitForTimeout(800);
  return frame.screenshot({ type: "png" });
}

/** Reference on the left, the app on the right, same CSS width, for the review folder. */
async function sideBySide(
  browser: Browser,
  ref: Buffer,
  app: Buffer,
  wide: boolean,
  label: string,
): Promise<Buffer> {
  const w = wide ? 1440 : 390;
  const context = await browser.newContext({ viewport: { width: w * 2 + 90, height: 900 } });
  const page = await context.newPage();
  const img = (b: Buffer): string => `data:image/png;base64,${b.toString("base64")}`;
  await page.setContent(`<!doctype html><body style="margin:0;padding:24px;background:#cfd6dc;font:600 18px system-ui;color:#1c2b36">
    <div style="display:flex;gap:40px;align-items:flex-start">
      <figure style="margin:0"><figcaption style="margin-bottom:8px">Reference · ${label}</figcaption><img src="${img(ref)}" style="width:${String(w)}px;display:block"></figure>
      <figure style="margin:0"><figcaption style="margin-bottom:8px">App · ${label}</figcaption><img src="${img(app)}" style="width:${String(w)}px;display:block"></figure>
    </div></body>`);
  await page.waitForFunction(() => [...document.images].every((i) => i.complete));
  const out = await page.screenshot({ type: "png", fullPage: true });
  await context.close();
  return out;
}

/** The scene list for `finalize` (contact sheets, INDEX.md): written once per capture run. */
async function writeManifest(): Promise<void> {
  const entries = SCENES.filter((s) => s.capture).map((s) => ({
    id: s.id,
    slug: s.slug,
    caption: s.caption,
    themes: s.dark ? ["light", "dark"] : ["light"],
  }));
  await write(
    join(ROOT, "screenshots", "manifest.json"),
    Buffer.from(JSON.stringify(entries, null, 2)),
  );
}

test.describe.configure({ mode: "serial" });

test.afterAll(async () => {
  if (MODE === "capture") await writeManifest();
});

for (const scene of SCENES) {
  if (MODE === "capture" && !scene.capture) continue;
  test(`${scene.id} ${scene.slug} (${MODE}, ${LANG})`, async ({ browser }) => {
    const themes: Theme[] = scene.dark ? ["light", "dark"] : ["light"];
    for (const theme of themes) {
      const page = await scene.run(browser, theme);
      await settle(page);
      // M12 holds the demo menu as part of its content; it is a comparison scene only.
      await expectChrome(page, scene.kind, scene.id === "M12");
      const shot = await page.screenshot({
        type: "png",
        animations: "disabled",
        caret: "hide",
        fullPage: scene.kind === "dashboard",
      });
      await page.context().close();
      if (MODE === "capture") {
        const out = scene.kind === "app" ? await framed(browser, shot) : shot;
        await write(join(ROOT, "screenshots", LANG, theme, `${scene.id}-${scene.slug}.png`), out);
      } else {
        const title = theme === "dark" ? (scene.refDark ?? scene.ref) : scene.ref;
        const ref = await reference(browser, scene, title);
        const both = await sideBySide(
          browser,
          ref,
          shot,
          scene.kind === "dashboard",
          `${scene.id} ${theme}`,
        );
        await write(
          join(ROOT, "review", `${scene.id}-${scene.slug}${theme === "dark" ? "-dark" : ""}.png`),
          both,
        );
      }
    }
  });
}

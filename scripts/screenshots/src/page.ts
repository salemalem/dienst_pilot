import { expect, type Browser, type Page } from "@playwright/test";

import { makeApi } from "../../e2e/api.ts";
import { API_URL, APP_URL, DASH_URL, LANG } from "./env.ts";
import { msg } from "./msg.ts";

export type Theme = "light" | "dark";
export type DashPersona = "brandt" | "vogel" | "it-admin";
export type AppPersona = "kaya" | "weber" | "alvarez" | "mehta" | "lorenz" | "nowak";

export const { login, api } = makeApi(API_URL);

/** The demo clock, moved by the Administrator (Berlin summer time on the demo days). */
export async function setClock(hhmm: string, day = "2026-10-20"): Promise<void> {
  const admin = await login("it-admin");
  await api(admin, "PUT", "/demo/clock", { now: `${day}T${hhmm}:00+02:00`, reset: false });
}

/** A planner dashboard page: 1440 px wide, scale 2, signed in as a persona in a theme. */
export async function dashboardPage(
  browser: Browser,
  persona: DashPersona,
  theme: Theme,
  path: string,
): Promise<Page> {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    deviceScaleFactor: 2,
    locale: LANG === "de" ? "de-DE" : "en-GB",
    timezoneId: "Europe/Berlin",
  });
  await context.addInitScript(
    ([p, t]) => {
      sessionStorage.setItem("dp-persona", String(p));
      localStorage.setItem("dp-theme", String(t));
    },
    [persona, theme],
  );
  const page = await context.newPage();
  await page.goto(`${DASH_URL}/${LANG}${path}`);
  return page;
}

/** A staff app page: 390×844, scale 2, a phone. Signed in as a persona (or signed out). */
export async function appPage(
  browser: Browser,
  persona: AppPersona | null,
  theme: Theme,
  path: string,
): Promise<Page> {
  let token: string | null = null;
  if (persona) {
    token = await login(persona);
    // Explicit theme, so a light capture is never dark just because the demo clock says 06:43.
    const current = await api<Record<string, unknown>>(token, "GET", "/me/settings");
    await api(token, "PUT", "/me/settings", { ...current, theme, language: LANG });
  }
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: LANG === "de" ? "de-DE" : "en-GB",
    timezoneId: "Europe/Berlin",
  });
  await context.addInitScript(
    ([lang, tok, who]) => {
      localStorage.setItem("dp-lang", String(lang));
      if (tok) {
        localStorage.setItem("dp-token", String(tok));
        localStorage.setItem("dp-persona", String(who));
      }
    },
    [LANG, token, persona],
  );
  const page = await context.newPage();
  await page.goto(`${APP_URL}${path}`);
  return page;
}

const QUIET = `*, *::before, *::after { transition: none !important; animation: none !important; caret-color: transparent !important; scroll-behavior: auto !important; }`;

/**
 * Get a page ready to be photographed: no animations, no caret, fonts loaded, network idle,
 * nothing still loading. Returns when the page has stopped changing.
 */
export async function settle(page: Page): Promise<void> {
  await page.addStyleTag({ content: QUIET });
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
  await expect(page.getByText(/^(Wird geladen|Loading)\s?…?$/)).toHaveCount(0);
  await expect(page.getByRole("progressbar").filter({ hasText: /./ })).toHaveCount(0);
  await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());
  await page.waitForTimeout(300);
}

/** The environment badge is visible and no persona or demo menu is open. */
export async function expectChrome(
  page: Page,
  kind: "dashboard" | "app",
  demoMenuIsContent = false,
): Promise<void> {
  await expect(page.getByText(msg("app.env"), { exact: true })).toBeVisible();
  if (kind === "app" && !demoMenuIsContent)
    await expect(page.locator('[data-testid^="persona-"]')).toHaveCount(0);
  else await expect(page.getByRole("listbox")).toHaveCount(0);
}

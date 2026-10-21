import { messages } from "@dienstpilot/i18n";
import { expect, type Page } from "@playwright/test";
import { IntlMessageFormat } from "intl-messageformat";

import { makeApi } from "../../../scripts/e2e/api.ts";
import { API_URL, LANG } from "../playwright.config.ts";

export { LANG };
export const { login, api } = makeApi(API_URL);

type Tree = { [k: string]: string | Tree };

/** A catalog message in the language of this run, formatted like the app does (ICU). */
export function msg(key: string, values: Record<string, string | number> = {}): string {
  let node: string | Tree | undefined = messages[LANG] as unknown as Tree;
  for (const part of key.split(".")) node = typeof node === "object" ? node[part] : undefined;
  if (typeof node !== "string") throw new Error(`no message ${key}`);
  return String(new IntlMessageFormat(node, LANG).format(values));
}

/** The demo clock, moved by the Administrator ("06:40" on 20 October 2026, Berlin time). */
export async function setClock(hhmm: string, day = "2026-10-20"): Promise<void> {
  const admin = await login("it-admin");
  await api(admin, "PUT", "/demo/clock", { now: `${day}T${hhmm}:00+02:00`, reset: false });
}

/** Start the app on the sign-in screen in the language of this run, with nobody signed in. */
export async function openApp(page: Page, path = "/sign-in"): Promise<void> {
  await page.addInitScript((lang) => {
    localStorage.setItem("dp-lang", lang);
  }, LANG);
  await page.goto(path);
}

/** Switch persona through the demo menu in M12 (Einstellungen), as the demo menu is meant to be used. */
export async function switchPersona(page: Page, key: string): Promise<void> {
  await page.goto("/settings");
  await page.getByTestId(`persona-${key}`).click();
  await expect(page.getByTestId("screen-today")).toBeVisible();
}

/** Sign in from M1 through the demo menu as a persona (a fresh browser starts signed out). */
export async function startAs(page: Page, key: string): Promise<void> {
  await openApp(page);
  await page.getByTestId("demo-toggle").click();
  await page.getByTestId(`persona-${key}`).click();
  await expect(page.getByTestId("screen-today")).toBeVisible();
}

/** Sign in from M1 as the default persona (Dr. Kaya). */
export async function signInDefault(page: Page): Promise<void> {
  await openApp(page);
  await page.getByTestId("sign-in").click();
  await expect(page.getByTestId("screen-today")).toBeVisible();
}

import { defineConfig } from "@playwright/test";

/** The staff app's e2e stack: API on :8100 (own database), the exported web build on :8083. */
export const API_PORT = 8100;
export const WEB_PORT = 8083;
export const API_URL = `http://localhost:${String(API_PORT)}`;
/** Each run covers one language; `pnpm e2e` runs German, then English, each on a fresh seed. */
export const LANG = process.env.E2E_LANG === "en" ? "en" : "de";

export default defineConfig({
  testDir: "./e2e",
  // One shared database that the specs change in order (the three situations, then the checks).
  workers: 1,
  fullyParallel: false,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: `http://localhost:${String(WEB_PORT)}`,
    // A phone: 390 pt wide, touch, a mobile user agent.
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    locale: LANG === "en" ? "en-GB" : "de-DE",
    timezoneId: "Europe/Berlin",
    trace: "retain-on-failure",
  },
  webServer: {
    command: `node e2e/serve.mjs dist-e2e ${String(WEB_PORT)}`,
    url: `http://localhost:${String(WEB_PORT)}/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

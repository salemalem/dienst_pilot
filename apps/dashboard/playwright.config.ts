import { defineConfig } from "@playwright/test";

/** The e2e stack: its own database and Redis database, API on :8100, dashboard on :3100. */
export const API_PORT = 8100;
export const WEB_PORT = 3100;
export const API_URL = `http://localhost:${String(API_PORT)}`;

export default defineConfig({
  testDir: "./e2e",
  // One shared database that the specs change in order (scenarios, December run, roles).
  workers: 1,
  fullyParallel: false,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : [["list"]],
  globalSetup: "./e2e/global-setup.ts",
  use: {
    baseURL: `http://localhost:${String(WEB_PORT)}`,
    viewport: { width: 1440, height: 900 },
    trace: "retain-on-failure",
    // Dates, clock and numbers must not depend on the machine's locale.
    locale: "de-DE",
    timezoneId: "Europe/Berlin",
  },
  webServer: {
    command: `pnpm exec next build && pnpm exec next start --port ${String(WEB_PORT)}`,
    url: `http://localhost:${String(WEB_PORT)}/de`,
    env: { API_URL },
    reuseExistingServer: Boolean(process.env.E2E_REUSE_WEB),
    timeout: 300_000,
  },
});

import { defineConfig } from "@playwright/test";

import { APP_PORT, API_URL, DASH_PORT, REF_PORT } from "./src/env.ts";

const skipBuild = process.env.SCREENSHOTS_SKIP_BUILD === "1";

export default defineConfig({
  testDir: "./tests",
  testMatch: "**/*.spec.ts",
  // The scenes build on each other (a sick report, then the cover request, then the cascade).
  workers: 1,
  fullyParallel: false,
  timeout: 600_000,
  expect: { timeout: 30_000 },
  retries: 0,
  reporter: [["list"]],
  globalSetup: "./global-setup.ts",
  use: { trace: "off" },
  webServer: [
    {
      command: `cd ../../apps/dashboard && ${skipBuild ? "" : "pnpm exec next build && "}pnpm exec next start --port ${String(DASH_PORT)}`,
      url: `http://localhost:${String(DASH_PORT)}/de`,
      env: { API_URL },
      reuseExistingServer: false,
      timeout: 300_000,
    },
    {
      // The exported staff app (`pnpm --filter @dienstpilot/mobile build:e2e`).
      command: `cd ../../apps/mobile && node ../../scripts/e2e/serve.mjs dist-e2e ${String(APP_PORT)}`,
      url: `http://localhost:${String(APP_PORT)}/`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `node ../e2e/serve.mjs ../../design/reference/html ${String(REF_PORT)}`,
      url: `http://localhost:${String(REF_PORT)}/dashboard/planer-dashboard.html`,
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});

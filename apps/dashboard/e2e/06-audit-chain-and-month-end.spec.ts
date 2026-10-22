import { expect, test } from "@playwright/test";

import { api, asPersona, login } from "./helpers.ts";

// Moves the demo clock; runs after the other specs (file order) and puts it back.
test.afterAll(async () => {
  await api(await login("it-admin"), "PUT", "/demo/clock", { reset: true });
});

test("W10: the chain indicator comes from a real check and 'Jetzt prüfen' runs one", async ({
  page,
}) => {
  await asPersona(page, "brandt");
  await page.goto("/de/protokoll");
  const chain = page.getByTestId("chain");
  await expect(chain).toHaveAttribute("data-state", "verified");
  await expect(chain).toContainText("Protokoll vollständig und unverändert");
  await expect(chain).toContainText("Einträge");
  await chain.getByRole("button", { name: "Jetzt prüfen" }).click();
  await expect(chain).toHaveAttribute("data-state", "verified");
});

test("W10: a clock that moves past the nightly check keeps the log verified by the nightly timer", async ({
  page,
}) => {
  const admin = await login("it-admin");
  await api(admin, "PUT", "/demo/clock", { now: "2026-10-23T08:00:00+02:00", reset: false });
  await asPersona(page, "brandt");
  await page.goto("/de/protokoll");
  await expect(page.getByTestId("chain")).toHaveAttribute("data-state", "verified");
  await api(admin, "PUT", "/demo/clock", { reset: true });
});

test("W12: the month end is prepared by itself, the Planner confirms with one click, then payroll is released", async ({
  page,
  context,
}) => {
  const admin = await login("it-admin");
  await asPersona(page, "vogel");
  await page.goto("/de/aufsicht");
  await expect(page.getByTestId("month-end-none")).toBeVisible();
  await api(admin, "PUT", "/demo/clock", { now: "2026-11-02T08:00:00+01:00", reset: false });
  await page.goto("/de/aufsicht");
  await expect(page.getByTestId("month-end-status")).toContainText("Wartet auf die Bestätigung");
  await expect(page.getByTestId("month-end-narrative")).toContainText("Platzhalter");
  await expect(page.getByTestId("payroll-export")).toBeDisabled();
  await expect(page.getByTestId("close-month")).toHaveCount(0); // Oversight cannot close
  const planner = await context.newPage();
  await asPersona(planner, "brandt");
  await planner.goto("/de/fairness");
  await planner.getByTestId("close-month").click();
  await expect(planner.getByTestId("month-end-status")).toContainText("Lohnexport ist freigegeben");
  await expect(planner.getByTestId("payroll-export")).toBeEnabled();
  await page.goto("/de/aufsicht");
  await expect(page.getByTestId("payroll-export")).toBeEnabled();
});

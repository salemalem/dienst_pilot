import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { api, LANG, login, msg, signInDefault } from "./helpers.ts";

const ROUTES = [
  "/sign-in",
  "/today",
  "/roster",
  "/notifications",
  "/settings",
  "/wishes",
  "/leave",
  "/swap",
  "/sick",
  "/cover",
  "/fairness",
  "/hours",
];

async function settle(page: Page): Promise<void> {
  await expect(page.getByRole("progressbar")).toHaveCount(0, { timeout: 30_000 });
}

for (const theme of ["light", "dark"] as const) {
  test(`every screen passes axe (WCAG A/AA), has named controls and 44 pt targets in ${LANG} / ${theme}`, async ({
    page,
  }) => {
    await signInDefault(page);
    const kaya = await login("kaya");
    await api(kaya, "PUT", "/me/settings", {
      language: LANG,
      theme,
      notifications: true,
      calendar_sync: false,
      preference_suggestions: true,
    });
    const problems: string[] = [];
    for (const route of ROUTES) {
      await page.goto(route);
      await page.waitForLoadState("networkidle");
      await settle(page);
      const r = await new AxeBuilder({ page })
        .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
        .analyze();
      for (const v of r.violations)
        problems.push(
          `${route} axe ${v.id}: ${v.nodes
            .map((n) => n.target.join(" "))
            .slice(0, 3)
            .join(" | ")}`,
        );
      // Touch targets: every button, switch and radio is at least 44 pt in both directions.
      const small = await page.evaluate(() =>
        [
          ...document.querySelectorAll(
            '[role="button"], [role="switch"], [role="radio"], [role="tab"], input, textarea',
          ),
        ]
          .map((el) => ({
            name: el.getAttribute("aria-label") ?? el.textContent ?? "",
            box: el.getBoundingClientRect(),
          }))
          .filter((x) => x.box.width > 0 && (x.box.height < 43.5 || x.box.width < 43.5))
          .map(
            (x) =>
              `${x.name.slice(0, 30)} ${String(Math.round(x.box.width))}x${String(Math.round(x.box.height))}`,
          ),
      );
      for (const s of small) problems.push(`${route} small target: ${s}`);
      // Every interactive element has an accessible name.
      const unnamed = await page.evaluate(() =>
        [...document.querySelectorAll('[role="button"], [role="switch"], [role="radio"]')]
          .filter((el) => (el.getAttribute("aria-label") ?? el.textContent ?? "").trim() === "")
          .map((el) => el.outerHTML.slice(0, 80)),
      );
      for (const s of unnamed) problems.push(`${route} unnamed control: ${s}`);
    }
    expect(problems).toEqual([]);
  });
}

test(`privacy in ${LANG}: no colleague names on M5, M9 compares only with the department average`, async ({
  page,
}) => {
  await signInDefault(page);
  await page.goto("/fairness");
  await expect(page.getByTestId("fairness-nights")).toBeVisible();
  const text = (await page.getByTestId("screen-fairness").textContent()) ?? "";
  expect(text).not.toMatch(/Dr\./);
  expect(text).toContain(msg("m9.privacy"));
  // The sentence reads like UI_SPEC's, in the language of the run.
  expect(text).toMatch(
    LANG === "de"
      ? /Sie liegen bei \w+diensten \d+ (unter|über) dem Durchschnitt|genau im Durchschnitt/
      : /You're \d+ \w+ (below|above) the department average|exactly at the average/,
  );
  await page.goto("/leave");
  await expect(page.getByTestId("screen-leave")).not.toContainText(/Dr\./);
});

test(`M1 switches the language and the choice sticks across a reload (${LANG} run)`, async ({
  page,
}) => {
  // No preset language here: the app starts in German, the default locale.
  await page.goto("/sign-in");
  await expect(page.getByTestId("sign-in")).toHaveAccessibleName("Mit Klinik-Konto anmelden");
  await page.getByTestId("locale-en").click();
  await expect(page.getByTestId("sign-in")).toHaveAccessibleName("Sign in with hospital account");
  await expect(page.locator("html")).toHaveAttribute("lang", "en");
  await page.reload();
  await expect(page.getByTestId("sign-in")).toHaveAccessibleName("Sign in with hospital account");
  await page.getByTestId("locale-de").click();
  await expect(page.getByTestId("sign-in")).toHaveAccessibleName("Mit Klinik-Konto anmelden");
  await expect(page.locator("html")).toHaveAttribute("lang", "de");
});

test(`M4 in ${LANG}: the confirmation preview labels a hard entry "can't" before anything is saved`, async ({
  page,
}) => {
  await signInDefault(page);
  await page.goto("/wishes");
  await page
    .getByTestId("free-text")
    .fill(LANG === "de" ? "Am 14.12. kann ich nicht." : "I can't work on 14.12.");
  await page.getByTestId("parse").click();
  const hard = page.getByTestId("parsed-hard-2026-12-14");
  await expect(hard).toBeVisible();
  await expect(hard).toContainText(LANG === "de" ? /^Kann nicht:/ : /^Can't:/);
  // Nothing is saved yet: the apply button is the only way, and the preview says what it is.
  await expect(page.getByTestId("parse-apply")).toBeVisible();
});

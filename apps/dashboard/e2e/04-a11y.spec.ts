import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

import { asPersona } from "./helpers.ts";

const PLANNER_ROUTES = [
  "",
  "/wunschphase",
  "/varianten",
  "/dienstplan",
  "/anfragen",
  "/ausfaelle",
  "/fairness",
  "/protokoll",
  "/regeln",
  "/ki-transparenz",
];

for (const locale of ["de", "en"] as const) {
  for (const theme of ["light", "dark"] as const) {
    test(`every screen works and passes axe (WCAG A/AA) in ${locale} / ${theme}`, async ({
      page,
    }) => {
      const check = async (path: string): Promise<void> => {
        await page.goto(`/${locale}${path}`);
        await expect(page.locator("[data-page-title]").first()).toBeVisible();
        await expect(
          page.getByRole("status").filter({ hasText: /Wird geladen|Loading/ }),
        ).toHaveCount(0);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
          .analyze();
        const summary = results.violations.map(
          (v) =>
            `${v.id}: ${v.nodes
              .map((n) => n.target.join(" "))
              .slice(0, 3)
              .join(" | ")}`,
        );
        expect(summary, `${path} (${locale}, ${theme})`).toEqual([]);
      };
      await asPersona(page, "brandt", theme);
      for (const r of PLANNER_ROUTES) await check(r);
      await asPersona(page, "vogel", theme);
      await check("/aufsicht");
    });
  }
}

test("the roster grid is keyboard-operable with a visible focus ring", async ({ page }) => {
  await asPersona(page, "brandt");
  await page.goto("/de/dienstplan?month=2026-11");
  const grid = page.getByTestId("roster-grid");
  await expect(grid).toBeVisible();
  const cells = grid.locator('td[role="gridcell"]');
  await expect(cells.first()).toBeVisible();
  // Exactly one cell is in the tab order (roving tabindex).
  await expect(grid.locator('td[role="gridcell"][tabindex="0"]')).toHaveCount(1);
  await grid.locator('td[role="gridcell"][tabindex="0"]').focus();
  const before = await page.evaluate(() => document.activeElement?.getAttribute("data-day"));
  await page.keyboard.press("ArrowRight");
  const after = await page.evaluate(() => document.activeElement?.getAttribute("data-day"));
  expect(after).not.toBe(before);
  const outline = await page.evaluate(
    () => getComputedStyle(document.activeElement as Element).outlineStyle,
  );
  expect(outline).toBe("solid");
  // Every cell has a complete accessible name: person, day, shift.
  await expect(cells.first()).toHaveAttribute("aria-label", /Dr\. .*, \d{2}\.\d{2}\./);
});

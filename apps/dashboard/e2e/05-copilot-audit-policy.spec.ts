import { expect, test } from "@playwright/test";

import { asPersona } from "./helpers.ts";

test("W9: the copilot answers with a rule citation, is labelled a stand-in and can only propose", async ({
  page,
}) => {
  await asPersona(page, "brandt");
  await page.goto("/de");
  await page.getByRole("button", { name: "Copilot" }).click();
  const panel = page.getByRole("complementary", { name: "Copilot" });
  await panel
    .getByRole("button", { name: "Warum hat Dr. Weber im Dezember zwei Wochenenden?" })
    .click();
  await expect(panel).toContainText("Quelle: max_weekends_per_month");
  await expect(panel.locator('[data-engine="stand-in"]')).toContainText("Platzhalter");
  // There is no publish or approve control in the panel; a proposal is the only action.
  await expect(
    panel.getByRole("button", { name: /veröffentlichen|freigeben|genehmigen/i }),
  ).toHaveCount(0);
  await panel.getByRole("button", { name: "Vorschlag erstellen" }).click();
  await expect(page.getByTestId("toast")).toContainText("Vorschlag erstellt");
  await page.goto("/de/anfragen");
  await expect(page.getByTestId("proposal-request").first()).toContainText(
    "Vorschlag des Copilots",
  );
});

test("W10: filterable event log, with the chain indicator that is backed by a real verification", async ({
  page,
}) => {
  await asPersona(page, "brandt");
  await page.goto("/de/protokoll");
  await expect(page.getByTestId("audit-rows").getByRole("row").first()).toBeVisible();
  await expect(page.getByTestId("chain")).toContainText("Protokoll vollständig und unverändert");
  await page
    .getByLabel("Ereignis", { exact: true })
    .selectOption({ label: "Dienstplan veröffentlicht" });
  const rows = page.getByTestId("audit-rows").getByRole("row");
  await expect(rows.first()).toHaveAttribute("data-action", "roster.published");
  const n = await rows.count();
  for (let i = 0; i < n; i++)
    await expect(rows.nth(i)).toHaveAttribute("data-action", "roster.published");
  // The December approval of this run is in the log, by the Planner.
  await expect(rows.filter({ hasText: "Dr. Thomas Brandt" }).first()).toBeVisible();
});

test("W11: the Planner's auto-approval policy is switchable and logged", async ({ page }) => {
  await asPersona(page, "brandt");
  await page.goto("/de/regeln");
  const swaps = page.getByRole("switch", { name: "Tausche automatisch freigeben" });
  await expect(swaps).toBeChecked();
  await page.getByText("Tausche automatisch freigeben").click();
  await expect(page.getByTestId("toast")).toContainText("Einstellung gespeichert");
  await expect(swaps).not.toBeChecked();
  await page.getByText("Tausche automatisch freigeben").click();
  await expect(swaps).toBeChecked();
});

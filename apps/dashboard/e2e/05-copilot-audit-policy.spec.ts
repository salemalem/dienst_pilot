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

test("W9: a what-if goes to the agent (recorded real answer), is labelled AI, shows the validator's verdict and its sources", async ({
  page,
}) => {
  await asPersona(page, "brandt");
  await page.goto("/de");
  await page.getByRole("button", { name: "Copilot" }).click();
  const panel = page.getByRole("complementary", { name: "Copilot" });
  await panel.getByRole("button", { name: /^Was passiert, wenn Dr\. Sofía Alvarez/ }).click();
  await expect(panel.getByTestId("copilot-answer")).toContainText("nicht zulässig");
  await expect(panel.locator('[data-engine="partial"]')).toContainText("Teilweise");
  await expect(panel).toContainText("Aufzeichnung einer echten Antwort");
  await expect(panel.getByTestId("copilot-whatif")).toContainText("Regelverletzungen gefunden");
  await panel.getByText(/^Quellen \(/).click();
  await expect(panel.getByTestId("copilot-sources")).toContainText("Was-wäre-wenn-Prüfung");
  // Still no publish or approve control; the only action is a proposal.
  await expect(
    panel.getByRole("button", { name: /veröffentlichen|freigeben|genehmigen/i }),
  ).toHaveCount(0);
  await expect(panel.getByRole("button", { name: "Vorschlag erstellen" })).toBeVisible();
});

test("W13: the C8 card shows the pre-registered gates, what is released and what stays a stand-in", async ({
  page,
}) => {
  await asPersona(page, "brandt");
  await page.goto("/de/ki-transparenz");
  const card = page.getByTestId("c8-metrics");
  await expect(card).toContainText("Freigegeben (Gates bestanden)");
  await expect(page.getByTestId("c8-served")).toContainText("Was-wäre-wenn");
  await expect(page.getByTestId("c8-served")).toContainText("Der Platzhalter bleibt für");
  await expect(page.getByTestId("c8-failed")).toContainText("Nicht bestanden: K1, K2");
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

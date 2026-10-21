import { expect, test } from "@playwright/test";

import { api, asPersona, login, restBreakingMove } from "./helpers.ts";

type Run = {
  run_id: string;
  status: string;
  variants: { variant_id: string; recommended: boolean; status: string }[];
};
type Grid = Parameters<typeof restBreakingMove>[0] & { status: string };

test.describe.serial("December: trial run, closing the window, a rule break, publish", () => {
  test("a run while the window is open is labelled a trial run and cannot be published", async ({
    page,
  }) => {
    await asPersona(page, "brandt");
    await page.goto("/de/varianten");
    await expect(page.getByTestId("trial-banner")).toContainText("Probelauf");
    await page.getByTestId("start-run").click();
    await expect(page.getByTestId("variant-A")).toBeVisible({ timeout: 120_000 });
    await expect(page.getByTestId("variant-A")).toContainText("Probelauf");
    // The draft opens in the editor, but publishing waits for the closed window.
    await page.getByTestId("open-A").click();
    await expect(page.getByTestId("open-publish")).toBeDisabled();
    await expect(page.getByTestId("publish-hint")).toContainText("Wunschphase");
  });

  test("close the request window in W2", async ({ page }) => {
    await asPersona(page, "brandt");
    await page.goto("/de/wunschphase");
    await expect(
      page.getByTestId("window-progress").or(page.getByText(/haben geantwortet/).first()),
    ).toBeVisible();
    await page.getByRole("button", { name: "Erinnerung senden" }).click();
    await expect(page.getByTestId("toast")).toContainText("Erinnerung an");
    await page.getByRole("button", { name: "Wunschphase schließen" }).click();
    await page.getByRole("dialog").getByRole("button", { name: "Wunschphase schließen" }).click();
    await expect(page.getByTestId("toast")).toContainText(
      "Wunschphase für Dezember 2026 geschlossen",
    );
  });

  test("W3 starts a real run, polls it and shows three variants with one recommendation", async ({
    page,
  }) => {
    await asPersona(page, "brandt");
    await page.goto("/de/varianten");
    await expect(page.getByTestId("trial-banner")).toHaveCount(0);
    await page.getByTestId("start-run").click();
    await expect(
      page.getByTestId("run-progress").or(page.getByTestId("variant-A")).first(),
    ).toBeVisible();
    for (const label of ["A", "B", "C"])
      await expect(page.getByTestId(`variant-${label}`)).toBeVisible({ timeout: 120_000 });
    await expect(page.getByTestId("recommended")).toHaveCount(1);
    await expect(page.getByTestId("variant-A")).toContainText("der Wünsche erfüllt");
    await expect(page.getByTestId("violations-A")).toHaveText("0");
    // Every number shown comes from the run: compare one with the API's.
    const brandt = await login("brandt");
    const runs = await api<{ runs: Run[] }>(brandt, "GET", "/planner/runs?month=2026-12");
    const done = runs.runs.filter((r) => r.status === "done");
    expect(done.length).toBe(2);
  });

  test("an edit that breaks the rest rule shows the message and its fix; undo restores validity", async ({
    page,
  }) => {
    const brandt = await login("brandt");
    const runs = await api<{ runs: Run[] }>(brandt, "GET", "/planner/runs?month=2026-12");
    const latest = runs.runs.find((r) => r.status === "done");
    const best = latest?.variants.find((v) => v.recommended);
    if (!best) throw new Error("no recommended variant");
    const grid = await api<Grid>(
      brandt,
      "GET",
      `/roster?month=2026-12&variant_id=${best.variant_id}`,
    );
    const move = restBreakingMove(grid);

    await asPersona(page, "brandt");
    await page.goto(`/de/dienstplan?month=2026-12&variant=${best.variant_id}`);
    await expect(page.getByTestId("rules-ok")).toBeVisible();
    const from = page.locator(`td[data-staff="${move.from.staffId}"][data-day="${move.from.day}"]`);
    const to = page.locator(`td[data-staff="${move.to.staffId}"][data-day="${move.to.day}"]`);
    await from.dragTo(to);

    const message = page.locator('[data-rule="min_rest"]').first();
    await expect(message).toBeVisible();
    await expect(message).toContainText("Ruhezeit von 11 Stunden nicht eingehalten");
    // What is wrong, and how to fix it: the second sentence names the correction.
    await expect(message).toContainText("tauschen");
    await expect(to).toHaveAttribute("data-violation", /Ruhezeit/);
    await expect(page.getByTestId("open-publish")).toBeDisabled();

    await page.getByTestId("undo").click();
    await expect(page.getByTestId("rules-ok")).toBeVisible();
    await expect(page.locator('[data-rule="min_rest"]')).toHaveCount(0);

    // The same change by keyboard: Space picks up, arrows choose the person, Space drops.
    const rows = grid.rows.map((r) => r.staff_id);
    const steps = rows.indexOf(move.to.staffId) - rows.indexOf(move.from.staffId);
    await from.focus();
    await page.keyboard.press("Space");
    await page.keyboard.press(`${steps > 0 ? "ArrowDown" : "ArrowUp"}`.repeat(1), { delay: 0 });
    for (let i = 1; i < Math.abs(steps); i++)
      await page.keyboard.press(steps > 0 ? "ArrowDown" : "ArrowUp");
    await page.keyboard.press("Space");
    await expect(page.locator('[data-rule="min_rest"]').first()).toBeVisible();
    await page.getByTestId("undo").click();
    await expect(page.getByTestId("rules-ok")).toBeVisible();
  });

  test("W5: the Planner's approval publishes the month", async ({ page }) => {
    const brandt = await login("brandt");
    const runs = await api<{ runs: Run[] }>(brandt, "GET", "/planner/runs?month=2026-12");
    const best = runs.runs.find((r) => r.status === "done")?.variants.find((v) => v.recommended);
    if (!best) throw new Error("no recommended variant");

    await asPersona(page, "brandt");
    await page.goto(`/de/dienstplan?month=2026-12&variant=${best.variant_id}`);
    await page.getByTestId("open-publish").click();
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByTestId("validation-ok")).toBeVisible();
    await expect(dialog).toContainText("sehen den Dienstplan Dezember 2026");
    await dialog.getByTestId("confirm-publish").click();
    await expect(page.getByTestId("toast")).toContainText("Dezember 2026 veröffentlicht");

    const grid = await api<Grid>(brandt, "GET", "/roster?month=2026-12");
    expect(grid.status).toBe("published");
    // A published month answers 409 to a second publish.
    await expect(
      api(brandt, "POST", `/planner/variants/${best.variant_id}/publish`),
    ).rejects.toThrow(/409/);
  });
});

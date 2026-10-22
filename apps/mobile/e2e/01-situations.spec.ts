import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import {
  api,
  LANG,
  login,
  msg,
  setClock,
  signInDefault,
  startAs,
  switchPersona,
} from "./helpers.ts";

type Roster = {
  days: {
    shifts: { date: string; shift_type: string; assignment_id: string; changed: boolean }[];
  }[];
};

async function axe(page: Page, where: string): Promise<void> {
  const r = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  expect(
    r.violations.map(
      (v) =>
        `${v.id}: ${v.nodes
          .map((n) => n.target.join(" "))
          .slice(0, 3)
          .join(" | ")}`,
    ),
    `axe: ${where} (${LANG})`,
  ).toEqual([]);
}

test.describe.serial("the three PROCESS.md situations on the demo clock", () => {
  test("A: Dr. Kaya requests 14 to 27 July 2027 and sees the honest default state", async ({
    page,
  }) => {
    await signInDefault(page);
    await expect(page.getByTestId("screen-today")).toContainText(msg("m2.nextShift"));
    await page.getByTestId("open-leave").click();
    await expect(page.getByTestId("screen-leave")).toBeVisible();
    // July 2027 is nine months after the demo month (October 2026).
    for (let i = 0; i < 9; i++) await page.getByTestId("month-next").click();
    await page.getByTestId("day-2027-07-14").click();
    await page.getByTestId("day-2027-07-27").click();

    // The instant hint is C6 (advisory). Its wording depends on the served model, so only its
    // presence and its label are asserted; the solver's answer below is the one that counts.
    const hint = page.getByTestId("leave-hint");
    await expect(hint).toBeVisible();
    await expect(hint.getByTestId("engine-C6")).toContainText(msg("common.built"));
    await expect(page.getByTestId("leave-hint-text")).not.toBeEmpty();

    // Then the real check by C1: coverable, with the two overlapping colleagues counted, not named.
    const result = page.getByTestId("leave-result");
    await expect(result).toBeVisible({ timeout: 120_000 });
    await expect(result.getByTestId("engine-C1")).toContainText(msg("common.built"));
    await expect(page.getByTestId("leave-coverable")).toHaveText(msg("m5.coverable", { count: 2 }));
    await expect(page.getByTestId("leave-trade-off")).toHaveCount(0);
    await expect(page.getByTestId("request-with-trade")).toHaveCount(0);
    await expect(page.getByTestId("screen-leave")).not.toContainText(/Dr\./);
    await axe(page, "M5 coverable");

    await page.getByTestId("request-leave").click();
    await expect(page.getByTestId("leave-created")).toBeVisible();
    await axe(page, "M5 sent");

    // The Planner sees the request (W6 of the dashboard shows it; here the API confirms it).
    const brandt = await login("brandt");
    const inbox = await api<{
      leave: { display_name: string; start_date: string; end_date: string }[];
    }>(brandt, "GET", "/planner/requests");
    expect(
      inbox.leave.some(
        (l) =>
          l.display_name === "Dr. Aylin Kaya" &&
          l.start_date === "2027-07-14" &&
          l.end_date === "2027-07-27",
      ),
    ).toBe(true);
  });

  test("B: Dr. Mehta offers his Saturday early shift (21.11.) as an exchange; Dr. Lorenz's exchange is auto-approved", async ({
    page,
  }) => {
    await startAs(page, "mehta");
    await page.getByTestId("quick-swap").click();
    await page.getByTestId("shift-2026-11-21-frueh").click();

    // Giving it away alone would put him below his contract hours: the app says so and offers an exchange.
    await expect(page.getByTestId("audience-text")).toBeVisible();
    await expect(page.getByTestId("giveaway-below-hours")).toHaveText(msg("m6.giveawayBelowHours"));
    // The audience is a count, never names.
    await expect(page.getByTestId("swap-audience")).not.toContainText(/Dr\./);
    await axe(page, "M6 offer");
    await page.getByTestId("offer-exchange").click();
    await expect(page.getByTestId("screen-swap-done")).toContainText(
      msg("m6.offeredBody").slice(0, 30),
    );
    await axe(page, "M6 offered");

    // Dr. Lorenz takes it against her early shift on Friday 27.11.
    await switchPersona(page, "lorenz");
    await page.getByTestId("quick-swap").click();
    await page.getByTestId("take-for-2026-11-27").click();
    await expect(page.getByTestId("swap-result")).toHaveText(msg("m6.status.approved"));
    await expect(page.getByTestId("swap-exchange")).toContainText("27");
    await expect(page.getByTestId("screen-swap-done")).toContainText(msg("m6.takenApproved"));

    // Both rosters changed (the Planner got a notice, not a request: see the dashboard spec).
    const mehta = await login("mehta");
    const roster = await api<Roster>(mehta, "GET", "/me/roster?month=2026-11");
    expect(
      roster.days
        .flatMap((d) => d.shifts)
        .find((s) => s.date === "2026-11-27" && s.shift_type === "frueh")?.changed,
    ).toBe(true);
  });

  test("C: Dr. Weber reports sick at 06:40; Dr. Alvarez gets the request, accepts at 06:43 and sees it confirmed", async ({
    page,
  }) => {
    await setClock("06:40");
    await startAs(page, "weber");
    await page.getByTestId("quick-sick").click();
    // One tap, no diagnosis field anywhere.
    await expect(page.getByTestId("screen-sick")).toContainText(msg("m7.noDiagnosis"));
    await expect(page.getByRole("textbox")).toHaveCount(0);
    await axe(page, "M7");
    await page.getByTestId("report-sick").click();
    await expect(page.getByTestId("screen-sick-done")).toContainText(
      msg("m7.done", { shift: msg("shift.frueh.name") }),
    );
    await expect(page.getByTestId("cover-started")).toHaveText(
      msg("m7.coverStarted", { count: 1 }),
    );
    await axe(page, "M7 done");

    // Three minutes later Dr. Alvarez has the request, with 12 minutes left.
    await setClock("06:43");
    await switchPersona(page, "alvarez");
    await expect(page.getByTestId("open-cover")).toBeVisible();
    await page.getByTestId("open-cover").click();
    await expect(page.getByTestId("screen-cover")).toContainText(msg("shift.frueh.name"));
    await expect(page.getByTestId("countdown")).toHaveText("12:00");
    await expect(page.getByTestId("screen-cover")).toContainText(
      msg("m8.replyBy", { time: "06:55" }),
    );
    await expect(page.getByTestId("hours-impact")).toBeVisible();
    await axe(page, "M8");
    await page.getByTestId("cover-accept").click();
    await expect(page.getByTestId("screen-cover-done")).toContainText(msg("m8.confirmedClosed"));
    await expect(page.getByTestId("cover-result")).toHaveText(msg("m8.accepted"));
    await axe(page, "M8 confirmed");

    // Her roster shows the changed shift on 20.10.; the Planner's W7 shows the gap closed at 06:43.
    const alvarez = await login("alvarez");
    const roster = await api<Roster>(alvarez, "GET", "/me/roster?month=2026-10");
    expect(
      roster.days
        .flatMap((d) => d.shifts)
        .find((s) => s.date === "2026-10-20" && s.shift_type === "frueh")?.changed,
    ).toBe(true);
    await page.goto("/roster");
    await expect(page.getByTestId("screen-roster")).toContainText(msg("m3.changed"));
  });
});

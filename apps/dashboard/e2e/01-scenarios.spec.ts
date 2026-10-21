import { expect, test } from "@playwright/test";

import { api, asPersona, login } from "./helpers.ts";

type Roster = { days: { shifts: { date: string; shift_type: string; assignment_id: string }[] }[] };

async function shift(token: string, day: string, type: string): Promise<string> {
  const r = await api<Roster>(token, "GET", `/me/roster?month=${day.slice(0, 7)}`);
  const s = r.days.flatMap((d) => d.shifts).find((x) => x.date === day && x.shift_type === type);
  if (!s) throw new Error(`no ${type} on ${day}`);
  return s.assignment_id;
}

test.describe.serial("the three PROCESS.md situations, seen from the dashboard", () => {
  test.beforeAll(async () => {
    // Situation A: Dr. Kaya asks for 14–27 July 2027 (the other personas play their parts by API).
    const kaya = await login("kaya");
    await api(kaya, "POST", "/me/leave", { start_date: "2027-07-14", end_date: "2027-07-27" });

    // Situation B: Dr. Mehta offers his Saturday Frühdienst (21.11.); Dr. Lorenz takes it in
    // exchange for her Frühdienst on 27.11.; C2 finds it valid, so the Planner's policy approves.
    const mehta = await login("mehta");
    const lorenz = await login("lorenz");
    const offered = await api<{ id: string }>(mehta, "POST", "/me/swaps", {
      assignment_id: await shift(mehta, "2026-11-21", "frueh"),
    });
    await api(lorenz, "POST", `/me/swap-offers/${offered.id}/take`, {
      give_assignment_id: await shift(lorenz, "2026-11-27", "frueh"),
    });

    // Situation C: Dr. Weber reports sick at 06:40, Dr. Alvarez accepts at 06:43 (demo clock).
    const admin = await login("it-admin");
    const at = (hhmm: string): Promise<unknown> =>
      api(admin, "PUT", "/demo/clock", { now: `2026-10-20T${hhmm}:00+02:00`, reset: false });
    await at("06:40");
    const weber = await login("weber");
    const early = await shift(weber, "2026-10-20", "frueh");
    await api(weber, "POST", "/me/sick", { start_date: "2026-10-20", end_date: "2026-10-20" });
    await at("06:43");
    const alvarez = await login("alvarez");
    const requests = await api<{ offer_id: string; shift: { assignment_id: string } }[]>(
      alvarez,
      "GET",
      "/me/cover-requests",
    );
    const mine = requests.find((r) => r.shift.assignment_id === early);
    if (!mine) throw new Error("Dr. Alvarez got no cover request");
    await api(alvarez, "POST", `/me/cover-requests/${mine.offer_id}`, { accept: true });
  });

  test("W6 shows Kaya's request with its computed impact", async ({ page }) => {
    await asPersona(page, "brandt");
    await page.goto("/de/anfragen");
    const item = page.getByTestId("leave-request").filter({ hasText: "Dr. Aylin Kaya" });
    await expect(item).toBeVisible();
    await expect(item).toContainText("14.–27.07. 2027");
    await item.click();
    const detail = page.getByTestId("request-detail");
    await expect(detail).toContainText("Dr. Aylin Kaya");
    await expect(detail.getByTestId("leave-impact")).toContainText("Abdeckbar");
    await expect(detail.getByTestId("approve-leave")).toBeEnabled();
    await page.goto("/en/anfragen");
    await expect(
      page.getByTestId("leave-request").filter({ hasText: "Dr. Aylin Kaya" }),
    ).toContainText("14–27 Jul 2027");
  });

  test("W1 shows the auto-approved exchange as a notice, not a request", async ({ page }) => {
    await asPersona(page, "brandt");
    await page.goto("/de");
    const recent = page.getByTestId("recent");
    const swap = recent
      .getByRole("listitem")
      .filter({ hasText: "Tausch" })
      .filter({ hasText: "21.11." });
    await expect(swap).toBeVisible();
    await expect(swap).toContainText("Automatisch freigegeben");
    // No escalated swap waits for the Planner.
    await page.goto("/de/anfragen");
    await expect(page.getByTestId("swap-request")).toHaveCount(0);
  });

  test("W7 shows the gap closed at 06:43", async ({ page }) => {
    await asPersona(page, "brandt");
    await page.goto("/de/ausfaelle");
    await expect(page.getByTestId("gap-closed").first()).toContainText(
      "Lücke geschlossen: Dr. Sofía Alvarez übernimmt, 06:43",
    );
    await page.goto("/en/ausfaelle");
    await expect(page.getByTestId("gap-closed").first()).toContainText(
      "Gap closed: Dr. Sofía Alvarez is covering, 06:43",
    );
    await expect(
      page
        .getByTestId("cascade")
        .first()
        .getByText(/Accepted/),
    ).toBeVisible();
  });
});

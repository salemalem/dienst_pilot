import { expect, type Browser, type Page } from "@playwright/test";

import { msg } from "./msg.ts";
import { restBreakingMove, type Grid } from "./moves.ts";
import { api, appPage, dashboardPage, login, setClock, type Theme } from "./page.ts";

export interface Scene {
  id: string;
  slug: string;
  /** One line for screenshots/INDEX.md (English; the images exist in both languages). */
  caption: string;
  kind: "dashboard" | "app";
  /** In the portfolio set (UI_SPEC §6). Scenes without it exist only for the comparison. */
  capture: boolean;
  /** Dark variants as well as light. */
  dark?: boolean;
  /** Title of the reference's iframe (design/reference/html), light; `refDark` for dark. */
  ref: string;
  refDark?: string;
  /** Bring up the page in the state to photograph. The caller settles, shoots and closes it. */
  run: (browser: Browser, theme: Theme) => Promise<Page>;
}

type Run = {
  run_id: string;
  status: string;
  variants: { variant_id: string; recommended: boolean }[];
};

async function recommended(token: string, month: string): Promise<string> {
  const runs = await api<{ runs: Run[] }>(token, "GET", `/planner/runs?month=${month}`);
  const done = runs.runs.find((r) => r.status === "done");
  const best = done?.variants.find((v) => v.recommended);
  if (!best) throw new Error("no recommended variant");
  return best.variant_id;
}

async function startRun(token: string, month: string): Promise<string> {
  const queued = await api<{ run_id: string }>(token, "POST", "/planner/runs", {
    roster_month: month,
  });
  for (let i = 0; i < 120; i++) {
    const r = await api<Run>(token, "GET", `/planner/runs/${queued.run_id}`);
    if (r.status === "done") {
      const best = r.variants.find((v) => v.recommended);
      if (!best) throw new Error("the run has no recommended variant");
      return best.variant_id;
    }
    await new Promise((res) => setTimeout(res, 1000));
  }
  throw new Error("the run did not finish");
}

/** The scenes in the order they must run: each one leaves the state the next one expects. */
export const SCENES: Scene[] = [
  {
    id: "M1",
    slug: "sign-in",
    caption: "Sign-in screen with the language switch",
    kind: "app",
    capture: false,
    ref: "M1 Anmeldung",
    run: async (b, theme) => {
      const p = await appPage(b, null, theme, "/sign-in");
      await expect(p.getByTestId("sign-in")).toBeVisible();
      return p;
    },
  },
  {
    id: "W1",
    slug: "overview",
    caption:
      "Planner overview: request window, open decisions, 14-day coverage with the C3 band, recent changes",
    kind: "dashboard",
    capture: true,
    dark: true,
    ref: "W1 Übersicht",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "");
      await expect(p.getByTestId("window-progress")).toBeVisible();
      await expect(p.getByTestId("recent")).toBeVisible();
      return p;
    },
  },
  {
    id: "W2",
    slug: "request-window",
    caption: "Request window: who has answered, remind, close",
    kind: "dashboard",
    capture: false,
    ref: "W2 Wunschphase",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "/wunschphase");
      await expect(p.getByRole("table").first()).toBeVisible();
      return p;
    },
  },
  {
    id: "M2",
    slug: "today",
    caption: "Today (Dr. Kaya): next shift, open tasks, quick actions",
    kind: "app",
    capture: true,
    dark: true,
    ref: "M2 Heute",
    refDark: "M2 Heute, dunkel",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/today");
      await expect(p.getByTestId("screen-today")).toBeVisible();
      await expect(p.getByText(msg("m2.nextShift"), { exact: true }).first()).toBeVisible();
      return p;
    },
  },
  {
    id: "M3",
    slug: "my-roster",
    caption: "My roster: month with shift letters and the list below",
    kind: "app",
    capture: false,
    ref: "M3 Mein Dienstplan",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/roster");
      await expect(p.getByTestId("calendar")).toBeVisible();
      return p;
    },
  },
  {
    id: "M4",
    slug: "wishes",
    caption: "Wishes: tap days, star two, free text read by C7",
    kind: "app",
    capture: false,
    ref: "M4 Wünsche (ganze Seite)",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/wishes");
      await expect(p.getByTestId("wish-calendar")).toBeVisible();
      return p;
    },
  },
  {
    id: "M9",
    slug: "fairness",
    caption: "Fairness balance: own figures against the department average only",
    kind: "app",
    capture: true,
    ref: "M9 Fairness-Bilanz",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/fairness");
      await expect(p.getByTestId("fairness-nights")).toBeVisible();
      return p;
    },
  },
  {
    id: "M10",
    slug: "hours",
    caption: "Hours: contract, planned, overtime, rest-period compliance",
    kind: "app",
    capture: false,
    ref: "M10 Stunden",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/hours");
      await expect(p.getByTestId("overtime")).toBeVisible();
      return p;
    },
  },
  {
    id: "M11",
    slug: "notifications",
    caption: "Notifications",
    kind: "app",
    capture: false,
    ref: "M11 Mitteilungen",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/notifications");
      await expect(p.getByTestId("screen-notifications")).toBeVisible();
      return p;
    },
  },
  {
    id: "M12",
    slug: "settings",
    caption: "Settings",
    kind: "app",
    capture: false,
    ref: "M12 Einstellungen",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/settings");
      await expect(p.getByTestId("screen-settings")).toBeVisible();
      return p;
    },
  },
  {
    id: "W8",
    slug: "fairness-compliance",
    caption: "Fairness and compliance",
    kind: "dashboard",
    capture: false,
    ref: "W8 Fairness und Compliance",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "/fairness");
      await expect(p.getByTestId("dist-nights")).toBeVisible();
      await expect(p.getByTestId("compliance-summary")).toBeVisible();
      return p;
    },
  },
  {
    id: "W13",
    slug: "ai-transparency",
    caption: "AI transparency: one card per component C1 to C8, with real status and metrics",
    kind: "dashboard",
    capture: true,
    ref: "W13 KI-Transparenz",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "/ki-transparenz");
      await expect(p.getByTestId("component-C8")).toBeVisible();
      await expect(p.getByTestId("c1-metrics")).toBeVisible();
      return p;
    },
  },
  {
    id: "W11",
    slug: "rules-master-data",
    caption: "Rules and master data (Administrator) with rule version 2026-1",
    kind: "dashboard",
    capture: true,
    ref: "W11 Regeln und Stammdaten",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "it-admin", theme, "/regeln");
      await expect(p.getByTestId("rule-sets")).toContainText("2026-1");
      return p;
    },
  },
  {
    id: "W12",
    slug: "oversight",
    caption: "Oversight (Katrin Vogel): read-only compliance, overtime and anonymous fairness",
    kind: "dashboard",
    capture: true,
    ref: "W12 Aufsicht",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "vogel", theme, "/aufsicht");
      await expect(p.getByTestId("read-only")).toBeVisible();
      await expect(p.getByTestId("cost-placeholder")).toBeVisible();
      return p;
    },
  },
  {
    id: "W3",
    slug: "variants",
    caption:
      "Variant comparison from a real solver run (a trial run while the request window is open)",
    kind: "dashboard",
    capture: true,
    ref: "W3 Varianten",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "/varianten");
      await p.getByTestId("start-run").click();
      await expect(p.getByTestId("variant-A")).toBeVisible({ timeout: 120_000 });
      await expect(p.getByTestId("violations-A")).toHaveText(/^\d+$/, { timeout: 30_000 });
      await expect(p.getByTestId("violations-C")).toHaveText(/^\d+$/);
      return p;
    },
  },
  {
    id: "W4",
    slug: "roster-editor",
    caption: "Roster editor with a rule message visible (11-hour rest period) and its fix",
    kind: "dashboard",
    capture: true,
    ref: "W4 Dienstplan-Editor",
    run: async (b, theme) => {
      const brandt = await login("brandt");
      const variant = await recommended(brandt, "2026-12");
      const grid = await api<Grid>(brandt, "GET", `/roster?month=2026-12&variant_id=${variant}`);
      const move = restBreakingMove(grid);
      await api(brandt, "PATCH", "/planner/roster/assignments", {
        variant_id: variant,
        assignment_id: move.assignmentId,
        new_staff_id: move.toStaffId,
      });
      const p = await dashboardPage(
        b,
        "brandt",
        theme,
        `/dienstplan?month=2026-12&variant=${variant}`,
      );
      await expect(p.locator('[data-rule="min_rest"]').first()).toBeVisible();
      await expect(p.getByTestId("roster-grid")).toBeVisible();
      return p;
    },
  },
  {
    id: "W9",
    slug: "copilot",
    caption: "Copilot answering with a rule citation (a stand-in, labelled as such)",
    kind: "dashboard",
    capture: true,
    ref: "W9 Copilot-Panel",
    run: async (b, theme) => {
      // The copilot beside the roster editor, as in the reference.
      const variant = await recommended(await login("brandt"), "2026-12");
      const p = await dashboardPage(
        b,
        "brandt",
        theme,
        `/dienstplan?month=2026-12&variant=${variant}`,
      );
      await expect(p.getByTestId("roster-grid")).toBeVisible();
      await p.getByRole("button", { name: msg("w9.toggle"), exact: true }).click();
      const panel = p.getByRole("complementary", { name: msg("w9.title") });
      await panel.getByRole("button", { name: msg("w9.sample") }).click();
      await expect(panel).toContainText(msg("w9.source"));
      return p;
    },
  },
  {
    id: "W9b",
    slug: "copilot-whatif",
    caption:
      "Copilot answering a what-if with the AI agent (a recorded real answer, labelled as such), the validator's verdict and its sources",
    kind: "dashboard",
    capture: true,
    ref: "W9 Copilot-Panel",
    run: async (b, theme) => {
      const variant = await recommended(await login("brandt"), "2026-12");
      const p = await dashboardPage(
        b,
        "brandt",
        theme,
        `/dienstplan?month=2026-12&variant=${variant}`,
      );
      await expect(p.getByTestId("roster-grid")).toBeVisible();
      await p.getByRole("button", { name: msg("w9.toggle"), exact: true }).click();
      const panel = p.getByRole("complementary", { name: msg("w9.title") });
      await panel.getByRole("button", { name: msg("w9.sampleWhatIf") }).click();
      await expect(panel.getByTestId("copilot-whatif")).toBeVisible();
      await expect(panel).toContainText(msg("ai.recorded"));
      return p;
    },
  },
  {
    id: "W5",
    slug: "approval",
    caption: "Approval dialog: what staff will see, then the Planner publishes",
    kind: "dashboard",
    capture: false,
    ref: "W5 Freigabe",
    run: async (b, theme) => {
      const brandt = await login("brandt");
      await api(brandt, "POST", "/planner/windows/2026-12/close");
      const variant = await startRun(brandt, "2026-12");
      const p = await dashboardPage(
        b,
        "brandt",
        theme,
        `/dienstplan?month=2026-12&variant=${variant}`,
      );
      await p.getByTestId("open-publish").click();
      await expect(p.getByRole("dialog").getByTestId("validation-ok")).toBeVisible();
      return p;
    },
  },
  {
    id: "M5",
    slug: "leave-request",
    caption:
      "Request leave (Situation A): 14 to 27 July 2027, coverable, no trade-off, no colleague names",
    kind: "app",
    capture: true,
    ref: "M5 Urlaub beantragen",
    run: async (b, theme) => {
      const p = await appPage(b, "kaya", theme, "/leave");
      await expect(p.getByTestId("screen-leave")).toBeVisible();
      for (let i = 0; i < 9; i++) await p.getByTestId("month-next").click();
      await p.getByTestId("day-2027-07-14").click();
      await p.getByTestId("day-2027-07-27").click();
      await expect(p.getByTestId("leave-result")).toBeVisible({ timeout: 120_000 });
      await expect(p.getByTestId("leave-coverable")).toBeVisible();
      return p;
    },
  },
  {
    id: "M6",
    slug: "exchange-offer",
    caption:
      "Exchange offer (Situation B): Dr. Mehta's Saturday early shift, offered only as an exchange",
    kind: "app",
    capture: true,
    ref: "M6 Dienst tauschen (Dr. Mehta)",
    run: async (b, theme) => {
      const p = await appPage(b, "mehta", theme, "/swap");
      await p.getByTestId("shift-2026-11-21-frueh").click();
      await expect(p.getByTestId("giveaway-below-hours")).toBeVisible();
      return p;
    },
  },
  {
    id: "M7",
    slug: "sick-report",
    caption: "Sick report (Situation C) at 06:40: one tap, no diagnosis, cover is being organised",
    kind: "app",
    capture: true,
    ref: "M7 Krank melden (Dr. Weber)",
    run: async (b, theme) => {
      await setClock("06:40");
      const p = await appPage(b, "weber", theme, "/sick");
      await p.getByTestId("report-sick").click();
      await expect(p.getByTestId("screen-sick-done")).toBeVisible();
      return p;
    },
  },
  {
    id: "M8",
    slug: "cover-request",
    caption: "Cover request at 06:43 (Dr. Alvarez): countdown, hours impact, take or decline",
    kind: "app",
    capture: true,
    dark: true,
    ref: "M8 Vertretungsanfrage (Dr. Alvarez)",
    refDark: "M8 Vertretungsanfrage, dunkel",
    run: async (b, theme) => {
      await setClock("06:43");
      const p = await appPage(b, "alvarez", theme, "/cover");
      await expect(p.getByTestId("countdown")).toHaveText("12:00");
      return p;
    },
  },
  {
    id: "W7",
    slug: "live-cascade",
    caption: "Live cover cascade: the gap closed at 06:43 by Dr. Alvarez",
    kind: "dashboard",
    capture: true,
    ref: "W7 Ausfälle live",
    run: async (b, theme) => {
      // Dr. Alvarez accepts (by API, as the person; the screens above showed her side).
      const alvarez = await login("alvarez");
      const requests = await api<{ offer_id: string }[]>(alvarez, "GET", "/me/cover-requests");
      const first = requests[0];
      if (!first) throw new Error("no cover request for Dr. Alvarez");
      await api(alvarez, "POST", `/me/cover-requests/${first.offer_id}`, { accept: true });
      const p = await dashboardPage(b, "brandt", theme, "/ausfaelle");
      await expect(p.getByTestId("gap-closed").first()).toContainText("06:43");
      return p;
    },
  },
  {
    id: "W7b",
    slug: "escalation",
    caption:
      "Escalation: nobody on the list answered in time, the Planner sees the options (auto-approval stays on)",
    kind: "dashboard",
    capture: true,
    ref: "W7b Eskalation",
    run: async (b, theme) => {
      // Dr. Nowak reports sick for tomorrow's early shift. The policy stays on; every eligible
      // colleague lets the 15-minute window run out (the demo clock moves on), so the list is
      // exhausted and the decision comes to the Planner.
      const nowak = await login("nowak");
      await api(nowak, "POST", "/me/sick", { start_date: "2026-10-21", end_date: "2026-10-21" });
      let id: string | null = null;
      for (let i = 1; i <= 10 && id === null; i++) {
        // 16 minutes per step on the demo clock (06:43 + 16 min, + 32 min, ...), Berlin time.
        const minutes = 6 * 60 + 43 + i * 16;
        const hh = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;
        await setClock(hh);
        const cascades = await api<
          { id: string; date: string; shift_type: string; status: string }[]
        >(await login("brandt"), "GET", "/planner/cascades");
        id =
          cascades.find((c) => c.date === "2026-10-21" && c.status === "pending_approval")?.id ??
          null;
      }
      if (!id) throw new Error("the cascade did not escalate on its own");
      const p = await dashboardPage(b, "brandt", theme, `/ausfaelle/${id}`);
      await expect(p.getByRole("radiogroup", { name: msg("w7b.optionsTitle") })).toBeVisible();
      return p;
    },
  },
  {
    id: "W10",
    slug: "audit-trail",
    caption: "Audit trail: who requested, proposed, approved and when",
    kind: "dashboard",
    capture: true,
    ref: "W10 Protokoll",
    run: async (b, theme) => {
      const p = await dashboardPage(b, "brandt", theme, "/protokoll");
      await expect(p.getByTestId("audit-rows").getByRole("row").first()).toBeVisible();
      return p;
    },
  },
];

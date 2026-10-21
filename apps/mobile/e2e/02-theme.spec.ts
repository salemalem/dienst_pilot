import { expect, test } from "@playwright/test";
import { colors } from "@dienstpilot/design-tokens";

import { api, login, msg, setClock, signInDefault } from "./helpers.ts";

/** rgb() of a token hex, as the browser reports a computed colour. */
function rgb(hex: string): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgb(${String((n >> 16) & 255)}, ${String((n >> 8) & 255)}, ${String(n & 255)})`;
}

const background = (page: import("@playwright/test").Page): Promise<string> =>
  page.getByTestId("screen-today").evaluate((el) => getComputedStyle(el).backgroundColor);

test.describe.serial("dark mode follows the demo clock, not the device clock", () => {
  test("20:00 to 07:00 is dark and the rest of the day is light, by the demo clock", async ({
    page,
  }) => {
    // The device clock of this browser says "now"; the demo clock decides.
    await setClock("12:00");
    await signInDefault(page);
    expect(await background(page)).toBe(rgb(colors.light.paper));

    await setClock("20:00");
    await page.reload();
    await expect(page.getByTestId("screen-today")).toBeVisible();
    expect(await background(page)).toBe(rgb(colors.dark.paper));

    await setClock("06:59");
    await page.reload();
    await expect(page.getByTestId("screen-today")).toBeVisible();
    expect(await background(page)).toBe(rgb(colors.dark.paper));

    await setClock("07:00");
    await page.reload();
    await expect(page.getByTestId("screen-today")).toBeVisible();
    expect(await background(page)).toBe(rgb(colors.light.paper));
  });

  test("M12: a manual choice overrides the clock, is kept, and 'automatisch' returns to the clock", async ({
    page,
  }) => {
    await setClock("23:00");
    await signInDefault(page);
    await page.goto("/settings");
    await expect(page.getByTestId("screen-settings")).toBeVisible();
    await expect(page.getByTestId("theme-note")).toContainText(msg("m12.now.dark"));

    await page.getByTestId("settings-theme-light").click();
    await expect(page.getByTestId("theme-note")).toHaveText(msg("m12.themeFixedNote"));
    expect(
      await page
        .getByTestId("screen-settings")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
    ).toBe(rgb(colors.light.paper));

    // Kept on the server, so it survives a reload (and another device).
    const kaya = await login("kaya");
    const saved = await api<{ theme: string }>(kaya, "GET", "/me/settings");
    expect(saved.theme).toBe("light");
    await page.reload();
    expect(
      await page
        .getByTestId("screen-settings")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
    ).toBe(rgb(colors.light.paper));

    await page.getByTestId("settings-theme-auto").click();
    await expect(page.getByTestId("theme-note")).toContainText(msg("m12.now.dark"));
    expect(
      await page
        .getByTestId("screen-settings")
        .evaluate((el) => getComputedStyle(el).backgroundColor),
    ).toBe(rgb(colors.dark.paper));
    await setClock("08:00");
  });
});

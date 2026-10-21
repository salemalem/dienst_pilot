import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import i18n from "../src/i18n";
import { EngineBadge } from "../src/components/chrome";
import { LeaveActions, LeaveResult } from "../src/components/LeaveParts";
import { ShiftChip } from "../src/components/ShiftChip";
import { Suggestion } from "../src/components/Suggestion";
import { Button, Segmented, TOUCH_MIN, ToggleRow, Txt } from "../src/components/ui";
import { formatCountdown } from "../src/lib/countdown";

// Icons are drawn with react-native-svg, which needs a native view; the tests care about text.
vi.mock("lucide-react-native", () => {
  const icon = (): null => null;
  return { CircleAlert: icon, CircleQuestionMark: icon, PencilLine: icon, FlaskConical: icon };
});

const standIn = { component: "C6", implementation: "stand-in", version: "standin-0.1", note: "" };
const built = { component: "C1", implementation: "built", version: "c1-1.0.1", note: "" };

beforeEach(async () => {
  await i18n.changeLanguage("de");
});
afterEach(cleanup);

const height = (el: HTMLElement): number => Number.parseFloat(getComputedStyle(el).minHeight);

describe("shift letters sit alongside colour and switch with the language", () => {
  it("F, S, N, B, R, U in German", () => {
    const letters = ["frueh", "spaet", "nacht", "bereitschaft", "ruf", "frei"].map((code) => {
      const { container, unmount } = render(<ShiftChip code={code} />);
      const text = container.textContent;
      unmount();
      return text;
    });
    expect(letters).toEqual(["F", "S", "N", "B", "R", "U"]);
  });

  it("E, L, N, O, H, V in English", async () => {
    await i18n.changeLanguage("en");
    const letters = ["frueh", "spaet", "nacht", "bereitschaft", "ruf", "frei"].map((code) => {
      const { container, unmount } = render(<ShiftChip code={code} />);
      const text = container.textContent;
      unmount();
      return text;
    });
    expect(letters).toEqual(["E", "L", "N", "O", "H", "V"]);
  });

  it("draws nothing for a code that is not a shift", () => {
    const { container } = render(<ShiftChip code="coffee" />);
    expect(container.textContent).toBe("");
  });
});

describe("one-handed use: targets of at least 44 pt and a name on every control", () => {
  it("a button is at least 44 pt tall, has role and name, and fires", () => {
    const onPress = vi.fn();
    render(<Button label="Krank melden" onPress={onPress} />);
    const button = screen.getByRole("button", { name: "Krank melden" });
    expect(height(button)).toBeGreaterThanOrEqual(44);
    expect(TOUCH_MIN).toBeGreaterThanOrEqual(44);
    fireEvent.click(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("a disabled or busy button does not fire", () => {
    const onPress = vi.fn();
    render(<Button label="Übernehmen" onPress={onPress} disabled />);
    fireEvent.click(screen.getByRole("button", { name: "Übernehmen" }));
    expect(onPress).not.toHaveBeenCalled();
  });

  it("a switch row is a whole-row target with its state", () => {
    const onChange = vi.fn();
    render(<ToggleRow label="Mit Kalender synchronisieren" value={false} onChange={onChange} />);
    const row = screen.getByRole("switch", { name: "Mit Kalender synchronisieren" });
    expect(height(row)).toBeGreaterThanOrEqual(44);
    expect(row.getAttribute("aria-checked")).toBe("false");
    fireEvent.click(row);
    expect(onChange).toHaveBeenCalledWith(true);
  });

  it("each option of a segmented control is at least 44 pt and says which is selected", () => {
    render(
      <Segmented
        label="Sprache"
        value="de"
        options={[
          { value: "de", label: "Deutsch" },
          { value: "en", label: "English" },
        ]}
        onChange={() => undefined}
      />,
    );
    const de = screen.getByRole("radio", { name: "Deutsch" });
    expect(height(de)).toBeGreaterThanOrEqual(44);
    expect(de.getAttribute("aria-checked")).toBe("true");
    expect(screen.getByRole("radio", { name: "English" }).getAttribute("aria-checked")).toBe(
      "false",
    );
  });
});

describe("AI output is labelled as the API reports it", () => {
  it("a stand-in shows the stand-in label, a built component does not", () => {
    render(
      <>
        <EngineBadge engine={standIn} />
        <EngineBadge engine={built} />
      </>,
    );
    expect(screen.getByTestId("engine-C6").textContent).toBe("C6 · Platzhalter · standin-0.1");
    expect(screen.getByTestId("engine-C1").textContent).toBe("C1 · Gebaut · c1-1.0.1");
  });

  it("the label switches with the language", async () => {
    await i18n.changeLanguage("en");
    render(<EngineBadge engine={standIn} />);
    expect(screen.getByTestId("engine-C6").textContent).toBe("C6 · Stand-in · standin-0.1");
  });

  it("a suggestion carries its label, hides the reasoning until 'Warum?' and never offers publishing", () => {
    render(
      <Suggestion engine={standIn} reasons={["Grundlage: 4 frühere Angaben"]}>
        <Txt>Abdeckbar.</Txt>
      </Suggestion>,
    );
    expect(screen.getByText("Vorschlag")).toBeTruthy();
    expect(screen.getByTestId("engine-C6")).toBeTruthy();
    expect(screen.queryByText(/Grundlage/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Warum?" }));
    expect(screen.getByText(/Grundlage/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /veröffentlichen|genehmigen/i })).toBeNull();
  });
});

describe("M5: the honest default, the trade-off only when the solver offers one", () => {
  const covered =
    "Abdeckbar. Zwei Kolleg:innen haben überschneidende Tage beantragt; die Besetzung bleibt gesichert, ohne Überstunden.";

  it("coverable: the default text, no trade-off, one plain request button", () => {
    render(
      <>
        <LeaveResult
          outcome="coverable"
          result={{ outcome: "coverable" }}
          engine={built}
          coveredText={covered}
          tradeMonth=""
        />
        <LeaveActions outcome="coverable" canRequest busy={false} onRequest={() => undefined} />
      </>,
    );
    expect(screen.getByTestId("leave-coverable").textContent).toBe(covered);
    expect(screen.queryByTestId("leave-trade-off")).toBeNull();
    expect(screen.getByRole("button", { name: "Urlaub beantragen" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mit Tausch beantragen" })).toBeNull();
  });

  it("trade-off: the extra weekend and the two request buttons", () => {
    const onRequest = vi.fn();
    render(
      <>
        <LeaveResult
          outcome="coverable_with_trade_off"
          result={{ outcome: "coverable_with_trade_off" }}
          engine={built}
          coveredText={covered}
          tradeMonth="Juni 2027"
        />
        <LeaveActions
          outcome="coverable_with_trade_off"
          canRequest
          busy={false}
          onRequest={onRequest}
        />
      </>,
    );
    expect(screen.getByTestId("leave-trade-off").textContent).toBe(
      "Abdeckbar, wenn Sie im Juni 2027 ein zusätzliches Wochenende übernehmen",
    );
    fireEvent.click(screen.getByRole("button", { name: "Mit Tausch beantragen" }));
    fireEvent.click(screen.getByRole("button", { name: "Ohne Tausch beantragen" }));
    expect(onRequest.mock.calls).toEqual([[true], [false]]);
  });

  it("not coverable: says so with the solver's reason, no colleague named", () => {
    render(
      <LeaveResult
        outcome="not_coverable"
        result={{
          outcome: "not_coverable",
          explanations: [
            {
              key: "infeasible.coverage",
              params: {
                date: "2027-07-20",
                shift: "nacht",
                qualification: "any",
                required: 2,
                available: 1,
              },
            },
          ],
        }}
        engine={built}
        coveredText=""
        tradeMonth=""
      />,
    );
    expect(screen.getByTestId("leave-not-coverable").textContent).toBe(
      "Nicht abdeckbar, ohne eine Regel zu verletzen.",
    );
    expect(screen.getByText(/20\.07\./)).toBeTruthy();
    expect(document.body.textContent).not.toMatch(/Dr\./);
  });

  it("the request button is disabled until the days are checked", () => {
    const onRequest = vi.fn();
    render(<LeaveActions outcome={null} canRequest={false} busy={false} onRequest={onRequest} />);
    fireEvent.click(screen.getByRole("button", { name: "Urlaub beantragen" }));
    expect(onRequest).not.toHaveBeenCalled();
  });
});

describe("M8 countdown", () => {
  it("shows minutes and seconds the API counts on the demo clock", () => {
    expect(formatCountdown(720)).toBe("12:00");
    expect(formatCountdown(59)).toBe("00:59");
    expect(formatCountdown(-5)).toBe("00:00");
  });
});

import { addMonths, daysInMonth, weekdayIndex } from "@dienstpilot/i18n";
import { radius, spacing } from "@dienstpilot/design-tokens";
import { ChevronLeft, ChevronRight } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Pressable, View } from "react-native";

import { useFmt } from "../lib/fmt";
import { useTheme } from "../lib/theme";
import { TOUCH_MIN, Txt } from "./ui";

export interface DayDecoration {
  /** Shift codes worked that day (chips) */
  shifts?: string[];
  selected?: boolean;
  /** Small shape-coded marks under the number (a wish, a star) */
  adornment?: ReactNode;
  /** Accessible description of the day beyond its date */
  description?: string;
  disabled?: boolean;
}

/**
 * A month as a 7-column grid, Monday first. Each day is at least 44 pt wide and tall; shifts show
 * as letter chips, so no day relies on colour alone.
 */
export function MonthCalendar({
  month,
  onMonth,
  decorate,
  onDay,
  renderShift,
  testID,
}: {
  month: string;
  onMonth?: (month: string) => void;
  decorate: (date: string) => DayDecoration;
  onDay?: (date: string) => void;
  renderShift?: (code: string) => ReactNode;
  testID?: string;
}): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const fmt = useFmt();
  const days = daysInMonth(month);
  const lead = weekdayIndex(days[0] ?? `${month}-01`);
  const cells: (string | null)[] = [...Array<null>(lead).fill(null), ...days];
  while (cells.length % 7 !== 0) cells.push(null);
  const headers = [
    "2026-10-19",
    "2026-10-20",
    "2026-10-21",
    "2026-10-22",
    "2026-10-23",
    "2026-10-24",
    "2026-10-25",
  ];
  return (
    <View testID={testID} style={{ gap: spacing[2] }}>
      <View style={{ flexDirection: "row", alignItems: "center", justifyContent: "space-between" }}>
        {onMonth ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("common.prevMonth")}
            onPress={() => {
              onMonth(addMonths(month, -1));
            }}
            style={{
              minHeight: TOUCH_MIN,
              minWidth: TOUCH_MIN,
              alignItems: "center",
              justifyContent: "center",
            }}
            testID="month-prev"
          >
            <ChevronLeft size={22} color={theme.ink} strokeWidth={1.75} />
          </Pressable>
        ) : null}
        <Txt variant="heading" accessibilityRole="header" testID="month-title">
          {fmt.month(month)}
        </Txt>
        {onMonth ? (
          <Pressable
            accessibilityRole="button"
            accessibilityLabel={t("common.nextMonth")}
            onPress={() => {
              onMonth(addMonths(month, 1));
            }}
            style={{
              minHeight: TOUCH_MIN,
              minWidth: TOUCH_MIN,
              alignItems: "center",
              justifyContent: "center",
            }}
            testID="month-next"
          >
            <ChevronRight size={22} color={theme.ink} strokeWidth={1.75} />
          </Pressable>
        ) : null}
      </View>
      <View style={{ flexDirection: "row" }}>
        {headers.map((h) => (
          <View key={h} style={{ flex: 1, alignItems: "center" }}>
            <Txt variant="caption" muted>
              {fmt.weekday(h)}
            </Txt>
          </View>
        ))}
      </View>
      {Array.from({ length: cells.length / 7 }, (_, row) => (
        <View key={row} style={{ flexDirection: "row" }}>
          {cells.slice(row * 7, row * 7 + 7).map((date, i) => {
            if (date === null) return <View key={`e${String(i)}`} style={{ flex: 1 }} />;
            const d = decorate(date);
            const weekend = weekdayIndex(date) >= 5;
            return (
              <Pressable
                key={date}
                accessibilityRole={onDay && d.disabled !== true ? "button" : "text"}
                accessibilityLabel={`${fmt.weekday(date)} ${fmt.dayMonth(date)}${d.description ? `, ${d.description}` : ""}`}
                accessibilityState={{
                  selected: d.selected === true,
                  disabled: d.disabled === true,
                }}
                disabled={!onDay || d.disabled === true}
                onPress={() => onDay?.(date)}
                testID={`day-${date}`}
                style={{
                  flex: 1,
                  minHeight: TOUCH_MIN + 8,
                  margin: 1,
                  alignItems: "center",
                  justifyContent: "flex-start",
                  paddingTop: 4,
                  gap: 2,
                  borderRadius: radius.mark,
                  backgroundColor: d.selected
                    ? theme.actionWash
                    : weekend
                      ? theme.sheetSunk
                      : theme.sheet,
                  borderWidth: d.selected ? 2 : 1,
                  borderColor: d.selected ? theme.action : theme.rule,
                  opacity: d.disabled ? 0.5 : 1,
                }}
              >
                <Txt variant="caption" muted={!d.selected}>
                  {Number(date.slice(8))}
                </Txt>
                {d.shifts && d.shifts.length > 0 && renderShift ? (
                  <View style={{ flexDirection: "row", gap: 2 }}>
                    {d.shifts.map((c) => (
                      <View key={c}>{renderShift(c)}</View>
                    ))}
                  </View>
                ) : null}
                {d.adornment ? (
                  <View style={{ flexDirection: "row", gap: 2 }}>{d.adornment}</View>
                ) : null}
              </Pressable>
            );
          })}
        </View>
      ))}
    </View>
  );
}

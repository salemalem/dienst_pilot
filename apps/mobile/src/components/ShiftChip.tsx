import {
  radius,
  shiftColors,
  shiftTypes,
  spacing,
  type ShiftType,
} from "@dienstpilot/design-tokens";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { StyleSheet, Text, View } from "react-native";

import { useTheme } from "../lib/theme";
import { type } from "../type";
import { Txt } from "./ui";

/** API shift codes are the six token names; anything else is not a shift. */
export function asShift(code: string): ShiftType | null {
  return (shiftTypes as readonly string[]).includes(code) ? (code as ShiftType) : null;
}

/** 45° hatching for leave, drawn with thin rotated stripes clipped by the chip. */
function Hatch({ color, box }: { color: string; box: number }): ReactNode {
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, { overflow: "hidden" }]}>
      {Array.from({ length: Math.ceil(box / 4) + 4 }, (_, i) => (
        <View
          key={i}
          style={{
            position: "absolute",
            top: -8,
            left: i * 5 - 14,
            width: 2,
            height: box + 16,
            backgroundColor: color,
            transform: [{ rotate: "45deg" }],
          }}
        />
      ))}
    </View>
  );
}

/**
 * A shift as colour plus letter: the letter switches with the language, leave is hatched and
 * Rufbereitschaft carries the dotted off-site edge, so no shift relies on colour alone.
 */
export function ShiftChip({ code, box = 32 }: { code: string; box?: number }): ReactNode {
  const { t } = useTranslation();
  const { themeId } = useTheme();
  const shift = asShift(code);
  if (!shift) return null;
  const c = shiftColors(themeId, shift);
  const leave = shift === "frei";
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{
        width: box,
        height: box,
        borderRadius: radius.mark,
        alignItems: "center",
        justifyContent: "center",
        overflow: "hidden",
        backgroundColor: leave ? c.wash : c.solid,
        borderWidth: leave || c.edge !== undefined ? 1 : 0,
        borderColor: leave ? c.solid : c.edge,
      }}
    >
      {leave ? <Hatch color={c.solid} box={box} /> : null}
      {shift === "ruf" ? (
        <View
          style={{
            position: "absolute",
            top: 3,
            left: 3,
            right: 3,
            bottom: 3,
            borderWidth: 1.5,
            borderStyle: "dotted",
            borderColor: c.on,
            borderRadius: 2,
          }}
        />
      ) : null}
      <Text
        style={[
          type.gridLetter,
          { color: c.on, paddingHorizontal: 2, borderRadius: 2 },
          leave ? { backgroundColor: c.solid } : null,
        ]}
      >
        {t(`shift.${shift}.letter`)}
      </Text>
    </View>
  );
}

/** Chip plus the shift's name. */
export function ShiftLabel({ code }: { code: string }): ReactNode {
  const { t } = useTranslation();
  const shift = asShift(code);
  return (
    <View style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
      <ShiftChip code={code} />
      <Txt variant="bodyStrong">{shift ? t(`shift.${shift}.name`) : code}</Txt>
    </View>
  );
}

/** The six shift types with their letters in the current language. */
export function ShiftLegend(): ReactNode {
  const { t } = useTranslation();
  return (
    <View style={{ gap: spacing[3] }}>
      <Txt variant="heading" accessibilityRole="header">
        {t("shell.shiftTypes")}
      </Txt>
      {shiftTypes.map((shift) => (
        <View key={shift} style={{ flexDirection: "row", alignItems: "center", gap: spacing[2] }}>
          <ShiftChip code={shift} />
          <Txt>{t(`shift.${shift}.name`)}</Txt>
        </View>
      ))}
    </View>
  );
}

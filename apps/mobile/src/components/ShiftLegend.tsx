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

import { theme } from "../theme";
import { type } from "../type";

const CHIP = 32;

/** 45° hatching for leave, drawn with thin rotated stripes clipped by the chip. */
function Hatch({ color }: { color: string }): ReactNode {
  return (
    <View pointerEvents="none" style={[StyleSheet.absoluteFill, styles.hatch]}>
      {Array.from({ length: 12 }, (_, i) => (
        <View key={i} style={[styles.stripe, { left: i * 5 - 14, backgroundColor: color }]} />
      ))}
    </View>
  );
}

function Chip({ shift, letter }: { shift: ShiftType; letter: string }): ReactNode {
  const c = shiftColors("light", shift);
  const leave = shift === "frei";
  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={[
        styles.chip,
        { backgroundColor: leave ? c.wash : c.solid },
        c.edge !== undefined && { borderWidth: 1, borderColor: c.edge },
        leave && { borderWidth: 1, borderColor: c.solid },
      ]}
    >
      {leave && <Hatch color={c.solid} />}
      {/* Rufbereitschaft: dotted off-site edge. Dotted means off-site; dashed means undecided. */}
      {shift === "ruf" && <View style={[styles.offsite, { borderColor: c.on }]} />}
      <Text
        style={[
          type.gridLetter,
          styles.letter,
          { color: c.on },
          leave && { backgroundColor: c.solid },
        ]}
      >
        {letter}
      </Text>
    </View>
  );
}

/** The six shift types with their letters in the current language. */
export function ShiftLegend(): ReactNode {
  const { t } = useTranslation();
  return (
    <View style={styles.section}>
      <Text accessibilityRole="header" style={[type.heading, { color: theme.ink }]}>
        {t("shell.shiftTypes")}
      </Text>
      {shiftTypes.map((shift) => (
        <View key={shift} style={styles.row}>
          <Chip shift={shift} letter={t(`shift.${shift}.letter`)} />
          <Text style={[type.body, { color: theme.ink }]}>{t(`shift.${shift}.name`)}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  section: { gap: spacing[3], marginTop: spacing[3] },
  row: { flexDirection: "row", alignItems: "center", gap: spacing[2] },
  chip: {
    width: CHIP,
    height: CHIP,
    borderRadius: radius.mark,
    alignItems: "center",
    justifyContent: "center",
    overflow: "hidden",
  },
  letter: { paddingHorizontal: 2, borderRadius: 2 },
  hatch: { overflow: "hidden" },
  stripe: {
    position: "absolute",
    top: -8,
    width: 2,
    height: CHIP + 16,
    transform: [{ rotate: "45deg" }],
  },
  offsite: {
    position: "absolute",
    top: 3,
    left: 3,
    right: 3,
    bottom: 3,
    borderWidth: 1.5,
    borderStyle: "dotted",
    borderRadius: 2,
  },
});

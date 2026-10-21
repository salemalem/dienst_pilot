import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { Async, Card, Txt } from "../components/ui";
import { Screen } from "../components/Screen";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useTheme } from "../lib/theme";

const METRICS = ["nights", "weekends", "holidays"] as const;

/** A dot on a line: where I am between the department's lowest and highest, with its mean as a tick. */
function Line({
  mine,
  mean,
  min,
  max,
  label,
}: {
  mine: number;
  mean: number;
  min: number;
  max: number;
  label: string;
}): ReactNode {
  const { theme } = useTheme();
  const span = Math.max(max - min, 1);
  const pos = (v: number): `${number}%` =>
    `${Math.min(100, Math.max(0, ((v - min) / span) * 100))}%`;
  return (
    <View
      accessible
      accessibilityRole="image"
      accessibilityLabel={label}
      style={{ height: 36, justifyContent: "center" }}
    >
      <View style={{ height: 2, backgroundColor: theme.ruleStrong }} />
      <View
        style={{
          position: "absolute",
          left: pos(mean),
          width: 2,
          height: 16,
          backgroundColor: theme.inkMuted,
          marginLeft: -1,
        }}
      />
      <View
        style={{
          position: "absolute",
          left: pos(mine),
          width: 16,
          height: 16,
          borderRadius: 8,
          backgroundColor: theme.ink,
          marginLeft: -8,
          borderWidth: 2,
          borderColor: theme.sheet,
        }}
      />
    </View>
  );
}

/** M9: my own counts against the department average only; no colleague is named or ranked. */
export function FairnessScreen(): ReactNode {
  const { t } = useTranslation();
  const fmt = useFmt();
  const q = useQuery((api) => unwrap(api.GET("/me/fairness", { params: { query: {} } })), []);
  return (
    <Screen
      title={t("m9.title")}
      status={
        q.data ? t("m9.status", { year: q.data.year, date: fmt.date(q.data.as_of) }) : undefined
      }
      back
      testID="screen-fairness"
    >
      <Async query={q}>
        {(d) => (
          <View style={{ gap: spacing[3] }}>
            {d.categories.map((c) => {
              const name = METRICS.includes(c.metric as "nights")
                ? t(`w8.metric.${c.metric as "nights"}`)
                : c.metric;
              const diff = Math.round(c.mine - c.department_mean);
              const n = Math.abs(diff);
              const word = METRICS.includes(c.metric as "nights")
                ? t(`m9.word.${c.metric as "nights"}`, { n })
                : name;
              const sentence =
                diff === 0
                  ? t("m9.equal", { name, word })
                  : diff < 0
                    ? t("m9.below", { name, word, n })
                    : t("m9.above", { name, word, n });
              return (
                <Card key={c.metric} testID={`fairness-${c.metric}`}>
                  <Txt variant="heading">{name}</Txt>
                  <Txt variant="bodyStrong" testID={`fairness-sentence-${c.metric}`}>
                    {sentence}
                  </Txt>
                  <Line
                    mine={c.mine}
                    mean={c.department_mean}
                    min={c.department_min}
                    max={c.department_max}
                    label={t("m9.lineLabel", {
                      name,
                      mine: c.mine,
                      mean: fmt.number(c.department_mean, 1),
                      min: c.department_min,
                      max: c.department_max,
                    })}
                  />
                  <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
                    <Txt variant="caption" muted>
                      {c.department_min}
                    </Txt>
                    <Txt variant="caption" muted>
                      {t("m9.figures", { mine: c.mine, mean: fmt.number(c.department_mean, 1) })}
                    </Txt>
                    <Txt variant="caption" muted>
                      {c.department_max}
                    </Txt>
                  </View>
                </Card>
              );
            })}
            <Txt variant="caption" muted>
              {t("m9.privacy")}
            </Txt>
          </View>
        )}
      </Async>
    </Screen>
  );
}

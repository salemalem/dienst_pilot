import { unwrap } from "@dienstpilot/api-client";
import { spacing } from "@dienstpilot/design-tokens";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { MoreStrip } from "../components/MoreStrip";
import { Screen } from "../components/Screen";
import { Async, Card, Txt } from "../components/ui";
import { useFmt } from "../lib/fmt";
import { useQuery } from "../lib/hooks";
import { useTheme } from "../lib/theme";

const METRICS = ["nights", "weekends", "holidays"] as const;

/** A dot on a line with its labels: the department's lowest and highest at the ends, its mean as a tick. */
function Line({
  mine,
  mean,
  min,
  max,
  label,
  meanLabel,
  mineLabel,
}: {
  mine: number;
  mean: number;
  min: number;
  max: number;
  label: string;
  meanLabel: string;
  mineLabel: string;
}): ReactNode {
  const { theme } = useTheme();
  const span = Math.max(max - min, 1);
  const pos = (v: number): `${number}%` =>
    `${Math.min(100, Math.max(0, ((v - min) / span) * 100))}%`;
  return (
    <View accessible accessibilityRole="image" accessibilityLabel={label} style={{ gap: 2 }}>
      <View style={{ height: 18 }}>
        <View
          style={{
            position: "absolute",
            left: pos(mean),
            marginLeft: -24,
            width: 48,
            alignItems: "center",
          }}
        >
          <Txt variant="caption" muted>
            {meanLabel}
          </Txt>
        </View>
      </View>
      <View style={{ height: 22, justifyContent: "center" }}>
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
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Txt variant="caption" muted>
          {min}
        </Txt>
        <Txt variant="caption" style={{ fontWeight: "700" }}>
          {mineLabel}
        </Txt>
        <Txt variant="caption" muted>
          {max}
        </Txt>
      </View>
    </View>
  );
}

/** M9: my own counts against the department average only; no colleague is named or ranked. */
export function FairnessScreen(): ReactNode {
  const { t } = useTranslation();
  const fmt = useFmt();
  const q = useQuery((api) => unwrap(api.GET("/me/fairness", { params: { query: {} } })), []);
  const sentenceOf = (metric: string, mine: number, mean: number): string => {
    const diff = Math.round(mine - mean);
    const n = Math.abs(diff);
    const name = METRICS.includes(metric as "nights")
      ? t(`w8.metric.${metric as "nights"}`)
      : metric;
    const word = METRICS.includes(metric as "nights")
      ? t(`m9.word.${metric as "nights"}`, { n })
      : name;
    return diff === 0
      ? t("m9.equal", { name, word })
      : diff < 0
        ? t("m9.below", { name, word, n })
        : t("m9.above", { name, word, n });
  };
  return (
    <Screen
      title={
        q.data?.categories[0]
          ? sentenceOf(
              q.data.categories[0].metric,
              q.data.categories[0].mine,
              q.data.categories[0].department_mean,
            )
          : t("m9.title")
      }
      status={
        q.data ? t("m9.status", { year: q.data.year, date: fmt.date(q.data.as_of) }) : undefined
      }
      strip={<MoreStrip active="fairness" />}
      testID="screen-fairness"
    >
      <Async query={q}>
        {(d) => (
          <View style={{ gap: spacing[3] }}>
            <Card style={{ padding: 0, gap: 0 }}>
              {d.categories.map((c, i) => {
                const name = METRICS.includes(c.metric as "nights")
                  ? t(`w8.metric.${c.metric as "nights"}`)
                  : c.metric;
                const diff = Math.round(c.mine - c.department_mean);
                const short =
                  diff === 0
                    ? t("m9.exactly")
                    : diff < 0
                      ? t("m9.shortBelow", { n: Math.abs(diff) })
                      : t("m9.shortAbove", { n: diff });
                return (
                  <View
                    key={c.metric}
                    testID={`fairness-${c.metric}`}
                    style={{
                      padding: spacing[4],
                      gap: spacing[2],
                      borderTopWidth: i === 0 ? 0 : 1,
                      borderTopColor: "rgba(125,135,147,0.35)",
                    }}
                  >
                    <View
                      style={{
                        flexDirection: "row",
                        justifyContent: "space-between",
                        gap: spacing[2],
                      }}
                    >
                      <Txt variant="heading">{name}</Txt>
                      <Txt variant="label" muted>
                        {short}
                      </Txt>
                    </View>
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
                      meanLabel={`Ø ${fmt.number(c.department_mean, 0)}`}
                      mineLabel={t("m9.you", { n: c.mine })}
                    />
                  </View>
                );
              })}
            </Card>
            <Txt variant="caption" muted>
              {t("m9.legend")}
            </Txt>
            <Txt variant="caption" muted>
              {t("m9.privacy")}
            </Txt>
          </View>
        )}
      </Async>
    </Screen>
  );
}

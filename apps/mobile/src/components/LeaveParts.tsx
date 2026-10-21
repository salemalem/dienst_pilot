import type { components } from "@dienstpilot/api-client";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useKeyText } from "../lib/keytext";
import { EngineBadge } from "./chrome";
import { Button, Card, Txt } from "./ui";

export type Result = {
  outcome?: string;
  reason?: string;
  trade_off?: { month?: string; weekends?: number } | null;
  explanations?: { key: string; params?: Record<string, unknown> }[];
};

/** The C1 answer for the chosen days. The trade-off is shown only when the solver found one. */
export function LeaveResult({
  outcome,
  result,
  engine,
  coveredText,
  tradeMonth,
}: {
  outcome: string;
  result: Result;
  engine: components["schemas"]["EngineLabel"];
  coveredText: string;
  tradeMonth: string;
}): ReactNode {
  const { t } = useTranslation();
  const keyText = useKeyText();
  return (
    <Card testID="leave-result">
      <EngineBadge engine={engine} />
      {outcome === "coverable" ? (
        <Txt variant="bodyStrong" testID="leave-coverable">
          {coveredText}
        </Txt>
      ) : null}
      {outcome === "coverable_with_trade_off" ? (
        <Txt variant="bodyStrong" testID="leave-trade-off">
          {t("m5.tradeOff", { month: tradeMonth })}
        </Txt>
      ) : null}
      {outcome === "not_coverable" ? (
        <>
          <Txt variant="bodyStrong" testID="leave-not-coverable">
            {t("m5.notCoverable")}
          </Txt>
          {(result.explanations ?? []).map((e, i) => (
            <Txt key={i}>{keyText(e.key, e.params ?? {})}</Txt>
          ))}
        </>
      ) : null}
      {outcome === "not_applicable" ? (
        <>
          <Txt variant="bodyStrong">{t("m5.notApplicable")}</Txt>
          {result.reason ? (
            <Txt>
              {t(`m5.reason.${result.reason as "spans_months"}`, { defaultValue: result.reason })}
            </Txt>
          ) : null}
        </>
      ) : null}
    </Card>
  );
}

/** "Mit Tausch / Ohne Tausch beantragen" only for a trade-off; otherwise one plain request button. */
export function LeaveActions({
  outcome,
  canRequest,
  busy,
  onRequest,
}: {
  outcome: string | null;
  canRequest: boolean;
  busy: boolean;
  onRequest: (withTrade: boolean) => void;
}): ReactNode {
  const { t } = useTranslation();
  if (outcome === "coverable_with_trade_off") {
    return (
      <>
        <Button
          label={t("m5.requestWithTrade")}
          kind="primary"
          busy={busy}
          onPress={() => {
            onRequest(true);
          }}
          testID="request-with-trade"
        />
        <Button
          label={t("m5.requestWithoutTrade")}
          busy={busy}
          onPress={() => {
            onRequest(false);
          }}
          testID="request-without-trade"
        />
      </>
    );
  }
  return (
    <Button
      label={t("m5.requestLeave")}
      kind="primary"
      disabled={!canRequest}
      busy={busy}
      onPress={() => {
        onRequest(false);
      }}
      testID="request-leave"
    />
  );
}

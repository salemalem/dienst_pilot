import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { View } from "react-native";

import { PERSONAS } from "../lib/config";
import { useAction } from "../lib/hooks";
import { useSession } from "../lib/session";
import { Button, Card, ErrorBox, Txt } from "./ui";

/** Demo menu: switch persona (Kaya default, Weber for M7, Alvarez for M8, Mehta and Lorenz for M6). */
export function DemoMenu(): ReactNode {
  const { t } = useTranslation();
  const { signIn, persona, me } = useSession();
  const router = useRouter();
  const sign = useAction(async (key: (typeof PERSONAS)[number]) => {
    await signIn(key);
    router.replace("/today");
  });
  return (
    <Card>
      <Txt variant="heading" accessibilityRole="header">
        {t("demo.title")}
      </Txt>
      <Txt muted>{t("demo.note")}</Txt>
      <View style={{ gap: spacing[2] }}>
        {PERSONAS.map((key) => (
          <Button
            key={key}
            label={t(`demo.persona.${key}`)}
            kind={me && key === persona ? "primary" : "secondary"}
            onPress={() => void sign.run(key)}
            busy={sign.pending}
            testID={`persona-${key}`}
            hint={t(`demo.hint.${key}`)}
          />
        ))}
      </View>
      {sign.error ? <ErrorBox error={sign.error} /> : null}
    </Card>
  );
}

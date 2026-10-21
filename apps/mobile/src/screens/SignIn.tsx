import { spacing } from "@dienstpilot/design-tokens";
import { useRouter } from "expo-router";
import { useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { ScrollView, View } from "react-native";

import { LocaleSwitch } from "../components/chrome";
import { DemoMenu } from "../components/DemoMenu";
import { Button, ErrorBox, Txt } from "../components/ui";
import { useAction } from "../lib/hooks";
import { useSession } from "../lib/session";
import { useTheme } from "../lib/theme";

/** M1: sign-in. The hospital-account button signs in as the default demo persona (Dr. Kaya). */
export function SignInScreen(): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  const { signIn, me, ready } = useSession();
  const router = useRouter();
  const [demo, setDemo] = useState(false);
  const login = useAction(async () => {
    await signIn("kaya");
    router.replace("/today");
  });
  useEffect(() => {
    if (ready && me) router.replace("/today");
  }, [ready, me, router]);
  if (ready && me) return null;
  return (
    <View style={{ flex: 1, backgroundColor: theme.paper }} testID="screen-sign-in">
      <ScrollView
        tabIndex={0}
        contentContainerStyle={{ padding: spacing[4], gap: spacing[4], paddingBottom: spacing[6] }}
      >
        <View style={{ gap: spacing[1] }}>
          <Txt variant="display" accessibilityRole="header">
            {t("app.name")}
          </Txt>
          <Txt muted>{t("app.department")}</Txt>
        </View>
        <Txt>{t("m1.intro")}</Txt>
        <LocaleSwitch />
        {login.error ? <ErrorBox error={login.error} /> : null}
        {demo ? <DemoMenu /> : null}
      </ScrollView>
      <View
        style={{
          padding: spacing[4],
          gap: spacing[2],
          backgroundColor: theme.sheet,
          borderTopWidth: 1,
          borderTopColor: theme.rule,
        }}
      >
        <Button
          label={t("m1.signIn")}
          kind="primary"
          onPress={() => void login.run()}
          busy={login.pending}
          testID="sign-in"
        />
        <Button
          label={demo ? t("m1.hideDemo") : t("m1.demo")}
          kind="quiet"
          onPress={() => {
            setDemo((v) => !v);
          }}
          testID="demo-toggle"
        />
      </View>
    </View>
  );
}

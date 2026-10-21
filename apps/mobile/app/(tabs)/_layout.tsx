import { Redirect, Tabs } from "expo-router";
import { Bell, CalendarDays, House, Settings, type LucideIcon } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useSession } from "../../src/lib/session";
import { useTheme } from "../../src/lib/theme";
import { type } from "../../src/type";

const VISIBLE: { name: string; key: string; Icon: LucideIcon }[] = [
  { name: "today", key: "today", Icon: House },
  { name: "roster", key: "roster", Icon: CalendarDays },
  { name: "notifications", key: "notifications", Icon: Bell },
  { name: "settings", key: "settings", Icon: Settings },
];
/** Bottom tabs sit in the thumb zone; the other screens (wishes, leave, ...) are stacked above them. */
export default function TabsLayout(): ReactNode {
  const { me, ready } = useSession();
  const { t } = useTranslation();
  const { theme } = useTheme();
  if (!ready) return null;
  if (!me) return <Redirect href="/sign-in" />;
  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: theme.action,
        tabBarInactiveTintColor: theme.inkMuted,
        tabBarStyle: { backgroundColor: theme.sheet, borderTopColor: theme.rule, height: 64 },
        tabBarLabelStyle: type.caption,
        sceneStyle: { backgroundColor: theme.paper },
      }}
    >
      {VISIBLE.map(({ name, key, Icon }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title: t(`tabs.${key}`),
            tabBarAccessibilityLabel: t(`tabs.${key}`),
            tabBarButtonTestID: `tab-${name}`,
            tabBarIcon: ({ color }) => <Icon size={22} color={color} strokeWidth={1.75} />,
          }}
        />
      ))}
    </Tabs>
  );
}

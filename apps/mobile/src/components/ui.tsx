import { radius, size, spacing } from "@dienstpilot/design-tokens";
import { CircleAlert } from "lucide-react-native";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import {
  ActivityIndicator,
  Pressable,
  Text,
  TextInput,
  View,
  type StyleProp,
  type TextProps,
  type TextStyle,
  type ViewStyle,
} from "react-native";

import { useTheme } from "../lib/theme";
import { type } from "../type";

/** Minimum touch target in points (UI_SPEC: at least 44; the design system uses 48). */
export const TOUCH_MIN = size.touchMin;

type Variant = keyof typeof type;

/** Text in a design-system style, in ink (or muted). */
export function Txt({
  variant = "body",
  muted,
  color,
  style,
  ...rest
}: TextProps & {
  variant?: Variant;
  muted?: boolean;
  color?: string;
  style?: StyleProp<TextStyle>;
}): ReactNode {
  const { theme } = useTheme();
  return (
    <Text
      {...rest}
      style={[type[variant], { color: color ?? (muted ? theme.inkMuted : theme.ink) }, style]}
    />
  );
}

type ButtonKind = "primary" | "secondary" | "quiet" | "pencil";

/** A button that names what happens. At least 48 pt tall; `label` is also its accessible name. */
export function Button({
  label,
  onPress,
  kind = "secondary",
  disabled,
  busy,
  icon,
  hint,
  testID,
  style,
}: {
  label: string;
  onPress: () => void;
  kind?: ButtonKind;
  disabled?: boolean;
  busy?: boolean;
  icon?: ReactNode;
  hint?: string;
  testID?: string;
  style?: StyleProp<ViewStyle>;
}): ReactNode {
  const { theme } = useTheme();
  const off = disabled === true || busy === true;
  const bg = kind === "primary" ? theme.ink : kind === "pencil" ? "transparent" : theme.sheet;
  const fg = kind === "primary" ? theme.onInk : kind === "pencil" ? theme.pencil : theme.ink;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={hint}
      accessibilityState={{ disabled: off, busy: busy === true }}
      disabled={off}
      onPress={onPress}
      testID={testID}
      style={({ pressed }) => [
        {
          minHeight: TOUCH_MIN,
          minWidth: TOUCH_MIN,
          paddingHorizontal: spacing[4],
          borderRadius: radius.control,
          flexDirection: "row",
          alignItems: "center",
          justifyContent: "center",
          gap: spacing[2],
          backgroundColor: off
            ? theme.sheetSunk
            : pressed
              ? kind === "primary"
                ? theme.inkMuted
                : theme.sheetSunk
              : bg,
          borderWidth: kind === "quiet" ? 0 : kind === "pencil" ? 1.5 : 1,
          borderStyle: kind === "pencil" ? "dashed" : "solid",
          borderColor: off
            ? theme.rule
            : kind === "primary"
              ? theme.ink
              : kind === "pencil"
                ? theme.pencil
                : theme.ruleStrong,
        },
        style,
      ]}
    >
      {busy === true ? <ActivityIndicator color={fg} /> : icon}
      <Text style={[type.label, { color: off ? theme.inkMuted : fg }]}>{label}</Text>
    </Pressable>
  );
}

/** A sheet-coloured block with a hairline: cards carry no shadow (design system). */
export function Card({
  children,
  style,
  dashed,
  testID,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  dashed?: boolean;
  testID?: string;
}): ReactNode {
  const { theme } = useTheme();
  return (
    <View
      testID={testID}
      style={[
        {
          backgroundColor: dashed === true ? theme.pencilWash : theme.sheet,
          borderWidth: dashed === true ? 1.5 : 1,
          borderStyle: dashed === true ? "dashed" : "solid",
          borderColor: dashed === true ? theme.pencil : theme.rule,
          borderRadius: dashed === true ? radius.panel : 0,
          padding: spacing[4],
          gap: spacing[3],
        },
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function Loading(): ReactNode {
  const { t } = useTranslation();
  return (
    <Txt muted accessibilityRole="progressbar">
      {t("common.loading")}
    </Txt>
  );
}

/** What is wrong and how to fix it; never an apology. */
export function ErrorBox({ error, onRetry }: { error: Error; onRetry?: () => void }): ReactNode {
  const { t } = useTranslation();
  const { theme } = useTheme();
  return (
    <View
      accessibilityRole="alert"
      style={{
        backgroundColor: theme.alertWash,
        borderRadius: radius.control,
        padding: spacing[3],
        gap: spacing[2],
      }}
    >
      <View style={{ flexDirection: "row", gap: spacing[2], alignItems: "flex-start" }}>
        <CircleAlert size={20} color={theme.alert} strokeWidth={1.75} />
        <View style={{ flex: 1 }}>
          <Txt variant="bodyStrong" color={theme.alert}>
            {t("common.error.title")}
          </Txt>
          <Txt>{t("common.error.fix")}</Txt>
          <Txt variant="caption" muted>
            {error.message}
          </Txt>
        </View>
      </View>
      {onRetry ? <Button label={t("common.retry")} onPress={onRetry} /> : null}
    </View>
  );
}

/** Loading, error or the data. */
export function Async<T>({
  query,
  children,
}: {
  query: { data: T | null; error: Error | null; reload: () => void };
  children: (data: T) => ReactNode;
}): ReactNode {
  if (query.data) return children(query.data);
  if (query.error) return <ErrorBox error={query.error} onRetry={query.reload} />;
  return <Loading />;
}

/** A labelled on/off switch row: the whole row is the target. */
export function ToggleRow({
  label,
  value,
  onChange,
  hint,
  testID,
}: {
  label: string;
  value: boolean;
  onChange: (value: boolean) => void;
  hint?: string;
  testID?: string;
}): ReactNode {
  const { theme } = useTheme();
  return (
    <Pressable
      accessibilityRole="switch"
      accessibilityLabel={label}
      accessibilityState={{ checked: value }}
      aria-checked={value}
      onPress={() => {
        onChange(!value);
      }}
      testID={testID}
      style={{
        minHeight: TOUCH_MIN,
        flexDirection: "row",
        alignItems: "center",
        justifyContent: "space-between",
        gap: spacing[3],
      }}
    >
      <View style={{ flex: 1 }}>
        <Txt>{label}</Txt>
        {hint ? (
          <Txt variant="caption" muted>
            {hint}
          </Txt>
        ) : null}
      </View>
      <View
        style={{
          width: 48,
          height: 28,
          borderRadius: 14,
          borderWidth: 1.5,
          borderColor: value ? theme.ink : theme.ruleStrong,
          backgroundColor: value ? theme.ink : theme.sheet,
          justifyContent: "center",
          paddingHorizontal: 3,
          alignItems: value ? "flex-end" : "flex-start",
        }}
      >
        <View
          style={{
            width: 18,
            height: 18,
            borderRadius: 9,
            backgroundColor: value ? theme.onInk : theme.inkMuted,
          }}
        />
      </View>
    </Pressable>
  );
}

/** A group of options, one selected (language, theme, shift type). */
export function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
  testID,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  testID?: string;
}): ReactNode {
  const { theme } = useTheme();
  return (
    <View
      accessibilityRole="radiogroup"
      accessibilityLabel={label}
      testID={testID}
      style={{
        flexDirection: "row",
        borderWidth: 1,
        borderColor: theme.ruleStrong,
        borderRadius: radius.control,
        padding: 2,
        gap: 2,
        backgroundColor: theme.sheet,
      }}
    >
      {options.map((o) => {
        const on = o.value === value;
        return (
          <Pressable
            key={o.value}
            accessibilityRole="radio"
            accessibilityLabel={o.label}
            accessibilityState={{ selected: on, checked: on }}
            aria-checked={on}
            onPress={() => {
              onChange(o.value);
            }}
            testID={testID ? `${testID}-${o.value}` : undefined}
            style={{
              flex: 1,
              minHeight: TOUCH_MIN,
              alignItems: "center",
              justifyContent: "center",
              borderRadius: 4,
              backgroundColor: on ? theme.action : "transparent",
              paddingHorizontal: spacing[2],
            }}
          >
            <Text style={[type.label, { color: on ? theme.onAction : theme.ink }]}>{o.label}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

/** A labelled text input. */
export function Field({
  label,
  value,
  onChangeText,
  placeholder,
  multiline,
  testID,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  placeholder?: string;
  multiline?: boolean;
  testID?: string;
}): ReactNode {
  const { theme } = useTheme();
  return (
    <View style={{ gap: spacing[1] }}>
      <Txt variant="label">{label}</Txt>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor={theme.inkMuted}
        multiline={multiline}
        testID={testID}
        style={[
          type.body,
          {
            minHeight: multiline === true ? 88 : TOUCH_MIN,
            color: theme.ink,
            backgroundColor: theme.sheet,
            borderWidth: 1,
            borderColor: theme.ruleStrong,
            borderRadius: radius.control,
            paddingHorizontal: spacing[3],
            paddingVertical: spacing[2],
            textAlignVertical: multiline === true ? "top" : "center",
          },
        ]}
      />
    </View>
  );
}

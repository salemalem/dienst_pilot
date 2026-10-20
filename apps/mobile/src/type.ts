import { nativeTypography, typography as exact, type TypeName } from "@dienstpilot/design-tokens";
import { Platform, type TextStyle } from "react-native";

// Web renders the design's exact variable-font weights (react-native-web passes them to CSS,
// where 650 is valid; React Native's types only list steps of 100, hence the cast). iOS and
// Android get weights rounded to the nearest step.
export const type: Record<TypeName, TextStyle> =
  Platform.OS === "web" ? (exact as unknown as Record<TypeName, TextStyle>) : nativeTypography;

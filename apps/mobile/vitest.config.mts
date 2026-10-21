import { defineConfig } from "vitest/config";

// Components render with react-native-web in jsdom: the same code the Expo web build runs.
export default defineConfig({
  resolve: { alias: { "react-native": "react-native-web" } },
  test: { include: ["tests/**/*.test.{ts,tsx}"], environment: "jsdom" },
});

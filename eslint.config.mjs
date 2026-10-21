import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: [
      "**/node_modules/**",
      "**/dist/**",
      "**/dist-e2e/**",
      "**/.next/**",
      "**/.expo/**",
      "**/next-env.d.ts",
      "packages/design-tokens/src/generated/**",
      "packages/api-client/src/schema.ts",
      "design/**",
      ".venv/**",
    ],
  },
  js.configs.recommended,
  ...tseslint.configs.strict,
  {
    languageOptions: { globals: { ...globals.browser, ...globals.node } },
  },
  {
    files: ["apps/mobile/metro.config.js"],
    languageOptions: { sourceType: "commonjs" },
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
  {
    // Metro needs require() to bundle the font asset.
    files: ["apps/mobile/app/_layout.tsx"],
    rules: { "@typescript-eslint/no-require-imports": "off" },
  },
);

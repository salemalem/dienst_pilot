import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

const config: NextConfig = {
  // Do not generate AGENTS.md; this repo documents its conventions in CLAUDE.md.
  agentRules: false,
  transpilePackages: ["@dienstpilot/i18n", "@dienstpilot/design-tokens"],
};

export default withNextIntl(config);

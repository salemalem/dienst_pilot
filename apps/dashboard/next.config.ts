import type { NextConfig } from "next";
import createNextIntlPlugin from "next-intl/plugin";

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

/** The backend the browser reaches through the same-origin `/api` proxy (no CORS needed). */
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const config: NextConfig = {
  // Do not generate AGENTS.md; this repo documents its conventions in CLAUDE.md.
  agentRules: false,
  transpilePackages: ["@dienstpilot/i18n", "@dienstpilot/design-tokens", "@dienstpilot/api-client"],
  rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default withNextIntl(config);

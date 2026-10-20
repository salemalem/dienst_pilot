# ADR-006: Monorepo tooling

- Status: Accepted
- Date: 2026-10-20
- Phase: 1 (scaffold)

## Context

DienstPilot is one repository with a Python backend and two TypeScript apps (Next.js dashboard, Expo staff app) that share a message catalog, design tokens and a generated API client. The stack in CLAUDE.md fixes the frameworks but not the workspace tooling, the Tailwind version, or how one catalog serves next-intl and i18next.

## Decision

1. **Python: a uv workspace.** The root `pyproject.toml` holds the tool config (ruff, mypy `--strict`, pytest, import-linter) and the dev dependency group; `backend/` is the only member for now. `uv.lock` pins everything. Python 3.12 is installed by uv, not taken from the system.
2. **TypeScript: a pnpm workspace** (`apps/*`, `packages/*`) with `nodeLinker: hoisted`, which Metro needs. Workspace packages ship TypeScript source; Next.js transpiles them (`transpilePackages`) and Metro reads them directly. No separate build step except the design tokens.
3. **Supply-chain guard.** pnpm's `minimumReleaseAge` is one day and dependency install scripts are off (`allowBuilds`). A package newer than a day is not installed; the version floor is lowered instead of excluding it from the rule.
4. **Tailwind v4.** The theme is generated from the tokens as an `@theme inline` block that points at the CSS variables, and the default palette is removed, so only token colours exist and the `dp-dark` class switches utilities too.
5. **One ICU catalog.** `packages/i18n/de.json` and `en.json` are written in ICU message syntax. next-intl reads ICU natively; the Expo app reads the same files through `i18next-icu`.
6. **Design tokens are generated, never copied.** `packages/design-tokens/scripts/build.ts` reads `design/reference/design-system/project/tokens.json` and writes CSS variables, the Tailwind theme and a typed native module. A test asserts that the generated variables equal the design system's own stylesheet. Native text styles round the design's variable-font weights to steps of 100, because iOS and Android render only those.
7. **Infrastructure for development.** Postgres, Redis and the API run in Docker Compose; the two apps run on the host, where Next.js and Metro hot reload work reliably.

## Consequences

- One command per concern (`make dev`, `make test`, `make lint`) works across both languages.
- Changing a token means changing `tokens.json` in the design system and rebuilding; the comparison test fails if the generator and the design system drift apart.
- The design system ships only woff2 fonts. iOS and Android cannot load woff2, so the native app uses the system font until TTF files are added; Expo web uses the real face.
- Releases from the last 24 hours cannot be installed without a deliberate policy change.

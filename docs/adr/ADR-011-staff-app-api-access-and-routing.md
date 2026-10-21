# ADR-011: How the staff app reaches the API, how it routes, and where its theme comes from

- Status: Accepted
- Date: 2026-10-21
- Phase: 5 (staff app)

## Context

The staff app (Expo SDK 58, React Native 0.88) runs on iOS, Android and the web (Expo web, used for the e2e tests and for the Phase 6 screenshots). The backend had no CORS configuration, and the dashboard's same-origin proxy (ADR-010) does not exist for an Expo app: `expo export` produces static files, and Metro's dev server has no proxy for the web build.

## Decision

1. **API access.**
   - **Native** (iOS simulator, Android emulator, devices): no browser, so no CORS. The app calls `EXPO_PUBLIC_API_URL` (default `http://localhost:8000`; the iOS simulator reaches the host's localhost, the Android emulator needs `http://10.0.2.2:8000`).
   - **Expo web**: the browser calls the same URL, so the API answers CORS preflights **only when `DEMO_MODE` is on**, and only for the origins in `CORS_ORIGINS` (default `http://localhost:8081`, the Expo dev server, and `http://localhost:8083`, the e2e static server). Methods and headers are listed (`authorization`, `content-type`), credentials are off (bearer tokens, no cookies). Without `DEMO_MODE` the API sends no CORS headers at all. Tests: `backend/tests/test_cors.py`.
   - Rejected: a wildcard origin (any page could call the API with a stolen token), a dev proxy (none for the exported web build), and running the app through the dashboard's origin (two apps, two origins).
2. **Routing: expo-router.** `expo-router@58.0.18` resolves under the 7-day release-age rule and builds for web and native. Every screen has its own URL (`/today`, `/roster`, `/wishes`, `/leave`, `/swap`, `/sick`, `/cover`, `/fairness`, `/hours`, `/notifications`, `/settings`, `/sign-in`), so Phase 6 can open each one directly for screenshots. The four tab screens (M2, M3, M11, M12) sit in a bottom tab bar in the thumb zone; the other screens are stacked above it with a back button, and the Android hardware back button pops the stack (expo-router/React Navigation). A route guard sends a signed-out visitor to `/sign-in`.
3. **Session.** Demo sign-in as Kaya by default; the demo menu (M1 and M12) signs in as Weber (M7), Alvarez (M8), Mehta (M6) or Lorenz (M6). The token and the language live in `localStorage` on web; on native they stay in memory (a demo sign-in is one tap, so no storage dependency is added). A 401 (the Administrator moved the demo clock) signs in again once.
4. **Theme from the demo clock.** Dark between 20:00 and 07:00 Europe/Berlin, decided from `GET /clock` (public, re-read every 30 seconds), never from the device clock. M12 offers "Automatisch / Hell / Dunkel"; the choice is saved with `PUT /me/settings` (`theme`), so it follows the person to another device.
5. **AI labels.** Every output of C3 to C8 (the C4 preference chips, the C7 reading of free text, the C6 instant hint) is drawn as a pencil suggestion with "Warum? / Why?" and the same stand-in label as the dashboard, built from the `engine` field the API sends. M8 shows no ranking text.
6. **Tests.** Component tests run the same components with `react-native-web` in jsdom (vitest). Playwright runs the exported web build on a 390-pt phone viewport against the real API, once per language (`pnpm e2e` = German, then English, each on a freshly seeded database): the three PROCESS.md situations, the dark-mode rules, privacy, axe (WCAG A/AA) on every screen and theme, and 44-pt touch targets.

## Consequences

- The web build embeds `EXPO_PUBLIC_API_URL` at export time (the e2e build uses `http://localhost:8100`).
- `DEMO_MODE` now also means "browsers on the dev origins may call the API". It is a demo-only switch, off in anything that is not the demo stack.
- Native storage is intentionally absent: a restarted native app signs in again.

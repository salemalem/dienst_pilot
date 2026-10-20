# Design reference (from Claude Design)

Exported 20 October 2026. Visual source of truth for apps/mobile and apps/dashboard.

## Contents
- html/dashboard/planer-dashboard.html: planner dashboard W1–W13 + W7b (German and English pages)
- html/mobile/staff-app.html: staff app M1–M12 (German, plus English and dark examples)
- handoff/dashboard/, handoff/mobile/: Claude Code handoff files, downloaded from the links below
- screens/: images per screen, named by UI_SPEC ID (if present)

## Handoff links (from Claude Design)
- Dashboard: https://claude.ai/code/artifact/a8cf0be9-493e-4ef8-92c2-84b4da547300
- Staff app: https://claude.ai/code/artifact/aae3e938-97cf-4bc2-8b63-499c3d919d11

## Rules
- Token source of truth: design-system/ (downloaded from the Design system link). The copies under handoff/*/project/ds/ are older snapshots; don't use them for tokens.
- Shift types and times: docs/UI_SPEC.md §5 is the source of truth. The mobile mockups predate Rufbereitschaft, so their shift times are outdated: Bereitschaftsdienst is 08:00–08:00 (+1 day); 16:00–07:30 is Rufbereitschaft.
- Take tokens, layout and component styling from here; build in the stack from CLAUDE.md. Do not copy prototype code wholesale.
- All numbers in the mockups (hours, fairness, overtime, costs) are illustrative. The coded apps must get every number from the backend.
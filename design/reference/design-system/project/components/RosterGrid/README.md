The roster grid (W4 and M3), modelled on the printed Dienstplan in the doctors' room and the one memorable element of DienstPilot.

**Consumer provides:**
- `days`: `[{ d, wd, weekend?, today? }]`
- `rows`: `[{ name, role?, hours?, cells: [cellOpts | letter | null] }]`
- optional `coverage`: one entry per day, either a short string or `{ gap: "S" }`
- `lang`, `caption` (the accessible name of the table), `interactive`, `legend` (default `true`)

**Anatomy:**
- **Sheet:** `sheet` + `shadow-sheet`, `radius-sheet` 0.
- **Header:** `sheet-sunk` and `num-small`. Each day shows the weekday and the day number. Weekend headers are in `ink`. Today's header is solid `action`.
- **Name column:** sticky, `rowhead-w`, `grid-name` + role in caption, separated by `rule-strong`.
- **Day cells:** `cell-w` × `cell-h`. Weekend columns are shaded `sheet-sunk`.
- **Hours column:** `num-small`, right-aligned.
- **Coverage footer:** "Besetzung / Coverage", where gaps appear.
- **Legend:** always under the grid.

**Rules**
- Keep the grid on its sheet. Never put it in a rounded card with a shadow.
- Do not add colour beyond the six shift types, ballpoint blue for today/selection, and red pen for violations.
- Show a full month at 1440px (31 × 36px + names). On mobile (M3) use the month view with chips and the list below it. Do not shrink the grid below `cell-w`.
- Rule messages for the selected violation appear beside the grid as `RuleMessage`. Gap suggestions appear as `Suggestion`, never as a silent fill.

The shift-type mark: a solid colour square with the shift letter, and the only place a shift's solid colour appears outside the grid's marker underline.

**Use for:** legends, the "next shift" card (M2), lists of shifts, notifications, variant summaries. **Not** for grid cells (use `RosterCell`).

**Consumer provides:** `shift` (`"frueh" | "spaet" | "nacht" | "bereitschaft" | "ruf" | "frei"`, or a letter in either language), `lang` (`"de"` default, `"en"`), optional `size` (`"sm"` 20px, default 24px, `"lg"` 32px), optional `label` (`true` for the shift name, or a string) and `time` (`"07:30–16:00"`, rendered in `num-small`).

**Rules**
- Always colour **and** letter. The letter follows the language: F/S/N/B/R/U in German, E/L/N/O/H/V in English. The colour never changes with language.
- Leave (`frei`) is always hatched; night always carries `shift-nacht-edge` (it keeps the navy chip visible on the dark sheet).
- Rufbereitschaft (`ruf`, R / H) always carries a dotted inner edge in `on-shift-ruf`: the off-site mark. Dotted means off-site; dashed is reserved for undecided things (pencil, gap).
- A chip without a visible label gets `role="img"` and the shift name as its accessible name. Don't add your own tooltip.
- Never recolour a chip to express status (approved, pending). Status belongs to the cell annotations or to text.

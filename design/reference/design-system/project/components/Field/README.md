A labelled text input, select or free-text area with optional hint and error.

**Consumer provides:** `label` (always visible, never a placeholder substitute), optional `value`, `placeholder`, `hint`, `error` (what is wrong) **with** `fix` (how to correct it), `options` (renders a select with a Lucide `chevron-down`), `multiline` (renders a textarea), `numeric` (tabular figures and numeric keyboard), `type`, `id`.

**Rules**
- Input text is 16px so iOS does not zoom.
- A hint states context ("Zwei andere Kolleg:innen haben überlappende Tage beantragt.").
- **Every error = red + icon + fix.** It shows a 2px `alert` border, then a line in `alert`: the Lucide `circle-alert` icon (16px), the problem in bold, then the fix.
  - "**25:00 ist keine gültige Uhrzeit.** Geben Sie eine Zeit von 00:00 bis 23:59 ein, z. B. 07:30."
  - "**Time format not recognised.** Use hours and minutes with a colon, e.g. 07:30."
  - Never write only "Ungültige Eingabe" or "Pflichtfeld". If `fix` is missing, the bundle warns in the console.
- Red covers input errors as well as rule violations, because both mean a rule is broken. The icon and the wording carry the meaning, so the error never relies on colour.
- Hint and error are linked by `aria-describedby`, and an invalid field sets `aria-invalid="true"`.
- The free-text wish box (M4) is followed by the "Wir haben verstanden: / Here's what we understood:" confirmation, drawn as a `Suggestion` because it is the AI's reading.

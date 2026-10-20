DienstPilot is AI-assisted duty scheduling for German hospital departments. The real object in this world is the printed **Dienstplan** pinned to the wall of the doctors' room: a dense grid of names and days with shift letters, marked up by hand. DienstPilot is that grid made alive and calm. The **roster grid** is the one memorable element. Everything around it stays quiet.

Two surfaces use this system: the **staff app** (mobile, one-handed, between patients, often at 03:00) and the **planner dashboard** (web, at a desk). German is the default, English the second language; every screen exists in both.

## Principles

1. **Status before detail.** The first line of every screen answers "what do I need to know or do now?" Set it in `title` (mobile) or `display` (dashboard), then detail in `body`.
2. **The AI only proposes.** Every AI output is drawn in *pencil* (`pencil`, `pencil-wash`, dashed) with the label "Vorschlag / Suggestion" and a "Warum? / Why?" affordance. It becomes ink only when a person accepts it. Never show an AI output in ink, and never put a publish action on an AI surface.
3. **Three pens on one sheet.**
   - **Ink** (`ink`) is decided: published shifts, text, the primary button.
   - **Ballpoint blue** (`action`) is a human action in progress: links, selection, focus, today.
   - **Pencil** (`pencil`) is the AI's proposal.
   - **Red pen** (`alert`) is a rule violation, and nothing else.
4. **Buttons name what happens**, and the confirmation repeats the verb. "Freigeben und veröffentlichen" is confirmed with "Veröffentlicht"; "Approve and publish" with "Published".
5. **Every error has three parts: red, an icon, and the fix.** It is set in `alert` with the Lucide `circle-alert` icon. It states what is wrong ("Ruhezeit von 11 Stunden nicht eingehalten (Dr. Lorenz, 14./15.12.)") and then how to fix it ("Tauschen Sie den Frühdienst am 15.12. oder verschieben Sie den Spätdienst."). No apologies, no "Oops", no error codes.
6. **Calm around the grid.** No illustrations, no gradients, no decorative colour. Colour is reserved for shift types, and the shift types live in the grid and in chips.
7. **Mobile: thumb zone, one hand.** Primary actions sit at the bottom, full width, `touch-min` (48px) tall (`Button size="lg" block`).

## Content

- **Voice:** a competent senior colleague. Short, factual, polite. In German use *Sie*, with gender-inclusive forms using the colon ("Kolleg:innen"). In English use *you*. No exclamation marks, no emoji.
- **Numbers carry the message:** "21 von 28 haben geantwortet", "Sie liegen bei Nachtdiensten 2 unter dem Durchschnitt". Times are 24-hour with an en dash: `07:30–16:00`. Dates are German style (`23.12.`) in DE and `23 Dec` in EN.
- **Date spans.** Two consecutive days, such as a night across midnight or a rest period between two shifts, are written with a slash: `14./15.12.` in DE and `14/15 Dec` in EN. A longer range uses an en dash: `14.–27.07.` / `14–27 Jul`. Never use an arrow.
- **Errors and validation.** Every form or rule error shows the `circle-alert` icon and two sentences in `alert`. The first, in bold, says what is wrong ("25:00 ist keine gültige Uhrzeit."). The second says what to do ("Geben Sie eine Zeit von 00:00 bis 23:59 ein, z. B. 07:30."). A message that only names the problem is not finished. `Field` takes `error` and `fix`, `RuleMessage` takes `title` and `detail`, and both warn in the console when the fix is missing.
- **Never apologise and never blame.** Not "Leider ist ein Fehler aufgetreten" but "Antwort bis 06:57".
- **Sick reports never ask for a diagnosis.** The copy ends warmly: "Gute Besserung." / "Get well soon."
- **Environment:** every screen shows `EnvBadge`: "Demo-Umgebung, synthetische Daten" / "Demo environment, synthetic data".

## Using tokens

Tokens compile to CSS custom properties (`var(--ink)`) and type classes (`.body`, `.num-time` …). Never paste raw hex values. The first theme, `light`, is the fallback. `dark` is first-class and turns on automatically between 20:00 and 07:00 on mobile.

**The official stylesheet: `css/dienstpilot-tokens.css`.** Every design project and both apps' web code load this one file instead of copying values:

- **Contents:** every token as a custom property (`--ink`, `--space-4`, `--radius-control`, `--shadow-raise`, `--font-sans`), each type style as a font shorthand (`font: var(--type-body)`) and as a class (`.body`, `.num-time` …, numeric styles with tabular figures), and the `@font-face` rules for the files in `fonts/` (keep `css/` and `fonts/` side by side).
- **Dark theme is one class.** Light is the default on `:root`. Add `dp-dark` to `<html>` to switch everything: `document.documentElement.classList.toggle("dp-dark", isNight)`. In the staff app, `isNight` is true from 20:00 to 07:00 unless the person picked "Hell" or "Dunkel". The class also works on a single container (for example a dark preview inside a light page): everything inside switches, aliases such as `--focus` included.
- **Generated, never edited.** The file is built from `tokens.json` by `css/build-tokens-css.mjs` (Node 18+, no dependencies): `node css/build-tokens-css.mjs`. After any token change, rerun it and commit both files together. The file's header names the tokens version it was built from.
- **React Native** cannot read CSS. The staff app reads `tokens.json` directly and applies the same rule: light values by default, dark values when the night switch is on.
- **Same output as the design-system page.** Rendered with `components/bundle.css`, it gives pixel-identical results to the page's own token CSS in both themes (checked on the roster grid, suggestion and form previews).

**Surfaces.** The page is `paper`. The roster and every card, input and dialog sit on `sheet`. Weekend columns and table headers use `sheet-sunk`. Text is `ink`, secondary text `ink-muted`.

**Lines.** `rule` is a decorative hairline (grid ruling, dividers). `rule-strong` is any border that defines a control (inputs, checkboxes, secondary buttons) and the edge of the name column. It holds 3:1 in both themes.

**Shift types.** Each type has four tokens: `shift-<type>` (solid, used for chips, the legend and the marker underline), `on-shift-<type>` (letter on the solid), `shift-<type>-wash` (grid-cell background) and `shift-<type>-ink` (letter on the wash). The types are `frueh`, `spaet`, `nacht`, `bereitschaft`, `ruf` and `frei`. Leave (`frei`) is always hatched at 45°. Night also has `shift-nacht-edge`, which keeps the navy chip visible on the dark sheet. Rufbereitschaft (`ruf`) always carries the **dotted off-site mark**: a dotted inner edge on the chip (`on-shift-ruf`) and a dotted marker underline in grid cells (`shift-ruf-ink`), because the doctor is on call from home, not in the building.

| Type | DE | EN | Token |
|---|---|---|---|
| Frühdienst / Early | **F** | **E** | `shift-frueh` |
| Spätdienst / Late | **S** | **L** | `shift-spaet` |
| Nachtdienst / Night | **N** | **N** | `shift-nacht` |
| Bereitschaft / On-call | **B** | **O** | `shift-bereitschaft` |
| Rufbereitschaft / On-call from home | **R** | **H** | `shift-ruf` + dotted off-site mark |
| Urlaub / Leave | **U** | **V** | `shift-frei` + hatching |

Letters switch with the language; the colours don't.

**Type.** Use one family only: Atkinson Hyperlegible Next, a variable font (200–800), shipped as files in `fonts/` (Latin subset; OFL licence in `fonts/OFL.txt`). It was designed for low-vision readers, and that is the point here: tired eyes at 03:00. Use these styles:

- Running text: `body` (16px; the mobile floor), `body-strong`, `label` (14px), `caption` (13px; the smallest allowed).
- Headings: `heading`, `title`, `display` (dashboard page titles only).
- Anything numeric, such as times, hours, day numbers, percentages and deadlines: `num-time`, `num-small`, `num-figure`. These classes switch on the font's real tabular figures (`tnum`), so columns of times and hours line up.
- In the grid: `grid-letter` for shift letters, `grid-name` for physician names.

The font's slashed zero is intentional (it tells 0 from O). **Copy uses only glyphs in the shipped Latin subset:** letters with German accents and ß, digits, basic punctuation, the en dash, typographic quotes and the euro sign. No arrows, check marks, stars or other symbols in text. Wherever a symbol is needed, use a Lucide icon (see Iconography).

**Spacing.** The base unit is 4px: `space-1` … `space-7`. The mobile gutter is `space-4`. Dialog padding is `space-5`, and dashboard sections are `space-6` apart. Grid geometry is fixed in `size`: `cell-w` 36, `cell-h` 34, `rowhead-w` 184. Controls use `control-h` 40, and mobile touch targets `touch-min` 48.

**Radius follows hierarchy:**

- `radius-sheet` 0: the roster, cells and tables, square like paper.
- `radius-mark` 3: chips, badges, checkboxes.
- `radius-control` 6: buttons, inputs, segmented controls.
- `radius-panel` 10: floating things only (dialogs, popovers, bottom sheets, the suggestion card).

**Shadows: only what leaves the paper casts a shadow.**

- `shadow-sheet`: the roster sheet on `paper`, barely lifted.
- `shadow-raise`: popovers, menus, a dragged cell.
- `shadow-overlay`: dialogs and bottom sheets, with a scrim.

Cards inside a page get no shadow. Separate them with `rule` and space.

## The roster grid

The grid recreates the paper plan, with the following rules:

- Physicians are rows and days are columns, on a `sheet` with `rule` hairlines. Weekend columns are shaded `sheet-sunk`. Today is a solid `action` header with thin `action` lines down the column.
- An assigned cell is a highlighter wash (`shift-<type>-wash`) with a heavy letter (`grid-letter`, `shift-<type>-ink`) and a short marker underline in the solid colour. Do not fill cells with the solid colour: a month of solid fills is a wall of noise.
- Hand markup is shape-coded and never relies on colour:
  - **Wish granted:** Lucide `check` at 12px in the top-right corner, `ink`.
  - **Wish missed:** Lucide `circle-slash-2` at 12px in the top-right corner, `ink-muted`.
  - **Rule violation:** a red-pen ellipse around the letter plus a Lucide `circle-alert` badge (14px) in the top-left corner, `alert` on a `sheet` disc.
  - **Gap** (demand without a doctor; shown in the "Besetzung / Coverage" row and in day views): a dashed `ink` box with the missing shift as a hollow letter.
  - **Leave:** 45° hatching with U / V on a clear patch.
  - **Suggested:** an AI proposal in pencil. Dashed `pencil` border on `pencil-wash`, italic letter.
  - **Off-site (Rufbereitschaft):** the marker underline is dotted instead of solid. **Dotted means off-site; dashed means undecided** (pencil, gap). Never swap them.
- A fully staffed day shows Lucide `check` in the coverage row. A gap shows the gap cell.
- Every cell has a complete accessible name ("Dr. Lea Lorenz, 15.12.: Früh, Regelverstoß: Ruhezeit 11 h, 14./15.12."). The legend is always visible under the grid.
- The last column holds hour totals in `num-small`. Rufbereitschaft adds nothing to it by itself: only time actually called in counts as working time, and it is added when recorded. The name column stays sticky when scrolling horizontally.

## Accessibility

- **Shift types never rely on colour alone.** Every shift is colour plus letter, everywhere, and leave also has hatching. Annotations are shapes: Lucide `check`, `circle-slash-2` and `circle-alert`, the red-pen ellipse, the dashed box and hatching.
- **Errors never rely on colour alone.** Every error has the `circle-alert` icon, a bold statement of the problem and a sentence with the fix. Invalid inputs also get a 2px border and `aria-invalid`, and the message is linked with `aria-describedby`.
- **Colour-blind tested.** The six shift solids were checked under protanopia, deuteranopia and tritanopia simulation in both themes (CAM02-UCS). Among the five coloured shifts, the closest pair is ΔE ≥ 22.7 in light and ≥ 20.6 in dark. The closest pair overall is Rufbereitschaft against grey leave (ΔE 18.0 light, 17.1 dark). Those two are also told apart by shape: leave is always hatched, and Rufbereitschaft always carries the dotted mark. The shifts differ in lightness too: amber and sky blue are light, violet and green are mid, navy is darkest. Bereitschaft moved from the starting teal to green because the teal was too close to grey leave for deuteranopes and protanopes.
- **AA contrast in both themes.** Every text token reaches ≥ 4.5:1 on the grounds its usage note names: `ink` and `ink-muted` on `paper`, `sheet` and `sheet-sunk`; `ink` on every wash; each `shift-<type>-ink` on its wash; each `on-shift-<type>` on its solid. `rule-strong`, `focus` and `shift-nacht-edge` reach ≥ 3:1. The night letter in dark is white on navy (11:1).
- **Visible focus.** Every focusable element shows a 2px solid `focus` ring (ballpoint blue) with a 2px offset in the surface colour. Grid cells draw it inset. Never remove an outline without replacing it.
- **Targets.** Mobile touch targets are ≥ 48px. Switch rows are full-row labels.
- **Motion.** Only 120ms colour and position transitions. Honour `prefers-reduced-motion`.
- **Language.** Set `lang="de"` / `lang="en"` on the root. Component strings switch with the `lang` prop.

## Components

Components live in `components/bundle.js` as `window.DienstPilot`. They are plain DOM factories with no framework dependency. Each returns an element, so `parent.append(DienstPilot.ShiftChip({ shift: "N", lang: "en" }))` works in any stack. The CSS contract is `components/bundle.css`, which must load after `css/dienstpilot-tokens.css`. The components are:

- `ShiftChip`
- `RosterCell`, `RosterGrid` (with `Legend`)
- `Button`
- `Field`, `Checkbox`, `Switch`, `Segmented`
- `Suggestion`
- `RuleMessage`
- `EnvBadge`

Each has its own guidelines.

## Iconography

**The icon set is [Lucide](https://lucide.dev), outline only, in `lucide-static` 1.52.0 (ISC licence).** Designs use the same icon names and geometry as `lucide-react` (web dashboard) and `lucide-react-native` (staff app), so what is drawn here is exactly what ships.

- **Stroke:** 1.75px on screen at every size. In code: `<CircleAlert size={16} strokeWidth={1.75} absoluteStrokeWidth />`, the same props in React Native. `DienstPilot.icon(name, size)` does the same in the bundle. Round caps and joins, `fill="none"`.
- **One filled exception:** the `star` of a wish marked important is filled with `currentColor` (`<Star fill="currentColor" … />`; `DienstPilot.icon("star", 20, null, true)`). An unmarked star is outline in `ink-muted`. The label changes too ("Als wichtig markieren" becomes "Wichtig"), and the toggle sets `aria-pressed`, so the state never depends on the fill alone. No other icon is ever filled.
- **Sizes:** 16px next to `label`, `caption` and in buttons; 20px next to `body`, in rule messages and in the dashboard navigation; 12–14px only for the corner marks inside roster cells.
- **Colour:** icons take `currentColor` from the text they accompany: `ink`, `ink-muted`, `pencil`, `alert`, `env`, or `action` for the active navigation item. They never get a colour of their own, and never a shift colour.
- **No decorative icons.** An icon either carries meaning (a status, an error) or labels an action or destination. Never put an icon in front of every heading or list item. **The one list with icons is the dashboard's main navigation:** each screen has one fixed icon, so the navigation can collapse to a 56px rail when the copilot panel is open on a 1280px screen. In the rail, every icon keeps its name as a tooltip and an `aria-label`.
- **One meaning per icon.** Before adding an icon, check the table. If the meaning is already covered, reuse that icon; if the icon is already taken, pick another. Add only icons a screen actually uses, and remove a row when its last use goes.

**Status and the roster**

| Lucide name | lucide-react | Meaning | Where |
|---|---|---|---|
| `check` | `Check` | Done for this item: wish granted, day fully staffed, checkbox ticked | grid corner, coverage row, `Checkbox` |
| `circle-slash-2` | `CircleSlash2` | Wish not granted | grid corner |
| `circle-alert` | `CircleAlert` | Rule violation or error | grid badge, `RuleMessage`, `Field` error, escalations (W1, W6, W7) |
| `star` | `Star` | Important wish (max. 2 per person); filled when marked | M4 wishes; W6 requests and the W4 cell tooltip show the star next to an important wish |
| `circle-check` | `CircleCheck` | An action completed: published, gap closed, swap confirmed | toasts ("Dezember veröffentlicht"), W7 "Lücke geschlossen", W1 recent auto-approved swaps |
| `shield-check` | `ShieldCheck` | Audit log verified: complete and unaltered | W10 "Protokoll vollständig und unverändert", W12 |

**Cover cascade (W7).** Each step on the timeline shows an icon plus a word, never colour alone:

| Lucide name | lucide-react | Step |
|---|---|---|
| `bell-ring` | `BellRing` | Asked ("Angefragt / Asked") |
| `circle-x` | `CircleX` | Declined ("Abgelehnt / Declined") |
| `timer-off` | `TimerOff` | No answer in time ("Keine Antwort / Timed out") |
| `circle-check` | `CircleCheck` | Accepted ("Übernommen / Accepted") |

**AI and copilot**

| Lucide name | lucide-react | Meaning | Where |
|---|---|---|---|
| `pencil-line` | `PencilLine` | AI suggestion or a request for one | "Vorschlag / Suggestion" tag, "Vorschlag erstellen" (W4, W9) |
| `circle-question-mark` | `CircleQuestionMark` | Show the reasoning | "Warum? / Why?" on every suggestion |
| `book-open-text` | `BookOpenText` | Rule source cited | copilot citations (W9), rule references in W8 and W11 |
| `send-horizontal` | `SendHorizontal` | Send a question to the copilot | W9 input |
| `panel-right` | `PanelRight` | Open or close the copilot panel | dashboard top bar (`aria-expanded`) |

**Actions and controls**

| Lucide name | lucide-react | Meaning | Where |
|---|---|---|---|
| `x` | `X` | Close or dismiss | inline suggestions, dialogs (W5), panels |
| `chevron-down` | `ChevronDown` | Open a select or menu | `Field` selects |
| `chevron-left`, `chevron-right` | `ChevronLeft`, `ChevronRight` | Previous / next month | W3, W4, W8 month switch |
| `list-filter` | `ListFilter` | Filter a list | W6 requests, W10 audit log |
| `download` | `Download` | Export a file | W10 and W12 audit and report export |
| `external-link` | `ExternalLink` | Opens outside the dashboard | W13 model card links |
| `flask-conical` | `FlaskConical` | Demo with synthetic data | `EnvBadge` |

**Dashboard navigation.** One icon per screen. W5 (approval) and W9 (copilot) are a dialog and a panel, not destinations.

| Screen | Lucide name | lucide-react |
|---|---|---|
| W1 Übersicht / Overview | `layout-dashboard` | `LayoutDashboard` |
| W2 Wunschphase / Request window | `calendar-clock` | `CalendarClock` |
| W3 Varianten / Variants | `columns-3` | `Columns3` |
| W4 Dienstplan-Editor / Roster editor | `calendar-days` | `CalendarDays` |
| W6 Anfragen / Requests | `inbox` | `Inbox` |
| W7 Ausfälle / Absences live | `user-x` | `UserX` |
| W8 Fairness und Compliance | `scale` | `Scale` |
| W10 Protokoll / Audit trail | `scroll-text` | `ScrollText` |
| W11 Regeln und Stammdaten / Rules and master data | `settings` | `Settings` |
| W12 Aufsicht / Oversight (read-only) | `eye` | `Eye` |
| W13 KI-Transparenz / AI transparency | `cpu` | `Cpu` |

These 33 icons are in the **Icons** asset group as SVGs, and `DienstPilot.icon` knows all of them (it refuses any other name). Gaps, leave and suggested cells are drawn shapes (dashed box, hatching, hollow letter), not icons.

No logo has been supplied: set "DienstPilot" in `title` or `display` weight 700 as the wordmark.

## Decisions

- **2026-10-20 · Date spans without arrows.** Consecutive days use the German slash notation (`14./15.12.`, EN `14/15 Dec`); ranges use the en dash. Reason: the arrow is not in the font's Latin subset and fell back to a system glyph. No copy may use a glyph outside the subset.
- **2026-10-20 · Lucide as the only icon set.** Outline icons with 1.75px absolute stroke replace all drawn glyphs (tick, slashed ring, "!", pencil dash, ×, the CSS select arrow, the hatched badge swatch). Reason: designs match `lucide-react` and `lucide-react-native` one to one.
- **2026-10-20 · Red stays for form errors, with an icon and a fix.** `alert` covers rule violations and input errors, since both mean a rule is broken. Every error carries `circle-alert` and a sentence that says how to fix it, so no error depends on colour alone.
- **2026-10-20 · One official token stylesheet.** `css/dienstpilot-tokens.css` is generated from `tokens.json` by `css/build-tokens-css.mjs`. Light is the default; the class `dp-dark` switches to dark. Every design project and web codebase loads this file. Reason: one source for values across the staff-app and dashboard projects.
- **2026-10-20 · Icons for the dashboard and important wishes.** `star` marks an important wish, the only icon that may be filled (when marked). The planner dashboard adds 24 icons: one per navigation destination, the cover-cascade steps, copilot actions and list tools. The dashboard's main navigation is the one list allowed to carry icons, because it collapses to a rail. The table lists only icons with a real use.
- **2026-10-20 · Rufbereitschaft as a sixth shift type.** R / H, sky blue `shift-ruf` with `on-shift-ruf`, `shift-ruf-wash` and `shift-ruf-ink`. The hue was chosen by searching for the colour farthest from the other five in both themes under all simulated colour-vision types. Warmer candidates (brown, wine) sat too close to the red pen, and a pink wash would read as an alert. The off-site cue is **dotted**, not dashed, because dashed already means undecided (AI pencil, gap). Its light wash is close to `action-wash`; the letter and the dotted underline keep them apart.
- **2026-10-20 · Earlier decisions.** Primary buttons are `ink`, not blue. AI output is drawn in pencil. Bereitschaft moved from teal to green for colour-blind separation. Radius and shadow follow hierarchy. Grid cells use a wash, not a solid fill.

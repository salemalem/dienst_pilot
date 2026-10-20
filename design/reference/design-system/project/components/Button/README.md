Buttons name what happens, in the verb the confirmation will repeat ("Freigeben und veröffentlichen", then the toast "Veröffentlicht").

**Consumer provides:** `label`, `variant`, optional `icon` (a Lucide name, placed before the label at 16px, 20px for `lg`), optional `size: "lg"` (48px, mobile), `block` (full width), `disabled`, `onClick`, `href` (renders a link).

| Variant | Look | Use |
|---|---|---|
| `primary` | `ink` fill, `on-ink` text | The one decision on a screen: approve and publish, take shift, submit wishes. At most one per view. |
| `secondary` | `sheet`, `rule-strong` border | Every other real action: send reminder, decline with reason. |
| `quiet` | text only, `sheet-sunk` hover | Cancel, dismiss, "Warum? / Why?". |
| `link` | `action` underlined | Navigation inside text. |
| `pencil` | dashed `pencil` border | Asks the AI for something ("Vorschlag erstellen / Create proposal"). Never used to apply an AI result. |

**Rules**
- The primary button is ink, not blue. Blue is the user's own pen (links, focus, selection), and a saturated blue primary would compete with the shift colours.
- There is no red "danger" button. `alert` belongs to rule violations. A destructive action is `secondary`, with a confirmation that names the consequence.
- On mobile, the primary is `size="lg" block` in the thumb zone at the bottom of the screen.
- The focus ring is the shared 2px `focus` with a 2px offset.
- Icons only where they add meaning: `pencil-line` on the pencil button, `circle-question-mark` on "Warum?". An icon-only button (`x`) must have an `aria-label`.

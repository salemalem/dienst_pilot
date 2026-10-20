One day for one physician in the roster grid, with every state the paper plan could show, drawn so that none depends on colour.

**Consumer provides:** `lang`, plus at most one content state and any annotations. The cell computes its own accessible name, and `interactive: true` makes it focusable with `role="button"`. Optional `onClick`.

| State | Props | Drawing |
|---|---|---|
| Assigned | `shift: "F"` | `shift-*-wash`, heavy letter in `shift-*-ink`, marker underline in the solid colour |
| Wish granted | `wish: "granted"` | Lucide `check` 12px top-right, `ink` |
| Wish missed | `wish: "missed"` | Lucide `circle-slash-2` 12px top-right, `ink-muted` |
| Rule violation | `violation: true` or a reason string | red-pen ellipse around the letter + Lucide `circle-alert` 14px badge top-left, `alert`; the reason becomes part of the accessible name |
| Gap | `gap: "S"` (the unstaffed shift) | dashed `ink` box, hollow letter; used in the coverage row and day views |
| Leave | `leave: true` | 45° hatching, U / V on a clear patch |
| Off-site on call | `shift: "R"` (DE) / `"H"` (EN) / `"ruf"` | `shift-ruf-wash`, letter in `shift-ruf-ink`, **dotted** marker underline (the off-site mark); adds no hours by itself |
| Suggested | `shift: "S", suggested: true` | pencil: dashed `pencil` box on `pencil-wash`, italic letter |
| Selected | `selected: true` | 2px inset `action` box |

**Rules**
- Annotations combine: a violation can sit on a granted wish. Content states do not combine (a cell is a shift, a gap or leave).
- A suggested cell must never look inked. When the planner accepts, it becomes a plain assigned cell.
- `alert` is used for rule violations only. A missed wish is information, not an error.

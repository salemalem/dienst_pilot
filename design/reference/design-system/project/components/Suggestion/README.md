The AI suggestion: anything the system proposes, drawn in pencil until a person accepts it, always with a "Warum? / Why?" affordance.

**Consumer provides:**
- `lang`
- `text`: what is proposed, in one sentence with the facts, e.g. "Lücke am 23.12., Spätdienst. Vorschlag: Dr. Mehta"
- `reasons`: `[{ text, source? }]`, the plain-language reasoning, with rule citations such as "§ 5 ArbZG" as `source`
- optional `accept` label (name the outcome: "Dr. Mehta eintragen"), `dismiss` label, `onAccept`, `onDismiss`, `open` (start expanded), `note` (default "Die KI schlägt nur vor. Entscheiden müssen Sie.")
- `inline: true` for the compact dismissible chip (M4 preference suggestions), with `onWhy`

**Anatomy:**
- The card: `pencil-wash` ground, 1.5px dashed `pencil` border, `radius-panel`.
- The Lucide `pencil-line` icon and the label "Vorschlag / Suggestion".
- The proposal text.
- Actions: accept (`primary`, because accepting is the human inking it), dismiss (`quiet`), and "Warum?" (`quiet`, Lucide `circle-question-mark`, `aria-expanded`).
- The reasoning panel behind a dashed divider.

**Rules**
- Every AI output uses this pattern: variant summaries (W3), gap fills (W4), cover ranking (W7), copilot proposals (W9), parsed wishes (M4).
- Never show a "publish" or "approve" action inside a suggestion. Accepting a suggestion places it in the draft; publishing stays the planner's separate act.
- Reasons are concrete and checkable (hours, rest periods, qualification, fairness). No confidence percentages without meaning, no sparkle icons, no purple gradients.
- Variants (W3): one Suggestion per variant, with the recommended one marked in text ("Empfohlen, weil …"), not by colour.

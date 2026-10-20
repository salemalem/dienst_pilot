A rule-violation message (component C2): what is broken, where, and the way to fix it. Shown the moment a change breaks a hard rule.

**Consumer provides:** `lang`, `title` (the violation in plain words with person and dates, e.g. "Ruhezeit von 11 Stunden nicht eingehalten (Dr. Lorenz, 14./15.12.)"), `detail` (required: how to fix it; the console warns without it), `fix` (button label, default "Korrektur ansehen / See correction", or `false` for no button), `onFix`.

**Rules**
- Red pen: `alert-wash` ground, Lucide `circle-alert` at 20px in `alert`, `alert` title, the fix in `ink`. No left-border stripe, no shake animation.
- Dates: two consecutive days as `14./15.12.` (EN `14/15 Dec`), never with an arrow.
- State the rule and the fix. Never apologise and never say "error".
- The proposed correction opens as a `Suggestion`. The message itself never changes the roster.
- Uses `role="alert"` when it appears in response to the user's own edit. Pair each message with the violating `RosterCell`, which carries the ellipse and the `circle-alert` badge.

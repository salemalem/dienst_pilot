A square checkbox with a full-width label, for independent yes/no choices.

**Consumer provides:** `label`, optional `hint`, `checked`, `name`, `onChange`.

**Rules:** a checked box is filled with `ink` and a Lucide `check` (16px) in `on-ink`. The unchecked border is `rule-strong` (3:1). The whole label is the hit target. Use it for things like "Als wichtig markieren (max. 2)": enforce the maximum by disabling further boxes and stating why, not by silently unchecking. For an on/off setting that takes effect immediately, use `Switch`.

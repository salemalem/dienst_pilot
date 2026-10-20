An on/off setting that applies immediately (M12 settings, calendar sync).

**Consumer provides:** `label`, `checked`, `lang` (for the "An/Aus" / "On/Off" state word), optional `onChange(checked)`.

**Rules:** the state is shown in words beside the track as well as by position and fill, so it never relies on colour. The row is `touch-min` tall and the whole row toggles. It uses `role="switch"`. Don't use it for choices that need a Save button.

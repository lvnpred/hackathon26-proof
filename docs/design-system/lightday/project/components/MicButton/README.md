# MicButton

The one round sun-coloured button that starts and stops voice capture; it is the heart of every Lightday screen.

**Consumer provides:** `recording` (boolean state, owned by the parent) and `onToggle`. Optional `label` to replace "Dictate" / "Stop".

- One per screen. Put it at the top of the dictation column, beside a `heading` prompt ("Tap to dictate") and a `body-sm` hint ("Name the patient first.").
- Resting: `sun` fill, `on-sun` glyph, `halo-sun` ring. Recording: `record` fill, `on-record` glyph, `halo-record` ring that pulses (none under reduced motion).
- While recording, show the running time in `title` with tabular numbers and say where the words are going: "Adding to Ravi Kumar · OP-1042".
- It sets `aria-pressed` and swaps its accessible name between "Start dictation" and "Stop dictation".

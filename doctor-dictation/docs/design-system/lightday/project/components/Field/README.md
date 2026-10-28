# Field

A labelled text or search input set into a `surface-sunk` well.

**Consumer provides:** `label` (always visible — never a placeholder in its place), and any input attributes (`type`, `placeholder`, `value`, `onChange`). Optional `hint` for a helper line.

- The border is `line-control` so the control is findable (3:1).
- Placeholders show an example of what to type ("Name or OP number"), never the label.
- Prefer voice: put a "Type instead" quiet button beside the mic rather than a form.

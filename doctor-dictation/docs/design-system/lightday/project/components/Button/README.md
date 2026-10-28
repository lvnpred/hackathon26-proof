# Button

Actions, labelled with a verb and the thing it acts on: "Save prescription", "New patient", "Type instead".

**Consumer provides:** `children` (the label), `onClick`, and a `variant`: `primary` (ink fill — once per view, for the thing the screen is for), `ghost` (default, bordered with `line-control`), `quiet` (sky text link, for low-stakes moves like "Say it (spell)"), `danger` (record border, for Delete). Optional `size="lg"` for the main action under the sheet, `block` to fill a phone width, and a built-in `icon`.

- Never put `sun` on a button; the sun belongs to the mic.
- Heights are `control-h` (46px), or 52px at `lg`. Never shrink below `touch-min`.
- In a row, primary goes first and takes more width; wrap on a phone.
- Sentence case. No "OK", "Submit" or "Click here".

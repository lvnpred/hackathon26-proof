# PaperSheet

The document Lightday produces — a prescription, discharge summary or letter — as a white sheet that looks exactly like its PDF.

**Consumer provides:** `title` (caps serif), `letterhead` (or the default placeholder pointing to Profile), `fields` (`{label, value}`; an empty value shows a muted dash), `sections` (`{heading, text, listening}`), and optional `children` such as a medicines table.

- The sheet is `sheet` / `sheet-ink` in every theme, with `shadow-sheet` — it is paper on a desk.
- The section being dictated gets the `sheet-active` tint inside a 2px `sun` ring and a "Listening" tag in `sheet-accent`.
- Empty sections say "Not dictated yet" in `sheet-muted`.
- Put the actions directly under it: primary "Save prescription", then ghost Print, Save PDF, Share.
- Wide content (the Rx table) scrolls inside the sheet; the sheet itself never scrolls sideways.

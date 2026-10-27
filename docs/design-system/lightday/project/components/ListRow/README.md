# ListRow

One item in a day's list — a patient, a task, a document — as a full-width tappable row.

**Consumer provides:** `title` (the name), `meta` (one line: "OP-1042 · 45 M · 10:20 am"), `tag` (one word: Open, Saved) and `onClick`. Set `selected` on the item being worked on.

- Rows are at least `row-h` (56px) and divided by `line` hairlines.
- The selected row takes `sun-soft`, so the thing you are speaking about glows the same colour everywhere.
- Newest first. Times in "10:20 am" form.

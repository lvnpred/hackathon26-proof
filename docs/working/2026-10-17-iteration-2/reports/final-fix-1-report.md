# Final fix 1 report

Status: DONE, uncommitted. Suite: 1982 passed, 1 skipped (baseline 1938; the other agent adds tests too).

## I1 strength marker prints on paper
- Page: `RxState.stripMarker` regex widened to ` ?\[unverified(?: strength)?: confirm with doctor\]` (rxstate.js); `pickChip` strips in the confirming (non dose-check) branch only (rxview.js). Confirm already calls stripMarker, so it now removes the strength marker too. Chip taps have no undo in this page (nothing to restore), the existing Use-this undo still restores the marker.
- Server: `core/safety.strip_grounding_markers` (pure) called in `create_document` right after `preserve_untouched_rx_status` (the gate has passed). Only the exact two markers go; status stays unverified-strength for the audit trail.
- Existing test `tests/test_confirmed_marker.py::...marker_the_page_kept_stays` pinned the opposite (server stores what the page sent); changed deliberately to expect the strip.
- `?v=` bumped: rxstate.js 6->7, rxview.js 7->8.

## I2 same-name rows
Exact pairing rule (`core/correction.preserve_untouched_rx_status`): prior rows are grouped by the existing name key (`_norm_name`: strip + lower) into a FIFO queue in page order; the Nth output row of a name takes the Nth prior row of that name. The queue is popped for every output row of that name, also for patch-named / extra_named rows (they still skip the restore), so later same-name rows keep their own slot. A name with no prior row left (a new row) is left as validate produced it. Unique names, renamed rows, patch-named and status-less rows behave as before. Other by-name keyings checked: `_merge_rx` (patch applies to the FIRST same-name row, unchanged by design), ops `_find_rx` (already refuses "many"); persistence only calls preserve. Tests: two orders, dose-check pair, A-B-A, delete-first, via preserve, /api/v1/correct and Save (incl. 409 by index).

## Minor
a. Inline Did you mean: top name must have 6+ letters and a letters-only difflib ratio >= 0.7 (INLINE_TEXT), and no OTHER option of a different generic may start with the typed letters (incomplete name). DEVIATION: the ordered 0.8 would also drop the required croissin -> Crocin (text ratio 0.714) and citrizene (0.737); measured wrong cases are 0.5-0.667 (Pirox and the hydral case also fail the 6-letter or prefix rule). Margin to hydral->Hytrol (0.667) is thin, so the prefix rule backs it. Vimoat, Brili, Paroxe, Trile, hydral give none; citrizene, croissin, amlodipin kept.
b. `_sound_options(..., prefix_first=True)`: names starting with the typed letters first ('paracet' -> Paracetamol before Prasita); inline passes False; usage tie-break and clinic order tests green. 'cetr' lists Ceftriaxone, Cetirizine first (unchanged: nothing starts with "cetr").
c. errorText: status >= 500 -> "The medicine check is not available right now."; 4xx keep their message. Three existing pins updated.
d. Labels: "Spell it: X", "Confirm as is: X" (visible text leads; test added).
e. Comment tidied in rxview.js useName.

## Mutations (19 on scratch copies): 18 killed; 1 survivor
Survivor "no pop for named rows" is equivalent: every row of a patch-named name is skipped anyway, so the slot is never read. Initially surviving ones (prefix guard counting the same generic, inline using prefix-first order) were killed by a test added in this round.

## Concerns
- 0.7 text bar is data-driven on a handful of cases; a wider sweep by a clinician would be wise.
- Chip taps have no undo (pre-existing).
- No frontend changes beyond rxstate.js, rxview.js, index.html; no lexicon files touched.

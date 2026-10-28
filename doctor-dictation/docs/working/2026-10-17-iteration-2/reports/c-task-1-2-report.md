# I2-c Tasks 1-2 report (uncommitted)

Status: DONE. Suite 1835 passed, 1 skipped (baseline 1825 + 10: plan's 4 + 6 extra).

Changes: api/rx.py (import options; check-row answer adds `options`, `total`; 71 lines); frontend/suglist.js (PAGE, page, list; 31 lines); index.html suglist.js ?v=2 -> ?v=3 (>= pins green); tests/test_spell_options.py (6), tests/test_frontend_suglist.py (4).

Anchors (dry run on scratchpad i2c/): all plan anchors matched; no adaptations. rowcheck.options/MAX_OPTIONS/POOL_ALL already existed from I2-a. Note: reason codes in options are "matched"/"clinic"/"sounds"/"lookalike" (display text is made by SugList.reasonText), as the plan's tests assume.
RED in real repo: 6 failed (KeyError options, SugList.page missing); the 4 rowcheck-level tests passed already (I2-a built options). GREEN after the edits.

Timing (median of 5, ms): empty layer 3.7-5.1; 1000-name layer 14.0-15.8 (plan bound 50). Test asserts < 250 ms (generous).
Mutations: 19 scratch mutants (PAGE, ceil/floor, clamp low/high, hasNext/hasPrev, total > vs >=, label text, from/to, no clear in list, reason off, response slice, total = len, MAX_OPTIONS 41, total after cap, clinic names for matched rows, tie-break removed): 0 survivors.
Offline guard (netguard) for test_frontend_suglist.py: 0 attempts.
Not done: Tasks 3-5 (modal, voice), keyboard helpers (plan puts none in suglist.js).

# I2-a Tasks 3-4 report (page + print)

Status: DONE, uncommitted. Full suite 1708 passed, 1 skipped (1702 + 6). Netguard on the 5 frontend/pdf test files: 0 attempts. Sizes: sheet.py 320, rxview.js 260, rxstate.js 165, suglist.js 18, rx.css 61.

New: frontend/suglist.js, tests/test_frontend_generic_dom.py (4). Changed: frontend/rxstate.js, rxview.js, rx.css, index.html (rxstate/rxview/rx.css v=3, suglist.js v=1, app.js v=31 as the plan says though app.js itself is unchanged), pdf/sheet.py, tests/test_pdf_sheet.py (+2), test_frontend_rxspell.py (pin v=3 / >=31), test_frontend_rxspell_dom.py (_run loads suglist.js), test_frontend_rxrow.py (2 expectations).

Anchor dry-run (scratch i2a3/work): every plan anchor matched exactly once. Adaptations (no assert loosened):
1. test_frontend_rxrow.py:145 pinned the class string "rx-extra rx-sub no-print", which the plan's change removes: pin now "rx-extra rx-gen-tag no-print".
2. test_frontend_rxrow.py:74 pinned the exact afterEdit dict for a name edit: now includes did_you_mean and did_you_mean_generic as "".
3. Stale .pyc (same-size v=2 -> v=3 edit inside one second) made one pin test look failing in scratch; run with PYTHONDONTWRITEBYTECODE=1.
Strengthened tests: blank row has no line/tag; nothing applied until tapped (name cell, no post, not confirmed, no undo); posted URL and row (dose and strength kept, name = suggested spelling not its generic); failed check leaves row unchanged with note; name hand-edit while pending drops the late answer; confirmed ctx hides the button; PDF: alias row, case-only difference, hostile text, identical print for all 8 statuses, older row without key, JS class not no-print.

Mutations (20 on scratch copies of the final code): 20 killed, 0 survived (line keeps no-print, tag inverted, equal-name line, didYouMean ignores confirmed / any status, name edit keeps suggestion, useName needs panel, click not routed, confirm after render, view-only ignored, missing '?', sends generic, sends cell text, sheet equal-name / no _esc / verified-only / no .gen style, print rule deleted, blank guard, case-sensitive sameName).

Real PDF (Chromium, offline, pdftotext -layout), Medicine cell:
 1 Tab. Crocin 500 mg / generic: Paracetamol   (brand)
 2 Tab. Amlo 5 mg / generic: Amlodipine        (alias)
 3 Tab. Cetirizine 10 mg                       (generic-named: no line)
 4 Tab. Citrizene 10 mg                        (unknown: no line)
Rendered file: scratchpad i2a3/pdf/rx.pdf.

Concerns: layout of the button (name + generic spans in an inline-flex pill, 390px wrap, tag spacing, print look of the browser fallback) is untested without a browser: live check needed. The suggestion button is shown beside Confirm and Spell it; the .sug-gen block rule is from the plan and may sit beside, not under, the name inside the flex pill.

## Fix round
Status: DONE, uncommitted. Files: frontend/rxview.js, rx.css, suglist.js, index.html (rx.css v=4, rxview.js v=4, suglist.js v=2; rxstate v=3, app.js v=31 unchanged), tests/test_frontend_generic_dom.py (+2 tests, 6 total), tests/test_generic_consistency.py (+1), tests/test_frontend_rxspell.py (pins now >= 4/4/2).
1. Generic after a tap: NEITHER side drops it. Server: check-row returns generic for unverified-name rows whose name resolves (probed in-process and through TestClient, empty and unrelated transcript: Cetirizine -> Cetirizine, Crocin -> Paracetamol; unresolved Citrizene -> ""; the combination-brand ambiguity stays "" by design). Page: useName writes meta from the answer, so the line/tag renders. No source change; added a server regression test and page tests (brand tap -> "generic: Paracetamol", generic-name tap -> "generic" tag, confirmed). If the live check still showed none, the cause is data-dependent (a name that resolves nowhere, or ambiguous), not this code path.
2. .rx-gen now color:var(--rx-muted) #566660: 6.06:1 white, 5.78:1 #fff8f7, 5.86:1 #fffbf0; print rule (#444, 9.7:1) still follows it.
3. Tag is inserted with nameEl.after(tag) (directly after the name span in td.med); .rx-gen-tag is inline-block nowrap so it moves as one piece; `.rx-gen-tag + .cell::before` keeps the space before the strength. It can still drop to the next line as a unit at 390 px when the name is long.
4. Did you mean button: disabled + aria-disabled follow state.working and view-only in renderRow and in sync(); sync runs when working changes (existing path).
5. aria-label inline: "Did you mean X? Use it for this row"; list items keep "Use X for this row". It does not repeat the "generic: Y" text.
6. .rx-act.sug: column, flex-start, gap 2px, padding 6px 14px, radius 14px, min-height 44px, max-width 100%, wraps.
suglist.js: o.cls kept (I2-c passes cls "spell-item"); `same` kept (used inside item; I2-c tests load suglist.js alone, so it cannot use RxState.sameName).
Mutations (13 on scratch copies): 13 killed after one test gain (F13 view-only in sync survived first, voSync assertion added, then killed): generic dropped after tap, teal back, tag after strength, working guard in sync and in render, aria-disabled, old label, no stack, radius 999, tag wrap, lost space, server verified-only generic.
Concern: layout and 390 px wrap are still only CSS-checked, not rendered.

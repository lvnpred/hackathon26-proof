# I1-h4 report: formulary isolation sweep and the Team "Clinic medicines" tab

Status: complete, uncommitted. Full suite: 1510 passed, 1 skipped, 1 deselected (baseline 1484, +26: 4 isolation, 22 frontend). Netguard on the new/changed test files: 0 attempts.

## Changed and new files
- NEW tests/test_isolation_formulary.py (4 tests), tests/test_frontend_team_medicines.py (22 incl. 8 parametrized), tests/team_medicines_fakedom.js (flat, no tests/js).
- frontend/team.js (212 -> 317 lines), team.css (+5 rules), index.html (team.css and team.js to ?v=2).
- tests/test_frontend_team.py: one pin edited (see adaptations).
- app.js untouched, polish test untouched, no Python source changed, no git writes.

## Tests first
Isolation tests passed on first run (the feature exists since h3; the plan says so). They were then checked for teeth by mutating the real code (below). Frontend tests: all 22 failed first for the right reason (strings missing, `Cannot read properties of undefined (reading 'parentNode'/'click')`, `team.css?v=1`), one fixture bug (assigning `global.navigator`) fixed, then green after the code.

## Behaviour
- Admin only: `showMedsTab()` fetches `/api/v1/auth/me`; unless `me.role === "admin"` it returns BEFORE `buildTabs()`/`buildMeds()`. A doctor (or single mode, /auth/me 404, or a failed fetch) gets no tab, no panel, no formulary call; the members screen is unchanged (the People content sits in a plain wrapper `#teamPeople`). Server still 403s a doctor.
- Table: Medicine, Confirmed on ("2 documents"), Last seen, Added by, Actions. `added_by` is joined client-side against GET /api/v1/users (display_name, else username); null or an id not on the team shows "Unknown"; if the users call fails, all show "Unknown".
- Remove: `window.confirm` first (copy says it comes back only after two new documents confirm it). DELETE `/api/v1/formulary/<Number(id)>`, then reload the list. Success sets the polite live region `#teamMedLive` (role=status): "Removed X. It comes back only after two new documents confirm it." Failure keeps the red `#teamError` box (role=alert) and reloads the rows. Focus goes to the "Clinic medicines" tab button after either outcome (the clicked button is gone or rebuilt). A declined confirm does nothing.
- Error shapes: new `errorText(b, status)` (also used by the members actions): `error` string, else `detail` string, else first `detail[].msg`, else "Something went wrong (code N). Try again."; 503 keeps "The server is busy...". Never an object or raw JSON. A failed list load keeps the screen and does not claim "Nothing learned yet".
- Names set with `textContent` only; a test feeds `<img onerror>` as a name and checks it stays text with no child nodes.
- CSS: Remove button 44px (`.team-row-actions .team-med-remove`, overrides the 36px row rule), tab buttons already 44px, focus ring is the existing accent rule, no color-only meaning (text "Unknown", text status line), no new host/font/animation. All rules scoped under `.team-panel`.
- Tab is keyboard-operable (real buttons, Tab/Enter/Space); no arrow-key tablist (backlog). Reopening the dialog always starts on People.

## Isolation sweep
- Existing: `ADMIN_ONLY` and two CLASSIFIED entries already present; unchanged. New 4th test in test_isolation_formulary.py reuses `ADMIN_ONLY` (imported from test_isolation_routes), asserts the admin-only route list is exactly `[DELETE /api/v1/formulary/{entry_id}]` (a new admin-only route fails it), then as B's admin: cross-clinic id -> 404 with no A markers, B's list empty, A's database fingerprint unchanged, A's admin still sees the name.
- Tests 1-3 (per plan, run as written with imports trimmed): A learns, B stays unknown; hints per clinic; doctor 403 / other admin 404 / own admin 200. TABLES in isolation_fixtures already had both formulary tables.

## Adaptations from the plan text
1. JS helper flat at tests/team_medicines_fakedom.js and a new test file tests/test_frontend_team_medicines.py (instead of appending to test_frontend_team.py and tests/js/); `node -e` driver as in test_frontend_steps.py.
2. Version pins: `>= 2` regex, not exact; polish test untouched.
3. Tab built and inserted only for admins (plan built the strip hidden for everyone and unhid it). Stronger: nothing to reveal.
4. Existing pin in tests/test_frontend_team.py (`role: "status"` count == 1) was edited to `== 2` plus a pin for `#teamMedLive`: the plan's "polite live region" requires a second `role="status"`, and `aria-live` is still banned by that test, so `role=status` is used. The password box is still not live. This is the only existing test touched.
5. Plan's `showErr`-style `removeMed` replaced with loadMeds/setLive; plan's 4-column table became 5 (Added by); count shows "N documents" not "prescriptions".
6. team.css reservation comment reworded (still contains "plan I1-h", which the polish test pins).
7. Plan's manual Step 6 and Task 3 Step 2 (live session) not done: no server/browser per instructions.

## Mutations (scratch copies, all in the scratchpad)
Frontend/sweep (24 mutants; 23 killed): admin check dropped; role inverted; confirm removed; confirm result ignored; added_by join dropped; null added_by shown raw; detail ignored; array msg ignored; object stringified; error key ignored; team.js v=1; team.css v=1; live region not role=status; success not announced; soft-removal copy dropped (confirm) and (hint); focus not returned; failure message lost after reload; name via innerHTML; Remove button back to 36px; DELETE method changed; ADMIN_ONLY emptied; CLASSIFIED entry renamed. All KILLED.
Real code (4): `use_clinic_layer` dropped from /api/format; from /api/transcribe; admin policy check dropped on DELETE; list leaking an extra name. All KILLED by test_isolation_formulary.py.
Survivors: none that are real. Two harness mutants were invalid and are not counted: one had old == new text (no-op); one weakened the test itself rather than the code.

## Concerns
- Failure-focus choice (tab button) is a judgement call; a browser/screen-reader check should confirm it reads well, and the "Unknown" wording for a null added_by.
- `added_by` is the user who made the count reach two; a disabled user still resolves (list includes them).
- The fake DOM is not a real browser: layout, the 44px target, and the dialog scrolling with the tab strip (negative margins) need the separate browser check.
- team.js is 317 lines (frontend, no limit). No Python file changed, so the 500-line limits are unaffected.

## Fix round
Suite: 1516 passed, 1 skipped, 1 deselected (focused set 92 passed; node --check clean). team.js 329 lines, team.css 45. Cache pins kept at ?v=2 (h4 unreleased).

1. Pending state: the fake DOM's querySelectorAll now really matches selectors (comma lists, descendant chains of .class/#id/tag). New test holds a DELETE: Remove buttons and Add are `disabled`, dialog aria-busy "true", the tab stays enabled; after release the rebuilt rows are enabled and aria-busy "false".
2. Stale list: `t.seq` token in `loadMeds`; only the newest load draws. A reload clears the rows, hides "Nothing learned yet" and sets the polite live line "Loading…" (cleared when the load finishes); a failed reload leaves an empty table plus the error. Tests park two GETs and answer them out of order (Newer wins, Older dropped), and check a failed reload shows 0 rows. Known limit: an older request that FAILS late still calls showErr (send() is not token-aware); the table is unaffected.
3. Focus after a successful removal: next row's Remove, else previous row's, else the tab button (failure still goes to the tab). Test walks middle, last, only row. The fake server now drops a removed item from its list.
4. Phone layout: `@media (max-width:520px)` in team.css, medicines table only (new class `team-meds-table`; People table untouched): thead hidden, table/tbody/tr/td block, name on its own line (16px, ink), meta lines 13px muted with inline labels via `td[data-label]::before` (data-label Confirmed on / Last seen / Added by), 44px Remove below. Wide layout keeps real table semantics. Existing "scoped to .team-panel" tests now also accept that one `@media (max-width:520px)` prefix (edited in test_frontend_team.py and mine). Static test pins the block (comment-stripped); a markup test pins the class and labels. Not verified in a browser (no browser allowed).
5. 404 on DELETE shows "That medicine was already removed. The list has been refreshed." (send() takes an optional notFound wording); other errors keep server text. Parametrized test updated plus a dedicated test.
6. M3: the h4 plan lists the columns Medicine, Confirmed on, Last seen, Actions only: no Generic and no First seen column in the plan, so none were added. ("Added by" exists because of the controller's added_by ruling, not the plan.)

Mutations on scratch copies (13, all KILLED after two fixes): busy() not disabling; aria-busy dropped; stale guard removed; rows not cleared on reload; no Loading line; focus always tab; focus prefers previous; focus never falls back to tab; 404 wording dropped; phone label rule dropped; phone rules aimed at the People table. Two first SURVIVED (table class `team-meds-table` dropped; `data-label` dropped): added test_the_phone_layout_has_what_it_needs_from_the_markup, both now killed. Survivors: none.

## Final review fixes
Suite: 1527 passed, 1 skipped, 1 deselected; `ls doctor_dictation/data` after the run: no such directory (no app.db).

- I1: tests/test_formulary_routes.py `test_the_formulary_routes_answer_503_when_the_database_fails` used `monkeypatch.undo()` (reverted the temp DB_PATH, the `single` fixture's DB_PATH and the blank keys). Now the first stub sits in `with monkeypatch.context()`, and the test ends with a guard: DB_PATH unchanged, not under doctor_dictation, OPENAI_API_KEY == "". Scan of every test file I wrote or edited in h4 (test_isolation_formulary, test_frontend_team*, test_formulary_routes/usage, isolation_fixtures) for `monkeypatch.undo` and `delenv`: no other escape (the only `delenv` calls are in tests/conftest.py fixtures, which are the intended isolation).
- M1: team.css `.team-panel .team-meds-table td:first-child { overflow-wrap:anywhere; word-break:break-word; }` at all widths; static test on comment-stripped CSS (rule before the phone block).
- M2: api/formulary.py gains `_today()` (UTC date, same behaviour); `load_layer` uses it. test_formulary_usage patches it to a fixed far-future date and pins Zebexin's exact score from `F.usage_score` (strictly below the age-0 score), so the test cannot flake at midnight and fails if `load_layer` ignores `_today`.
- Mutations (scratch copies, all KILLED): `monkeypatch.undo()` reintroduced; overflow-wrap removed; word-break removed; `_today` not used (this one first SURVIVED because every assertion was date-independent; fixed by the exact-score assertion above).

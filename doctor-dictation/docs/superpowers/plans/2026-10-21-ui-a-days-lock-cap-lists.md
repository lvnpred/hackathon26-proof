# UI-A: older days in the list, past prescriptions view-only, 5-minute dictation, list polish

> **For agentic workers:** execute task by task, test-first. Never commit. Run single-mode code only with `DB_PATH` set
> to a temp file. Never write `from conftest import *`. Tests are offline. Full suite:
> `DB_PATH=$(mktemp -d)/t.db .venv/bin/python -m pytest tests/ -q` (baseline 2827 passed, 1 skipped on 2026-10-21).
> **Do not edit the `?v=` cache-busting numbers in `frontend/index.html` or the tests that pin them**: the
> orchestrator bumps them once at the end, so parallel lanes never edit the same line.

**Goal:** Doctors can browse prescriptions of earlier days (today stays the default), open them view-and-reprint
only, dictate at most 5 minutes, and admins get a tidier Medicines / Investigations screen.

**Owner decisions (2026-10-21, binding):** past days are view and reprint only (option A); dictation is capped at
5 minutes; the list polish is "a little", inside the existing Team dialog (no new screen).

**Architecture:** server changes in `api/visit.py` (clinic-zone day bounds) and `api/persistence.py` (date filter,
`past` flag, past-day re-save refusal); page changes in `frontend/app.js`, `frontend/authorship.js`,
`frontend/index.html`, `frontend/styles.css`; list polish in `frontend/clinlists.js`, `frontend/team.css`,
`frontend/team.js`. No migration. No new endpoint: `GET /api/v1/encounters/today` gains an optional `date`.

**Lanes:** Lane A = Tasks 1 → 2 → 3 (they share `app.js`). Lane B = Task 4 (only the list files). Lanes run in
parallel; the orchestrator then bumps versions, runs the full suite and a whole-diff review.

## Facts (verified 2026-10-21)

- `GET /api/v1/encounters/today` (`api/persistence.py:111`) uses `dbmod.local_day_bounds_utc()` (`db/__init__.py:408`),
  the HOST time zone. Visit days use the CLINIC zone (`api/visit.py today()`, `to_clinic()`). The new code uses the
  clinic zone for both.
- A re-save is allowed for any document the author owns (`create_document`, `api/persistence.py:~215-262`); the visit
  day is fixed at first save (`visit_day(existing)`).
- `get_document` (`api/persistence.py:366`) returns `visit_date` (clinic-zone ISO day) and, signed in, `author` and
  `can_edit`. `Authorship.onOpen(doc)` (`frontend/authorship.js`) returns early when there is no `author`
  (single-database mode), so the past-day lock must be applied before that return.
- `Authorship.enforce()` disables `recBtn`, `saveBtn`, `confirmAllBtn` and every sheet control when view-only; Print
  stays usable (`refreshPrintButton`, `app.js`).
- Recording: `beginRecording()` (`app.js:352`) starts a 500 ms `tick` that only updates the timer; there is no cap.
  `mr.onstop` runs `onRecordingStop()`. `MAX_AUDIO_BYTES` (10 MiB) already covers 5 minutes.
- Today list: `renderToday`, `highlightToday`, `loadToday` (`app.js:216-262`); markup `index.html:35-43`.
- Team > Medicines tab (screenshot 2026-10-21, demo clinic): Edit/Hide stacked so ~4 rows per screen; search box
  without label; no count; "Shared list" wraps; narrow dialog; headers scroll away. Investigations tab shows "No
  investigations in this list yet." ABOVE the column headers (the shared catalogue file is not shipped).

## Task 1 (Lane A): past prescriptions are view and reprint only

Server:
- `get_document` adds `"past": bool`: true when the document's visit day (`visit_day(row)`) is before
  `visit.today()`. Unknown visit day → false.
- `create_document`: a re-save (`document_id` given) of a past document returns **409**
  `{"error": "past prescription", "hint": "This prescription is from <date text>. Past prescriptions are view and
  reprint only; start a new visit to change the treatment."}` (`<date text>` via `visit.date_text(day)`), checked
  right after the authorship check and BEFORE the unverified-rows gate, and nothing is written. Today's re-save is
  unchanged.
Page:
- `Authorship.onOpen(doc)`: when `doc.past`, set a past-day lock BEFORE the single-mode early return. The banner
  (`#viewOnlyBanner`) reads "Prescription from <date>: view and reprint only" (date via `window.Dates`), mic off,
  Save off, rows read-only, Print on. `isViewOnly()` is true while locked; `clear()` (New patient, opening another
  document) unlocks. A colleague's past document shows the colleague banner (it is also view-only).
Tests (new `tests/test_past_documents.py` + a frontend test in the `tests/test_frontend_authorship.py` style):
- re-save of a yesterday document → 409 with `error == "past prescription"`, row unchanged; today's → 200.
- `get_document` → `past` true for yesterday, false for today (freeze `visit.today` with monkeypatch).
- page: `onOpen({past: true, visit_date: ...})` in single mode → banner text, `isViewOnly()` true, `recBtn` and
  `saveBtn` disabled; `clear()` → unlocked.

## Task 2 (Lane A): browse earlier days in the Today list

Server:
- `api/visit.py day_bounds_utc(day: date) -> tuple[str, str]`: the clinic-zone midnight of `day` and of the next day,
  as UTC `%Y-%m-%dT%H:%M:%SZ` (the `created_at` format). Missing zone data falls back like `to_clinic`.
- `GET /api/v1/encounters/today?date=YYYY-MM-DD` (optional; default `visit.today()`). Bad format → 400
  `{"error": "date must be YYYY-MM-DD"}`; a day after `visit.today()` → 400 `{"error": "date is in the future"}`.
  Response shape unchanged in both modes; `scope` works as today. The default now uses the clinic zone.
Page:
- Sidebar header becomes a day navigator: `‹` (`#dayPrev`), title (`#dayTitle`: "Today" or e.g. "Mon, 20 Oct"),
  calendar button (`#dayPick`) that opens a hidden `<input type="date" id="dayInput" max="<today>">`
  (`showPicker()` when available, else focus), `›` (`#dayNext`, disabled on today), and "Back to today"
  (`#dayToday`, hidden on today). Every control has an `aria-label`; the aside's label becomes "Prescriptions by day".
- `state.listDay` = "" (today) or an ISO day. `loadToday()` adds `date=` when set (keep `Authorship.todayQuery()`).
  Empty text: "No patients completed yet today." today, "No prescriptions on <date>." otherwise.
- Back to today after a successful Save of a NEW document and after New patient.
- The page's "today" is the clinic-zone day: add `Dates.todayIso()` to `frontend/dates.js` if no helper exists.
Tests: API (default day in the clinic zone with a frozen clock; `date=` filters; future and malformed → 400; scope +
date in multi-clinic mode), page (prev/next/today change the query; next disabled on today; empty text).

## Task 3 (Lane A): dictation stops at 5 minutes

- `app.js`: `MAX_RECORD_S = 300`, `WARN_RECORD_S = 270`. In the recording tick: from 270 s the timer gets class
  `rec-warn` and the status says "30 seconds left — finish the dictation." once; at 300 s call `mr.stop()` once (the
  normal `onRecordingStop` path transcribes) and set status "Stopped at 5 minutes — transcribing." Applies to first
  dictations and corrections; the Spell it voice input is unchanged.
- `styles.css`: `.rec-warn` uses an existing warning colour token (no raw colour).
Tests (frontend, fake timers): warning class and status at 270 s; `mr.stop` called exactly once at 300 s; no
warning before 270 s.

## Task 4 (Lane B): Medicines and Investigations tabs, light polish

`frontend/clinlists.js`, `frontend/team.css`, and only the dialog width in `frontend/team.js`/`team.css`:
- Edit and Hide on ONE line as compact buttons; row height about one line (~12 rows visible at 900 px height).
- Dialog wide enough for the table on list tabs (`min(1100px, 96vw)`); the table scrolls inside the panel with a
  sticky header row.
- Search: visible label or `aria-label` + placeholder "Search name, generic or brand"; a live count "Showing N of M".
- Replace the "Only changed or flagged" checkbox with filter chips: All · Clinic changes · Learned · Hidden (with
  counts), keyboard reachable, `aria-pressed`. "Clinic changes" = what the checkbox showed.
- Source shown as a small tag (Shared / Learned / Added by clinic / Hidden), no wrapping.
- Intro shortened to one sentence; the full explanation behind a `<details>` "What do these mean?".
- Empty list: hide the table header; Investigations empty text: "The shared test list is not loaded yet. Tests your
  doctors add or remember appear here."
- Same behaviour for every existing action (add, edit, hide, unhide, remove learned) and the same requests.
Tests: extend `tests/test_frontend_clinic_lists.py` (and siblings) for the count, chips filtering, inline actions,
empty state with no header, labelled search. Existing assertions change only where markup moved.

## Finish (orchestrator)

1. Bump `?v=` in `frontend/index.html` for every changed asset; update the pinning tests.
2. Full suite green; one whole-diff review (spec match, S1-style safety: nothing edits a past prescription).
3. Leave uncommitted; report changed files.

# Working folder: Iteration 3 (date format)

**What this is.** The working record of Iteration 3 (2026-10-17 and 2026-10-18): dates and times display in the Indian style on the page and on the printed prescription. Scope is display only. The implementer report is copied verbatim to `reports/implementer-report.md`; the live check is `reports/live-check.md`.

**Status.** Built on branch `iteration-3` (from `05a4527`). Nothing is committed. Full suite: 2048 passed, 1 skipped (baseline 1992). Live check: all steps passed except the Team page, which cannot be opened in single mode.

**In one picture.** A visit on 18 Oct 2026 shows `18 Oct 2026` on the sheet, `18 Oct 2026` in the PDF header, and `Review after 1 week (Sun 25 Oct 2026)` as the follow-up. The Today list shows `8:36 am`.

**Decisions needed from the owner**
1. Commit and merge plan for Iteration 3 (same pattern as Iteration 2: one commit, fast-forward to `main`, push). Not done.
2. Accept the behaviour change: a later re-save no longer moves the header day or the review base (see below).
3. Confirm the host-clock caveat is acceptable (OP number and Today list), or ask for a follow-up.

## Owner decisions (2026-10-17)

| # | Decision |
|---|---|
| 1b | Display `17 Oct 2026`. The follow-up label keeps the weekday: `Sat 24 Oct 2026`. |
| 2a | One `DATE_LOCALE` setting, default `en-IN`, for the page AND the printed PDF. Unknown value: fall back to `en-IN` with one logged warning. |
| 3a | 12-hour clock, lower case: `3:05 pm`. |
| TZ | `TZ=Asia/Kolkata` in `Dockerfile` and `docker-compose.yml` (plus `tzdata` in the image). |
| Visit date | The sheet date is read-only and shows the document's own visit day. |
| Visit day rule | The visit day is fixed at first save. Re-save, PDF render, reprint and the review base use the stored day. |

**Behaviour change.** Before, a re-save on a later day re-rendered the PDF with the re-save day and recomputed `review_date` from it, so screen, print and review could disagree. Now the day comes from the stored `created_at` (clinic zone). Live check: a document created 10 Oct and re-saved 18 Oct prints `10 Oct 2026` and `Sat 17 Oct 2026`. A changed review text recomputes from the same stored day. No test pinned the old behaviour.

## What changed

| Area | Before | Now |
|---|---|---|
| Sheet date | Editable, browser `17/10/2026` | Read-only, `17 Oct 2026`, `aria-label="Visit date"` |
| PDF header | ISO `2026-10-17`, server day | `17 Oct 2026`, visit day |
| Reopened document | Showed today | Shows its `visit_date` (GET and save responses carry it) |
| Follow-up label | Two copies of one rule (Python, JS) | Both use the shared formatter |
| Today list time | Browser default | `3:05 pm`, clinic zone |
| Team timestamps | `toLocaleString()` | `17 Oct 2026, 3:05 pm`, clinic zone |
| `/api/health` | no date fields | adds `date_locale` and `timezone` (effective zone) |
| Server "today" | container clock | clinic zone (`visit.today()`) |

Unchanged on purpose: stored ISO UTC timestamps, stored PDFs, text a doctor typed, OP number format.

## How it was checked

- Unit and integration: 2048 passed, 1 skipped. New tests also pass under the network guard (0 attempts) and with host `TZ=UTC`. One shared table, `tests/data/date_formats.json`, is read by both the Python and the node tests.
- Real Chromium plus `pdftotext` test for the PDF header: ran and passed.
- Mutation testing: 19 scratch mutants in the first round, all killed after one added health-field test; 13 more in the fix batch, all killed.
- Live check on a keyless server with a temp DB: `reports/live-check.md`.

## Caveats

- **OP number and Today list use the host clock.** They agree with the visit day when `TZ=Asia/Kolkata` is set (Docker, compose). On a host with another zone they roll over at a different time for about 5.5 hours around midnight IST.
- **A bad `TZ` name** makes `/api/health` report the host abbreviation (for example `IST`). The browser rejects it, so the page falls back to the browser zone. Docker with `tzdata` avoids this. The server's own "today" falls back to server-local with one warning.
- **`frontend/app.js` is 1251 lines**, over the 500-line rule (it was 1245 before; +3 net from this work plus the fix batch).
- **Tests came after the code in the fix batch.** The implementation was written before the new tests that round (not RED first). The 13 mutants all being killed is the proof the tests bite.
- Only one locale exists, so `DATE_LOCALE` is plumbing only. `core/followup.DAYS` and `MONTHS` are now unused (kept).
- Today-list times drawn before `/api/health` answers use the default zone.
- The Team page was not opened live (single mode has no sign-in); its formatter was checked through `Dates.dateTime` and the node tests.
- The letterhead 502 seen earlier is unrelated to dates and is still undiagnosed.

## Open items

1. Commit and merge (owner).
2. Open the Team page once in multi-clinic mode and read a timestamp.
3. Diagnose the letterhead 502.
4. Split `frontend/app.js` (backlog).
5. Seen in the live check, not date related: the rules-only path read "three times a day" as `1-0-0`.

## Folder map

- `README.md`: this page.
- `reports/implementer-report.md`: the implementer report, verbatim.
- `reports/live-check.md`: the live check.
- Plan: `docs/superpowers/plans/2026-10-17-i3-date-format.md`.

## Appendix: file:line references

| Claim | Where |
|---|---|
| Locale resolve and formatters | `doctor_dictation/core/datefmt.py:27` (`resolve_locale`), `:66` (`format_date`), `:72` (`format_label`), `:78` (`format_time`), `:86` (`format_datetime`) |
| Clinic zone and today | `doctor_dictation/api/visit.py:20` (`zone_name`), `:42` (`to_clinic`), `:50` (`today`), `:60` (`date_text`) |
| Stored visit day | `doctor_dictation/api/persistence.py:124` (`visit_day`), `:132` (`visit_day_iso`) |
| `visit_date` in responses | `doctor_dictation/api/persistence.py:325` (save), `:362` (GET) |
| Health fields | `doctor_dictation/api/health.py:53-54` |
| Setting | `doctor_dictation/config.py:70`, `:123` |
| Read-only sheet date | `frontend/index.html:99` |
| Sheet date render | `frontend/app.js:913`; `visitDate` state `:33`; set on open `:308`; from save `:1044`; reset `:528`, `:1201` |
| Page init from health | `frontend/app.js:92` (`Dates.initFrom`) |
| Page formatter | `frontend/dates.js` (script order in `frontend/index.html:263`) |
| Deployment zone | `Dockerfile:7` (`ENV TZ`), `:11` (`tzdata`); `docker-compose.yml:11` |
| Host-clock caveat | `doctor_dictation/db/opno.py:48`; `doctor_dictation/db/__init__.py` (Today list) |
| Shared test table | `tests/data/date_formats.json`; `tests/test_datefmt.py`; `tests/test_frontend_dates.py` |

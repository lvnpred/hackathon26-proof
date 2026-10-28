# I3: date format (display only)

Branch `iteration-3` from 05a4527. Status: building. Scope is DATE FORMATTING only.

## Decisions (owner, 2026-10-17)
| # | Decision |
|---|---|
| 1b | Date `17 Oct 2026`; follow-up label keeps the weekday `Sat 24 Oct 2026`. |
| 2a | One app-wide `DATE_LOCALE` (env, via `config.py`, default `en-IN`) used by page AND printed PDF. Unknown value: fall back to `en-IN`, ONE logged warning, never an error. The page reads `date_locale` and `timezone` from `/api/health`. |
| 3a | 12-hour clock `3:05 pm` (lower-case, no leading zero on the hour). |
| TZ | Deployment sets `TZ=Asia/Kolkata`. Code reads `TZ` (default `Asia/Kolkata`) only to NAME the zone; the server's "today" follows that zone explicitly, with a logged fallback to server-local when zone data is missing. |
| Typed | A date a doctor types in the sheet date is kept as typed. Saved documents keep their saved text. Stored PDFs are never rewritten. |

## Inventory of places that format a date
| Where | Today | After |
|---|---|---|
| `frontend/app.js` `today()` (sheet date default, 3 uses) | `17/10/2026` (browser en-IN) | `Dates.today()` -> `17 Oct 2026` |
| `api/persistence.py` `_pdf_inputs` header date | ISO `2026-10-17` | `17 Oct 2026` via `datefmt` |
| `api/persistence.py` on-demand re-render (created_at day) | server-local day, ISO | clinic-zone day, new format |
| `core/followup.date_label` and `frontend/sections.js` `dateLabel` | two copies of one rule | both call the shared formatter |
| `frontend/app.js` `fmtClock` (Today list) | browser default | `Dates.time()` -> `3:05 pm`, clinic zone |
| `frontend/team.js` `when()` | `toLocaleString()` | `Dates.dateTime()` -> `17 Oct 2026, 3:05 pm`, clinic zone |
| `api/visit.today()` | container clock | `datetime.now(ZoneInfo(name)).date()` |
Unchanged: OP number (`db/opno.py`), stored ISO UTC timestamps (`db/__init__.py`).

## Design
- `core/datefmt.py` (pure): `SUPPORTED`, `DEFAULT_LOCALE`, `resolve_locale(name)`, `format_date(d, locale)`, `format_label(d, locale)`, `format_time(dt, locale)`, `format_datetime(dt, locale)`. Tables per locale. Invalid input gives `""`.
- `api/visit.py`: `zone_name()`, `today()`, `to_clinic(dt)`, `date_text(d)` (locale from settings).
- `config.py`: `date_locale` setting. `/api/health` adds `date_locale` (resolved) and `timezone`.
- `frontend/dates.js` (UMD, `window.Dates`): same tables; `init({locale, timezone})`; `Intl.DateTimeFormat(...).formatToParts` with `timeZone` only converts the instant; text is assembled from own tables.
- ONE shared test table `tests/data/date_formats.json` read by Python and node tests.
- Dockerfile: `ENV TZ=Asia/Kolkata`, add `tzdata` to apt-get. Compose: `TZ: Asia/Kolkata`.

## Tasks
1. Tests first (RED). 2. `datefmt.py`, config, health, visit. 3. PDF header and re-render. 4. `dates.js` and wiring (index.html `?v=` bumps). 5. Docker files. 6. Mutations. 7. Full suite.

## Tests
Table test (py and node); `resolve_locale` fallback and one warning; health fields; `visit.today` at 00:00-05:30 IST and across midnight; PDF header text (HTML, and pdftotext if Chromium is present); `date_label` unchanged; page: default sheet date, time list, Team stamps, typed date kept, invalid ISO gives `''`; static: script order, Dockerfile and compose TZ, tzdata.

## Out of scope
Language switch, text translation, other locales, OP number, stored values, rewriting stored PDFs.

## Visit day is fixed at first save (fix batch, owner ruling 2026-10-17, option a)
- The sheet date `#pDate` is READ-ONLY (no contenteditable, `aria-label="Visit date"`). It was never stored; the PDF always printed the server day.
- A new sheet shows today (clinic zone). A reopened document shows ITS visit day: `visit_date` (ISO, clinic-zone day of `created_at`) on `GET /api/v1/documents/{id}`; the save response carries it too.
- A document's visit day is fixed at first save. A first save uses `visit.today()`; every later re-save, PDF render, reprint and review-date computation uses `api/persistence.visit_day(row)` (created_at). Before this, a re-save re-rendered the PDF with the re-save day and recomputed `review_date` from it, so screen, print and review could disagree. A changed review text recomputes from the same stored day. A row with no readable `created_at` falls back to today.
- Date rules shared with the page: strict ASCII `YYYY-MM-DD` (no trailing newline), year 1000 or later.
- `/api/health` `timezone` is the EFFECTIVE zone (TZ name if its data loads, else the host zone name).
- Host-clock caveat (no behaviour change): the OP number (`db/opno.py`) and the Today list (`db/__init__.py`) use the HOST zone. They agree with the visit day when `TZ=Asia/Kolkata` is set (Dockerfile, compose); on a host with another TZ they roll over at different times for about 5.5 hours around midnight IST. Compose `environment` overrides `env_file` for TZ.

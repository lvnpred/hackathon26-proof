# I3 report: date format (uncommitted, branch iteration-3)

Status: done. Full suite 2048 passed, 1 skipped (baseline 1992 + 56). New tests also pass under netguard (0 attempts) and with host TZ=UTC.

Files: new core/datefmt.py, frontend/dates.js, tests/data/date_formats.json, tests/test_datefmt.py, tests/test_frontend_dates.py, plan docs/superpowers/plans/2026-10-17-i3-date-format.md. Changed: api/visit.py, api/health.py, api/persistence.py, config.py, core/followup.py, frontend app.js (+3 lines net), sections.js, team.js, index.html (dates.js?v=1, sections v3, app v35, team v3), Dockerfile, docker-compose.yml; tests: team_medicines_fakedom.js (opts.dates), test_followup_routes.py (Q7 test now clinic zone), test_frontend_sections.py (loads dates.js), test_sections_prose.py (pin >=).

TZ/tzdata: Dockerfile read only; cannot tell whether python:3.12-slim-bookworm ships tzdata, so added `tzdata` to the apt-get line and `ENV TZ=Asia/Kolkata`; compose service gets `environment: TZ: Asia/Kolkata`. Code names the zone from TZ (default Asia/Kolkata); missing zone data falls back to server-local date with one warning.

Adaptations: page defaults to en-IN / Asia/Kolkata until /api/health answers; Dates.initFrom re-defaults #pDate only if it still shows the default (typed text kept). Python datefmt takes wall-clock datetimes; zone conversion is visit.to_clinic. Real Chromium + pdftotext test ran and passed.

Mutations (19 scratch copies): all killed after adding a health-field test (first run: "health locale ignored" survived because only one locale exists; fixed with a test locale via Dates.tables).

Concerns: Today-list times drawn before health answers use the default zone; only one supported locale so DATE_LOCALE is plumbing only; core/followup.DAYS/MONTHS now unused (kept).

## Fix batch
Status: done, uncommitted. Note: implementation was written before the new tests this round (not RED first); mutation testing was used to prove the tests bite (13 mutants, all killed).
- Sheet date read-only; new sheet shows today, reopened document shows `visit_date`; GET and save responses carry `visit_date`.
- Re-save rule: day = clinic-zone day of the stored created_at for every re-save (PDF header, review_date base, reprint); first save uses visit.today(); no readable created_at falls back to today.
- Changed existing tests: test_safety.py and test_today.py (exact key-set pins gained `visit_date`). test_followup_routes Q7 test unchanged (first save still passes visit.today()). The old "re-save uses today" behaviour was not pinned by any test.
- Minor: strict ASCII date regex with \Z; year >= 1000 in Python and JS (table rows added); health timezone is the effective zone; host-clock caveat commented at db/opno.py and db/__init__.py and in the plan.
- Concerns: an unloadable TZ makes health report the host abbreviation (for example "IST"), which Intl rejects, so the page falls back to the browser zone; Docker with tzdata avoids this.

# Built during the hackathon

Every feature below was written in this repository. Nothing was copied from Doctor Dictation or OPD Companion.

Dates come from `git log --format=%ad --date=short -- <path>`. The first commit (`eb76d59`, 27 Oct 2026) holds the whole build, so git cannot date the pieces more finely than that day.

## Committed on 27 Oct 2026

| Feature | Date | Where |
| --- | --- | --- |
| Event ledger, zones, spoken parser | 2026-10-27 | `backend/app/core/`, `backend/app/store.py` |
| Rules R1–R6 and the closing gate | 2026-10-27 | `backend/app/core/rules.py` |
| Tracker, including cross-chunk re-link | 2026-10-27 | `backend/app/core/tracker.py` |
| SAM 3.1, Voice, Spark Open, Spark 1.3 adapters | 2026-10-27 | `backend/app/adapters/` |
| Reconciler, tools, advice check, template fallback | 2026-10-27 | `backend/app/agent/` |
| FastAPI routes and websocket | 2026-10-27 | `backend/app/api/` |
| PDF count sheet | 2026-10-27 | `backend/app/report/count_sheet.py` |
| Five scripted eval clips and `make eval` | 2026-10-27 | `backend/app/scenarios.py`, `eval/run_eval.py` |
| Camera screens: setup, live, evidence drawer, close | 2026-10-27 | `frontend/src/screens/Setup.jsx`, `Live.jsx`, `Close.jsx` |
| Morning timeline, append-only; a correction hides the old line | 2026-10-27 | `backend/app/morning/store.py` |
| Medicine strips: strip text to grounded names, demo drug map | 2026-10-27 | `backend/app/morning/strips.py`, `brownbag.py`, `lexicon.py` |
| Drug log and spoken pack lines | 2026-10-27 | `backend/app/morning/druglog.py`, `intents.py` |
| Swab count: bucket dwell, closing reconcile, copy from a camera case | 2026-10-27 | `backend/app/morning/count_rules.py`, `camera_file.py` |
| Vitals sim and fact card | 2026-10-27 | `backend/app/morning/vitals.py`, `sim.py`, `script.py` |
| Discharge sheet, discharge PDF, follow-up ICS | 2026-10-27 | `backend/app/morning/discharge.py`, `pdf.py`, `ics.py` |
| Plain-language guide for one morning | 2026-10-27 | `backend/app/morning/guide.py` |
| Morning routes | 2026-10-27 | `backend/app/morning/api.py`, `routes_extra.py` |
| Product map (`GET /product`) | 2026-10-27 | `backend/app/site.py` |
| Morning screens: Home, Opd, Ot, Ward, Guide, Morning | 2026-10-27 | `frontend/src/screens/Home.jsx`, `Opd.jsx`, `Ot.jsx`, `Ward.jsx`, `Guide.jsx`, `Morning.jsx` |

## Changed overnight, 27–28 Oct 2026, committed as e36cd87

The overnight loop made these changes. They went in as one commit, e36cd87, on 28 Oct 2026. The item ids are in `docs/loop/backlog.md`.

| Change | Backlog | Where |
| --- | --- | --- |
| PDF tests read the real page text | B1 | `backend/tests/conftest.py`, `backend/tests/test_e2e_uc1.py`, `backend/tests/test_e2e_uc4.py` |
| Demo adds unannounced gauze (R4); the filed count sums only opened types | B2 | `backend/app/scenarios.py`, `backend/app/morning/camera_file.py` |
| Live screen runs the scripted demo or uploads a file | B3 | `frontend/src/screens/Live.jsx` |
| Upload refuses folder names in the file name and bad JSON | B5 | `backend/app/api/routes.py` |
| Video failures give a one-line 400 or 502, not a 500 | B6 | `backend/app/api/routes.py`, `backend/app/media_pipeline.py` |
| Close screen shows a failed resolution | B7 | `frontend/src/screens/Close.jsx` |
| Count sheet and Close print "Resolved by X: reason" | B8 | `backend/app/report/count_sheet.py`, `frontend/src/screens/Close.jsx` |
| Evidence drawer shows the spoken line around an alert | B9 | `frontend/src/screens/Live.jsx` |
| Spark 1.3 second look on R5, only with a key | B10 | `backend/app/engine.py` |
| Fact-card toggle on the OT screen | B11 | `frontend/src/screens/Ot.jsx` |
| Morning stream follows new events with `?follow=1` | B12 | `backend/app/morning/api.py` |
| Websocket tests | B13 | `backend/tests/test_ws.py` |
| Case and zone input checks | B16 | `backend/app/models.py` |
| README run section, submission notes, and this list | B17, B18 | `README.md`, `docs/new-work.md` |
| Eval goes through the upload route, with ground-truth files | B19 | `eval/run_eval.py`, `eval/ground_truth/` |
| Test that `.env`, keys and media stay out of git | B20 | `backend/tests/test_repo_hygiene.py` |
| PDFs survive em dashes and smart quotes | B21 | `backend/app/report/count_sheet.py`, `backend/app/morning/pdf.py` |
| R1 and R2 alerts say "No camera time (spoken count)" | B22 | `frontend/src/screens/Live.jsx` |

## Added on 28 Oct 2026: the care journey

The doctor's, nurse's and patient's stories on one timeline. The plan is `docs/hackathon/07-care-journey.md` at the workspace root.

| Feature | Date | Where |
| --- | --- | --- |
| Prescription read from Doctor Dictation over HTTP (option A), or the synthetic one | 2026-10-28 | `backend/app/journey/rx.py` |
| Dose schedule and calendar reminders | 2026-10-28 | `backend/app/journey/schedule.py` |
| Nudge rules: strips vs prescription, doses vs orders, observations vs limits, count, help, check-in | 2026-10-28 | `backend/app/journey/nudges.py` |
| Three stories, clinic discharge template, audit rows | 2026-10-28 | `backend/app/journey/stories.py` |
| Journey routes and the three-act play | 2026-10-28 | `backend/app/journey/api.py`, `play.py` |
| Strip photo read by Muse Spark 1.3 | 2026-10-28 | `backend/app/adapters/spark.py` |
| Shift handover: timeline template, Muse Spark Open rewording behind the wording check | 2026-10-28 | `backend/app/journey/handover.py`, `frontend/src/screens/NurseHandover.jsx` |
| Journey tests | 2026-10-28 | `backend/tests/test_journey.py` |

Not built yet: a recorded prop-tray video, a paid SAM measurement, a public GitHub push, the 3-minute video, the X post. Covasant IP check: not applicable.

# Use cases

Each card is one subagent. The subagent may edit only the files named here. It does not commit.

## UC1 — one patient, six steps

Pass when one labelled episode has all of these, and `guide.done` is 6:

1. A grounded strip (`brownbag.med_found`).
2. "opening twenty swabs" (`count.pack_opened`).
3. Tray replay (`count.closing` with opened 20, returned 19, unaccounted 1, track `swab-20`).
4. One confirmed drug (`druglog.given`).
5. One blood-pressure reading (`vitals.reading`).
6. Discharge draft (`discharge.drafted`), a PDF that starts with `%PDF`, and an `.ics` that contains `BEGIN:VCALENDAR`.

Files: `backend/tests/test_e2e_uc1.py` only, unless the walk fails. Then the morning route or screen that broke, and no count-rule file.

Command: `PYTHONPATH=backend .venv/bin/pytest backend/tests/test_e2e_uc1.py -q`

## UC2 — second patient is empty

Pass when patient B has `guide.done == 0` after patient A finished UC1.

Files: extend `backend/tests/test_e2e_uc1.py` or add `backend/tests/test_e2e_uc2.py`.

## UC3 — camera count filed

Pass when the demo camera case (opened 10, back 9, unaccounted 1, source `camera`) is filed on the current patient and is the sheet's closing line.

Files: `backend/tests/test_e2e_uc3.py`. Do not change `backend/app/core/rules.py`.

## UC4 — fact card stays off the sheet

Pass when `GET /morning/episodes/{id}/card` is 404 and the PDF text has none of: should, recommend, x-ray, re-explore.

Files: the UC1 test, or `backend/tests/test_e2e_uc4.py`.

## UC5 — scripted clips

Pass when `PYTHONPATH=backend .venv/bin/python eval/run_eval.py` exits 0.

Files: none, unless a use case broke the eval.

## UC6 — real SAM clip

Blocked. Needs `MODEL_API_KEY` and a tray clip shot for this project. Do not invent detections.

# Demo Guide

> Snapshot of `main` @ `e40d8c7`, generated 2026-11-01. Companion to [index.html](index.html) — same data, same numbers.

## Summary

16 scripted demos, every one backed by existing code. **13 run offline with no keys**; 3 need a key or a second app.

- **Lead demo:** D1 swab count hard stop (Count Guard) and D9 offline prescription + verify gate (Doctor Dictation).
- **Say plainly:** every Count Guard model result is a prepared fixture, chosen by the uploaded file name. Keep the generated media file names unchanged.
- **Do not show:** older Count Guard screens to non-technical audiences, or dose/investigation checks (no data ships).
- **Ports:** `make dev` uses the `.env` ports (default 8000, 8100, 5173). The automated `make demo-check` uses 8200/5273.

**Decision needed:** pick the audience journey below for the next presentation.

## Setup

### Doctor Dictation (offline)

```bash
make dd-setup   # once: venv + .[dev,pdf]
doctor-dictation/.venv/bin/playwright install chromium   # optional: server PDFs
cd doctor-dictation && OPENAI_API_KEY= DB_PATH=$(mktemp -d)/app.db .venv/bin/uvicorn doctor_dictation.main:app --port 8000
# Empty OPENAI_API_KEY forces offline rules; a temp DB_PATH keeps local data untouched
```

### Count Guard (offline)

```bash
make cg-setup   # once: venv + npm install
cd count-guard && .venv/bin/python eval/p2/make_media.py && .venv/bin/python eval/p3/make_clips.py && .venv/bin/python eval/p4/make_photos.py
make cg         # API :8100 + web :5173 (from the root .env)
# Open http://127.0.0.1:5173 · Dock → Reset seeds Ward 4 (Kumar, Iyer, Das)
# Offline = no keys: model results come from prepared fixtures, chosen by uploaded FILE NAME
```

## Recommended journeys by audience

| Audience | Sequence | Time | Label | Key message | Avoid |
| --- | --- | --- | --- | --- | --- |
| Executive / Leadership | D3 → D1 → D2 → D9 | 12 min | Supported | Two products, one idea: AI drafts and reads; people decide; every number has a record. Lead with the swab hard stop and the prescription verify gate. | Do not show older screens or imply live model accuracy — all Count Guard model results are prepared fixtures. |
| Business / Product stakeholders | D3 → D4 → D1 → D6 → D9 → D11 → D13 | 25 min | Supported | Walk the patient's day across roles, then the OPD prescription path. Close on what is Mock vs real. | Dose-range and investigation checks have no data yet. |
| Technical architects | D7 → D1 → D10 → D14 → D15 | 30 min | Supported | Append-only ledger with supersede, server-enforced gates, live/prepared seam, ops policy gate; DD tenancy and the HTTP link. | Present the Proposed module split as a recommendation, not current state. |
| Developers | D8 → D9 → D10 → D15 → D16 | 30 min | Supported | How to run, test and extend; where legacy code lives; the 4,509-test safety net. | Never run checks on 8100/5173 — the owner's dev servers use them. |
| Customers / end users (clinicians) | D12 → D11 → D3 → D1 → D6 | 15 min | Suggested | Doctor speaks, the sheet is ready and checked; the ward never loses a swab or a question. | D12 needs a working key and rehearsal; Count Guard is a research demo with synthetic data, not for clinical use. |

*Supported* means every step exists in code. *Suggested* means the ordering is a recommendation and at least one demo needs setup.

## Demo index

| ID | Demo | Product | Group | No keys? | Complexity | Time |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Swab count hard stop | Count Guard | Standalone | Yes | Medium | ~4 min |
| D2 | Tray check: missing needle holder | Count Guard | Standalone | Yes | Low | ~2 min |
| D3 | Dictated orders + AI admin with Undo | Count Guard | End-to-end | Yes | Medium | ~4 min |
| D4 | Low BP alert loop (Iyer) | Count Guard | End-to-end | Yes | Medium | ~5 min |
| D5 | Strip photo vs prescription (Das) | Count Guard | Standalone | Yes | Low | ~2 min |
| D6 | Patient Ask and doctor reply | Count Guard | End-to-end | Yes | Medium | ~4 min |
| D7 | AI activity page & Inspector | Count Guard | Advanced technical | Yes | Low | ~3 min |
| D8 | Automated 32-beat demo run | Count Guard | Advanced technical | Yes | Low | ~6 min |
| D9 | Offline prescription structuring + verify gate | Doctor Dictation | Standalone | Yes | Low | ~3 min |
| D10 | Multi-clinic isolation with demo seed | Doctor Dictation | Advanced technical | Yes | Medium | ~6 min |
| D11 | Patient share link & QR | Doctor Dictation | Standalone | Yes | Low | ~2 min |
| D12 | Live dictation, spoken correction, patient-switch warning | Doctor Dictation | End-to-end | Needs setup | Medium | ~5 min |
| D13 | Clinic learning: formulary and 'Your usual' | Doctor Dictation | Cross-module | Needs setup | Medium | ~4 min |
| D14 | OPD prescription flows into the ward (DD → CG) | Both | Cross-module | Needs setup | High | ~6 min |
| D15 | Legacy camera swab counter (scripted) | Count Guard | Experimental | Yes | Medium | ~4 min |
| D16 | Legacy morning timeline | Count Guard | Experimental | Yes | Low | ~3 min |

## Standalone demonstrations

### D1 · Swab count hard stop

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Business, Customer, Architect · **Features:** CG-08, CG-10

**Why it matters:** The single most important safety claim: a retained swab cannot be signed away. It is enforced on the server, not just hidden in the UI.

**Prerequisites:** Count Guard running; Generated media (eval/p3/swabs-closing.mp4); Kumar seeded and moved to theatre (Doctor: sign orders, admit, send to theatre)

**Steps**

1. Switch the dock role to Nurse and open Kumar's chart.
2. Press 'Surgery began'. Enter Pack opened = 15.
3. Upload eval/p3/swabs-closing.mp4 as the camera count. Note 'Camera read 14' appears beside the count, and the Back field stays empty.
4. Enter Back = 14 with no reason and save. The server refuses: the count does not match.
5. Try to end surgery. The server answers 'Save the swab count first.'
6. Save Back = 15, or 14 with a reason. End surgery: 'Count complete' and 'Back to ward' unlock.

**Expected outcome:** Surgery can only end after a person saves a closing count that adds up or carries a reason. The camera never fills the count.

**What to explain**

- The camera assists; a person decides.
- The pack count only goes up once surgery began.
- Try it with curl: POST …/surgery step=ended returns 409 until the gate is 'ok'.

**APIs:** `POST /journey/episodes/{id}/count`, `POST /journey/episodes/{id}/surgery`, `POST /journey/episodes/{id}/video?check=swabs`

**Evidence:** `count-guard/backend/app/journey/states.py:95-110`, `count-guard/backend/app/journey/flow_api.py:68-76`

### D2 · Tray check: missing needle holder

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Customer, Business · **Features:** CG-09, CG-18

**Why it matters:** Shows video understanding checked against a cited procedure plan, with boxes on frames as evidence.

**Prerequisites:** Kumar in theatre before 'Surgery began'; eval/p3/tray-hernia.mp4 generated

**Steps**

1. As Nurse, open Kumar's chart and choose 'Film the tray'.
2. Upload eval/p3/tray-hernia.mp4.
3. Open 'Details' on the result row to see the Inspector with frame boxes.

**Expected outcome:** One needle holder flagged missing; evidence boxes on frames. After surgery begins the check returns 409 ('the tray is checked before it begins').

**What to explain**

- Offline the detections are a hand-made fixture selected by file name — say so (status: Mock).
- With MODEL_API_KEY set, SAM 3.1 would be called instead.

**APIs:** `POST /journey/episodes/{id}/video?check=tray`, `GET /journey/episodes/{id}/evidence/{eid}`

**Evidence:** `count-guard/backend/app/journey/video_api.py:152-227`, `count-guard/backend/app/journey/prepared/tray-hernia.json`

### D5 · Strip photo vs prescription (Das)

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Customer · **Features:** CG-04, CG-11

**Why it matters:** Medication reconciliation in one photo.

**Prerequisites:** eval/p4/strip-amlodipine.png generated

**Steps**

1. As Doctor, open Das (clinic). In the dock click 'Use the demo prescription'.
2. Upload strip-amlodipine.png under 'Photo of strips'.
3. Close the visit.

**Expected outcome:** 'Strip reads amlodipine 10 mg; prescription says 5 mg.'

**What to explain**

- The photo read is a prepared fixture offline (Mock); the mismatch rule is real.

**APIs:** `POST …/rx/demo`, `POST …/strips/photo`

**Evidence:** `count-guard/backend/app/journey/media_api.py:266-280`

### D9 · Offline prescription structuring + verify gate

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Executive, Customer, Business, Developer · **Features:** DD-07, DD-09, DD-10, DD-13

**Why it matters:** Shows the safety core without any AI key: drug names repaired, rows graded, unverified rows blocked from printing.

**Prerequisites:** Doctor Dictation running offline (see setup)

**Steps**

1. GET /api/health — note llm_configured:false and lexicon 1.4.0 / 448.
2. POST /api/format with a transcript containing 'tablet tam sulosin 0.4 mg … tablet crocin 650 mg as needed'.
3. Note engine 'fallback-rules+lexicon…', rows Tamsulosin and Paracetamol each with a status.
4. POST the structured object to /api/v1/documents with confirmed_rows: [] → 409 'unverified medicines' if any row is unverified.
5. Resend with confirmed_rows [0,1] → document_id. GET …/pdf (needs Playwright).

**Expected outcome:** Correct generic names, status pills, a 409 block, then a saved document and PDF.

**What to explain**

- The UI shows the same flow: dictate → sheet → pills → Save & Print.
- Dose and investigation catalogues do not ship yet — do not claim those checks.

**APIs:** `GET /api/health`, `POST /api/format`, `POST /api/v1/documents`, `GET /api/v1/documents/{id}/pdf`

**Evidence:** `doctor-dictation/doctor_dictation/core/fallback.py`, `doctor-dictation/doctor_dictation/api/persistence.py:223-235`

### D11 · Patient share link & QR

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Customer, Business · **Features:** DD-25

**Why it matters:** Patient gets the prescription on their phone; the clinic can revoke it.

**Prerequisites:** A saved document (from D9 or D10)

**Steps**

1. GET /api/v1/documents/{id}/share → url /s/<slug>/<token>; the PDF carries a QR valid for 7 days.
2. Open the URL in a private window with no login: the PDF downloads.
3. POST …/share/revoke, open the URL again: generic 404.

**Expected outcome:** Working, then revoked, public link.

**What to explain**

- Tokens are masked in server and proxy logs.

**APIs:** `GET …/share`, `POST …/share/revoke`, `GET /s/{slug}/{token}`

**Evidence:** `doctor-dictation/doctor_dictation/api/share.py:67,93`

## End-to-end demonstrations

### D3 · Dictated orders + AI admin with Undo

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Business, Architect, Customer · **Features:** CG-03, CG-17, CG-02

**Why it matters:** Shows the trust model: AI drafts and does clerical work; every AI action is labelled, explained and undoable; clinical acts are 'Never'.

**Prerequisites:** Count Guard running; eval/p2/kumar-orders.wav generated

**Steps**

1. As Doctor, open Kumar (clinic). Choose 'Dictate orders' and upload kumar-orders.wav.
2. Review the draft labelled 'Drafted from voice'. Sign it, then admit.
3. See the AI row 'Acknowledged … orders' with 'Undo · 10 min' and 'Why'.
4. Switch to Nurse: the orders already show as acknowledged, with Undo.
5. Press Pause in the header. New AI work now shows 'Waiting for a person'.

**Expected outcome:** Orders become records only after a signature; the ops agent acts within policy and can be undone or paused.

**What to explain**

- The policy table lists prescribe, change_dose, advise_patient, clear_count and discharge as 'Never'.
- The planner is rules, not an LLM.

**APIs:** `POST …/dictate/orders`, `POST …/orders/sign`, `POST …/ops/work/{id}/undo`, `POST /journey/ops/pause`

**Evidence:** `count-guard/backend/app/ops/policy.py:7-27`, `count-guard/backend/app/journey/media_api.py:93`

### D4 · Low BP alert loop (Iyer)

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Business, Customer · **Features:** CG-07, CG-03, CG-09, CG-16

**Why it matters:** A full nurse → doctor → nurse loop driven by one observation.

**Prerequisites:** eval/p2/iyer-bp.wav, iyer-saline.wav and eval/p3/saline-setup.mp4 generated

**Steps**

1. As Nurse on Iyer, record BP by voice with iyer-bp.wav (88/54).
2. See the red Now card: 'Systolic BP … below limit', naming who set the limit.
3. As Doctor, find Iyer in the queue and dictate saline orders (iyer-saline.wav).
4. As Nurse, film saline-setup.mp4. The set-up matches.
5. Jump the clock 2 h, type a recheck above the limit, answer 'What did you do?'.

**Expected outcome:** The alert is raised, routed, acted on and cleared, and every step is on the timeline.

**What to explain**

- Status colour equals the clinical finding.
- One Now card per person, chosen by a fixed rank.

**APIs:** `POST …/dictate/task`, `POST …/obs`, `POST …/nudges/{id}/seen`, `POST …/video?check=setup`

**Evidence:** `count-guard/backend/app/journey/nudges.py`, `count-guard/frontend/src/care/rank.js`

### D6 · Patient Ask and doctor reply

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Customer, Business, Executive · **Features:** CG-13, CG-15

**Why it matters:** A patient-facing assistant that answers only from the record and never gives advice.

**Prerequisites:** Kumar discharged home (or use Das); wound-day3.png and rao-answer.wav generated

**Steps**

1. As Patient, open Ask and ask about a tablet. The answer names its source.
2. Ask Dr. Rao and attach wound-day3.png.
3. As Doctor, open the review beside the day-0 reference and answer by voice (rao-answer.wav) with a decision.
4. As Patient, see the answer on Ask.

**Expected outcome:** Grounded answer with source; doctor's decision (no visit / come in / call) reaches the patient.

**What to explain**

- The bot is rules-first; Spark only rewords when a key is set.

**APIs:** `POST …/ask/bot`, `POST …/ask/doctor`, `POST …/ask/review`, `POST …/reviews/{id}/answer`

**Evidence:** `count-guard/backend/app/journey/ask_api.py:77-221`

### D12 · Live dictation, spoken correction, patient-switch warning

**Product:** Doctor Dictation · **Ready without keys:** no · **Audience:** Executive, Customer, Business · **Features:** DD-01, DD-02, DD-06, DD-14

**Why it matters:** The headline experience: speak a visit, get a prescription, correct it by voice.

**Prerequisites:** OPENAI_API_KEY (covers whisper-1 STT and the LLM) or another configured provider; A real microphone; verify the configured model name answers

**Steps**

1. Dictate a full visit and stop. The sheet fills; engine shows openai:<model>+lexicon…
2. Dictate 'change paracetamol to 500 mg'. Only that row changes.
3. Dictate a different patient's name. An other-patient warning appears.
4. Save & Print.

**Expected outcome:** Structured draft from speech, targeted correction, safety warning.

**What to explain**

- Rehearse first: live vendors and the default model name are unverified in this repo.

**APIs:** `POST /api/transcribe`, `POST /api/format`, `POST /api/v1/correct`

**Evidence:** `doctor-dictation/doctor_dictation/api/format.py:126-301`

## Cross-module demonstrations

### D13 · Clinic learning: formulary and 'Your usual'

**Product:** Doctor Dictation · **Ready without keys:** no · **Audience:** Business, Customer · **Features:** DD-26, DD-28

**Why it matters:** The app gets better for each clinic without retraining.

**Prerequisites:** Several saved visits for the same diagnosis (seed by saving 2–3 times)

**Steps**

1. Save the same brand twice; it appears in GET /api/v1/formulary and the admin lists screen.
2. Dictate the same diagnosis; 'Your usual' suggests the regimen once ≥60% of past visits agree.

**Expected outcome:** Learned names verify; usual regimen offered.

**What to explain**

- Three learning stores exist (formulary, overlay, spoken terms) — see Overlap.

**APIs:** `GET /api/v1/formulary`, `POST /api/v1/spoken/usual`

**Evidence:** `doctor-dictation/doctor_dictation/api/your_usual.py:66`

### D14 · OPD prescription flows into the ward (DD → CG)

**Product:** Both · **Ready without keys:** no · **Audience:** Architect, Executive · **Features:** CG-05, DD-21

**Why it matters:** The only real integration between the two apps.

**Prerequisites:** Both apps running (make dev); A saved DD document id; Count Guard older clinic panel (Older screens)

**Steps**

1. Save a prescription in Doctor Dictation; note its document id.
2. In Count Guard open Older screens → the clinic panel and import that id.
3. See rx rows on the episode timeline.

**Expected outcome:** Rx rows copied into the Count Guard record over HTTP.

**What to explain**

- Single-mode DD has no auth, which is why the call works; multi-clinic DD would reject it.
- The current care app uses the demo prescription instead.

**APIs:** `POST /journey/episodes/{id}/rx/import`, `GET {DD_BASE_URL}/api/v1/documents/{id}`

**Evidence:** `count-guard/backend/app/journey/rx.py:83-107`

## Advanced technical demonstrations

### D7 · AI activity page & Inspector

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Architect, Developer, Executive · **Features:** CG-18, CG-19

**Why it matters:** Explainability and provenance: every model call is recorded as live, prepared or failed.

**Prerequisites:** Count Guard running, ward seeded

**Steps**

1. As Doctor or Nurse, open the AI activity tab (/ai).
2. Click 'Try sample' on SAM 3.1: 'Saw 2 of 3 needle holders', '1 missing', mode prepared.
3. Open any AI row's Inspector → Model tab.

**Expected outcome:** Per-patient pipelines, model cards and the provenance of each result.

**What to explain**

- Model names appear only here and on the Model tab — the product text hides them by design.

**APIs:** `GET /journey/ai/summary`, `POST /journey/ai/try/{model}`

**Evidence:** `count-guard/backend/app/journey/ai_api.py:56-130`

### D8 · Automated 32-beat demo run

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Developer, Architect · **Features:** CG-29

**Why it matters:** Shows the whole demo story is regression-tested offline.

**Prerequisites:** System Chrome installed; Ports 8200 and 5273 free

**Steps**

1. Run: cd count-guard && make demo-check.
2. Open count-guard/demo-shots/ to see one screenshot per beat.

**Expected outcome:** 32 beats pass; any failure saves NN-<beat>-FAIL.png.

**What to explain**

- The harness empties all model keys and aborts if the API reports live models.
- It also scans product text for banned words (model names, event names).

**APIs:** `Spawns its own API + Vite`

**Evidence:** `count-guard/frontend/scripts/demo/run.mjs:60-100`, `count-guard/frontend/scripts/demo/server.mjs:7-44`

### D10 · Multi-clinic isolation with demo seed

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Architect, Developer, Customer · **Features:** DD-29, DD-30, DD-32

**Why it matters:** Shows tenant isolation, authorship and roles — the production-shaped part of DD.

**Prerequisites:** MULTI_CLINIC=1 DEMO_MODE=1 with an empty temp DATA_DIR and a 48-byte SESSION_SECRET; eval "$(.venv/bin/python scripts/demo_browser.py --print-env)" for stub STT/LLM

**Steps**

1. Run python -m doctor_dictation.admin seed-demo, then start uvicorn.
2. Sign in as dr.rao and dr.iyer in two browser profiles: different clinics and Today lists.
3. As dr.rao tap the mic and stop: the canned 'Kiran Joshi' fever draft appears. Save & Print.
4. As dr.mehta switch Today to 'Whole clinic' and open Rao's prescription: view-only; re-save returns 403.
5. Open Rao's /api/v1/documents/<id>/pdf in Iyer's window: 404.

**Expected outcome:** Clinic data never crosses; colleagues can view but not edit.

**What to explain**

- Optional: scripts/demo_browser.py automates this with screenshots.

**APIs:** `POST /api/v1/auth/login`, `GET /api/v1/encounters/today?scope=`, `POST /api/v1/documents`

**Evidence:** `doctor-dictation/doctor_dictation/admin_demo.py`, `doctor-dictation/doctor_dictation/api/session.py:44-70`

## Experimental demonstrations

### D15 · Legacy camera swab counter (scripted)

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Architect, Developer · **Features:** CG-25, CG-27, CG-30

**Why it matters:** Shows the original tracking rules and the eval that measured them.

**Prerequisites:** Count Guard running

**Steps**

1. Older screens → Camera count. Create a case and run the scripted demo (or POST /cases/$ID/upload?scenario=clip2).
2. See R1 and R3 flags for the lap sponge; the close gate blocks.
3. Resolve with a reason; download the PDF count sheet.
4. Run make eval: 3 of 3 planted discrepancies caught on 5 scripted clips.

**Expected outcome:** Rule flags, blocked close, resolved close, PDF.

**What to explain**

- Scripted detections only — this measures the rules, not SAM.

**APIs:** `POST /cases`, `POST /cases/{id}/upload?scenario=`, `POST /cases/{id}/close`, `GET /cases/{id}/report.pdf`

**Evidence:** `count-guard/backend/app/scenarios.py`, `count-guard/eval/run_eval.py`

### D16 · Legacy morning timeline

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Developer · **Features:** CG-23

**Why it matters:** Historic context: the first one-patient-one-morning story.

**Prerequisites:** Count Guard running

**Steps**

1. Open /steps (Older screens) and walk OPD → OT → Ward.
2. Download the discharge PDF and follow-up .ics.

**Expected outcome:** Single-patient morning with brown-bag, drug log, vitals card and discharge.

**What to explain**

- Superseded by the care app; shares the same morning.db.

**APIs:** `/morning/*`

**Evidence:** `count-guard/backend/app/morning/api.py`

# Demo Guide

> Snapshot of `main` @ `90e0f56`, generated 2026-11-02. Companion to [index.html](index.html) — same data, same numbers.

## Summary

16 scripted demos, every one backed by existing code. **12 run offline with no keys**; 4 need a key or a second app.

- **Lead demo:** D14, one patient across both apps (the 3-minute video flow), with D1 swab count hard stop.
- **Say plainly:** with no key every Count Guard model result is prepared and labelled "Prepared"; tray, set-up and swab fixtures are chosen by file name, so keep generated media names unchanged. Live calls answered on 2 Nov, but live SAM found 0 swabs on the drawn demo media.
- **Do not show:** dose/investigation checks (no data ships). The older screens are archived and no longer reachable.
- **Ports:** `make dev` uses the `.env` ports (default 8000, 8100, 5173). The automated `make demo-check` starts its own DD on 8300 and CG on 8200/5273.

**Decision needed:** pick the audience journey below for the next presentation.

## Setup

### Doctor Dictation (offline)

```bash
make dd-setup   # once: venv + .[dev,pdf]
doctor-dictation/.venv/bin/playwright install chromium   # optional: server PDFs
cd doctor-dictation && OPENAI_API_KEY= DB_PATH=$(mktemp -d)/app.db .venv/bin/uvicorn doctor_dictation.main:app --port 8000
# Empty OPENAI_API_KEY forces offline rules; a temp DB_PATH keeps local data untouched
# For the two-app flow: COUNT_GUARD_URL defaults to http://127.0.0.1:8100; DEMO_BANNER=1 shows the research-demo banner
```

### Count Guard (offline)

```bash
make cg-setup   # once: venv + npm install
cd count-guard && .venv/bin/python eval/make_media.py && .venv/bin/python eval/p2/make_media.py && .venv/bin/python eval/p3/make_clips.py && .venv/bin/python eval/p4/make_photos.py
make dev        # from the root: DD :8000 + CG API :8100 + web :5173 (or make cg for Count Guard alone)
# Open http://127.0.0.1:5173 · Dock → Reset seeds Ward 4 (Kumar, Iyer, Das)
# No key: every AI step gives a result labelled 'Prepared'. With MODEL_API_KEY set the live switches call the real models
# Automated: cd count-guard && make demo-check (its own DD :8300, CG :8200/5273, keys emptied)
```

## Recommended journeys by audience

| Audience | Sequence | Time | Label | Key message | Avoid |
| --- | --- | --- | --- | --- | --- |
| Executive / Leadership / judges | D14 → D1 | 12 min | Supported | One synthetic patient, two apps: the doctor dictates and admits; the ward checks photos; theatre gets context, not alarms; a missing swab is caught with a frame; the discharge writes itself. The system formats. The doctor decides. | Do not imply model accuracy: offline results are labelled Prepared, and live SAM has not yet counted swabs on real media. |
| Business / Product stakeholders | D14 → D3 → D4 → D6 → D9 → D11 → D13 | 25 min | Supported | Walk the patient's day across roles and both apps, then the OPD prescription path. Close on what is Prepared vs live. | Dose-range and investigation checks have no data yet. |
| Technical architects | D7 → D1 → D15 → D10 → D14 | 30 min | Supported | Append-only ledger with supersede, server-enforced gates proven by a route sweep, live/prepared switches, push + Sync integration with one intake path, ops policy gate; DD tenancy. | Present the Proposed module split as a recommendation, not current state. |
| Developers | D8 → D9 → D10 → D16 | 30 min | Supported | How to run, test and extend; the archive and archive_set.py; the 4,809-test safety net; demo-check and live-check. | Never run checks on 8000/8100/5173 — the owner's dev servers use them. |
| Customers / end users (clinicians) | D12 → D14 → D6 | 15 min | Suggested | Doctor speaks, the sheet is ready and checked; the ward never loses a swab or a question. | D12 needs a working key and rehearsal; Count Guard is a research demo with synthetic data, not for clinical use. |

*Supported* means every step exists in code. *Suggested* means the ordering is a recommendation and at least one demo needs setup.

## Demo index

| ID | Demo | Product | Group | No keys? | Complexity | Time |
| --- | --- | --- | --- | --- | --- | --- |
| D1 | Swab count hard stop | Count Guard | Standalone | Yes | Medium | ~4 min |
| D2 | Tray check: missing needle holder | Count Guard | Standalone | Yes | Low | ~2 min |
| D3 | Dictated orders + AI admin with Undo | Count Guard | End-to-end | Yes | Medium | ~4 min |
| D4 | Low BP alert loop (Iyer) | Count Guard | End-to-end | Yes | Medium | ~5 min |
| D5 | Photo of medicines from home (Das) | Count Guard | Standalone | Yes | Low | ~2 min |
| D6 | Patient Ask and doctor reply | Count Guard | End-to-end | Yes | Medium | ~4 min |
| D7 | AI activity page & Inspector | Count Guard | Advanced technical | Yes | Low | ~3 min |
| D8 | Automated two-app demo-check (20 beats, 180 s) | Both | Advanced technical | Yes | Low | ~6 min |
| D9 | Offline prescription structuring + verify gate | Doctor Dictation | Standalone | Yes | Low | ~3 min |
| D10 | Multi-clinic isolation with demo seed | Doctor Dictation | Advanced technical | Yes | Medium | ~6 min |
| D11 | Patient share link & QR | Doctor Dictation | Standalone | Yes | Low | ~2 min |
| D12 | Live dictation, spoken correction, patient-switch warning | Doctor Dictation | End-to-end | Needs setup | Medium | ~5 min |
| D13 | Clinic learning: formulary and 'Your usual' | Doctor Dictation | Cross-module | Needs setup | Medium | ~4 min |
| D14 | One patient, two apps: clinic → ward → theatre → home (the video flow) | Both | Cross-module | Needs setup | High | ~8 min |
| D15 | Theatre swab camera extras: replay, resolve, close, count sheet | Count Guard | Advanced technical | Yes | Medium | ~4 min |
| D16 | Live model check | Count Guard | Experimental | Needs setup | Low | ~2 min |

## Standalone demonstrations

### D1 · Swab count hard stop

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Business, Customer, Architect · **Features:** CG-08, CG-25

**Why it matters:** The single most important safety claim: a retained swab cannot be signed away. It is enforced on the server, and a route sweep proves no other write route can close the count.

**Prerequisites:** Count Guard running; A patient in theatre (the D14 patient, or Kumar: sign orders, admit, send to theatre)

**Steps**

1. As Nurse, open the theatre chart. Press 'Surgery began', then 'Record pack opened' with 15.
2. Start the swab camera and play the recorded theatre clip. The advice reads 'One lap sponge was not seen back' with its last frame — labelled Prepared and 'Advice only'.
3. Type 14 in 'Closing count (returned)'. 'What did the team do? (required)' appears; 'Surgery ended' stays locked.
4. Acknowledge the advice ('Found under the drape, counted by hand'), save 15, then press 'Surgery ended' → 'Back to ward'.

**Expected outcome:** Surgery can only end after a person saves a closing count that adds up or carries a reason. The camera never fills the count.

**What to explain**

- The camera and rules R1–R6 are advice only (U10); count_gate reads only a person's closing.
- A closing whose 'by' reads as the AI or camera — even with look-alike letters — never counts.
- Try it with curl: POST …/surgery step=ended returns 409 until the gate is 'ok'.

**APIs:** `POST /journey/episodes/{id}/count`, `POST /journey/episodes/{id}/surgery`, `POST /journey/episodes/{id}/camera/clip`

**Evidence:** `count-guard/backend/app/journey/states.py:95-109`, `count-guard/backend/tests/test_route_sweep.py:125-209`

### D2 · Tray check: missing needle holder

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Customer, Business · **Features:** CG-09, CG-18

**Why it matters:** Shows video understanding checked against a cited procedure plan, with boxes on frames as evidence.

**Prerequisites:** Kumar in theatre before 'Surgery began'; eval/p3/tray-hernia.mp4 generated

**Steps**

1. As Nurse, open Kumar's chart and choose 'Film the tray'.
2. Upload eval/p3/tray-hernia.mp4.
3. Open 'Details' on the result row to see the Inspector with frame boxes.

**Expected outcome:** One needle holder flagged missing; evidence boxes on frames. After surgery begins the check returns 409.

**What to explain**

- With no key the detections are a prepared fixture selected by file name, labelled Prepared — say so (status: Mock).
- With MODEL_API_KEY and TRAY_LIVE, SAM 3.1 is called instead.

**APIs:** `POST /journey/episodes/{id}/video?check=tray`, `GET /journey/episodes/{id}/evidence/{eid}`

**Evidence:** `count-guard/backend/app/journey/video_api.py:149`, `count-guard/backend/app/journey/prepared/tray-hernia.json`

### D5 · Photo of medicines from home (Das)

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Executive, Customer · **Features:** CG-04, CG-11

**Why it matters:** Medicine reconciliation in one photo; the rows later feed the theatre context card.

**Prerequisites:** Generated media (eval/make_media.py)

**Steps**

1. As Doctor, open Das (clinic). In the dock click 'Use the demo prescription'.
2. Upload the committed demo photo under 'Photo of medicines from home'.
3. See metoprolol and amlodipine listed against the prescription.

**Expected outcome:** Rows from the photo, each with its source, beside the prescription.

**What to explain**

- Offline the read is prepared and chosen by the photo's bytes, not its file name (Mock); with MEDICINES_LIVE and a key Spark 1.3 vision reads it.

**APIs:** `POST …/rx/demo`, `POST …/strips/photo`

**Evidence:** `count-guard/backend/app/journey/media_api.py:278-301`, `count-guard/backend/app/journey/home_medicines.py:1-6`

### D9 · Offline prescription structuring + verify gate

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Executive, Customer, Business, Developer · **Features:** DD-07, DD-09, DD-10, DD-13

**Why it matters:** Shows the safety core without any AI key: drug names repaired, rows graded, unverified rows blocked from printing.

**Prerequisites:** Doctor Dictation running offline (see setup)

**Steps**

1. GET /api/health — note llm_configured:false and lexicon 1.4.0 / 448.
2. POST /api/format with a transcript containing 'tablet tam sulosin 0.4 mg … tablet crocin 650 mg as needed'.
3. Note rows Tamsulosin and Paracetamol each with a status.
4. POST the structured object to /api/v1/documents with confirmed_rows: [] → 409 if any row is unverified.
5. Resend with confirmed_rows [0,1] → document_id. GET …/pdf (needs Playwright).

**Expected outcome:** Correct generic names, status pills, a 409 block, then a saved document and PDF.

**What to explain**

- Dose and investigation catalogues do not ship yet — do not claim those checks.

**APIs:** `GET /api/health`, `POST /api/format`, `POST /api/v1/documents`, `GET /api/v1/documents/{id}/pdf`

**Evidence:** `doctor-dictation/doctor_dictation/core/fallback.py`, `doctor-dictation/doctor_dictation/api/persistence.py:223-235`

### D11 · Patient share link & QR

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Customer, Business · **Features:** DD-25

**Why it matters:** Patient gets the prescription on their phone; the clinic can revoke it.

**Prerequisites:** A saved document (from D9 or D10)

**Steps**

1. GET /api/v1/documents/{id}/share → url /s/<slug>/<token>; the PDF carries a QR valid for 7 days.
2. Open the URL in a private window: the PDF downloads.
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
4. Press Pause in the header. New AI work now shows 'Waiting for a person'.

**Expected outcome:** Orders become records only after a signature; the ops agent acts within policy and can be undone or paused.

**What to explain**

- The policy table lists prescribe, change_dose, advise_patient, clear_count and discharge as 'Never'.
- The planner is rules, not an LLM.

**APIs:** `POST …/dictate/orders`, `POST …/orders/sign`, `POST …/ops/work/{id}/undo`, `POST /journey/ops/pause`

**Evidence:** `count-guard/backend/app/ops/policy.py:7-27`, `count-guard/backend/app/journey/media_api.py:98`

### D4 · Low BP alert loop (Iyer)

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Business, Customer · **Features:** CG-07, CG-03, CG-09, CG-16

**Why it matters:** A full nurse → doctor → nurse loop driven by one observation.

**Prerequisites:** eval/p2/iyer-bp.wav, iyer-saline.wav and eval/p3/saline-setup.mp4 generated

**Steps**

1. As Nurse on Iyer, record BP by voice with iyer-bp.wav (88/54).
2. See the red Now card: 'Systolic BP … below limit', naming who set the limit.
3. As Doctor, dictate saline orders (iyer-saline.wav).
4. As Nurse, film saline-setup.mp4. The set-up matches.
5. Jump the clock 2 h, type a recheck above the limit, answer 'What did you do?'.

**Expected outcome:** The alert is raised, routed, acted on and cleared, and every step is on the timeline.

**What to explain**

- Status colour equals the clinical finding.
- One Now card per person, chosen by a fixed rank.

**APIs:** `POST …/dictate/task`, `POST …/obs`, `POST …/nudges/{id}/seen`, `POST …/video?check=setup`

**Evidence:** `count-guard/backend/app/journey/nudges.py`, `count-guard/frontend/src/care/rank.js`

### D6 · Patient Ask and doctor reply

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Customer, Business, Executive · **Features:** CG-13, CG-15, CG-21

**Why it matters:** A patient-facing assistant that answers only from the record and never gives advice.

**Prerequisites:** A patient discharged home (or use Das); wound-day3.png and rao-answer.wav generated

**Steps**

1. As Patient, open Ask and ask about a tablet. The answer names its source.
2. Ask Dr. Rao and attach wound-day3.png.
3. As Doctor, open the review and answer by voice (rao-answer.wav) with a decision.
4. As Patient, see the answer, the reminders (.ics) and the check-in on the patient view.

**Expected outcome:** Grounded answer with source; the doctor's decision reaches the patient.

**What to explain**

- The bot is rules-first; Spark only rewords when SPARK_LIVE is on.

**APIs:** `POST …/ask/bot`, `POST …/ask/doctor`, `POST …/ask/review`, `POST …/reviews/{id}/answer`

**Evidence:** `count-guard/backend/app/journey/ask_api.py:76-161`

### D12 · Live dictation, spoken correction, patient-switch warning

**Product:** Doctor Dictation · **Ready without keys:** no · **Audience:** Executive, Customer, Business · **Features:** DD-01, DD-02, DD-06, DD-14

**Why it matters:** The headline experience: speak a visit, get a prescription, correct it by voice.

**Prerequisites:** A working STT/LLM key (OpenAI, or Meta Muse via STT_ENGINE/LLM_PROVIDER); A real microphone

**Steps**

1. Dictate a full visit and stop. The sheet fills.
2. Dictate 'change paracetamol to 500 mg'. Only that row changes.
3. Dictate a different patient's name. An other-patient warning appears.
4. Save & Print.

**Expected outcome:** Structured draft from speech, targeted correction, safety warning.

**What to explain**

- Rehearse first: live vendor behaviour is not covered by the tests (vendors are mocked).

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

### D14 · One patient, two apps: clinic → ward → theatre → home (the video flow)

**Product:** Both · **Ready without keys:** no · **Audience:** Executive, Architect, Business, Customer · **Features:** DD-37, CG-36, CG-39, CG-40, CG-24, CG-25, CG-08, CG-14

**Why it matters:** The hackathon story: one synthetic patient crosses both apps, and the three judging points (context card, missing swab with a frame, discharge from the timeline) each get one beat.

**Prerequisites:** Both apps running (make dev), DEMO_BANNER=1 on DD; Optional: MODEL_API_KEY for live models (switches follow the key)

**Steps**

1. DD: dictate 'M. Fernandes (synthetic), 52 F … Admit for hernia repair'. Wait for 'All medicines are ready'.
2. Press 'Save & admit to ward', type the reason, save: 'Saved. Sending to Count Guard…' → 'Saved and in Count Guard.'
3. CG as Nurse: the patient is on Patients, 'Being admitted', with a 'Doctor Dictation PDF' link. Wristband photo → Accepted; wrong consent photo → Not accepted; retake → Complete admission.
4. As Doctor: hernia repair → Send to theatre. As Nurse: 'Drug given' by voice → Confirm; step the vitals and tick 'Context card (research tier)'.
5. Run D1 (swab camera, missing sponge with its last frame, hard stop, reconcile).
6. As Doctor: Draft discharge → Sign discharge → open the Discharge PDF and the follow-up .ics. As Nurse: discharge photos, Complete discharge → Home.
7. If the push was missed, press 'Sync' on the CG ward list; 'New patient' adds a walk-in.

**Expected outcome:** The patient is on the CG ward within about 3 s of Save, and the discharge PDF holds the DD prescription, the drug given and 'Opened 15. Returned 15. Unaccounted 0.'

**What to explain**

- Push after commit, Sync as backup, one intake path: a push and a Sync racing make one patient.
- Without a key every model step is labelled Prepared; say so on screen.
- Live SAM found 0 swabs on the drawn media (2 Nov); the script recommends a filmed prop tray for the live camera.

**APIs:** `POST /api/v1/documents {admit}`, `POST /journey/intake`, `POST /journey/sync → GET /api/v1/admissions`, `POST …/checks/{item}/photo`, `POST …/discharge/draft`

**Evidence:** `docs/demo/dd-cg-flow-video-script.md`, `doctor-dictation/doctor_dictation/api/admit.py:101-140`, `count-guard/backend/app/journey/intake.py:1-4`

## Advanced technical demonstrations

### D7 · AI activity page & Inspector

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Architect, Developer, Executive · **Features:** CG-18, CG-19, CG-43, CG-45

**Why it matters:** Explainability and provenance: every model call is recorded as live, prepared or failed.

**Prerequisites:** Count Guard running, ward seeded

**Steps**

1. As Doctor or Nurse, open the AI activity tab (/ai). Click 'Try sample' on SAM 3.1.
2. Open any AI row's Inspector → Model tab, then History (the audit list).
3. On a typed observation, use Correct: the old line stays in History, superseded.

**Expected outcome:** Per-patient pipelines, model cards, provenance of each result, and a correction that supersedes.

**What to explain**

- Model names appear only here and on the Model tab — the product text hides them by design.

**APIs:** `GET /journey/ai/summary`, `POST /journey/ai/try/{model}`, `POST …/correct`

**Evidence:** `count-guard/backend/app/journey/ai_api.py`, `count-guard/backend/app/journey/correct_api.py:58`

### D8 · Automated two-app demo-check (20 beats, 180 s)

**Product:** Both · **Ready without keys:** yes · **Audience:** Developer, Architect · **Features:** CG-29, DD-37

**Why it matters:** Proves the whole DD → CG film plays offline, beat by beat, before it is recorded.

**Prerequisites:** System Chrome installed; Both venvs set up (make setup); Ports 8200, 5273 and 8300 free

**Steps**

1. Run: cd count-guard && make demo-check.
2. Watch it start its own DD (:8300) and CG (:8200/5273), with every model key emptied.
3. Open count-guard/demo-shots/ to see one screenshot per beat.

**Expected outcome:** 'DEMO CHECK PASSED: 20 beats; filmed DD 30 s, ward 25 s, theatre 60 s, discharge 40 s, total 180 s'. A failure saves NN-<beat>-FAIL.png.

**What to explain**

- The harness refuses the owner's ports (8000, 8100, 5173) and aborts if the API reports live models.
- doc.test.mjs fails if the video script and the beat table drift apart.

**APIs:** `Spawns its own DD, CG API and Vite`

**Evidence:** `count-guard/Makefile:44-50`, `count-guard/frontend/scripts/demo/server.mjs:7-30`, `count-guard/frontend/scripts/demo/run.mjs:116-117`

### D10 · Multi-clinic isolation with demo seed

**Product:** Doctor Dictation · **Ready without keys:** yes · **Audience:** Architect, Developer, Customer · **Features:** DD-29, DD-30, DD-32

**Why it matters:** Shows tenant isolation, authorship and roles — the production-shaped part of DD.

**Prerequisites:** MULTI_CLINIC=1 DEMO_MODE=1 with an empty temp DATA_DIR and a 48-byte SESSION_SECRET; eval "$(.venv/bin/python scripts/demo_browser.py --print-env)" for stub STT/LLM

**Steps**

1. Run python -m doctor_dictation.admin seed-demo, then start uvicorn.
2. Sign in as dr.rao and dr.iyer in two browser profiles: different clinics and Today lists.
3. As dr.mehta open Rao's prescription: view-only; re-save returns 403.
4. Open Rao's /api/v1/documents/<id>/pdf in Iyer's window: 404.

**Expected outcome:** Clinic data never crosses; colleagues can view but not edit.

**What to explain**

- Save & admit is single-clinic only: in this mode the admissions routes answer 404.

**APIs:** `POST /api/v1/auth/login`, `GET /api/v1/encounters/today?scope=`, `POST /api/v1/documents`

**Evidence:** `doctor-dictation/doctor_dictation/admin_demo.py`, `doctor-dictation/doctor_dictation/api/session.py:44-70`

### D15 · Theatre swab camera extras: replay, resolve, close, count sheet

**Product:** Count Guard · **Ready without keys:** yes · **Audience:** Architect, Developer · **Features:** CG-42, CG-26, CG-27, CG-43

**Why it matters:** The old camera counter's rules and records, now inside the theatre panel and kept advice-only.

**Prerequisites:** A patient in theatre with the swab camera started (D1 steps 1–2)

**Steps**

1. Replay the recorded detections and run the bucket-dwell counter: both labelled Prepared.
2. Resolve an advice row: a reason is required.
3. Close the camera case; download the count-sheet PDF.
4. Open Inspector → Evidence for the case's frames and tracks.

**Expected outcome:** Advice rows resolved with reasons, a closed case, a PDF, frames — and the swab gate unchanged.

**What to explain**

- count_gate reads none of the camera.* events (test_replay_resolve_and_close_never_make_the_gate_ok).
- make eval still measures the rules on 5 scripted clips (3/3), not SAM.

**APIs:** `POST …/camera/replay`, `POST …/camera/dwell`, `POST …/camera/advice/{id}/resolve`, `POST …/camera/close`, `GET …/camera/count-sheet.pdf`

**Evidence:** `count-guard/backend/app/journey/camera_close_api.py:56-132`, `count-guard/backend/tests/test_count_gate_paths.py:200`

## Experimental demonstrations

### D16 · Live model check

**Product:** Count Guard · **Ready without keys:** no · **Audience:** Developer, Architect · **Features:** CG-38, CG-33

**Why it matters:** Proves each of the four models answers with the real key, on synthetic media only.

**Prerequisites:** MODEL_API_KEY in the root .env (never printed)

**Steps**

1. cd count-guard && make live-check.
2. Read the four rows (voice, spark-text, spark-vision, sam) and the artifacts in eval/live/<date>/ (git-ignored).
3. Optional: make cost CLIP=… prints the SAM cost before a live camera run.

**Expected outcome:** Logged 2 Nov: voice ok 2.8 s, spark-text ok 7.2 s, spark-vision ok 4.8 s, sam ok 2.2 s.

**What to explain**

- 'ok' means the call answered, not that it was accurate: SAM found 0 swabs on the drawn tray image.
- It refuses to run without a key.

**APIs:** `Meta API: SAM 3.1, Muse Voice, Spark 1.3`

**Evidence:** `count-guard/backend/app/live_check.py:1-6`, `count-guard/Makefile:52-54`

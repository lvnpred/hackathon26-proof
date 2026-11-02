# Feature Catalogue

> Snapshot of `main` @ `e40d8c7`, generated 2026-11-01. Companion to [index.html](index.html) — same data, same numbers.

## Summary

70 user-visible capabilities across the two products. Status is judged from code — persistence, auth, validation, tests, mocks and data — not from whether a screen exists.

| Status | Count | Meaning |
| --- | --- | --- |
| Implemented | 42 | Wired end to end with supporting code and tests |
| Partial | 4 | Code works but data or wiring is missing |
| Mock | 4 | Real logic, simulated model output (prepared fixtures) |
| Demo | 5 | Exists to demonstrate |
| POC | 5 | Experimental, never run live |
| Stub | 2 | Placeholder |
| Planned | 1 | Promised, not built |
| Deprecated | 7 | Superseded; still present |

Demo availability: **41 ready with no keys**, 15 need setup, 14 not demoable.

**Decision needed:** whether the Partial safety checks in Doctor Dictation (LASA, dose range, investigations) may be shown to customers before their data ships.


## Doctor Dictation

| ID | Feature | Module | Status | Lifecycle | Demo | Complexity | User value | Entry point | Dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| DD-01 | Dictation recording | Capture | Implemented | Current | Setup | Low | Doctor speaks the whole visit hands-free. | Mic button → POST /api/transcribe | An STT engine (cloud key or local faster-whisper) |
| DD-02 | STT provider chain with fallback | Capture | Implemented | Current | Setup | Medium | Cloud first, local fallback, provider choice by env. | STT_CHAIN / STT_ENGINE | OPENAI / GROQ / ASSEMBLYAI / META key, or faster-whisper extra |
| DD-03 | ONNX / Snapdragon on-device STT | Capture | Stub | Legacy | No | High | On-device speech recognition on ARM laptops. | STT_ENGINE=onnx | QNN SDK, exported Whisper ONNX |
| DD-04 | Browser Web Speech fallback | Capture | Planned | Current | No | Low | Free on-device STT when no server engine exists. | 503 hint text only | — |
| DD-05 | STT vocabulary hints & silence trim | Capture | Implemented | Current | Setup | Medium | Better drug-name recall using the doctor's own terms and recent visits. | STT_USE_HINTS, STT_TRIM_SILENCE (off by default) | Cloud STT that accepts prompts; ffmpeg |
| DD-06 | LLM structuring (extract → ground → repair loop) | Structuring | Implemented | Current | Setup | Medium | Free speech becomes an editable structured prescription sheet. | POST /api/format | LLM key (OpenAI-compatible: openai, deepseek, groq, meta) |
| DD-07 | Offline rules fallback | Structuring | Implemented | Current | Ready | Low | The app still drafts a sheet with no AI key. | POST /api/format with no LLM key | None |
| DD-08 | Deterministic normalisation & cache | Structuring | Implemented | Current | No | Low | Same transcript gives the same sheet. | Internal | None |
| DD-09 | Drug lexicon & STT name repair | Medication safety | Implemented | Current | Ready | Low | Fixes STT errors such as 'tam sulosin' and maps brands to generics. | Inside format / check-row | None |
| DD-10 | Per-row grounding pills | Medication safety | Implemented | Current | Ready | Low | Visible trust signal on every medicine row (verified, unknown, look-alike, dose-check…). | Rx table in the sheet | None |
| DD-11 | Look-alike / sound-alike (LASA) guard | Medication safety | Partial | Current | Ready | Low | Catches mix-ups like Prednisone vs Prednisolone. | Row pill 'lookalike-check' | None |
| DD-12 | Dose-range check | Medication safety | Partial | Current | No | Low | Flags a daily dose above the maximum. | Row pill 'dose-check' | Dosing data |
| DD-13 | Verify gate on Save | Medication safety | Implemented | Current | Ready | Low | No unconfirmed medicine is ever printed. | Save & Print → POST /api/v1/documents (409 'unverified medicines') | None |
| DD-14 | Spoken correction & other-patient warning | Structuring | Implemented | Current | Setup | Medium | Change one field by voice; warns if a different patient is named. | POST /api/v1/correct | LLM key |
| DD-15 | Spelled names & 'Spell it / Say it' | Structuring | Implemented | Current | Ready | Low | Exact names for rare drugs by letters, search or voice. | Row popover → POST /api/v1/rx/check-row | Search works offline; 'Say it' needs STT |
| DD-16 | Vitals grounded in dictation | Clinical fields | Implemented | Current | Ready | Low | BP, pulse, weight, SpO2, temperature are never invented. | Sheet vitals block | None |
| DD-17 | Investigations (advised tests) | Clinical fields | Partial | Current | Ready | Low | A test that was never dictated is flagged and blocks Save. | POST /api/v1/investigations/lookup | Catalogue file |
| DD-18 | Follow-up date from the review line | Clinical fields | Implemented | Current | Ready | Low | Auto 'review on' date. | POST /api/v1/review-date | None |
| DD-19 | Configurable sheet sections | Clinical fields | Partial | Current | No | Low | Clinic-specific sheet layout. | GET /api/v1/sections | — |
| DD-20 | Prose tidy & unheard-words check | Clinical fields | Implemented | Current | Ready | Low | Shows draft text the doctor never said. | Sheet prose fields | None |
| DD-21 | Save, reopen, Today list, past-day lock | Records & output | Implemented | Current | Ready | Low | Daily worklist; records become immutable after the visit day. | POST/GET /api/v1/documents, GET /api/v1/encounters/today | None |
| DD-22 | Server PDF (headless Chromium) | Records & output | Implemented | Current | Setup | Low | Printable prescription on the clinic letterhead. | GET /api/v1/documents/{id}/pdf | Playwright + Chromium (optional extra) |
| DD-23 | Letterhead from a photo | Records & output | Implemented | Current | Setup | Medium | Clinic's own pad on every print, built from a phone photo. | POST /api/v1/templates (+ accept, lines, doctors, preview) | Vision-capable LLM key |
| DD-24 | Clinic profile & OP numbers | Records & output | Implemented | Current | Ready | Low | Header details and patient IDs PREFIX-YYYYMMDD-NNN. | GET/PUT /api/v1/profile | None |
| DD-25 | Private share link & QR | Records & output | Implemented | Current | Ready | Low | Patient downloads the PDF from a 7-day revocable link. | GET …/share, POST …/share/revoke, public GET /s/{slug}/{token} | None |
| DD-26 | Learned formulary & clinic list overlay | Clinic learning | Implemented | Current | Ready | Medium | Clinic-specific names verify after repeated use; admin curates lists. | GET /api/v1/formulary, /api/v1/lists/{kind} | None |
| DD-27 | Owner curation of shipped lists | Clinic learning | Implemented | Current | Setup | Medium | Central review of what clinics add, folded back via CLI. | /api/v1/owner/lists/{kind} | MULTI_CLINIC=1, OWNER_USERNAMES |
| DD-28 | Doctor spoken terms & 'Your usual' | Clinic learning | Implemented | Current | Setup | Medium | Personal hints; one-tap usual regimen for a diagnosis. | GET /api/v1/spoken/mishearings, POST /api/v1/spoken/usual | Prior saved visits (≥60% agreement) |
| DD-29 | Multi-clinic sign-in, sessions & isolation | Access & tenancy | Implemented | Current | Setup | Medium | Each clinic's data is isolated; secure login. | /login, POST /api/v1/auth/login | MULTI_CLINIC=1, SESSION_SECRET |
| DD-30 | Roles, authorship & team admin | Access & tenancy | Implemented | Current | Setup | Medium | View-not-edit a colleague's Rx; admin manages users. | /api/v1/users, policy.can | MULTI_CLINIC=1 |
| DD-31 | Operator CLI, Docker/Caddy & VPS scripts | Operations | Implemented | Tooling | No | High | Deploy, migrate, back up, restore. | python -m doctor_dictation.admin …; scripts/deploy/* | Docker, VPS |
| DD-32 | Demo seed & browser walkthrough | DD demo & tooling | Demo | Tooling | Ready | Low | Safe two-clinic demo with stub STT/LLM. | admin seed-demo; scripts/demo_browser.py | DEMO_MODE=1, empty DATA_DIR, ALLOW_STUB_PROVIDERS=1 |
| DD-33 | STT benchmark | DD demo & tooling | POC | Tooling | No | Medium | Pick an STT provider by word error rate, drug recall and cost. | python -m doctor_dictation.bench.run | Real consented clips (none ship) |
| DD-34 | Government generics sync & promotion | DD demo & tooling | Implemented | Tooling | No | Medium | Grow the lexicon from an official list with a reviewed ledger. | core/lexicon/generics_sync.py, admin promote-* | PROMOTION_LEDGER_PEPPER |
| DD-35 | Patient / encounter CRUD routes | Records & output | Deprecated | Legacy | No | Low | — | GET/POST /api/v1/patients, /api/v1/encounters | — |
| DD-36 | Health endpoint | Operations | Implemented | Current | Ready | Low | Top bar shows the engine and model; ops probe. | GET /api/health | None |

## Count Guard

| ID | Feature | Module | Status | Lifecycle | Demo | Complexity | User value | Entry point | Dependencies |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CG-01 | Ward seed & Demo dock (role, patient, clock, reset) | Demo & showcase | Demo | Current | Ready | Low | One presenter drives doctor, nurse and patient views. | Dashed dock at the bottom; POST /journey/demo/seed, …/tick | None |
| CG-02 | Patient state machine & checklists | Patient flow | Implemented | Current | Ready | Low | Enforced stage transitions with plain reasons. | Chart action buttons → POST …/state | None |
| CG-03 | Dictated orders → draft → sign → acknowledge | Orders & tasks | Implemented | Current | Ready | Medium | A spoken order becomes a record only when a person signs it. | Doctor 'Dictate orders' → POST …/dictate/orders, /orders/sign, /orders/{id}/ack | Prepared media file names offline |
| CG-04 | Demo prescription | Orders & tasks | Demo | Current | Ready | Low | Puts Rx rows on a clinic chart instantly. | Dock 'Use the demo prescription' → POST …/rx/demo | None |
| CG-05 | Import a Doctor Dictation prescription | Orders & tasks | Implemented | Legacy | Setup | High | Cross-app: the OPD prescription flows into the ward record. | Older clinic panel → POST …/rx/import → DD GET /api/v1/documents/{id} | Doctor Dictation running with a saved document; DD_BASE_URL |
| CG-06 | Nurse tasks with values & photo proof | Orders & tasks | Implemented | Current | Ready | Medium | Auditable care rounds: begin, done by tap/voice/text, proof photo checked. | NurseTasks → POST …/tasks/{id}/begin\|done, …/photos | Prepared photo reads offline |
| CG-07 | Observations vs limits → named alert | Observations & alerts | Implemented | Current | Ready | Low | 'Systolic BP 82 below limit' with who set the limit, then 'What did you do?'. | Alert card → POST …/obs, …/nudges/{id}/seen | None |
| CG-08 | Swab count hard stop | Swab count | Implemented | Current | Ready | Medium | Retained-swab prevention: surgery cannot end until a person saves a count that adds up or states a reason. | Theatre chart CountPanel → POST …/count, POST …/surgery step=ended | None |
| CG-09 | Tray & saline set-up video checks | Video & photo checks | Mock | Current | Ready | Medium | Spot a missing instrument or wrong set-up against a cited procedure plan. | Nurse 'Film the tray' → POST …/video check=tray\|setup | Generated media with exact fixture names |
| CG-10 | Swab camera count (assist) | Video & photo checks | Mock | Current | Ready | Medium | Camera read shown beside the typed count. | Count panel upload → POST …/video check=swabs | swabs-closing media file |
| CG-11 | Medicine strip photo vs prescription | Video & photo checks | Mock | Current | Ready | Low | 'Strip reads amlodipine 10 mg; prescription says 5 mg.' | Doctor clinic 'Photo of strips' → POST …/strips/photo | Generated strip image |
| CG-12 | Patient 'medicines from home' photo → day plan | Video & photo checks | Mock | Current | Ready | Low | Patient photographs their tablets; one row is flagged. | Patient Today / My care → POST …/ask/medicines | Generated photo |
| CG-13 | Patient Ask: record bot, ask the doctor, photo review | Patient Ask | Implemented | Current | Ready | Medium | Patient gets answers only from their record, with sources; the doctor answers with a decision. | Patient /ask → POST …/ask/bot\|doctor\|review, …/questions/{id}/answer | Prepared voice/photo for the doctor reply |
| CG-14 | Discharge: dictate → sign → checks → home | Patient flow | Implemented | Current | Ready | Medium | Clean, recorded discharge. | Doctor 'Dictate discharge' → POST …/dictate/discharge, …/discharge/sign | Prepared transcript offline |
| CG-15 | Doctor status chip | Patient flow | Implemented | Current | Ready | Low | Patients and nurses see 'In theatre' / 'free soon' / 'available'. | Header chip → GET/POST /journey/staff/doctor | None |
| CG-16 | 'Now' card ranking & waiting pills | Patient flow | Implemented | Current | Ready | Low | One next action per person: danger > blocked > late > due > review. | Top of each chart | None |
| CG-17 | AI admin: act, Undo, approve, Pause | AI admin ops agent | Implemented | Current | Ready | Medium | Removes clerical work while staying reversible and never touching clinical decisions. | Chart 'AI admin' rows, header Pause → /journey/ops/*, …/ops/work/{id}/undo\|approve\|reject | None (on by default, CG_OPS_AGENT) |
| CG-18 | Inspector (Why / Evidence / History / Model) | Inspector & AI activity | Implemented | Current | Ready | Low | Every AI row explains itself; boxes on frames. | 'Why' / 'Details' on a row → GET …/evidence/{id} | None |
| CG-19 | AI activity page & 'Try sample' | Inspector & AI activity | Demo | Current | Ready | Low | Showcases the four models and per-patient AI pipelines. | /ai (staff) → GET /journey/ai/summary, POST /journey/ai/try/{model} | None |
| CG-20 | Nurse handover draft | Care journey v1 | Implemented | Legacy | Setup | Low | Shift handover worded from the record. | Older Nurse screen → POST …/handover | Spark key for rewording (template otherwise) |
| CG-21 | Reminders (.ics), check-in, help | Care journey v1 | Implemented | Legacy | Ready | Low | Post-discharge follow-up for the patient. | Older /patient screen → …/reminders, …/reminders.ics, …/checkin | None |
| CG-22 | Three-act scripted journey play | Care journey v1 | Deprecated | Legacy | No | Low | One-click demo of the v1 story. | POST …/play (route /journey has no nav link) | None |
| CG-23 | Morning timeline: brown-bag, drug log, vitals sim, discharge PDF/ICS | Morning timeline | Deprecated | Legacy | Ready | Medium | Generation-B single-patient morning record. | Older screens /steps, /opd, /ot, /ward, /morning → /morning/* | None |
| CG-24 | Decision-tier fact card toggle | Morning timeline | Deprecated | Legacy | No | Low | Gate decision-support content behind a tier. | GET/POST /morning/tier | DECISION_TIER |
| CG-25 | Camera case: zones, rules R1–R6, discrepancies, close gate | Camera swab counter | Deprecated | Legacy | Ready | Medium | The original video swab counter. | Older screens /count → /case/:id → /close; /cases/* | None for scripted replay |
| CG-26 | Discrepancy narrative (Spark Open reconciler) | Camera swab counter | POC | Legacy | Setup | High | Plain-language explanation of a count discrepancy, advice-filtered. | POST /cases/{id}/close | BASETEN_API_KEY |
| CG-27 | PDF count sheet | Camera swab counter | Deprecated | Legacy | Ready | Low | Printable record of a camera case. | GET /cases/{id}/report.pdf | None |
| CG-28 | Real-video SAM pipeline & live WebSocket | Camera swab counter | POC | Legacy | Setup | High | Track swabs from a real theatre clip, stream live. | POST /cases/{id}/upload (file), WS /cases/{id}/stream | MODEL_API_KEY, ffmpeg |
| CG-29 | Headless demo-check (32 beats) | Demo & showcase | Demo | Tooling | Ready | Medium | Proves the whole demo story still plays, offline, with screenshots. | make demo-check (ports 8200/5273) | System Chrome, Node, Python venv |
| CG-30 | Evaluation: scripted clips & ops replay | Demo & showcase | Implemented | Tooling | Ready | Low | Measures camera rules (3/3 planted discrepancies) and ops-agent precision/undo rate. | make eval; eval/replay_ops.py | None |
| CG-31 | Fixture recorder | Research POCs | POC | Tooling | No | Medium | Re-record prepared fixtures from real model calls. | eval/record_fixtures.py --spend | Model keys, money |
| CG-32 | Spark-only baseline scoring | Research POCs | Stub | Tooling | No | Medium | Compare Spark alone against the rules. | make baseline | Keys |
| CG-33 | Day-1 API check & SAM cost estimator | Research POCs | POC | Tooling | No | Low | Go/no-go on model access; cost per clip without calling. | make day1, make cost CLIP=… | Keys for day1 |
| CG-34 | Feature guide page | Morning timeline | Deprecated | Legacy | Ready | Low | Old navigation map of features. | /guide → GET /product | None |

## Why each status, with evidence

| ID | Feature | Status | Why this status | Evidence |
| --- | --- | --- | --- | --- |
| DD-01 | Dictation recording | Implemented | MediaRecorder capture wired to the transcribe route; needs a working STT engine to produce text. | `doctor-dictation/frontend/app.js:380-385`<br>`doctor-dictation/doctor_dictation/api/stt.py:88-116` |
| DD-02 | STT provider chain with fallback | Implemented | Five real providers behind one factory; vendor HTTP is mocked in tests, so live vendor behaviour is unverified here. | `doctor-dictation/doctor_dictation/providers/stt/factory.py:16-75`<br>`doctor-dictation/tests/test_stt_providers.py` |
| DD-03 | ONNX / Snapdragon on-device STT | Stub | File header says 'DEFERRED / NOT NEEDED'; nothing installs requirements-onnx.txt. | `doctor-dictation/doctor_dictation/providers/stt/onnx.py:1-19`<br>`doctor-dictation/doctor_dictation/requirements-onnx.txt` |
| DD-04 | Browser Web Speech fallback | Planned | The 503 error promises 'the page will auto-retry with … Web Speech' but no SpeechRecognition code exists in frontend/. | `doctor-dictation/doctor_dictation/providers/stt/factory.py:112-116` |
| DD-05 | STT vocabulary hints & silence trim | Implemented | Implemented and tested; disabled unless the env flags are set. | `doctor-dictation/doctor_dictation/api/stt.py:52-85`<br>`doctor-dictation/doctor_dictation/core/hints.py`<br>`doctor-dictation/doctor_dictation/audio/trim.py` |
| DD-06 | LLM structuring (extract → ground → repair loop) | Implemented | JSON-mode call, re-validated against the lexicon, repair passes up to a cap. Default model name 'gpt-6-luna' and the Meta endpoint ('not yet verified') are unverified. | `doctor-dictation/doctor_dictation/api/format.py:126-214`<br>`doctor-dictation/doctor_dictation/config.py:74,139` |
| DD-07 | Offline rules fallback | Implemented | Deterministic rules formatter used when no LLM is configured or the LLM errors; seeded sample text is tagged with a DEMO_WARNING. | `doctor-dictation/doctor_dictation/core/fallback.py:54,74`<br>`doctor-dictation/doctor_dictation/core/rulesplit.py`<br>`doctor-dictation/doctor_dictation/api/format.py:145-156` |
| DD-08 | Deterministic normalisation & cache | Implemented | 512-entry in-memory cache, per worker process (Docker runs 2) — not shared or persisted. | `doctor-dictation/doctor_dictation/core/determinism.py:61-62,305-312` |
| DD-09 | Drug lexicon & STT name repair | Implemented | 448-entry lexicon (v1.4.0) plus seed and import files; not clinician-reviewed. | `doctor-dictation/doctor_dictation/core/drugnames.py`<br>`doctor-dictation/doctor_dictation/core/lexicon/drugs.json` |
| DD-10 | Per-row grounding pills | Implemented | One code path for format, correct and check-row. | `doctor-dictation/doctor_dictation/core/rowcheck.py` |
| DD-11 | Look-alike / sound-alike (LASA) guard | Partial | Code works, but only 8 curated pairs ship and all are marked reviewed:false. | `doctor-dictation/doctor_dictation/core/lasa.py`<br>`doctor-dictation/doctor_dictation/core/lexicon/lasa_pairs.json` |
| DD-12 | Dose-range check | Partial | Inert: dosing.json ships as version 'none' with zero entries, so every row returns cannot-check. A CSV builder exists. | `doctor-dictation/doctor_dictation/core/dosing.py`<br>`doctor-dictation/doctor_dictation/core/lexicon/dosing.json` |
| DD-13 | Verify gate on Save | Implemented | Server blocks Save unless rows are verified or confirmed. Caveat: row status is client-supplied on Save and not re-grounded server-side. | `doctor-dictation/doctor_dictation/core/safety.py:29`<br>`doctor-dictation/doctor_dictation/api/persistence.py:223-235` |
| DD-14 | Spoken correction & other-patient warning | Implemented | Offline the patch is empty and nothing changes. | `doctor-dictation/doctor_dictation/api/format.py:241-301`<br>`doctor-dictation/doctor_dictation/core/patientswitch.py` |
| DD-15 | Spelled names & 'Spell it / Say it' | Implemented | Letter-spelling override and the row popover are wired and tested. | `doctor-dictation/doctor_dictation/core/spelled.py`<br>`doctor-dictation/doctor_dictation/api/rx.py:59`<br>`doctor-dictation/frontend/spellmodal.js` |
| DD-16 | Vitals grounded in dictation | Implemented | Values must be heard in the transcript. | `doctor-dictation/doctor_dictation/core/vitals.py` |
| DD-17 | Investigations (advised tests) | Partial | Shipped catalogue core/lexicon/investigations.json is absent ('grounding is off'); only the was-it-heard check and clinic overlay work. A draft CSV sits in docs/working. | `doctor-dictation/doctor_dictation/core/investigations.py:19,40-58` |
| DD-18 | Follow-up date from the review line | Implemented | Deterministic parser, tested. | `doctor-dictation/doctor_dictation/core/followup.py`<br>`doctor-dictation/doctor_dictation/api/review.py:19` |
| DD-19 | Configurable sheet sections | Partial | Only the shipped sections.json is served; per-clinic/per-doctor overrides are planned. | `doctor-dictation/doctor_dictation/api/sections.py:24-25` |
| DD-20 | Prose tidy & unheard-words check | Implemented | Implemented and tested. | `doctor-dictation/doctor_dictation/core/tidy.py`<br>`doctor-dictation/doctor_dictation/core/prose.py` |
| DD-21 | Save, reopen, Today list, past-day lock | Implemented | SQLite persistence with audit_log; past-day re-save returns 409. | `doctor-dictation/doctor_dictation/api/persistence.py:114,198,370`<br>`doctor-dictation/doctor_dictation/api/pastday.py` |
| DD-22 | Server PDF (headless Chromium) | Implemented | Without Playwright the route returns 503 fallback:browser and the page uses browser print. | `doctor-dictation/doctor_dictation/pdf/renderer.py`<br>`doctor-dictation/doctor_dictation/api/persistence.py:359-362,428` |
| DD-23 | Letterhead from a photo | Implemented | Vision LLM proposes a layout; image sanitising, quota, TTL. Returns 503 without a vision model. | `doctor-dictation/doctor_dictation/templates/builder.py:101-121`<br>`doctor-dictation/doctor_dictation/api/templates.py` |
| DD-24 | Clinic profile & OP numbers | Implemented | Implemented and tested. | `doctor-dictation/doctor_dictation/api/profile.py:65-75`<br>`doctor-dictation/doctor_dictation/db/opno.py` |
| DD-25 | Private share link & QR | Implemented | Token-masked logs; rate limit is in-memory per worker. | `doctor-dictation/doctor_dictation/api/share.py:67,93`<br>`doctor-dictation/doctor_dictation/api/share_public.py:29-30,108`<br>`doctor-dictation/doctor_dictation/pdf/qr.py` |
| DD-26 | Learned formulary & clinic list overlay | Implemented | Learned on Save (threshold 2); admin-only writes. | `doctor-dictation/doctor_dictation/api/formulary.py:125-135`<br>`doctor-dictation/doctor_dictation/api/lists.py:52,173`<br>`doctor-dictation/doctor_dictation/core/overlay.py` |
| DD-27 | Owner curation of shipped lists | Implemented | Changes stored in a JSON file, applied with 'admin apply-list-changes'. | `doctor-dictation/doctor_dictation/api/owner_lists.py:34,111-177`<br>`doctor-dictation/doctor_dictation/listchanges.py` |
| DD-28 | Doctor spoken terms & 'Your usual' | Implemented | Learned on Save; data-dependent so needs history to show. | `doctor-dictation/doctor_dictation/api/spoken.py:103-113`<br>`doctor-dictation/doctor_dictation/api/your_usual.py:66`<br>`doctor-dictation/doctor_dictation/core/your_usual.py` |
| DD-29 | Multi-clinic sign-in, sessions & isolation | Implemented | scrypt, HMAC-signed cookie, lockout 5/300s, revocation, CSRF header, per-clinic DB; 14 isolation test modules. Off by default — single mode has no auth and CORS '*'. | `doctor-dictation/doctor_dictation/api/session.py:21-70`<br>`doctor-dictation/doctor_dictation/sessions.py:69-89`<br>`doctor-dictation/doctor_dictation/api/app.py:81-87` |
| DD-30 | Roles, authorship & team admin | Implemented | Admin/author/owner rules enforced; the 'assistant' role has no distinct restrictions. | `doctor-dictation/doctor_dictation/policy.py:20-44`<br>`doctor-dictation/doctor_dictation/api/users.py:59-116` |
| DD-31 | Operator CLI, Docker/Caddy & VPS scripts | Implemented | Real scripts with stubbed-binary tests. 02-deploy.sh clones a separate upstream repo, not this monorepo. A live pilot is claimed in docs/working but not verifiable from code. | `doctor-dictation/doctor_dictation/admin.py:209-236`<br>`doctor-dictation/Dockerfile`<br>`doctor-dictation/scripts/deploy/02-deploy.sh:6` |
| DD-32 | Demo seed & browser walkthrough | Demo | Refuses to run on a non-empty data dir; published demo passwords. | `doctor-dictation/doctor_dictation/admin_demo.py`<br>`doctor-dictation/scripts/demo_browser.py:40-48` |
| DD-33 | STT benchmark | POC | CLI and metrics exist; only an example manifest, no audio. | `doctor-dictation/doctor_dictation/bench/run.py:11` |
| DD-34 | Government generics sync & promotion | Implemented | Offline tooling, tested. | `doctor-dictation/doctor_dictation/core/lexicon/generics_sync.py`<br>`doctor-dictation/doctor_dictation/promotion.py` |
| DD-35 | Patient / encounter CRUD routes | Deprecated | Mounted and tested, but the UI never calls them. | `doctor-dictation/doctor_dictation/api/persistence.py:60-89` |
| DD-36 | Health endpoint | Implemented | Public; exposes provider/model names and key presence booleans. | `doctor-dictation/doctor_dictation/api/health.py:16-66` |
| CG-01 | Ward seed & Demo dock (role, patient, clock, reset) | Demo | Role is client-side state (sessionStorage), not authentication. | `count-guard/frontend/src/care/DemoDock.jsx`<br>`count-guard/backend/app/journey/api.py:317,409`<br>`count-guard/frontend/src/care/ward.js:7-10` |
| CG-02 | Patient state machine & checklists | Implemented | clinic → admitting → ward ⇄ theatre → discharging → home; 409 on illegal moves. | `count-guard/backend/app/journey/states.py:19-38`<br>`count-guard/backend/app/journey/flow_api.py:41` |
| CG-03 | Dictated orders → draft → sign → acknowledge | Implemented | Offline: transcript from a prepared file chosen by file name; structuring falls back to rules without a key. | `count-guard/backend/app/journey/media_api.py:59-113`<br>`count-guard/backend/app/journey/flow_api.py:148-158`<br>`count-guard/backend/app/journey/dictation.py` |
| CG-04 | Demo prescription | Demo | Hard-coded demo rows. | `count-guard/backend/app/journey/api.py:241` |
| CG-05 | Import a Doctor Dictation prescription | Implemented | HTTP client implemented and tested; only the older screens call it. | `count-guard/backend/app/journey/rx.py:83,107`<br>`count-guard/backend/app/journey/api.py:224`<br>`count-guard/backend/tests/test_journey.py:213,229` |
| CG-06 | Nurse tasks with values & photo proof | Implemented | Task flow is real; photo reading uses prepared fixtures offline. | `count-guard/backend/app/journey/tasks.py`<br>`count-guard/backend/app/journey/proof.py`<br>`count-guard/backend/app/journey/flow_api.py:163-168` |
| CG-07 | Observations vs limits → named alert | Implemented | Rule-based nudges raised on every write. | `count-guard/backend/app/journey/nudges.py`<br>`count-guard/frontend/src/care/AlertCard.jsx:39` |
| CG-08 | Swab count hard stop | Implemented | Enforced on the server: pack count only goes up after surgery began; closing must follow 'began', be saved by a person, add up or carry a reason; camera read never auto-fills. Tested in test_count_gate.py. | `count-guard/backend/app/journey/states.py:95-110`<br>`count-guard/backend/app/journey/flow_api.py:68-76`<br>`count-guard/backend/app/journey/count_api.py:53-88` |
| CG-09 | Tray & saline set-up video checks | Mock | Comparison logic is real, but detections come from hand-made JSON fixtures picked by uploaded file name. Live SAM path coded, never run with a key. | `count-guard/backend/app/journey/video_api.py:21-23,152-227`<br>`count-guard/backend/app/journey/live.py:87-100`<br>`count-guard/backend/app/journey/prepared/tray-hernia.json` |
| CG-10 | Swab camera count (assist) | Mock | Prepared fixture swabs-closing.json; never seeds the gate on its own. | `count-guard/backend/app/journey/prepared/swabs-closing.json`<br>`count-guard/backend/app/journey/count_api.py:84-87` |
| CG-11 | Medicine strip photo vs prescription | Mock | Mismatch logic real; photo read from prepared strip-*.json. | `count-guard/backend/app/journey/media_api.py:266-280` |
| CG-12 | Patient 'medicines from home' photo → day plan | Mock | Prepared meds-*.json; MEDICINES_LIVE flag. | `count-guard/backend/app/journey/ask_api.py:32,171-199`<br>`count-guard/backend/app/journey/medicines.py` |
| CG-13 | Patient Ask: record bot, ask the doctor, photo review | Implemented | Rules-first bot; Spark rewords only with a key. | `count-guard/backend/app/journey/ask_api.py:77-221`<br>`count-guard/backend/app/journey/ask.py` |
| CG-14 | Discharge: dictate → sign → checks → home | Implemented | Flow real; transcript prepared offline. | `count-guard/backend/app/journey/media_api.py:113`<br>`count-guard/backend/app/journey/flow_api.py:181` |
| CG-15 | Doctor status chip | Implemented | Implemented. | `count-guard/backend/app/journey/staff_api.py:58,72`<br>`count-guard/backend/app/journey/doctor_status.py` |
| CG-16 | 'Now' card ranking & waiting pills | Implemented | Pure frontend logic with unit tests. | `count-guard/frontend/src/care/rank.js`<br>`count-guard/frontend/src/care/now.js`<br>`count-guard/frontend/src/care/derive.js` |
| CG-17 | AI admin: act, Undo, approve, Pause | Implemented | Rule-based planner (model 'rules'), policy levels with 'Never' list, 10-minute Undo, runs synchronously inside each write. | `count-guard/backend/app/ops/policy.py:7-27`<br>`count-guard/backend/app/ops/run.py:79-98`<br>`count-guard/backend/app/journey/api.py:153-163` |
| CG-18 | Inspector (Why / Evidence / History / Model) | Implemented | Patient sees Why and Evidence only. | `count-guard/frontend/src/care/Inspector.jsx`<br>`count-guard/backend/app/journey/ai_api.py:28`<br>`count-guard/backend/app/journey/evidence.py` |
| CG-19 | AI activity page & 'Try sample' | Demo | Summary is real provenance; Try sample runs bundled samples, and spark-open always returns prepared text even with a key. | `count-guard/frontend/src/care/AiDashboard.jsx`<br>`count-guard/backend/app/journey/ai_api.py:56-130` |
| CG-20 | Nurse handover draft | Implemented | Works; only the older screens call it. | `count-guard/backend/app/journey/handover.py`<br>`count-guard/backend/app/journey/api.py:337-372` |
| CG-21 | Reminders (.ics), check-in, help | Implemented | Works; only the older screens call it. | `count-guard/backend/app/journey/schedule.py`<br>`count-guard/backend/app/journey/api.py:270-395` |
| CG-22 | Three-act scripted journey play | Deprecated | Retired from menus (spec D15). | `count-guard/backend/app/journey/play.py`<br>`count-guard/frontend/src/care/older.js` |
| CG-23 | Morning timeline: brown-bag, drug log, vitals sim, discharge PDF/ICS | Deprecated | Functional and tested but superseded by the care app; /morning has no nav link. | `count-guard/backend/app/morning/api.py:73-310`<br>`count-guard/backend/app/morning/routes_extra.py` |
| CG-24 | Decision-tier fact card toggle | Deprecated | Runtime toggle has no authentication, contradicting the documented 'admin only, audited' design. | `count-guard/backend/app/morning/api.py:73-81`<br>`docs/hackathon/02-architecture.md` |
| CG-25 | Camera case: zones, rules R1–R6, discrepancies, close gate | Deprecated | Runs on scripted detections only (scenarios.py); 'every count shown is scripted replay'. | `count-guard/backend/app/core/rules.py:17-338`<br>`count-guard/backend/app/engine.py`<br>`count-guard/backend/app/api/routes.py:70-253`<br>`count-guard/README.md:282` |
| CG-26 | Discrepancy narrative (Spark Open reconciler) | POC | Tool-loop agent with verifier and retry; never called live ('not yet called from this machine'). | `count-guard/backend/app/agent/reconciler.py:26-60`<br>`count-guard/backend/app/api/routes.py:56` |
| CG-27 | PDF count sheet | Deprecated | fpdf, separate from DD's Chromium renderer. | `count-guard/backend/app/report/count_sheet.py` |
| CG-28 | Real-video SAM pipeline & live WebSocket | POC | Never exercised with a key; WS has tests but no frontend caller. | `count-guard/backend/app/media_pipeline.py`<br>`count-guard/backend/app/api/ws.py:20` |
| CG-29 | Headless demo-check (32 beats) | Demo | Generates synthetic media, empties keys, plays 32 beats, scans product text, saves demo-shots/*.png. | `count-guard/Makefile`<br>`count-guard/frontend/scripts/demo/run.mjs:60-100`<br>`count-guard/frontend/scripts/demo/beats.mjs` |
| CG-30 | Evaluation: scripted clips & ops replay | Implemented | Measures rules on scripted clips, not SAM accuracy. | `count-guard/eval/run_eval.py`<br>`count-guard/eval/replay_ops.py`<br>`count-guard/README.md:287` |
| CG-31 | Fixture recorder | POC | Never run per README. | `count-guard/eval/record_fixtures.py` |
| CG-32 | Spark-only baseline scoring | Stub | Raises NotImplementedError — the only TODO in the repo. | `count-guard/backend/app/baseline.py:66-67` |
| CG-33 | Day-1 API check & SAM cost estimator | POC | Estimator only, no runtime metering. | `count-guard/backend/app/day1.py`<br>`count-guard/backend/app/spend.py:1-8` |
| CG-34 | Feature guide page | Deprecated | Superseded by the care app and README. | `count-guard/backend/app/site.py:139`<br>`count-guard/backend/app/morning/guide.py` |

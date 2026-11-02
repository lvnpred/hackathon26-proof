# Product Inventory

> Snapshot of `main` @ `90e0f56`, generated 2026-11-02. Companion to [index.html](index.html) — same data, same numbers.

## Summary

- **What this repo is:** a monorepo hosting **two apps** that share one `.env`, one Makefile and the Meta Muse model key, and since 2 Nov form **one patient flow** (`docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md:6-21`). Separate servers, databases and code.
- **Product 1 — Doctor Dictation:** OPD voice → structured, safety-checked prescription → PDF and share link, or **Save & admit to ward** → Count Guard. Shipping-shaped: multi-clinic tenancy, Docker/Caddy deploy, 3,361 tests. Safety *data* is partly missing; admit is single-clinic only.
- **Product 2 — Count Guard care app "Ward 4"** plus its **AI admin ops agent:** one append-only timeline per patient from intake through ward, theatre and discharge, with a server-enforced swab-count hard stop. Research demo: no auth, no deploy. Every AI step has a live switch; live calls answered on 2 Nov, but the demo default is prepared results, labelled.
- **Archived:** the three earlier generations (camera swab counter, morning timeline, journey v1) had every feature moved into the care app; their 44 screen, route and test files sit in `count-guard/archive/`, unmounted. A demo layer and research POCs remain.
- **Integration:** DD pushes each admission to `POST /journey/intake` after Save; CG **Sync** pulls `GET /api/v1/admissions` as a backup (`doctor-dictation/doctor_dictation/api/admit.py:101-178`, `count-guard/backend/app/journey/intake.py`).

**Decision needed:** confirm the two apps and the one patient flow as the submission boundary, and whether the live swab camera is filmed on a prop tray or shown as Prepared.

## Headline numbers

| Metric | Value | Breakdown |
| --- | --- | --- |
| Products | 2 | Doctor Dictation; Count Guard care app + AI admin agent |
| Patient flow across both apps | 1 | DD Save & admit → CG ward → theatre → discharge |
| Tracked files | 1,248 | DD 698 · CG 496 (44 in archive/) · docs 50 · root 4 |
| Lines of app code (excl. tests, archive) | ≈49.8k | DD ≈24.4k (Python 18.4k + JS 5.9k) · CG ≈25.4k (Python 16.0k + React 8.4k + demo scripts 0.9k) |
| HTTP endpoints | ≈151 | DD ≈56 · CG ≈95 (incl. 1 WebSocket, 2 SSE) |
| Automated tests | 4,809 | DD 3,361 · CG 921 backend + ≈470 UI logic + 57 demo-harness |
| Commits | 286 | 2026-10-13 → 2026-11-02; 23 in the consolidation |
| TODO / FIXME markers | 1 | count-guard/backend/app/baseline.py:66 |

## Product hierarchy

- **hackathon26 workspace** — Shared, Implemented
  - **Doctor Dictation (Lightday Rx)** — Product, Implemented
    - **Capture** — Module, Implemented
    - **Structuring** — Module, Implemented
    - **Medication safety** — Module, Partial
    - **Clinical fields** — Module, Partial
    - **Records & output** — Module, Implemented
    - **Admit to ward (→ Count Guard)** — Module, Implemented
    - **Clinic learning** — Module, Implemented
    - **Access & tenancy** — Module, Implemented
    - **Operations** — Shared, Implemented
    - **DD demo & tooling** — Demo, Demo
  - **Count Guard** — Product, Implemented
    - **Care app 'Ward 4'** — Product, Implemented
      - **Ward list, intake & Sync** — Module, Implemented
      - **Patient flow** — Module, Implemented
      - **Orders, tasks & ward care** — Module, Implemented
      - **Photo proofs & verdicts** — Module, Implemented
      - **Theatre** — Module, Implemented
      - **Swab count hard stop** — Module, Implemented
      - **Discharge** — Module, Implemented
      - **Video, photo & voice reads** — Module, Mock
      - **Observations & alerts** — Module, Implemented
      - **Patient Ask** — Module, Implemented
      - **Inspector, correction & Help** — Module, Implemented
    - **AI admin ops agent** — Module, Implemented
    - **Care platform kernel** — Platform, Implemented
    - **Archive (camera counter, morning, journey v1)** — Legacy, Deprecated
    - **Demo & showcase layer** — Demo, Demo
    - **Research POCs** — POC, POC, legacy
  - **DD → CG patient flow** — Shared, Implemented
  - **Design docs & specs** — Shared, Partial

## Inventory

Every significant item, its classification and where it lives.

| Name | Category | Status | Parent | Description | Users | Source |
| --- | --- | --- | --- | --- | --- | --- |
| hackathon26 workspace | Shared | Implemented (Current) | — | A monorepo that hosts two separate apps (own servers, own databases) sharing one .env, one Makefile and the Meta Muse model key. Since 2 Nov they form one patient flow: a Doctor Dictation clinic visit saved with 'Save & admit to ward' becomes a Count Guard ward patient. | Developers, hackathon judges | `README.md`<br>`Makefile`<br>`.env.example` |
| Doctor Dictation (Lightday Rx) | Product | Implemented (Current) | hackathon26 workspace | Voice-to-prescription web app for Indian outpatient clinics. Doctor dictates the visit → STT → LLM drafts a structured sheet → deterministic grounding and safety checks → verify gate → Save (send home, or Save & admit to ward) → PDF on clinic letterhead, with QR share link. | OPD doctors, clinic assistants, clinic admin, app owner | `doctor-dictation/doctor_dictation/`<br>`doctor-dictation/frontend/` |
| Capture | Module | Implemented | Doctor Dictation (Lightday Rx) | Browser recording, STT provider chain (OpenAI, Groq, AssemblyAI, Meta Muse, local faster-whisper), vocabulary hints, silence trim. |  | `doctor-dictation/doctor_dictation/api/stt.py`<br>`doctor-dictation/doctor_dictation/providers/stt/`<br>`doctor-dictation/doctor_dictation/audio/` |
| Structuring | Module | Implemented | Doctor Dictation (Lightday Rx) | LLM extract → ground → repair loop, deterministic normalisation and cache, offline rules fallback, spoken corrections, spelled names. |  | `doctor-dictation/doctor_dictation/api/format.py`<br>`doctor-dictation/doctor_dictation/core/determinism.py`<br>`doctor-dictation/doctor_dictation/core/fallback.py` |
| Medication safety | Module | Partial | Doctor Dictation (Lightday Rx) | Lexicon (448 entries), per-row grounding pills, LASA guard (8 unreviewed pairs), dose check (no data ships), verify gate on Save. |  | `doctor-dictation/doctor_dictation/core/rowcheck.py`<br>`doctor-dictation/doctor_dictation/core/lasa.py`<br>`doctor-dictation/doctor_dictation/core/dosing.py`<br>`doctor-dictation/doctor_dictation/core/safety.py` |
| Clinical fields | Module | Partial | Doctor Dictation (Lightday Rx) | Vitals grounding, investigations (catalogue missing), follow-up date, sections, prose tidy. |  | `doctor-dictation/doctor_dictation/core/vitals.py`<br>`doctor-dictation/doctor_dictation/core/investigations.py`<br>`doctor-dictation/doctor_dictation/core/followup.py` |
| Records & output | Module | Implemented | Doctor Dictation (Lightday Rx) | Save/reopen, Today list, past-day lock, Chromium PDF, letterhead-from-photo, OP numbers, share link + QR. |  | `doctor-dictation/doctor_dictation/api/persistence.py`<br>`doctor-dictation/doctor_dictation/pdf/`<br>`doctor-dictation/doctor_dictation/templates/`<br>`doctor-dictation/doctor_dictation/api/share.py` |
| Admit to ward (→ Count Guard) | Module | Implemented | Doctor Dictation (Lightday Rx) | New 2 Nov. 'Save & admit to ward' with a required reason; an admissions table; a background push to Count Guard's /journey/intake after the commit (1 s connect / 3 s total); GET /api/v1/admissions for CG Sync; single-clinic only (404 in multi-clinic). |  | `doctor-dictation/doctor_dictation/api/admit.py`<br>`doctor-dictation/doctor_dictation/db/migrations/015_admissions.sql`<br>`doctor-dictation/frontend/admit.js` |
| Clinic learning | Module | Implemented | Doctor Dictation (Lightday Rx) | Learned clinic formulary, clinic list overlay, owner list curation, doctor spoken terms, 'Your usual'. |  | `doctor-dictation/doctor_dictation/api/formulary.py`<br>`doctor-dictation/doctor_dictation/core/overlay.py`<br>`doctor-dictation/doctor_dictation/api/spoken.py`<br>`doctor-dictation/doctor_dictation/api/your_usual.py` |
| Access & tenancy | Module | Implemented | Doctor Dictation (Lightday Rx) | Multi-clinic mode (off by default): scrypt login, signed session cookie, lockout, revocation, per-clinic DB, roles, authorship, team admin. |  | `doctor-dictation/doctor_dictation/api/session.py`<br>`doctor-dictation/doctor_dictation/sessions.py`<br>`doctor-dictation/doctor_dictation/directory/`<br>`doctor-dictation/doctor_dictation/policy.py` |
| Operations | Shared | Implemented | Doctor Dictation (Lightday Rx) | Operator CLI, Docker + Caddy, VPS harden/deploy/backup/restore-drill scripts. |  | `doctor-dictation/doctor_dictation/admin.py`<br>`doctor-dictation/Dockerfile`<br>`doctor-dictation/docker-compose.yml`<br>`doctor-dictation/scripts/deploy/` |
| DD demo & tooling | Demo | Demo | Doctor Dictation (Lightday Rx) | seed-demo (DEMO_MODE=1), DEMO_BANNER research-demo banner, Playwright browser walkthrough, stub providers, STT benchmark (POC, no clips), ONNX STT (stub). |  | `doctor-dictation/doctor_dictation/admin_demo.py`<br>`doctor-dictation/frontend/demobanner.js`<br>`doctor-dictation/scripts/demo_browser.py`<br>`doctor-dictation/doctor_dictation/bench/` |
| Count Guard | Product | Implemented (Current) | hackathon26 workspace | One FastAPI app + one React app for one product: the 'Ward 4' care app with the AI admin ops agent. Since 2 Nov every feature of the older generations (camera counter, morning timeline, journey v1) lives in the care app; their screens and route files sit in count-guard/archive/, unmounted. Libraries they used (morning/, core/, engine.py, report/, agent/) stay in place because the care app imports them. | Ward doctor, nurse, theatre nurse, patient (synthetic data, research demo) | `count-guard/backend/app/`<br>`count-guard/frontend/src/` |
| Care app 'Ward 4' | Product | Implemented (Current) | Count Guard | Doctor, nurse and patient share one append-only timeline per patient: server ward list, intake from DD, state machine, orders and tasks, photo proofs with verdicts, theatre (drug by voice, vitals, context card, swab camera), swab-count hard stop, discharge drafted from the timeline, patient Ask, Inspector, Help. |  | `count-guard/backend/app/journey/`<br>`count-guard/frontend/src/care/` |
| Ward list, intake & Sync | Module | Implemented | Care app 'Ward 4' | Server-owned ward list and demo clock; one intake path for a DD push, Sync (pull from DD) and New patient; idempotent per (source, document_id); SSE ward stream. |  | `count-guard/backend/app/journey/ward_api.py`<br>`count-guard/backend/app/journey/intake.py`<br>`count-guard/backend/app/journey/sync.py`<br>`count-guard/backend/app/journey/clock.py` |
| Patient flow | Module | Implemented | Care app 'Ward 4' | clinic → admitting → ward ⇄ theatre → discharging → home with checklists; 409 with a plain reason on illegal moves; admission and discharge stay open while a photo check is not accepted. |  | `count-guard/backend/app/journey/states.py`<br>`count-guard/backend/app/journey/flow_api.py`<br>`count-guard/backend/app/journey/check_gate.py` |
| Orders, tasks & ward care | Module | Implemented | Care app 'Ward 4' | Dictate/type → draft → sign → acknowledge; tasks with values and photo proof; handover, dose given, reminders, check-in (moved from journey v1). |  | `count-guard/backend/app/journey/dictation.py`<br>`count-guard/backend/app/journey/tasks.py`<br>`count-guard/backend/app/journey/api.py:272-401` |
| Photo proofs & verdicts | Module | Implemented | Care app 'Ward 4' | Accepted / Not accepted / Not checked per checklist photo; an open item needs a retake or a typed override (U9). Spark vision when PROOF_LIVE, else a prepared verdict chosen by the photo's bytes. |  | `count-guard/backend/app/journey/verdict.py`<br>`count-guard/backend/app/journey/verdict_api.py` |
| Theatre | Module | Implemented | Care app 'Ward 4' | Drug given and packs heard by voice (a person confirms), simulated vitals strip, research-tier context card, swab camera with rules R1–R6 as advice, missing-swab last frame, replay, bucket-dwell, resolve, close, count-sheet PDF. |  | `count-guard/backend/app/journey/theatre_api.py`<br>`count-guard/backend/app/journey/camera_api.py`<br>`count-guard/backend/app/journey/camera_close_api.py`<br>`count-guard/backend/app/journey/advice.py` |
| Swab count hard stop | Module | Implemented | Care app 'Ward 4' | Surgery cannot end until a person saves a closing count that adds up or gives a reason; camera and rules are advice only and never fill it. count_gate is unchanged; a route sweep proves no other write route can close the count. |  | `count-guard/backend/app/journey/states.py:95-109`<br>`count-guard/backend/app/journey/count_api.py`<br>`count-guard/backend/tests/test_route_sweep.py` |
| Discharge | Module | Implemented | Care app 'Ward 4' | Draft discharge from the timeline (DD prescription, drugs given, count), dictate changes, sign, discharge PDF + follow-up .ics, discharge card in the patient view. |  | `count-guard/backend/app/journey/discharge_draft.py`<br>`count-guard/backend/app/journey/discharge_api.py` |
| Video, photo & voice reads | Module | Mock | Care app 'Ward 4' | Tray, saline set-up, swab camera, medicines from home, voice. Every step has a live switch; one live call per model succeeded on 2 Nov, but the demo default (and demo-check) is prepared results, labelled 'Prepared'. |  | `count-guard/backend/app/journey/switches.py`<br>`count-guard/backend/app/journey/live.py`<br>`count-guard/backend/app/journey/prepared/` |
| Observations & alerts | Module | Implemented | Care app 'Ward 4' | Obs vs doctor-set limits → named alert → 'What did you do?'. |  | `count-guard/backend/app/journey/nudges.py`<br>`count-guard/frontend/src/care/AlertCard.jsx` |
| Patient Ask | Module | Implemented | Care app 'Ward 4' | Record-grounded bot, question to doctor, healing-photo review, doctor voice answer with decision. |  | `count-guard/backend/app/journey/ask.py`<br>`count-guard/backend/app/journey/ask_api.py` |
| Inspector, correction & Help | Module | Implemented | Care app 'Ward 4' | Why / Evidence / History / Model per row, camera evidence, Correct (supersedes) for typed obs and theatre drug lines, staff AI activity page, Help page. |  | `count-guard/frontend/src/care/Inspector.jsx`<br>`count-guard/backend/app/journey/correct_api.py`<br>`count-guard/frontend/src/care/Help.jsx` |
| AI admin ops agent | Module | Implemented (Current) | Count Guard | watch → plan → policy gate → apply inside every write; L3/L2 act (10-min Undo), L1 propose, 'Never' for prescribe/dose/advise/clear count/discharge; Pause. Rule-based; optional Spark rewording. |  | `count-guard/backend/app/ops/` |
| Care platform kernel | Platform | Implemented (Current) | Count Guard | Episode + append-only event store with supersede corrections (morning.db), visible_events, the live/prepared seam and switches, four model adapters, advice-word verifier, and the camera libraries the theatre now reuses (core/ tracker, rules, ledger; engine.py; report/). Still spread across morning/, journey/, adapters/, agent/, core/. |  | `count-guard/backend/app/morning/store.py`<br>`count-guard/backend/app/journey/live.py`<br>`count-guard/backend/app/adapters/`<br>`count-guard/backend/app/agent/verifier.py`<br>`count-guard/backend/app/core/` |
| Archive (camera counter, morning, journey v1) | Legacy | Deprecated (Archived) | Count Guard | 44 files moved with git mv on 2 Nov: 21 old React screens, morning/api.py, routes_extra.py, script.py, sim.py, camera_file.py, care_guard.py, api/routes.py, api/ws.py, journey/play.py, and their tests. Not imported, not mounted; the set is computed from the import graph. |  | `count-guard/archive/`<br>`count-guard/scripts/archive_set.py`<br>`count-guard/backend/tests/test_archive.py` |
| Demo & showcase layer | Demo | Demo (Current) | Count Guard | DemoDock (role, patient, clock, reset), seed, demo prescription, Try sample, prepared fixtures, generated demo media, the two-app 20-beat demo-check (180 s), make live-check, eval scripts. |  | `count-guard/frontend/src/care/DemoDock.jsx`<br>`count-guard/backend/app/journey/seed.py`<br>`count-guard/frontend/scripts/demo/`<br>`count-guard/backend/app/live_check.py`<br>`count-guard/eval/` |
| Research POCs | POC | POC (Legacy) | Count Guard | Spark-only baseline (NotImplementedError), day-1 API check, SAM cost estimator, fixture recorder. |  | `count-guard/backend/app/baseline.py`<br>`count-guard/backend/app/day1.py`<br>`count-guard/backend/app/spend.py`<br>`count-guard/eval/record_fixtures.py` |
| DD → CG patient flow | Shared | Implemented | hackathon26 workspace | Push: DD Save & admit → admissions row → background POST /journey/intake. Pull: CG Sync → DD GET /api/v1/admissions. Optional shared CG_SYNC_TOKEN header. Separate servers and databases; no shared code. |  | `doctor-dictation/doctor_dictation/api/admit.py:101-178`<br>`count-guard/backend/app/journey/intake_api.py:78-111`<br>`count-guard/backend/app/journey/sync.py` |
| Design docs & specs | Shared | Partial | hackathon26 workspace | docs/hackathon (21 Oct umbrella plan, mostly superseded), docs/superpowers (Count Guard specs and plans incl. the 2 Nov patient-flow spec), demo video scripts. |  | `docs/hackathon/`<br>`docs/superpowers/`<br>`docs/demo/dd-cg-flow-video-script.md` |

## Evidence for the top-level classification

- **hackathon26 workspace:** `README.md:3 — 'Two apps in one repo… They share one .env and run on separate ports.'`; `docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md:6-21 — one patient, two apps`; `Makefile:32-37 — make dev runs both`
- **Doctor Dictation (Lightday Rx):** `doctor-dictation/doctor_dictation/api/format.py:126-214 (format pipeline)`; `doctor-dictation/doctor_dictation/api/persistence.py:198-235 (verify gate)`; `doctor-dictation/doctor_dictation/api/persistence.py:147-148,360-361 (admit on Save)`
- **Count Guard:** `count-guard/backend/app/main.py:58-84 (26 routers, all care app)`; `count-guard/frontend/src/App.jsx:34-44 (care routes only)`; `count-guard/README.md:121-123 (Archived screens)`

## Features per product and status

| Product | Implemented | Partial | Demo | POC | Mock | Stub | Planned | Deprecated | Unknown | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Doctor Dictation | 29 | 4 | 2 | 1 | 0 | 1 | 1 | 1 | 0 | 39 |
| Count Guard | 28 | 1 | 4 | 3 | 6 | 1 | 0 | 2 | 0 | 45 |
| **All** | 57 | 5 | 6 | 4 | 6 | 2 | 1 | 3 | 0 | 84 |

## Repository map

- `hackathon26/` — Monorepo: two apps, one patient flow, shared .env and Makefile *(Workspace, Implemented)*
  - `README.md · Makefile · .env.example` — How to set up, run and test both apps; ports and the shared model key *(Workspace, Implemented)*
  - `docs/` — Cross-app plans and Count Guard design history *(Docs, Partial)*
    - `hackathon/ (01–07)` — 21–28 Oct umbrella plan (one timeline inside DD). Mostly superseded; no marker yet. *(Docs, Deprecated)*
    - `superpowers/specs, plans` — 11 specs + 16 plans, ending with the 2 Nov DD → CG patient-flow spec and plan (§9 feature map, row → test appendix) *(Count Guard, Implemented)*
    - `demo/dd-cg-flow-video-script.md` — Current 3:00 judges' video, 20 beats, kept in step with beats.mjs by doc.test.mjs *(Both, Demo)*
    - `demo/count-guard-v2-video-script.md` — Earlier 32-beat Count Guard-only script *(Count Guard, Deprecated)*
    - `product-overview/` — This overview *(Docs, Implemented)*
  - `doctor-dictation/` — Doctor Dictation product (698 files) *(Doctor Dictation, Implemented)*
    - `doctor_dictation/api/` — 20 FastAPI routers + session middleware; admit.py pushes admissions to Count Guard *(Doctor Dictation, Implemented)*
    - `doctor_dictation/core/` — Pure offline rules: normalisation, grounding, LASA, dosing, vitals, investigations, learning *(Doctor Dictation, Implemented)*
    - `doctor_dictation/core/lexicon/` — Drug data (448) + builders; dosing empty, investigations missing, LASA unreviewed *(Doctor Dictation, Partial)*
    - `doctor_dictation/db/, directory/` — sqlite3 repositories, 15 clinic migrations (015 admissions) + directory *(Doctor Dictation, Implemented)*
    - `doctor_dictation/providers/` — LLM (OpenAI-compatible + stub) and STT (5 real + onnx/browser/stub) *(Doctor Dictation, Implemented)*
    - `doctor_dictation/pdf/, templates/` — Chromium PDF, QR, letterhead-from-photo *(Doctor Dictation, Implemented)*
    - `doctor_dictation/bench/` — STT benchmark CLI, no clips *(Doctor Dictation, POC)*
    - `frontend/` — Vanilla JS SPA, admit.js, demobanner.js, login page, fonts *(Doctor Dictation, Implemented)*
    - `tests/` — 245 test modules, 3,361 tests; isolation, deploy, admit and load suites *(Doctor Dictation, Implemented)*
    - `Dockerfile, docker-compose.yml, Caddyfile, scripts/deploy/` — Container, HTTPS proxy, VPS harden/deploy/backup *(Doctor Dictation, Implemented)*
    - `docs/` — Runbooks, Lightday design system, plans, working notes *(Doctor Dictation, Partial)*
  - `count-guard/` — Count Guard (496 files) — one care app + ops agent, plus an archive *(Count Guard, Implemented)*
    - `backend/app/journey/` — Care app: ward, intake, Sync, flow, verdicts, theatre, camera, count, discharge, ask, stream, correct, AI routers; switches; prepared fixtures *(Count Guard, Implemented)*
    - `backend/app/ops/` — AI admin ops agent *(Count Guard, Implemented)*
    - `backend/app/morning/` — No routes any more: the event store plus helpers the theatre and discharge reuse (druglog, vitals, pdf, ics, count_rules) *(Count Guard, Implemented)*
    - `backend/app/core/, engine.py, scenarios.py, report/, store.py` — Camera tracker, rules R1–R6, ledger, count sheet — now libraries for the theatre camera *(Count Guard, Implemented)*
    - `backend/app/agent/` — Advice verifier (ops, handover) and reconciler (camera close explanation) *(Count Guard, Implemented)*
    - `backend/app/adapters/` — SAM, Voice, Spark 1.3, Spark Open HTTP clients *(Count Guard, Implemented)*
    - `backend/app/live_check.py` — make live-check: one real call per model *(Count Guard, Implemented)*
    - `backend/app/baseline.py, day1.py, spend.py, media_pipeline.py` — Research POCs (baseline is a stub); media_pipeline serves the live camera *(Count Guard, POC)*
    - `backend/tests/` — 81 files, 921 tests incl. test_route_sweep.py and test_archive.py *(Count Guard, Implemented)*
    - `frontend/src/care/` — The only UI (181 files, 50 logic test files) *(Count Guard, Implemented)*
    - `frontend/scripts/demo/` — Two-app demo-check harness (20 beats, 180 s) *(Both, Demo)*
    - `archive/` — 44 archived files: old screens, morning/api.py, routes_extra.py, api/routes.py, api/ws.py, play.py, script.py, sim.py and their tests *(Count Guard, Deprecated)*
    - `scripts/archive_set.py` — Computes the archive set from the import graph *(Count Guard, Implemented)*
    - `eval/` — Media generators and SOURCES.md, scripted clip eval, ops replay, fixture recorder *(Count Guard, Demo)*
    - `docs/` — architecture.md (camera counter only), new-work.md, loop state *(Count Guard, Partial)*

## Coverage and method

Refreshed on 2026-11-02 after the Doctor Dictation → Count Guard consolidation (23 commits e40d8c7..90e0f56). Read-only inspection of all 1,248 tracked files against the patient-flow spec (docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md §9) and its plan appendix (§9 row → test); every named test was confirmed to exist. Test counts are from pytest --collect-only and a count of node test() calls; no servers were started and no tests were run for this refresh. The live-check and demo-check results quoted are the runs logged on 2026-11-02. No secrets were read. All 1,248 tracked files were in scope; git-ignored local data (databases, generated media, live-check artifacts, `.env`) was not opened.

**Not done:** no tests were executed and no app was started for this refresh, and no application code was changed.

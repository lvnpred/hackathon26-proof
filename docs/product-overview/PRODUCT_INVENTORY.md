# Product Inventory

> Snapshot of `main` @ `e40d8c7`, generated 2026-11-01. Companion to [index.html](index.html) — same data, same numbers.

## Summary

- **What this repo is:** a monorepo hosting **two independent products** that share one `.env`, one Makefile and the Meta Muse model key. There is no umbrella product in code (`README.md:3`).
- **Product 1 — Doctor Dictation:** OPD voice → structured, safety-checked prescription → PDF and share link. Shipping-shaped: multi-clinic tenancy, Docker/Caddy deploy, 3,338 tests. Safety *data* is partly missing.
- **Product 2 — Count Guard care app "Ward 4"** plus its **AI admin ops agent:** one append-only timeline per patient shared by doctor, nurse and patient, with a server-enforced swab-count hard stop. Research demo: no auth, no deploy, all model output is prepared fixtures.
- **Not the product:** inside `count-guard/` three earlier generations (camera swab counter, morning timeline, journey v1) are still mounted, plus a demo layer and research POCs.
- **Only integration:** Count Guard reads a saved Doctor Dictation document over HTTP (`count-guard/backend/app/journey/rx.py:83-107`).

**Decision needed:** confirm the two products above as the official product boundary, and that the three Count Guard generations are archive.

## Headline numbers

| Metric | Value | Breakdown |
| --- | --- | --- |
| Shipping products | 2 | Doctor Dictation; Count Guard care app |
| Legacy products inside Count Guard | 3 | camera counter, morning timeline, journey v1 |
| Tracked files | 1,117 | DD 691 · CG 390 · docs 32 · root 4 |
| Lines of app code (excl. tests) | ≈48k | DD ≈24k (Python 17.1k + JS 7.1k) · CG ≈24k (Python 12.9k + React 10.6k + demo scripts 0.9k) |
| HTTP endpoints | ≈148 | DD ≈53 · CG ≈95 (incl. 1 WebSocket, 1 SSE) |
| Automated tests | 4,509 | DD 3,338 · CG 704 backend + ≈420 UI logic + 47 demo-harness |
| Commits | 262 | 2026-10-13 → 2026-11-01; 194 in the last 4 days |
| TODO / FIXME markers | 1 | count-guard/backend/app/baseline.py:66 |

## Product hierarchy

- **hackathon26 workspace** — Shared, Implemented
  - **Doctor Dictation (Lightday Rx)** — Product, Implemented
    - **Capture** — Module, Implemented
    - **Structuring** — Module, Implemented
    - **Medication safety** — Module, Partial
    - **Clinical fields** — Module, Partial
    - **Records & output** — Module, Implemented
    - **Clinic learning** — Module, Implemented
    - **Access & tenancy** — Module, Implemented
    - **Operations** — Shared, Implemented
    - **DD demo & tooling** — Demo, Demo
  - **Count Guard** — Product, Partial
    - **Care app 'Ward 4' (generation D)** — Product, Implemented
      - **Patient flow** — Module, Implemented
      - **Orders & nurse tasks** — Module, Implemented
      - **Swab count hard stop** — Module, Implemented
      - **Video & photo checks** — Module, Mock
      - **Observations & alerts** — Module, Implemented
      - **Patient Ask** — Module, Implemented
      - **Inspector & AI activity** — Module, Implemented
    - **AI admin ops agent (generation E)** — Module, Implemented
    - **Care platform kernel** — Platform, Implemented
    - **Camera swab counter (generation A, v1)** — Legacy, Deprecated, legacy
    - **Morning timeline (generation B)** — Legacy, Deprecated, legacy
    - **Care journey v1 (generation C)** — Legacy, Deprecated, legacy
    - **Demo & showcase layer** — Demo, Demo
    - **Research POCs** — POC, POC, legacy
  - **DD → CG prescription link** — Shared, Implemented
  - **Design docs & specs** — Shared, Partial

## Inventory

Every significant item, its classification and where it lives.

| Name | Category | Status | Parent | Description | Users | Source |
| --- | --- | --- | --- | --- | --- | --- |
| hackathon26 workspace | Shared | Implemented (Current) | — | Not a product. A monorepo that hosts two independent apps sharing one .env, one Makefile and the Meta Muse model key. No umbrella product exists in code. | Developers | `README.md`<br>`Makefile`<br>`.env.example` |
| Doctor Dictation (Lightday Rx) | Product | Implemented (Current) | hackathon26 workspace | Voice-to-prescription web app for Indian outpatient clinics. Doctor dictates the visit → STT → LLM drafts a structured sheet → deterministic grounding and safety checks → verify gate → Save → PDF on clinic letterhead, with QR share link. | OPD doctors, clinic assistants, clinic admin, app owner | `doctor-dictation/doctor_dictation/`<br>`doctor-dictation/frontend/` |
| Capture | Module | Implemented | Doctor Dictation (Lightday Rx) | Browser recording, STT provider chain (OpenAI, Groq, AssemblyAI, Meta Muse, local faster-whisper), vocabulary hints, silence trim. |  | `doctor-dictation/doctor_dictation/api/stt.py`<br>`doctor-dictation/doctor_dictation/providers/stt/`<br>`doctor-dictation/doctor_dictation/audio/` |
| Structuring | Module | Implemented | Doctor Dictation (Lightday Rx) | LLM extract → ground → repair loop, deterministic normalisation and cache, offline rules fallback, spoken corrections, spelled names. |  | `doctor-dictation/doctor_dictation/api/format.py`<br>`doctor-dictation/doctor_dictation/core/determinism.py`<br>`doctor-dictation/doctor_dictation/core/fallback.py` |
| Medication safety | Module | Partial | Doctor Dictation (Lightday Rx) | Lexicon (448 entries), per-row grounding pills, LASA guard (8 unreviewed pairs), dose check (no data ships), verify gate on Save. |  | `doctor-dictation/doctor_dictation/core/rowcheck.py`<br>`doctor-dictation/doctor_dictation/core/lasa.py`<br>`doctor-dictation/doctor_dictation/core/dosing.py`<br>`doctor-dictation/doctor_dictation/core/safety.py` |
| Clinical fields | Module | Partial | Doctor Dictation (Lightday Rx) | Vitals grounding, investigations (catalogue missing), follow-up date, sections, prose tidy. |  | `doctor-dictation/doctor_dictation/core/vitals.py`<br>`doctor-dictation/doctor_dictation/core/investigations.py`<br>`doctor-dictation/doctor_dictation/core/followup.py` |
| Records & output | Module | Implemented | Doctor Dictation (Lightday Rx) | Save/reopen, Today list, past-day lock, Chromium PDF, letterhead-from-photo, OP numbers, share link + QR. |  | `doctor-dictation/doctor_dictation/api/persistence.py`<br>`doctor-dictation/doctor_dictation/pdf/`<br>`doctor-dictation/doctor_dictation/templates/`<br>`doctor-dictation/doctor_dictation/api/share.py` |
| Clinic learning | Module | Implemented | Doctor Dictation (Lightday Rx) | Learned clinic formulary, clinic list overlay, owner list curation, doctor spoken terms, 'Your usual'. |  | `doctor-dictation/doctor_dictation/api/formulary.py`<br>`doctor-dictation/doctor_dictation/core/overlay.py`<br>`doctor-dictation/doctor_dictation/api/spoken.py`<br>`doctor-dictation/doctor_dictation/api/your_usual.py` |
| Access & tenancy | Module | Implemented | Doctor Dictation (Lightday Rx) | Multi-clinic mode (off by default): scrypt login, signed session cookie, lockout, revocation, per-clinic DB, roles, authorship, team admin. |  | `doctor-dictation/doctor_dictation/api/session.py`<br>`doctor-dictation/doctor_dictation/sessions.py`<br>`doctor-dictation/doctor_dictation/directory/`<br>`doctor-dictation/doctor_dictation/policy.py` |
| Operations | Shared | Implemented | Doctor Dictation (Lightday Rx) | Operator CLI, Docker + Caddy, VPS harden/deploy/backup/restore-drill scripts. |  | `doctor-dictation/doctor_dictation/admin.py`<br>`doctor-dictation/Dockerfile`<br>`doctor-dictation/docker-compose.yml`<br>`doctor-dictation/scripts/deploy/` |
| DD demo & tooling | Demo | Demo | Doctor Dictation (Lightday Rx) | seed-demo (DEMO_MODE=1), Playwright browser walkthrough, stub providers, STT benchmark (POC, no clips), ONNX STT (stub). |  | `doctor-dictation/doctor_dictation/admin_demo.py`<br>`doctor-dictation/scripts/demo_browser.py`<br>`doctor-dictation/doctor_dictation/bench/`<br>`doctor-dictation/doctor_dictation/providers/stt/onnx.py` |
| Count Guard | Product | Partial (Current) | hackathon26 workspace | One FastAPI app + one React app that host five product generations. The current product is the 'Ward 4' care app (D) with the AI admin ops agent (E). Generations A–C are still mounted and reachable via 'Older screens'. | Ward doctor, nurse, patient (synthetic data, research demo) | `count-guard/backend/app/`<br>`count-guard/frontend/src/` |
| Care app 'Ward 4' (generation D) | Product | Implemented (Current) | Count Guard | Three roles share one append-only timeline per patient: state machine, orders and tasks, swab-count hard stop, video and photo checks, alerts, patient Ask, discharge, Inspector, AI activity. |  | `count-guard/backend/app/journey/`<br>`count-guard/frontend/src/care/` |
| Patient flow | Module | Implemented | Care app 'Ward 4' (generation D) | clinic → admitting → ward ⇄ theatre → discharging → home with checklists; 409 with a plain reason on illegal moves. |  | `count-guard/backend/app/journey/states.py`<br>`count-guard/backend/app/journey/flow_api.py` |
| Orders & nurse tasks | Module | Implemented | Care app 'Ward 4' (generation D) | Dictate/type → draft → sign → acknowledge; tasks with values and photo proof. |  | `count-guard/backend/app/journey/dictation.py`<br>`count-guard/backend/app/journey/tasks.py`<br>`count-guard/backend/app/journey/media_api.py` |
| Swab count hard stop | Module | Implemented | Care app 'Ward 4' (generation D) | Surgery cannot end until a person saves a closing count that adds up or gives a reason; camera read shown, never auto-filled. |  | `count-guard/backend/app/journey/states.py:95-110`<br>`count-guard/backend/app/journey/count_api.py`<br>`count-guard/frontend/src/care/CountPanel.jsx` |
| Video & photo checks | Module | Mock | Care app 'Ward 4' (generation D) | Tray vs procedure plan, saline set-up, strip vs Rx, medicines from home. Results come from hand-made fixtures unless a key is set (never done). |  | `count-guard/backend/app/journey/video_api.py`<br>`count-guard/backend/app/journey/live.py`<br>`count-guard/backend/app/journey/prepared/` |
| Observations & alerts | Module | Implemented | Care app 'Ward 4' (generation D) | Obs vs doctor-set limits → named alert → 'What did you do?'. |  | `count-guard/backend/app/journey/nudges.py`<br>`count-guard/frontend/src/care/AlertCard.jsx` |
| Patient Ask | Module | Implemented | Care app 'Ward 4' (generation D) | Record-grounded bot, question to doctor, healing-photo review, doctor voice answer with decision. |  | `count-guard/backend/app/journey/ask.py`<br>`count-guard/backend/app/journey/ask_api.py` |
| Inspector & AI activity | Module | Implemented | Care app 'Ward 4' (generation D) | Why / Evidence / History / Model per AI row; staff AI activity page with model cards (Try sample is demo). |  | `count-guard/frontend/src/care/Inspector.jsx`<br>`count-guard/frontend/src/care/AiDashboard.jsx`<br>`count-guard/backend/app/journey/ai_api.py` |
| AI admin ops agent (generation E) | Module | Implemented (Current) | Count Guard | watch → plan → policy gate → apply inside every write; L3/L2 act (10-min Undo), L1 propose, 'Never' for prescribe/dose/advise/clear count/discharge; Pause. Rule-based; optional Spark rewording. |  | `count-guard/backend/app/ops/` |
| Care platform kernel | Platform | Implemented (Current) | Count Guard | Episode + append-only event store with supersede corrections (morning.db), visible_events, the live/prepared perception seam, four model adapters, advice-word verifier. Spread across morning/, journey/, adapters/, agent/. |  | `count-guard/backend/app/morning/store.py`<br>`count-guard/backend/app/morning/discharge.py`<br>`count-guard/backend/app/journey/live.py`<br>`count-guard/backend/app/adapters/`<br>`count-guard/backend/app/agent/verifier.py` |
| Camera swab counter (generation A, v1) | Legacy | Deprecated (Legacy) | Count Guard | The original 'Count Guard': SAM tracks, zones, rules R1–R6, discrepancies, Spark Open narrative, PDF count sheet. Runs on scripted detections only. |  | `count-guard/backend/app/core/`<br>`count-guard/backend/app/engine.py`<br>`count-guard/backend/app/agent/reconciler.py`<br>`count-guard/backend/app/report/`<br>`count-guard/backend/app/api/` |
| Morning timeline (generation B) | Legacy | Deprecated (Legacy) | Count Guard | Single-patient OPD → OT → ward morning: brown-bag strips, drug log, vitals sim + fact card, discharge PDF/ICS, SSE stream. |  | `count-guard/backend/app/morning/`<br>`count-guard/frontend/src/screens/` |
| Care journey v1 (generation C) | Legacy | Deprecated (Legacy) | Count Guard | Doctor / Nurse / Patient / Audit screens, three-act scripted play, handover, reminders. |  | `count-guard/backend/app/journey/api.py`<br>`count-guard/backend/app/journey/play.py`<br>`count-guard/frontend/src/screens/` |
| Demo & showcase layer | Demo | Demo (Current) | Count Guard | DemoDock (role, patient, clock, reset), seed, demo prescription, Try sample, prepared fixtures, 32-beat headless demo-check, eval scripts. |  | `count-guard/frontend/src/care/DemoDock.jsx`<br>`count-guard/backend/app/journey/seed.py`<br>`count-guard/frontend/scripts/demo/`<br>`count-guard/eval/` |
| Research POCs | POC | POC (Legacy) | Count Guard | Spark-only baseline (NotImplementedError), day-1 API check, SAM cost estimator, real-video pipeline, fixture recorder. |  | `count-guard/backend/app/baseline.py`<br>`count-guard/backend/app/day1.py`<br>`count-guard/backend/app/spend.py`<br>`count-guard/backend/app/media_pipeline.py`<br>`count-guard/eval/record_fixtures.py` |
| DD → CG prescription link | Shared | Implemented | hackathon26 workspace | The only runtime coupling: Count Guard GETs a saved Doctor Dictation document over HTTP (option A, no shared code). |  | `count-guard/backend/app/journey/rx.py:83-107`<br>`count-guard/backend/app/config.py:103` |
| Design docs & specs | Shared | Partial | hackathon26 workspace | docs/hackathon (21 Oct umbrella plan, mostly superseded), docs/superpowers (10 specs + 13 plans for Count Guard), demo video script. |  | `docs/hackathon/`<br>`docs/superpowers/`<br>`docs/demo/count-guard-v2-video-script.md` |

## Evidence for the top-level classification

- **hackathon26 workspace:** `README.md:3 — 'Two apps in one repo… They share one .env and run on separate ports.'`; `Makefile:18-43 — setup/dev/test fan out to both apps`
- **Doctor Dictation (Lightday Rx):** `doctor-dictation/doctor_dictation/api/format.py:126-214 (format pipeline)`; `doctor-dictation/doctor_dictation/api/persistence.py:198-235 (verify gate)`
- **Count Guard:** `count-guard/backend/app/main.py:31-69 (18 routers)`; `count-guard/frontend/src/App.jsx:170-195 (8 care + 16 old routes)`

## Features per product and status

| Product | Implemented | Partial | Demo | POC | Mock | Stub | Planned | Deprecated | Unknown | Total |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Doctor Dictation | 27 | 4 | 1 | 1 | 0 | 1 | 1 | 1 | 0 | 36 |
| Count Guard | 15 | 0 | 4 | 4 | 4 | 1 | 0 | 6 | 0 | 34 |
| **All** | 42 | 4 | 5 | 5 | 4 | 2 | 1 | 7 | 0 | 70 |

## Repository map

- `hackathon26/` — Monorepo: two apps, shared .env and Makefile *(Workspace, Implemented)*
  - `README.md · Makefile · .env.example` — How to set up, run and test both apps; ports and the shared model key *(Workspace, Implemented)*
  - `docs/` — Cross-app plans and Count Guard design history *(Docs, Partial)*
    - `hackathon/ (01–07)` — 21–28 Oct umbrella plan (one timeline inside DD). Mostly superseded; 07 introduced the care journey and the HTTP link. *(Docs, Deprecated)*
    - `superpowers/specs, plans` — 10 specs + 13 plans: Count Guard v2 → v3 → v4 → ops agent → product design (29 Oct–1 Nov) *(Count Guard, Implemented)*
    - `demo/count-guard-v2-video-script.md` — Current 3:20 demo film script, 32 beats *(Count Guard, Demo)*
    - `product-overview/` — This overview *(Docs, Implemented)*
  - `doctor-dictation/` — Doctor Dictation product (691 files) *(Doctor Dictation, Implemented)*
    - `doctor_dictation/api/` — 19 FastAPI routers + session middleware *(Doctor Dictation, Implemented)*
    - `doctor_dictation/core/` — Pure offline rules: normalisation, grounding, LASA, dosing, vitals, investigations, learning *(Doctor Dictation, Implemented)*
    - `doctor_dictation/core/lexicon/` — Drug data (448) + builders; dosing empty, investigations missing, LASA unreviewed *(Doctor Dictation, Partial)*
    - `doctor_dictation/db/, directory/` — sqlite3 repositories, 14 clinic + directory migrations *(Doctor Dictation, Implemented)*
    - `doctor_dictation/providers/` — LLM (OpenAI-compatible + stub) and STT (5 real + onnx/browser/stub) *(Doctor Dictation, Implemented)*
    - `doctor_dictation/pdf/, templates/` — Chromium PDF, QR, letterhead-from-photo *(Doctor Dictation, Implemented)*
    - `doctor_dictation/bench/` — STT benchmark CLI, no clips *(Doctor Dictation, POC)*
    - `doctor_dictation/admin.py, admin_demo.py` — Operator CLI; demo seed gated by DEMO_MODE *(Doctor Dictation, Implemented)*
    - `frontend/` — Vanilla JS SPA, login page, bundled fonts *(Doctor Dictation, Implemented)*
    - `tests/` — 242 test modules, 3,338 tests; isolation, deploy and load suites *(Doctor Dictation, Implemented)*
    - `Dockerfile, docker-compose.yml, Caddyfile, scripts/deploy/` — Container, HTTPS proxy, VPS harden/deploy/backup *(Doctor Dictation, Implemented)*
    - `docs/` — Runbooks, Lightday design system, 78 plans, working notes (incl. scratch tools) *(Doctor Dictation, Partial)*
  - `count-guard/` — Count Guard app (390 files) — five generations *(Count Guard, Partial)*
    - `backend/app/journey/` — Care app D: states, flow, count, tasks, video, media, ask, AI, staff routers; prepared fixtures *(Count Guard, Implemented)*
    - `backend/app/ops/` — AI admin ops agent E *(Count Guard, Implemented)*
    - `backend/app/morning/` — Legacy B routes AND the shared event store used by D and E *(Count Guard, Deprecated)*
    - `backend/app/core/, engine.py, api/, report/, scenarios.py` — Legacy A camera swab counter *(Count Guard, Deprecated)*
    - `backend/app/agent/` — Spark Open reconciler (POC) + advice verifier (shared, live) *(Count Guard, POC)*
    - `backend/app/adapters/` — SAM, Voice, Spark 1.3, Spark Open HTTP clients *(Count Guard, Implemented)*
    - `backend/app/baseline.py, day1.py, spend.py, media_pipeline.py` — Research POCs; baseline is a stub *(Count Guard, POC)*
    - `backend/tests/` — 66 files, 704 tests *(Count Guard, Implemented)*
    - `frontend/src/care/` — Current care UI (142 files, 39 logic test files) *(Count Guard, Implemented)*
    - `frontend/src/screens/` — Older screens for A, B, C *(Count Guard, Deprecated)*
    - `frontend/scripts/demo/` — Headless demo-check harness (32 beats) *(Count Guard, Demo)*
    - `eval/` — Scripted clip eval, ops replay, fixture recorder, media generators *(Count Guard, Demo)*
    - `docs/` — architecture.md (legacy A only), overnight loop state, build log *(Count Guard, Partial)*

## Coverage and method

Read-only inspection of all 1,117 tracked files: three parallel deep reads (Doctor Dictation, Count Guard, docs vs code), followed by spot-checks of every high-impact claim against source. No servers were started, no tests were run (test counts are from pytest --collect-only), no secrets were read. All 1,117 tracked files were in scope; git-ignored local data (databases, generated media, `.env`) was not opened.

**Not done:** no tests were executed, no app was started, and no code was changed.

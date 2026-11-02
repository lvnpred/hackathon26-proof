/* Product & Codebase Overview data: meta, metrics, product hierarchy, classification, repository tree.
   Source: repository at commit 90e0f56 (main, 2026-11-02), after the Doctor Dictation → Count Guard consolidation.
   Every claim cites a repo-relative path. */
window.DATA = window.DATA || {};

DATA.meta = {
  title: "hackathon26 — Product & Codebase Overview",
  commit: "90e0f56",
  branch: "main",
  generated: "2026-11-02",
  method: "Refreshed on 2026-11-02 after the Doctor Dictation → Count Guard consolidation (23 commits e40d8c7..90e0f56). Read-only inspection of all 1,248 tracked files against the patient-flow spec (docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md §9) and its plan appendix (§9 row → test); every named test was confirmed to exist. Test counts are from pytest --collect-only and a count of node test() calls; no servers were started and no tests were run for this refresh. The live-check and demo-check results quoted are the runs logged on 2026-11-02. No secrets were read."
};

DATA.metrics = [
  { v: "2", l: "Products", s: "Doctor Dictation; Count Guard care app + AI admin agent" },
  { v: "1", l: "Patient flow across both apps", s: "DD Save & admit → CG ward → theatre → discharge" },
  { v: "1,248", l: "Tracked files", s: "DD 698 · CG 496 (44 in archive/) · docs 50 · root 4" },
  { v: "≈49.8k", l: "Lines of app code (excl. tests, archive)", s: "DD ≈24.4k (Python 18.4k + JS 5.9k) · CG ≈25.4k (Python 16.0k + React 8.4k + demo scripts 0.9k)" },
  { v: "≈151", l: "HTTP endpoints", s: "DD ≈56 · CG ≈95 (incl. 1 WebSocket, 2 SSE)" },
  { v: "4,809", l: "Automated tests", s: "DD 3,361 · CG 921 backend + ≈470 UI logic + 57 demo-harness" },
  { v: "286", l: "Commits", s: "2026-10-13 → 2026-11-02; 23 in the consolidation" },
  { v: "1", l: "TODO / FIXME markers", s: "count-guard/backend/app/baseline.py:66" }
];

/* Product hierarchy. category: Product | Platform | Module | Feature | Demo | POC | Shared | Legacy */
DATA.products = [
  {
    id: "ws", name: "hackathon26 workspace", category: "Shared", status: "Implemented", lifecycle: "Current",
    desc: "A monorepo that hosts two separate apps (own servers, own databases) sharing one .env, one Makefile and the Meta Muse model key. Since 2 Nov they form one patient flow: a Doctor Dictation clinic visit saved with 'Save & admit to ward' becomes a Count Guard ward patient.",
    purpose: "Run, test and demo the two apps as one clinic → ward → theatre → discharge story.",
    persona: "Developers, hackathon judges", paths: ["README.md", "Makefile", ".env.example"],
    evidence: ["README.md:3 — 'Two apps in one repo… They share one .env and run on separate ports.'", "docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md:6-21 — one patient, two apps", "Makefile:32-37 — make dev runs both"],
    children: [
      {
        id: "dd", name: "Doctor Dictation (Lightday Rx)", category: "Product", status: "Implemented", lifecycle: "Current",
        desc: "Voice-to-prescription web app for Indian outpatient clinics. Doctor dictates the visit → STT → LLM drafts a structured sheet → deterministic grounding and safety checks → verify gate → Save (send home, or Save & admit to ward) → PDF on clinic letterhead, with QR share link.",
        purpose: "Cut prescription writing time while never printing an unverified medicine; hand admitted patients to the ward.",
        persona: "OPD doctors, clinic assistants, clinic admin, app owner",
        paths: ["doctor-dictation/doctor_dictation/", "doctor-dictation/frontend/"],
        ui: "http://127.0.0.1:8000 (single page, vanilla JS)", db: "SQLite: app.db per clinic + directory.db",
        evidence: ["doctor-dictation/doctor_dictation/api/format.py:126-214 (format pipeline)", "doctor-dictation/doctor_dictation/api/persistence.py:198-235 (verify gate)", "doctor-dictation/doctor_dictation/api/persistence.py:147-148,360-361 (admit on Save)"],
        children: [
          { id: "dd-capture", name: "Capture", category: "Module", status: "Implemented", desc: "Browser recording, STT provider chain (OpenAI, Groq, AssemblyAI, Meta Muse, local faster-whisper), vocabulary hints, silence trim.", paths: ["doctor-dictation/doctor_dictation/api/stt.py", "doctor-dictation/doctor_dictation/providers/stt/", "doctor-dictation/doctor_dictation/audio/"] },
          { id: "dd-struct", name: "Structuring", category: "Module", status: "Implemented", desc: "LLM extract → ground → repair loop, deterministic normalisation and cache, offline rules fallback, spoken corrections, spelled names.", paths: ["doctor-dictation/doctor_dictation/api/format.py", "doctor-dictation/doctor_dictation/core/determinism.py", "doctor-dictation/doctor_dictation/core/fallback.py"] },
          { id: "dd-safety", name: "Medication safety", category: "Module", status: "Partial", desc: "Lexicon (448 entries), per-row grounding pills, LASA guard (8 unreviewed pairs), dose check (no data ships), verify gate on Save.", paths: ["doctor-dictation/doctor_dictation/core/rowcheck.py", "doctor-dictation/doctor_dictation/core/lasa.py", "doctor-dictation/doctor_dictation/core/dosing.py", "doctor-dictation/doctor_dictation/core/safety.py"] },
          { id: "dd-fields", name: "Clinical fields", category: "Module", status: "Partial", desc: "Vitals grounding, investigations (catalogue missing), follow-up date, sections, prose tidy.", paths: ["doctor-dictation/doctor_dictation/core/vitals.py", "doctor-dictation/doctor_dictation/core/investigations.py", "doctor-dictation/doctor_dictation/core/followup.py"] },
          { id: "dd-records", name: "Records & output", category: "Module", status: "Implemented", desc: "Save/reopen, Today list, past-day lock, Chromium PDF, letterhead-from-photo, OP numbers, share link + QR.", paths: ["doctor-dictation/doctor_dictation/api/persistence.py", "doctor-dictation/doctor_dictation/pdf/", "doctor-dictation/doctor_dictation/templates/", "doctor-dictation/doctor_dictation/api/share.py"] },
          { id: "dd-admit", name: "Admit to ward (→ Count Guard)", category: "Module", status: "Implemented", desc: "New 2 Nov. 'Save & admit to ward' with a required reason; an admissions table; a background push to Count Guard's /journey/intake after the commit (1 s connect / 3 s total); GET /api/v1/admissions for CG Sync; single-clinic only (404 in multi-clinic).", paths: ["doctor-dictation/doctor_dictation/api/admit.py", "doctor-dictation/doctor_dictation/db/migrations/015_admissions.sql", "doctor-dictation/frontend/admit.js"] },
          { id: "dd-learn", name: "Clinic learning", category: "Module", status: "Implemented", desc: "Learned clinic formulary, clinic list overlay, owner list curation, doctor spoken terms, 'Your usual'.", paths: ["doctor-dictation/doctor_dictation/api/formulary.py", "doctor-dictation/doctor_dictation/core/overlay.py", "doctor-dictation/doctor_dictation/api/spoken.py", "doctor-dictation/doctor_dictation/api/your_usual.py"] },
          { id: "dd-tenancy", name: "Access & tenancy", category: "Module", status: "Implemented", desc: "Multi-clinic mode (off by default): scrypt login, signed session cookie, lockout, revocation, per-clinic DB, roles, authorship, team admin.", paths: ["doctor-dictation/doctor_dictation/api/session.py", "doctor-dictation/doctor_dictation/sessions.py", "doctor-dictation/doctor_dictation/directory/", "doctor-dictation/doctor_dictation/policy.py"] },
          { id: "dd-ops", name: "Operations", category: "Shared", status: "Implemented", desc: "Operator CLI, Docker + Caddy, VPS harden/deploy/backup/restore-drill scripts.", paths: ["doctor-dictation/doctor_dictation/admin.py", "doctor-dictation/Dockerfile", "doctor-dictation/docker-compose.yml", "doctor-dictation/scripts/deploy/"] },
          { id: "dd-demo", name: "DD demo & tooling", category: "Demo", status: "Demo", desc: "seed-demo (DEMO_MODE=1), DEMO_BANNER research-demo banner, Playwright browser walkthrough, stub providers, STT benchmark (POC, no clips), ONNX STT (stub).", paths: ["doctor-dictation/doctor_dictation/admin_demo.py", "doctor-dictation/frontend/demobanner.js", "doctor-dictation/scripts/demo_browser.py", "doctor-dictation/doctor_dictation/bench/"] }
        ]
      },
      {
        id: "cg", name: "Count Guard", category: "Product", status: "Implemented", lifecycle: "Current",
        desc: "One FastAPI app + one React app for one product: the 'Ward 4' care app with the AI admin ops agent. Since 2 Nov every feature of the older generations (camera counter, morning timeline, journey v1) lives in the care app; their screens and route files sit in count-guard/archive/, unmounted. Libraries they used (morning/, core/, engine.py, report/, agent/) stay in place because the care app imports them.",
        purpose: "Make sure nothing gets lost around one patient: instruments, swabs, medicines, words, questions. 'The system formats. The doctor decides.'",
        persona: "Ward doctor, nurse, theatre nurse, patient (synthetic data, research demo)",
        paths: ["count-guard/backend/app/", "count-guard/frontend/src/"],
        ui: "http://127.0.0.1:5173 (React) → API :8100", db: "SQLite: morning.db (care, journey, ops, intake keys) + countguard.db (theatre camera cases)",
        evidence: ["count-guard/backend/app/main.py:58-84 (26 routers, all care app)", "count-guard/frontend/src/App.jsx:34-44 (care routes only)", "count-guard/README.md:121-123 (Archived screens)"],
        children: [
          {
            id: "cg-care", name: "Care app 'Ward 4'", category: "Product", status: "Implemented", lifecycle: "Current",
            desc: "Doctor, nurse and patient share one append-only timeline per patient: server ward list, intake from DD, state machine, orders and tasks, photo proofs with verdicts, theatre (drug by voice, vitals, context card, swab camera), swab-count hard stop, discharge drafted from the timeline, patient Ask, Inspector, Help.",
            paths: ["count-guard/backend/app/journey/", "count-guard/frontend/src/care/"],
            children: [
              { id: "cg-intake", name: "Ward list, intake & Sync", category: "Module", status: "Implemented", desc: "Server-owned ward list and demo clock; one intake path for a DD push, Sync (pull from DD) and New patient; idempotent per (source, document_id); SSE ward stream.", paths: ["count-guard/backend/app/journey/ward_api.py", "count-guard/backend/app/journey/intake.py", "count-guard/backend/app/journey/sync.py", "count-guard/backend/app/journey/clock.py"] },
              { id: "cg-flow", name: "Patient flow", category: "Module", status: "Implemented", desc: "clinic → admitting → ward ⇄ theatre → discharging → home with checklists; 409 with a plain reason on illegal moves; admission and discharge stay open while a photo check is not accepted.", paths: ["count-guard/backend/app/journey/states.py", "count-guard/backend/app/journey/flow_api.py", "count-guard/backend/app/journey/check_gate.py"] },
              { id: "cg-orders", name: "Orders, tasks & ward care", category: "Module", status: "Implemented", desc: "Dictate/type → draft → sign → acknowledge; tasks with values and photo proof; handover, dose given, reminders, check-in (moved from journey v1).", paths: ["count-guard/backend/app/journey/dictation.py", "count-guard/backend/app/journey/tasks.py", "count-guard/backend/app/journey/api.py:272-401"] },
              { id: "cg-proof", name: "Photo proofs & verdicts", category: "Module", status: "Implemented", desc: "Accepted / Not accepted / Not checked per checklist photo; an open item needs a retake or a typed override (U9). Spark vision when PROOF_LIVE, else a prepared verdict chosen by the photo's bytes.", paths: ["count-guard/backend/app/journey/verdict.py", "count-guard/backend/app/journey/verdict_api.py"] },
              { id: "cg-theatre", name: "Theatre", category: "Module", status: "Implemented", desc: "Drug given and packs heard by voice (a person confirms), simulated vitals strip, research-tier context card, swab camera with rules R1–R6 as advice, missing-swab last frame, replay, bucket-dwell, resolve, close, count-sheet PDF.", paths: ["count-guard/backend/app/journey/theatre_api.py", "count-guard/backend/app/journey/camera_api.py", "count-guard/backend/app/journey/camera_close_api.py", "count-guard/backend/app/journey/advice.py"] },
              { id: "cg-count", name: "Swab count hard stop", category: "Module", status: "Implemented", desc: "Surgery cannot end until a person saves a closing count that adds up or gives a reason; camera and rules are advice only and never fill it. count_gate is unchanged; a route sweep proves no other write route can close the count.", paths: ["count-guard/backend/app/journey/states.py:95-109", "count-guard/backend/app/journey/count_api.py", "count-guard/backend/tests/test_route_sweep.py"] },
              { id: "cg-discharge", name: "Discharge", category: "Module", status: "Implemented", desc: "Draft discharge from the timeline (DD prescription, drugs given, count), dictate changes, sign, discharge PDF + follow-up .ics, discharge card in the patient view.", paths: ["count-guard/backend/app/journey/discharge_draft.py", "count-guard/backend/app/journey/discharge_api.py"] },
              { id: "cg-checks", name: "Video, photo & voice reads", category: "Module", status: "Mock", desc: "Tray, saline set-up, swab camera, medicines from home, voice. Every step has a live switch; one live call per model succeeded on 2 Nov, but the demo default (and demo-check) is prepared results, labelled 'Prepared'.", paths: ["count-guard/backend/app/journey/switches.py", "count-guard/backend/app/journey/live.py", "count-guard/backend/app/journey/prepared/"] },
              { id: "cg-alerts", name: "Observations & alerts", category: "Module", status: "Implemented", desc: "Obs vs doctor-set limits → named alert → 'What did you do?'.", paths: ["count-guard/backend/app/journey/nudges.py", "count-guard/frontend/src/care/AlertCard.jsx"] },
              { id: "cg-ask", name: "Patient Ask", category: "Module", status: "Implemented", desc: "Record-grounded bot, question to doctor, healing-photo review, doctor voice answer with decision.", paths: ["count-guard/backend/app/journey/ask.py", "count-guard/backend/app/journey/ask_api.py"] },
              { id: "cg-explain", name: "Inspector, correction & Help", category: "Module", status: "Implemented", desc: "Why / Evidence / History / Model per row, camera evidence, Correct (supersedes) for typed obs and theatre drug lines, staff AI activity page, Help page.", paths: ["count-guard/frontend/src/care/Inspector.jsx", "count-guard/backend/app/journey/correct_api.py", "count-guard/frontend/src/care/Help.jsx"] }
            ]
          },
          { id: "cg-ops", name: "AI admin ops agent", category: "Module", status: "Implemented", lifecycle: "Current", desc: "watch → plan → policy gate → apply inside every write; L3/L2 act (10-min Undo), L1 propose, 'Never' for prescribe/dose/advise/clear count/discharge; Pause. Rule-based; optional Spark rewording.", paths: ["count-guard/backend/app/ops/"] },
          { id: "cg-kernel", name: "Care platform kernel", category: "Platform", status: "Implemented", lifecycle: "Current", desc: "Episode + append-only event store with supersede corrections (morning.db), visible_events, the live/prepared seam and switches, four model adapters, advice-word verifier, and the camera libraries the theatre now reuses (core/ tracker, rules, ledger; engine.py; report/). Still spread across morning/, journey/, adapters/, agent/, core/.", paths: ["count-guard/backend/app/morning/store.py", "count-guard/backend/app/journey/live.py", "count-guard/backend/app/adapters/", "count-guard/backend/app/agent/verifier.py", "count-guard/backend/app/core/"] },
          { id: "cg-archive", name: "Archive (camera counter, morning, journey v1)", category: "Legacy", status: "Deprecated", lifecycle: "Archived", desc: "44 files moved with git mv on 2 Nov: 21 old React screens, morning/api.py, routes_extra.py, script.py, sim.py, camera_file.py, care_guard.py, api/routes.py, api/ws.py, journey/play.py, and their tests. Not imported, not mounted; the set is computed from the import graph.", paths: ["count-guard/archive/", "count-guard/scripts/archive_set.py", "count-guard/backend/tests/test_archive.py"] },
          { id: "cg-demo", name: "Demo & showcase layer", category: "Demo", status: "Demo", lifecycle: "Current", desc: "DemoDock (role, patient, clock, reset), seed, demo prescription, Try sample, prepared fixtures, generated demo media, the two-app 20-beat demo-check (180 s), make live-check, eval scripts.", paths: ["count-guard/frontend/src/care/DemoDock.jsx", "count-guard/backend/app/journey/seed.py", "count-guard/frontend/scripts/demo/", "count-guard/backend/app/live_check.py", "count-guard/eval/"] },
          { id: "cg-poc", name: "Research POCs", category: "POC", status: "POC", lifecycle: "Legacy", desc: "Spark-only baseline (NotImplementedError), day-1 API check, SAM cost estimator, fixture recorder.", paths: ["count-guard/backend/app/baseline.py", "count-guard/backend/app/day1.py", "count-guard/backend/app/spend.py", "count-guard/eval/record_fixtures.py"] }
        ]
      },
      { id: "link", name: "DD → CG patient flow", category: "Shared", status: "Implemented", desc: "Push: DD Save & admit → admissions row → background POST /journey/intake. Pull: CG Sync → DD GET /api/v1/admissions. Optional shared CG_SYNC_TOKEN header. Separate servers and databases; no shared code.", paths: ["doctor-dictation/doctor_dictation/api/admit.py:101-178", "count-guard/backend/app/journey/intake_api.py:78-111", "count-guard/backend/app/journey/sync.py"] },
      { id: "docs", name: "Design docs & specs", category: "Shared", status: "Partial", desc: "docs/hackathon (21 Oct umbrella plan, mostly superseded), docs/superpowers (Count Guard specs and plans incl. the 2 Nov patient-flow spec), demo video scripts.", paths: ["docs/hackathon/", "docs/superpowers/", "docs/demo/dd-cg-flow-video-script.md"] }
    ]
  }
];

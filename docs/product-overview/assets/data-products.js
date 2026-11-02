/* Product & Codebase Overview data: meta, metrics, product hierarchy, classification, repository tree.
   Source: repository at commit e40d8c7 (main, 2026-11-01). Every claim cites a repo-relative path. */
window.DATA = window.DATA || {};

DATA.meta = {
  title: "hackathon26 — Product & Codebase Overview",
  commit: "e40d8c7",
  branch: "main",
  generated: "2026-11-01",
  method: "Read-only inspection of all 1,117 tracked files: three parallel deep reads (Doctor Dictation, Count Guard, docs vs code), followed by spot-checks of every high-impact claim against source. No servers were started, no tests were run (test counts are from pytest --collect-only), no secrets were read."
};

DATA.metrics = [
  { v: "2", l: "Shipping products", s: "Doctor Dictation; Count Guard care app" },
  { v: "3", l: "Legacy products inside Count Guard", s: "camera counter, morning timeline, journey v1" },
  { v: "1,117", l: "Tracked files", s: "DD 691 · CG 390 · docs 32 · root 4" },
  { v: "≈48k", l: "Lines of app code (excl. tests)", s: "DD ≈24k (Python 17.1k + JS 7.1k) · CG ≈24k (Python 12.9k + React 10.6k + demo scripts 0.9k)" },
  { v: "≈148", l: "HTTP endpoints", s: "DD ≈53 · CG ≈95 (incl. 1 WebSocket, 1 SSE)" },
  { v: "4,509", l: "Automated tests", s: "DD 3,338 · CG 704 backend + ≈420 UI logic + 47 demo-harness" },
  { v: "262", l: "Commits", s: "2026-10-13 → 2026-11-01; 194 in the last 4 days" },
  { v: "1", l: "TODO / FIXME markers", s: "count-guard/backend/app/baseline.py:66" }
];

/* Product hierarchy. category: Product | Platform | Module | Feature | Demo | POC | Shared | Legacy */
DATA.products = [
  {
    id: "ws", name: "hackathon26 workspace", category: "Shared", status: "Implemented", lifecycle: "Current",
    desc: "Not a product. A monorepo that hosts two independent apps sharing one .env, one Makefile and the Meta Muse model key. No umbrella product exists in code.",
    purpose: "Run, test and demo two hackathon apps side by side.",
    persona: "Developers", paths: ["README.md", "Makefile", ".env.example"],
    evidence: ["README.md:3 — 'Two apps in one repo… They share one .env and run on separate ports.'", "Makefile:18-43 — setup/dev/test fan out to both apps"],
    children: [
      {
        id: "dd", name: "Doctor Dictation (Lightday Rx)", category: "Product", status: "Implemented", lifecycle: "Current",
        desc: "Voice-to-prescription web app for Indian outpatient clinics. Doctor dictates the visit → STT → LLM drafts a structured sheet → deterministic grounding and safety checks → verify gate → Save → PDF on clinic letterhead, with QR share link.",
        purpose: "Cut prescription writing time while never printing an unverified medicine.",
        persona: "OPD doctors, clinic assistants, clinic admin, app owner",
        paths: ["doctor-dictation/doctor_dictation/", "doctor-dictation/frontend/"],
        ui: "http://127.0.0.1:8000 (single page, vanilla JS)", db: "SQLite: app.db per clinic + directory.db",
        evidence: ["doctor-dictation/doctor_dictation/api/format.py:126-214 (format pipeline)", "doctor-dictation/doctor_dictation/api/persistence.py:198-235 (verify gate)"],
        children: [
          { id: "dd-capture", name: "Capture", category: "Module", status: "Implemented", desc: "Browser recording, STT provider chain (OpenAI, Groq, AssemblyAI, Meta Muse, local faster-whisper), vocabulary hints, silence trim.", paths: ["doctor-dictation/doctor_dictation/api/stt.py", "doctor-dictation/doctor_dictation/providers/stt/", "doctor-dictation/doctor_dictation/audio/"] },
          { id: "dd-struct", name: "Structuring", category: "Module", status: "Implemented", desc: "LLM extract → ground → repair loop, deterministic normalisation and cache, offline rules fallback, spoken corrections, spelled names.", paths: ["doctor-dictation/doctor_dictation/api/format.py", "doctor-dictation/doctor_dictation/core/determinism.py", "doctor-dictation/doctor_dictation/core/fallback.py"] },
          { id: "dd-safety", name: "Medication safety", category: "Module", status: "Partial", desc: "Lexicon (448 entries), per-row grounding pills, LASA guard (8 unreviewed pairs), dose check (no data ships), verify gate on Save.", paths: ["doctor-dictation/doctor_dictation/core/rowcheck.py", "doctor-dictation/doctor_dictation/core/lasa.py", "doctor-dictation/doctor_dictation/core/dosing.py", "doctor-dictation/doctor_dictation/core/safety.py"] },
          { id: "dd-fields", name: "Clinical fields", category: "Module", status: "Partial", desc: "Vitals grounding, investigations (catalogue missing), follow-up date, sections, prose tidy.", paths: ["doctor-dictation/doctor_dictation/core/vitals.py", "doctor-dictation/doctor_dictation/core/investigations.py", "doctor-dictation/doctor_dictation/core/followup.py"] },
          { id: "dd-records", name: "Records & output", category: "Module", status: "Implemented", desc: "Save/reopen, Today list, past-day lock, Chromium PDF, letterhead-from-photo, OP numbers, share link + QR.", paths: ["doctor-dictation/doctor_dictation/api/persistence.py", "doctor-dictation/doctor_dictation/pdf/", "doctor-dictation/doctor_dictation/templates/", "doctor-dictation/doctor_dictation/api/share.py"] },
          { id: "dd-learn", name: "Clinic learning", category: "Module", status: "Implemented", desc: "Learned clinic formulary, clinic list overlay, owner list curation, doctor spoken terms, 'Your usual'.", paths: ["doctor-dictation/doctor_dictation/api/formulary.py", "doctor-dictation/doctor_dictation/core/overlay.py", "doctor-dictation/doctor_dictation/api/spoken.py", "doctor-dictation/doctor_dictation/api/your_usual.py"] },
          { id: "dd-tenancy", name: "Access & tenancy", category: "Module", status: "Implemented", desc: "Multi-clinic mode (off by default): scrypt login, signed session cookie, lockout, revocation, per-clinic DB, roles, authorship, team admin.", paths: ["doctor-dictation/doctor_dictation/api/session.py", "doctor-dictation/doctor_dictation/sessions.py", "doctor-dictation/doctor_dictation/directory/", "doctor-dictation/doctor_dictation/policy.py"] },
          { id: "dd-ops", name: "Operations", category: "Shared", status: "Implemented", desc: "Operator CLI, Docker + Caddy, VPS harden/deploy/backup/restore-drill scripts.", paths: ["doctor-dictation/doctor_dictation/admin.py", "doctor-dictation/Dockerfile", "doctor-dictation/docker-compose.yml", "doctor-dictation/scripts/deploy/"] },
          { id: "dd-demo", name: "DD demo & tooling", category: "Demo", status: "Demo", desc: "seed-demo (DEMO_MODE=1), Playwright browser walkthrough, stub providers, STT benchmark (POC, no clips), ONNX STT (stub).", paths: ["doctor-dictation/doctor_dictation/admin_demo.py", "doctor-dictation/scripts/demo_browser.py", "doctor-dictation/doctor_dictation/bench/", "doctor-dictation/doctor_dictation/providers/stt/onnx.py"] }
        ]
      },
      {
        id: "cg", name: "Count Guard", category: "Product", status: "Partial", lifecycle: "Current",
        desc: "One FastAPI app + one React app that host five product generations. The current product is the 'Ward 4' care app (D) with the AI admin ops agent (E). Generations A–C are still mounted and reachable via 'Older screens'.",
        purpose: "Make sure nothing gets lost around one patient: instruments, swabs, medicines, words, questions. 'The AI does the reading, counting and writing. People decide.'",
        persona: "Ward doctor, nurse, patient (synthetic data, research demo)",
        paths: ["count-guard/backend/app/", "count-guard/frontend/src/"],
        ui: "http://127.0.0.1:5173 (React) → API :8100", db: "SQLite: morning.db (care, journey, ops) + countguard.db (camera counter)",
        evidence: ["count-guard/backend/app/main.py:31-69 (18 routers)", "count-guard/frontend/src/App.jsx:170-195 (8 care + 16 old routes)"],
        children: [
          {
            id: "cg-care", name: "Care app 'Ward 4' (generation D)", category: "Product", status: "Implemented", lifecycle: "Current",
            desc: "Three roles share one append-only timeline per patient: state machine, orders and tasks, swab-count hard stop, video and photo checks, alerts, patient Ask, discharge, Inspector, AI activity.",
            paths: ["count-guard/backend/app/journey/", "count-guard/frontend/src/care/"],
            children: [
              { id: "cg-flow", name: "Patient flow", category: "Module", status: "Implemented", desc: "clinic → admitting → ward ⇄ theatre → discharging → home with checklists; 409 with a plain reason on illegal moves.", paths: ["count-guard/backend/app/journey/states.py", "count-guard/backend/app/journey/flow_api.py"] },
              { id: "cg-orders", name: "Orders & nurse tasks", category: "Module", status: "Implemented", desc: "Dictate/type → draft → sign → acknowledge; tasks with values and photo proof.", paths: ["count-guard/backend/app/journey/dictation.py", "count-guard/backend/app/journey/tasks.py", "count-guard/backend/app/journey/media_api.py"] },
              { id: "cg-count", name: "Swab count hard stop", category: "Module", status: "Implemented", desc: "Surgery cannot end until a person saves a closing count that adds up or gives a reason; camera read shown, never auto-filled.", paths: ["count-guard/backend/app/journey/states.py:95-110", "count-guard/backend/app/journey/count_api.py", "count-guard/frontend/src/care/CountPanel.jsx"] },
              { id: "cg-checks", name: "Video & photo checks", category: "Module", status: "Mock", desc: "Tray vs procedure plan, saline set-up, strip vs Rx, medicines from home. Results come from hand-made fixtures unless a key is set (never done).", paths: ["count-guard/backend/app/journey/video_api.py", "count-guard/backend/app/journey/live.py", "count-guard/backend/app/journey/prepared/"] },
              { id: "cg-alerts", name: "Observations & alerts", category: "Module", status: "Implemented", desc: "Obs vs doctor-set limits → named alert → 'What did you do?'.", paths: ["count-guard/backend/app/journey/nudges.py", "count-guard/frontend/src/care/AlertCard.jsx"] },
              { id: "cg-ask", name: "Patient Ask", category: "Module", status: "Implemented", desc: "Record-grounded bot, question to doctor, healing-photo review, doctor voice answer with decision.", paths: ["count-guard/backend/app/journey/ask.py", "count-guard/backend/app/journey/ask_api.py"] },
              { id: "cg-explain", name: "Inspector & AI activity", category: "Module", status: "Implemented", desc: "Why / Evidence / History / Model per AI row; staff AI activity page with model cards (Try sample is demo).", paths: ["count-guard/frontend/src/care/Inspector.jsx", "count-guard/frontend/src/care/AiDashboard.jsx", "count-guard/backend/app/journey/ai_api.py"] }
            ]
          },
          { id: "cg-ops", name: "AI admin ops agent (generation E)", category: "Module", status: "Implemented", lifecycle: "Current", desc: "watch → plan → policy gate → apply inside every write; L3/L2 act (10-min Undo), L1 propose, 'Never' for prescribe/dose/advise/clear count/discharge; Pause. Rule-based; optional Spark rewording.", paths: ["count-guard/backend/app/ops/"] },
          { id: "cg-kernel", name: "Care platform kernel", category: "Platform", status: "Implemented", lifecycle: "Current", desc: "Episode + append-only event store with supersede corrections (morning.db), visible_events, the live/prepared perception seam, four model adapters, advice-word verifier. Spread across morning/, journey/, adapters/, agent/.", paths: ["count-guard/backend/app/morning/store.py", "count-guard/backend/app/morning/discharge.py", "count-guard/backend/app/journey/live.py", "count-guard/backend/app/adapters/", "count-guard/backend/app/agent/verifier.py"] },
          { id: "cg-a", name: "Camera swab counter (generation A, v1)", category: "Legacy", status: "Deprecated", lifecycle: "Legacy", desc: "The original 'Count Guard': SAM tracks, zones, rules R1–R6, discrepancies, Spark Open narrative, PDF count sheet. Runs on scripted detections only.", paths: ["count-guard/backend/app/core/", "count-guard/backend/app/engine.py", "count-guard/backend/app/agent/reconciler.py", "count-guard/backend/app/report/", "count-guard/backend/app/api/"] },
          { id: "cg-b", name: "Morning timeline (generation B)", category: "Legacy", status: "Deprecated", lifecycle: "Legacy", desc: "Single-patient OPD → OT → ward morning: brown-bag strips, drug log, vitals sim + fact card, discharge PDF/ICS, SSE stream.", paths: ["count-guard/backend/app/morning/", "count-guard/frontend/src/screens/"] },
          { id: "cg-c", name: "Care journey v1 (generation C)", category: "Legacy", status: "Deprecated", lifecycle: "Legacy", desc: "Doctor / Nurse / Patient / Audit screens, three-act scripted play, handover, reminders.", paths: ["count-guard/backend/app/journey/api.py", "count-guard/backend/app/journey/play.py", "count-guard/frontend/src/screens/"] },
          { id: "cg-demo", name: "Demo & showcase layer", category: "Demo", status: "Demo", lifecycle: "Current", desc: "DemoDock (role, patient, clock, reset), seed, demo prescription, Try sample, prepared fixtures, 32-beat headless demo-check, eval scripts.", paths: ["count-guard/frontend/src/care/DemoDock.jsx", "count-guard/backend/app/journey/seed.py", "count-guard/frontend/scripts/demo/", "count-guard/eval/"] },
          { id: "cg-poc", name: "Research POCs", category: "POC", status: "POC", lifecycle: "Legacy", desc: "Spark-only baseline (NotImplementedError), day-1 API check, SAM cost estimator, real-video pipeline, fixture recorder.", paths: ["count-guard/backend/app/baseline.py", "count-guard/backend/app/day1.py", "count-guard/backend/app/spend.py", "count-guard/backend/app/media_pipeline.py", "count-guard/eval/record_fixtures.py"] }
        ]
      },
      { id: "link", name: "DD → CG prescription link", category: "Shared", status: "Implemented", desc: "The only runtime coupling: Count Guard GETs a saved Doctor Dictation document over HTTP (option A, no shared code).", paths: ["count-guard/backend/app/journey/rx.py:83-107", "count-guard/backend/app/config.py:103"] },
      { id: "docs", name: "Design docs & specs", category: "Shared", status: "Partial", desc: "docs/hackathon (21 Oct umbrella plan, mostly superseded), docs/superpowers (10 specs + 13 plans for Count Guard), demo video script.", paths: ["docs/hackathon/", "docs/superpowers/", "docs/demo/count-guard-v2-video-script.md"] }
    ]
  }
];

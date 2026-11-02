/* Architecture diagrams (Mermaid sources). kind: Implemented | Documented (described, not built) | Proposed (recommendation). */
window.DATA = window.DATA || {};

DATA.diagrams = [
  { id: "hier", title: "Product hierarchy", kind: "Implemented",
    note: "Solid = current product. Dashed = archived to count-guard/archive/ (not mounted). The thick arrow is the DD → CG patient flow added on 2 Nov.",
    src: `flowchart TB
  WS["hackathon26 workspace<br/>(shared .env, Makefile)"]
  WS --> DD["Doctor Dictation<br/>OPD voice → prescription"]
  WS --> CG["Count Guard<br/>(one FastAPI + one React)"]
  DD --> DD1[Capture] & DD2[Structuring] & DD3[Medication safety] & DD4[Records & output] & DD5[Admit to ward] & DD6[Access & tenancy]
  CG --> D["Care app 'Ward 4'<br/>ward · theatre · discharge"]
  CG --> E["AI admin ops agent"]
  CG --> K["Care platform kernel<br/>ledger · switches · camera libs · verifier"]
  CG --> X["Demo layer<br/>dock · seed · demo-check · live-check"]
  CG -.-> AR["archive/<br/>camera counter · morning · journey v1 screens & routes"]
  DD5 ==Save & admit: push to /journey/intake==> D
  D ==Sync: GET /api/v1/admissions==> DD` },
  { id: "app", title: "Application architecture (as built)", kind: "Implemented",
    note: "Two servers, two databases, no shared code. DD pushes admissions to CG; CG pulls them on Sync; CG links to the DD PDF. The legacy camera libraries (core/, engine.py, report/) are now imported by the theatre camera.",
    src: `flowchart LR
  subgraph DDapp["Doctor Dictation :8000"]
    DUI["Vanilla JS SPA<br/>app.js · admit.js"] --> DAPI["FastAPI<br/>20 routers"]
    DAPI --> DCORE["core/ pure rules<br/>lexicon · rowcheck · LASA · vitals"]
    DAPI --> DDB[("SQLite<br/>app.db per clinic (+ admissions)<br/>directory.db")]
    DAPI --> PDF["Chromium PDF pool"]
    DAPI --> ADM["api/admit.py<br/>background push"]
  end
  subgraph CGapp["Count Guard :5173 → :8100"]
    CUI["React 19 + Vite<br/>src/care only"] -->|"Vite proxy · SSE"| CAPI["FastAPI<br/>26 routers"]
    CAPI --> J["journey/ care app<br/>intake · ward · theatre · camera · discharge"]
    CAPI --> O["ops/ agent"]
    J & O --> MDB[("morning.db<br/>episodes · timeline · intake_keys · clock")]
    J --> CAM["core/ · engine.py · report/<br/>camera libraries"] --> CDB[("countguard.db<br/>camera cases")]
    J --> SW["switches.py + live.py<br/>live : prepared (labelled)"]
  end
  DAPI --> LLM["LLM: OpenAI-compatible<br/>openai · deepseek · groq · meta"]
  DAPI --> STT["STT: OpenAI · Groq · AssemblyAI<br/>Muse · faster-whisper"]
  SW --> META["Meta API<br/>SAM 3.1 · Voice · Spark 1.3"]
  ADM -->|"POST /journey/intake"| CAPI
  J -->|"Sync: GET /api/v1/admissions"| DAPI` },
  { id: "integration", title: "DD → Count Guard: Save & admit, push, Sync", kind: "Implemented",
    note: "doctor_dictation/api/admit.py:101-178, migration 015_admissions.sql, count-guard journey/intake.py, intake_api.py:78-111, sync.py. Single-clinic DD only; optional CG_SYNC_TOKEN header on both hops; the token never reaches a browser.",
    src: `sequenceDiagram
  participant Dr as Doctor (DD page)
  participant DD as DD FastAPI
  participant ADB as DD app.db (admissions)
  participant CG as CG FastAPI
  participant IN as journey/intake.py
  participant MDB as morning.db
  Dr->>DD: POST /api/v1/documents {admit: true, admit_reason}
  DD->>ADB: commit document + admissions row (status admit)
  DD-->>Dr: document_id (Save never waits for CG)
  DD--)CG: background POST /journey/intake (1 s connect, 3 s total)
  CG->>IN: take(source, document_id)
  IN->>MDB: claim intake_keys first (duplicate = already here)
  IN->>MDB: patient.registered → rx.ordered → clinic→admitting
  CG->>CG: settle(): nudges + ops agent
  CG-->>DD: 200
  DD->>ADB: pushed_at (or last_error)
  Dr->>DD: poll GET /api/v1/documents/{id}/admission
  Note over CG,DD: Backup: nurse presses Sync
  CG->>DD: GET /api/v1/admissions?since=
  DD-->>CG: same payloads as the push
  CG->>IN: take() each row: new / already here / updated` },
  { id: "cgwrite", title: "Count Guard: one write, end to end", kind: "Implemented",
    note: "Every care write recomputes alerts and runs the ops agent synchronously before returning the patient view; the SSE streams then notify the ward list and chart.",
    src: `sequenceDiagram
  participant UI as React care app
  participant R as journey router
  participant S as MorningStore (morning.db)
  participant N as nudges
  participant OPS as ops agent
  UI->>R: POST /journey/episodes/{id}/count
  R->>R: Pydantic validate (extra=forbid, bounds), at_ms clamped to the server clock
  R->>S: append event (append-only, supersedes_id for corrections)
  R->>N: settle(): raise_nudges
  R->>OPS: settle(): watch → plan → gate → apply
  OPS->>S: work.* events as "AI (on behalf of Ward 4)"
  R->>S: view(): recompute stories, flow, ai_moments, ops
  R-->>UI: full patient view
  S--)UI: SSE /journey/ward/stream · /episodes/{id}/stream` },
  { id: "gate", title: "Swab-count hard stop", kind: "Implemented",
    note: "count_gate in journey/states.py:95-109, unchanged by the consolidation; by_ai in stories.py:245-249 folds look-alike letters. test_route_sweep.py proves only POST …/count writes a person's closing.",
    src: `flowchart TD
  S[POST surgery step=ended] --> G{count_gate}
  G -->|no closing after 'began'| N["409 Save the swab count first"]
  G -->|closing 'by' reads as AI or camera| N
  G -->|opened − returned ≠ 0 and no reason| U["409 count does not add up"]
  G -->|adds up OR reason given| OK["surgery.ended recorded"]
  P["Pack opened / extra pack / confirmed heard pack"] -->|adds to opened| G
  CAM["Swab camera, rules R1–R6, replay, dwell"] -.advice only, never read.-> G
  AI["AI-signed confirm"] -->|422 refused| P` },
  { id: "states", title: "Patient state machine", kind: "Implemented",
    note: "journey/states.py:130-170 and check_gate.py. The current state is the latest patient.state event. Intake enters at clinic (New patient) or admitting (DD admission).",
    src: `stateDiagram-v2
  [*] --> clinic: New patient
  [*] --> admitting: DD Save & admit
  clinic --> clinic_done
  clinic --> admitting
  admitting --> ward: checklist + photo checks accepted
  ward --> theatre
  theatre --> ward: needs count_gate ok
  ward --> discharging
  discharging --> home: checks + photo checks accepted
  clinic_done --> [*]
  home --> [*]` },
  { id: "ddflow", title: "Doctor Dictation: dictate → save → (admit)", kind: "Implemented",
    src: `sequenceDiagram
  participant Dr as Doctor (browser)
  participant API as DD FastAPI
  participant STT as STT chain
  participant L as LLM (optional)
  participant C as core rules
  participant DB as clinic app.db
  Dr->>API: POST /api/transcribe (audio)
  API->>STT: provider chain, fallback to next
  STT-->>Dr: transcript
  Dr->>API: POST /api/format
  alt LLM configured
    API->>L: JSON-mode extract
    API->>C: ground + repair loop (≤ cap)
  else no key
    API->>C: rules fallback + lexicon
  end
  API-->>Dr: sheet + row pills
  Dr->>API: POST /api/v1/documents (confirmed_rows, admit?)
  API->>C: verify gate (409 if unverified)
  API->>DB: document, audit, learning side effects, admissions row
  API-->>Dr: document_id → PDF, share link
  API--)API: admit? background push to Count Guard` },
  { id: "auth", title: "Authentication & authorisation", kind: "Implemented",
    note: "Doctor Dictation only, and only with MULTI_CLINIC=1 (where intake answers 404). Count Guard has no user authentication: the actor is a free-text 'by' field and role is client UI state. The DD↔CG hops can share an optional CG_SYNC_TOKEN header.",
    src: `sequenceDiagram
  participant B as Browser
  participant MW as SessionMiddleware
  participant A as /api/v1/auth/login
  participant DIR as directory.db
  participant CL as clinic app.db
  B->>A: username + password
  A->>DIR: login_index → clinic, lockout 5/300s
  A->>CL: scrypt verify
  A-->>B: dd_session (HMAC, 12h, HttpOnly, SameSite=Lax)
  B->>MW: request + cookie (+ X-DD-Client on writes)
  MW->>CL: session_version, active user
  MW->>DIR: sid not revoked
  MW-->>B: scoped to one clinic DB, or 401` },
  { id: "data", title: "Data stores", kind: "Implemented",
    src: `erDiagram
  DD_CLINIC_DB ||--o{ users : has
  DD_CLINIC_DB ||--o{ patients : has
  patients ||--o{ encounters : has
  encounters ||--o{ documents : has
  documents ||--o| admissions : "admit / send_home (015)"
  encounters ||--o| share_links : has
  DD_CLINIC_DB ||--o{ clinic_formulary : learns
  DD_CLINIC_DB ||--o{ spoken_terms : learns
  DD_DIRECTORY ||--o{ clinics : lists
  DD_DIRECTORY ||--o{ login_index : maps
  CG_MORNING_DB ||--o{ episodes : "patients + staff board + ops site"
  episodes ||--o{ timeline : "append-only events (supersedes_id)"
  episodes ||--o| episode_beds : bed
  CG_MORNING_DB ||--o{ intake_keys : "source + document_id → episode"
  CG_MORNING_DB ||--o| clock : "server demo clock"
  CG_COUNTGUARD_DB ||--o{ cases : "theatre camera cases"` },
  { id: "deploy", title: "Deployment", kind: "Documented",
    note: "DD's Docker/Caddy/VPS assets are real; the live pilot (docs/working/2026-10-18-deployment) cannot be verified from code, and 02-deploy.sh clones a separate upstream repo. Count Guard has no deployment assets: local dev only, and the DD→CG push assumes both on one machine (COUNT_GUARD_URL default 127.0.0.1:8100).",
    src: `flowchart LR
  subgraph VPS["Ubuntu VPS (documented pilot)"]
    CADDY["Caddy 2<br/>auto-HTTPS, log masking"] --> APP["DD container<br/>uvicorn ×2, Chromium, ffmpeg<br/>MULTI_CLINIC=1"]
    APP --> VOL[("/data volume")]
    BK["03-backup.sh<br/>age-encrypted, every 6h"] --> VOL
  end
  GH["upstream repo"] -->|02-deploy.sh| APP
  LOCAL["Laptop: make dev<br/>DD :8000 · CG :8100/:5173<br/>demo-check: DD :8300 · CG :8200/:5273"]` },
  { id: "plan", title: "Originally planned architecture (21 Oct)", kind: "Documented",
    note: "docs/hackathon/02-architecture.md. NOT built: superseded by decisions D1 and J1 (separate Count Guard app, HTTP link) and by the 2 Nov push + Sync design.",
    src: `flowchart LR
  DDp["Doctor Dictation"] --> HX["doctor_dictation/hx/<br/>HACKATHON=1"]
  HX --> TL[("timeline_events<br/>011_timeline.sql")]
  HX --> VP["VisionPort<br/>sam-api · replay · sam-local"]
  HX --> VT["VitalsPort<br/>sim · hl7 · screen"]
  HX --> SSE["SSE /api/hx/episodes/{id}/stream"]` },
  { id: "proposed", title: "Recommended module boundaries", kind: "Proposed",
    note: "Recommendation only. The archive step is done (2 Nov); the platform extraction and async ops runner are not.",
    src: `flowchart TB
  subgraph Products
    RX["Doctor Dictation<br/>(OPD prescription + admit)"]
    WARD["Count Guard Care<br/>(ward, theatre, discharge, ask)"]
  end
  subgraph Platform["Care platform (extract from CG) — not done"]
    LED["ledger: episodes, events, supersede, intake keys"]
    PER["perception: adapters + switches + camera libs"]
    OPS["ops agent (async, outbox)"]
    VER["advice verifier"]
  end
  subgraph Showcase
    DEMO["demo: dock, seed, fixtures, demo-check, live-check"]
  end
  subgraph Archive["Archive — done 2 Nov"]
    ARC["count-guard/archive/"]
  end
  WARD --> LED & PER & OPS
  OPS --> VER
  RX -->|"intake push"| WARD
  WARD -->|"Sync pull"| RX
  DEMO -.-> WARD` }
];

/* Product vs Demo vs POC classification */
DATA.classification = [
  { bucket: "Product (current)", status: "Implemented", items: [
    ["Doctor Dictation core", "Dictate → structure → ground → verify → save → PDF/share, multi-clinic tenancy, Save & admit", "doctor-dictation/doctor_dictation/api/"],
    ["Count Guard care app", "Ward list + intake/Sync, state machine, photo verdicts, theatre, swab hard stop, discharge draft/PDF, Ask, Inspector, Help", "count-guard/backend/app/journey/, count-guard/frontend/src/care/"],
    ["AI admin ops agent", "Rule-based clerical agent with policy gate and Undo", "count-guard/backend/app/ops/"],
    ["DD → CG patient flow", "Push on admit, Sync pull, one intake path", "doctor-dictation/doctor_dictation/api/admit.py, count-guard/backend/app/journey/intake.py"]] },
  { bucket: "Partial (real code, missing data or wiring)", status: "Partial", items: [
    ["LASA guard", "8 unreviewed pairs", "doctor-dictation/doctor_dictation/core/lexicon/lasa_pairs.json"],
    ["Dose-range check", "dosing.json is empty", "doctor-dictation/doctor_dictation/core/lexicon/dosing.json"],
    ["Investigations grounding", "catalogue file missing", "doctor-dictation/doctor_dictation/core/investigations.py:19"],
    ["Live camera / real-video SAM", "Live call works; 0 swabs found on drawn media; no real clip measured", "count-guard/backend/app/journey/camera_extra_api.py:96, media_pipeline.py"]] },
  { bucket: "Mock (real logic, prepared or simulated model output)", status: "Mock", items: [
    ["Count Guard video, photo and voice reads (switch off)", "Prepared results labelled 'Prepared'; tray/set-up/swab fixtures still picked by file name, photos by bytes", "count-guard/backend/app/journey/live.py:94-98, switches.py"],
    ["Recorded theatre clip", "Scripted scenario, labelled Prepared", "count-guard/backend/app/scenarios.py, journey/camera_api.py:163-200"],
    ["Theatre vitals", "Simulated strip", "count-guard/backend/app/morning/vitals.py"]] },
  { bucket: "Demo / showcase only", status: "Demo", items: [
    ["Count Guard Demo dock, seed, demo prescription", "Presenter controls outside the product", "count-guard/frontend/src/care/DemoDock.jsx"],
    ["AI activity 'Try sample'", "Bundled samples unless a switch is live", "count-guard/backend/app/journey/ai_api.py"],
    ["Two-app demo-check (20 beats, 180 s)", "Headless regression of the video flow", "count-guard/frontend/scripts/demo/"],
    ["DD seed-demo, demo_browser.py, DEMO_BANNER", "Fake clinics, stub STT/LLM, research banner", "doctor-dictation/doctor_dictation/admin_demo.py"]] },
  { bucket: "POC / experimental", status: "POC", items: [
    ["Discrepancy explanation", "Wired into camera close; live only with SPARK_LIVE / Baseten; not live-checked", "count-guard/backend/app/journey/camera_explain.py"],
    ["Fixture recorder, day-1 check, cost estimator", "Research tooling", "count-guard/eval/record_fixtures.py, backend/app/day1.py, spend.py"],
    ["DD STT benchmark", "No clips ship", "doctor-dictation/doctor_dictation/bench/"]] },
  { bucket: "Stub / planned", status: "Stub", items: [
    ["Spark baseline", "NotImplementedError", "count-guard/backend/app/baseline.py:66-67"],
    ["ONNX/Snapdragon STT", "Deferred", "doctor-dictation/doctor_dictation/providers/stt/onnx.py"],
    ["Browser Web Speech fallback", "Promised in an error message, not built", "doctor-dictation/doctor_dictation/providers/stt/factory.py:116"],
    ["CG discharge report back to DD", "Deferred until after the hackathon (spec U16)", "docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md:50"]] },
  { bucket: "Archived / deprecated", status: "Deprecated", items: [
    ["Camera counter, morning and journey v1 screens & routes", "Moved with git mv; not imported or mounted", "count-guard/archive/"],
    ["Scripted plays (three-act, morning)", "Retired (U13)", "count-guard/archive/backend/app/journey/play.py, morning/script.py"],
    ["CG POST …/rx/import", "Still mounted; no screen calls it (intake replaced it)", "count-guard/backend/app/journey/api.py:226"],
    ["DD patient/encounter CRUD", "UI never calls", "doctor-dictation/doctor_dictation/api/persistence.py:60-89"]] }
];

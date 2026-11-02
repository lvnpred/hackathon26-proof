/* Architecture diagrams (Mermaid sources). kind: Implemented | Documented (described, not built) | Proposed (recommendation). */
window.DATA = window.DATA || {};

DATA.diagrams = [
  { id: "hier", title: "Product hierarchy", kind: "Implemented",
    note: "Solid = current product. Dashed = legacy generations still mounted in Count Guard.",
    src: `flowchart TB
  WS["hackathon26 workspace<br/>(shared .env, Makefile)"]
  WS --> DD["Doctor Dictation<br/>OPD voice → prescription"]
  WS --> CG["Count Guard app<br/>(one FastAPI + one React)"]
  DD --> DD1[Capture] & DD2[Structuring] & DD3[Medication safety] & DD4[Records & output] & DD5[Clinic learning] & DD6[Access & tenancy]
  CG --> D["D · Care app 'Ward 4'<br/>CURRENT"]
  CG --> E["E · AI admin ops agent<br/>CURRENT"]
  CG --> K["Care platform kernel<br/>ledger · perception seam · verifier"]
  CG -.-> A["A · Camera swab counter<br/>legacy"]
  CG -.-> B["B · Morning timeline<br/>legacy"]
  CG -.-> C["C · Care journey v1<br/>legacy"]
  CG --> X["Demo layer<br/>dock · seed · fixtures · demo-check"]
  CG ==HTTP GET document==> DD` },
  { id: "app", title: "Application architecture (as built)", kind: "Implemented",
    note: "The two apps share no code. The only runtime link is Count Guard reading a Doctor Dictation document over HTTP.",
    src: `flowchart LR
  subgraph DDapp["Doctor Dictation :8000"]
    DUI["Vanilla JS SPA<br/>frontend/app.js"] --> DAPI["FastAPI<br/>19 routers"]
    DAPI --> DCORE["core/ pure rules<br/>lexicon · rowcheck · LASA · vitals"]
    DAPI --> DDB[("SQLite<br/>app.db per clinic<br/>directory.db")]
    DAPI --> PDF["Chromium PDF pool"]
  end
  subgraph CGapp["Count Guard :5173 → :8100"]
    CUI["React 19 + Vite<br/>src/care · src/screens"] -->|"Vite proxy"| CAPI["FastAPI<br/>18 routers"]
    CAPI --> J["journey/ care app"]
    CAPI --> O["ops/ agent"]
    CAPI --> M["morning/ (legacy + store)"]
    CAPI --> V1["core/ engine/ (legacy)"]
    J & O & M --> MDB[("morning.db<br/>episodes + timeline")]
    V1 --> CDB[("countguard.db")]
    J --> LIVE["live.py seam<br/>key? live : prepared JSON"]
  end
  DAPI --> LLM["LLM: OpenAI-compatible<br/>openai · deepseek · groq · meta"]
  DAPI --> STT["STT: OpenAI · Groq · AssemblyAI<br/>Muse · faster-whisper"]
  LIVE --> META["Meta API<br/>SAM 3.1 · Voice · Spark 1.3"]
  V1 --> BT["Baseten<br/>Spark Open"]
  J -->|"rx/import"| DAPI` },
  { id: "cgwrite", title: "Count Guard: one write, end to end", kind: "Implemented",
    note: "Every care write recomputes alerts and runs the ops agent synchronously before returning the whole patient view.",
    src: `sequenceDiagram
  participant UI as React care app
  participant R as journey router
  participant S as MorningStore (morning.db)
  participant N as nudges
  participant OPS as ops agent
  UI->>R: POST /journey/episodes/{id}/count
  R->>R: Pydantic validate (extra=forbid, bounds)
  R->>S: append event (append-only, supersedes_id for corrections)
  R->>N: settle(): raise_nudges
  R->>OPS: settle(): watch → plan → gate → apply (≤3 passes, per-episode lock)
  OPS->>S: work.* events as "AI (on behalf of Ward 4)"
  R->>S: view(): recompute stories, flow, ai_moments, ops
  R-->>UI: full patient view` },
  { id: "gate", title: "Swab-count hard stop", kind: "Implemented",
    note: "count_gate in journey/states.py:95-110; enforced by POST …/surgery step=ended (flow_api.py:68-76).",
    src: `flowchart TD
  S[POST surgery step=ended] --> G{count_gate}
  G -->|no closing after 'began'| N["409 Save the swab count first"]
  G -->|closing by AI / no person| N
  G -->|opened − returned ≠ 0 and no reason| U["409 count does not add up"]
  G -->|adds up OR reason given| OK["surgery.ended recorded"]
  P[Pack opened] -->|after began: only up| G
  CAM[Camera read] -.shown beside, never fills.-> G` },
  { id: "states", title: "Patient state machine", kind: "Implemented",
    note: "journey/states.py:19-38. The current state is the latest patient.state event.",
    src: `stateDiagram-v2
  [*] --> clinic
  clinic --> clinic_done
  clinic --> admitting
  admitting --> ward: checklist band · allergies · baseline obs · consent
  ward --> theatre
  theatre --> ward: needs count_gate ok
  ward --> discharging
  discharging --> home: card · medicines · reminders
  clinic_done --> [*]
  home --> [*]` },
  { id: "ddflow", title: "Doctor Dictation: dictate → save", kind: "Implemented",
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
  Dr->>API: POST /api/v1/documents (confirmed_rows)
  API->>C: verify gate (409 if unverified)
  API->>DB: document, audit, learning side effects
  API-->>Dr: document_id → PDF, share link` },
  { id: "auth", title: "Authentication & authorisation", kind: "Implemented",
    note: "Doctor Dictation only, and only with MULTI_CLINIC=1. Count Guard has no authentication: the actor is a free-text 'by' field and role is client UI state.",
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
  encounters ||--o| share_links : has
  DD_CLINIC_DB ||--o{ clinic_formulary : learns
  DD_CLINIC_DB ||--o{ clinic_overlay : curates
  DD_CLINIC_DB ||--o{ spoken_terms : learns
  DD_DIRECTORY ||--o{ clinics : lists
  DD_DIRECTORY ||--o{ login_index : maps
  CG_MORNING_DB ||--o{ episodes : "patients + staff board + ops site"
  episodes ||--o{ timeline : "append-only events (supersedes_id)"
  CG_COUNTGUARD_DB ||--o{ cases : "legacy camera counter"` },
  { id: "deploy", title: "Deployment", kind: "Documented",
    note: "DD's Docker/Caddy/VPS assets are real; the live pilot (docs/working/2026-10-18-deployment) cannot be verified from code, and 02-deploy.sh clones a separate upstream repo. Count Guard has no deployment assets: local dev only.",
    src: `flowchart LR
  subgraph VPS["Ubuntu VPS (documented pilot)"]
    CADDY["Caddy 2<br/>auto-HTTPS, log masking"] --> APP["DD container<br/>uvicorn ×2, Chromium, ffmpeg<br/>MULTI_CLINIC=1"]
    APP --> VOL[("/data volume")]
    BK["03-backup.sh<br/>age-encrypted, every 6h"] --> VOL
  end
  GH["upstream repo<br/>lvnpred/doctor-dictation"] -->|02-deploy.sh| APP
  LOCAL["Laptop: make dev<br/>DD :8000 · CG :8100/:5173"]` },
  { id: "plan", title: "Originally planned architecture (21 Oct)", kind: "Documented",
    note: "docs/hackathon/02-architecture.md. NOT built: superseded by decisions D1 and J1 (separate Count Guard repo, HTTP link).",
    src: `flowchart LR
  DDp["Doctor Dictation"] --> HX["doctor_dictation/hx/<br/>HACKATHON=1"]
  HX --> TL[("timeline_events<br/>011_timeline.sql")]
  HX --> VP["VisionPort<br/>sam-api · replay · sam-local"]
  HX --> VT["VitalsPort<br/>sim · hl7 · screen"]
  HX --> SSE["SSE /api/hx/episodes/{id}/stream"]` },
  { id: "proposed", title: "Recommended module boundaries", kind: "Proposed",
    note: "Recommendation only — nothing has been moved.",
    src: `flowchart TB
  subgraph Products
    RX["Doctor Dictation<br/>(OPD prescription)"]
    WARD["Count Guard Care<br/>(ward: flow, count, tasks, ask)"]
  end
  subgraph Platform["Care platform (extract from CG)"]
    LED["ledger: episodes, events, supersede"]
    PER["perception: adapters + live/prepared seam"]
    OPS["ops agent (async, outbox)"]
    VER["advice verifier"]
  end
  subgraph Showcase
    DEMO["demo: dock, seed, fixtures, demo-check"]
  end
  subgraph Archive
    ARC["camera counter · morning · journey v1"]
  end
  WARD --> LED & PER & OPS
  OPS --> VER
  WARD -->|"Rx API"| RX
  DEMO -.-> WARD` }
];

/* Product vs Demo vs POC classification */
DATA.classification = [
  { bucket: "Product (current)", status: "Implemented", items: [
    ["Doctor Dictation core", "Dictate → structure → ground → verify → save → PDF/share, multi-clinic tenancy", "doctor-dictation/doctor_dictation/api/"],
    ["Count Guard care app (D)", "State machine, orders/tasks, swab hard stop, alerts, Ask, discharge, Inspector", "count-guard/backend/app/journey/, count-guard/frontend/src/care/"],
    ["AI admin ops agent (E)", "Rule-based clerical agent with policy gate and Undo", "count-guard/backend/app/ops/"]] },
  { bucket: "Partial (real code, missing data or wiring)", status: "Partial", items: [
    ["LASA guard", "8 unreviewed pairs", "doctor-dictation/doctor_dictation/core/lexicon/lasa_pairs.json"],
    ["Dose-range check", "dosing.json is empty", "doctor-dictation/doctor_dictation/core/lexicon/dosing.json"],
    ["Investigations grounding", "catalogue file missing", "doctor-dictation/doctor_dictation/core/investigations.py:19"],
    ["Sheet sections", "no per-clinic override", "doctor-dictation/doctor_dictation/api/sections.py:24"]] },
  { bucket: "Mock (real logic, simulated model output)", status: "Mock", items: [
    ["Count Guard video, photo and voice reads", "Hand-made fixtures chosen by uploaded file name; no real key ever used", "count-guard/backend/app/journey/live.py:87-100, journey/prepared/*.json"],
    ["Legacy camera counter detections", "Scripted scenarios", "count-guard/backend/app/scenarios.py"],
    ["Vitals feed", "Simulator", "count-guard/backend/app/morning/sim.py"]] },
  { bucket: "Demo / showcase only", status: "Demo", items: [
    ["Count Guard Demo dock, seed, demo prescription, clock", "Presenter controls outside the product", "count-guard/frontend/src/care/DemoDock.jsx"],
    ["AI activity 'Try sample'", "Bundled samples; spark-open always prepared", "count-guard/backend/app/journey/ai_api.py:96-130"],
    ["demo-check (32 beats)", "Headless regression of the demo story", "count-guard/frontend/scripts/demo/"],
    ["DD seed-demo and demo_browser.py", "Two fake clinics, stub STT/LLM", "doctor-dictation/doctor_dictation/admin_demo.py"],
    ["DD stub providers", "ALLOW_STUB_PROVIDERS=1", "doctor-dictation/doctor_dictation/providers/llm/stub.py"]] },
  { bucket: "POC / experimental", status: "POC", items: [
    ["Spark Open discrepancy reconciler", "Never called live", "count-guard/backend/app/agent/reconciler.py"],
    ["Real-video SAM pipeline + WebSocket", "Never run with a key; WS has no caller", "count-guard/backend/app/media_pipeline.py, api/ws.py"],
    ["Fixture recorder, day-1 check, cost estimator", "Research tooling", "count-guard/eval/record_fixtures.py, backend/app/day1.py, spend.py"],
    ["DD STT benchmark", "No clips ship", "doctor-dictation/doctor_dictation/bench/"]] },
  { bucket: "Stub / planned", status: "Stub", items: [
    ["Spark baseline", "NotImplementedError", "count-guard/backend/app/baseline.py:66-67"],
    ["ONNX/Snapdragon STT", "Deferred", "doctor-dictation/doctor_dictation/providers/stt/onnx.py"],
    ["Browser Web Speech fallback", "Promised in an error message, not built", "doctor-dictation/doctor_dictation/providers/stt/factory.py:116"],
    ["MedASR / ElevenLabs STT, HL7 vitals, sam-local, hx/ timeline", "Docs only", "doctor-dictation/docs/superpowers/plans/, docs/hackathon/02-architecture.md"]] },
  { bucket: "Legacy (superseded but mounted)", status: "Deprecated", items: [
    ["Camera swab counter (A)", "Older screens /count, /case/:id", "count-guard/backend/app/core/, engine.py, api/routes.py"],
    ["Morning timeline (B)", "/steps, /opd, /ot, /ward, /morning", "count-guard/backend/app/morning/"],
    ["Care journey v1 (C)", "/journey, /doctor, /nurse, /patient, /audit", "count-guard/backend/app/journey/api.py, play.py, frontend/src/screens/"],
    ["DD patient/encounter CRUD", "UI never calls", "doctor-dictation/doctor_dictation/api/persistence.py:60-89"]] }
];

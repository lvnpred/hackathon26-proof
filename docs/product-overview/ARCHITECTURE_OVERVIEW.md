# Architecture Overview

> Snapshot of `main` @ `e40d8c7`, generated 2026-11-01. Companion to [index.html](index.html) — same data, same numbers.

## Summary

- **As built:** two FastAPI + SQLite apps with no shared code. Doctor Dictation serves a vanilla JS single page; Count Guard serves React 19 through Vite.
- **Only coupling:** Count Guard calls Doctor Dictation's `GET /api/v1/documents/{id}` over HTTP.
- **Count Guard core pattern:** an append-only event timeline per patient (`morning.db`). Corrections are new events with `supersedes_id`. Every write raises alerts, runs the ops agent synchronously, and returns a recomputed patient view.
- **Doctor Dictation core pattern:** an LLM draft wrapped in deterministic grounding, plus a server-side verify gate. Per-clinic SQLite files sit behind a session middleware, active only in multi-clinic mode.
- **Labels:** each diagram is marked **Implemented** (read from code), **Documented** (described in docs, not all built) or **Proposed** (recommendation). An intended architecture is never shown as built.

**Decision needed:** whether to adopt the Proposed module boundaries (last diagram) as the target.

## Product hierarchy — Implemented

Solid = current product. Dashed = legacy generations still mounted in Count Guard.

```mermaid
flowchart TB
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
  CG ==HTTP GET document==> DD
```

## Application architecture (as built) — Implemented

The two apps share no code. The only runtime link is Count Guard reading a Doctor Dictation document over HTTP.

```mermaid
flowchart LR
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
  J -->|"rx/import"| DAPI
```

## Count Guard: one write, end to end — Implemented

Every care write recomputes alerts and runs the ops agent synchronously before returning the whole patient view.

```mermaid
sequenceDiagram
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
  R-->>UI: full patient view
```

## Swab-count hard stop — Implemented

count_gate in journey/states.py:95-110; enforced by POST …/surgery step=ended (flow_api.py:68-76).

```mermaid
flowchart TD
  S[POST surgery step=ended] --> G{count_gate}
  G -->|no closing after 'began'| N["409 Save the swab count first"]
  G -->|closing by AI / no person| N
  G -->|opened − returned ≠ 0 and no reason| U["409 count does not add up"]
  G -->|adds up OR reason given| OK["surgery.ended recorded"]
  P[Pack opened] -->|after began: only up| G
  CAM[Camera read] -.shown beside, never fills.-> G
```

## Patient state machine — Implemented

journey/states.py:19-38. The current state is the latest patient.state event.

```mermaid
stateDiagram-v2
  [*] --> clinic
  clinic --> clinic_done
  clinic --> admitting
  admitting --> ward: checklist band · allergies · baseline obs · consent
  ward --> theatre
  theatre --> ward: needs count_gate ok
  ward --> discharging
  discharging --> home: card · medicines · reminders
  clinic_done --> [*]
  home --> [*]
```

## Doctor Dictation: dictate → save — Implemented

```mermaid
sequenceDiagram
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
  API-->>Dr: document_id → PDF, share link
```

## Authentication & authorisation — Implemented

Doctor Dictation only, and only with MULTI_CLINIC=1. Count Guard has no authentication: the actor is a free-text 'by' field and role is client UI state.

```mermaid
sequenceDiagram
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
  MW-->>B: scoped to one clinic DB, or 401
```

## Data stores — Implemented

```mermaid
erDiagram
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
  CG_COUNTGUARD_DB ||--o{ cases : "legacy camera counter"
```

## Deployment — Documented

DD's Docker/Caddy/VPS assets are real; the live pilot (docs/working/2026-10-18-deployment) cannot be verified from code, and 02-deploy.sh clones a separate upstream repo. Count Guard has no deployment assets: local dev only.

```mermaid
flowchart LR
  subgraph VPS["Ubuntu VPS (documented pilot)"]
    CADDY["Caddy 2<br/>auto-HTTPS, log masking"] --> APP["DD container<br/>uvicorn ×2, Chromium, ffmpeg<br/>MULTI_CLINIC=1"]
    APP --> VOL[("/data volume")]
    BK["03-backup.sh<br/>age-encrypted, every 6h"] --> VOL
  end
  GH["upstream repo<br/>lvnpred/doctor-dictation"] -->|02-deploy.sh| APP
  LOCAL["Laptop: make dev<br/>DD :8000 · CG :8100/:5173"]
```

## Originally planned architecture (21 Oct) — Documented

docs/hackathon/02-architecture.md. NOT built: superseded by decisions D1 and J1 (separate Count Guard repo, HTTP link).

```mermaid
flowchart LR
  DDp["Doctor Dictation"] --> HX["doctor_dictation/hx/<br/>HACKATHON=1"]
  HX --> TL[("timeline_events<br/>011_timeline.sql")]
  HX --> VP["VisionPort<br/>sam-api · replay · sam-local"]
  HX --> VT["VitalsPort<br/>sim · hl7 · screen"]
  HX --> SSE["SSE /api/hx/episodes/{id}/stream"]
```

## Recommended module boundaries — Proposed

Recommendation only — nothing has been moved.

```mermaid
flowchart TB
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
  DEMO -.-> WARD
```

## Technical stack

### Languages

- **Python 3.12** — Both backends
- **JavaScript (ES modules)** — DD vanilla SPA; CG React + Node scripts
- **SQL** — DD numbered migrations
- **Shell** — DD deploy and backup scripts

### Backend frameworks

- **FastAPI + Uvicorn + Pydantic v2** — Both
- **httpx** — Model and vendor clients
- **python-dotenv** — Shared .env loading

### Frontend

- **Vanilla JS, no build** — Doctor Dictation (app.js 1,404 lines + ~30 modules)
- **React 19, React Router 7, Vite 6** — Count Guard
- **Lightday design system** — Both (tokens in doctor-dictation/docs/design-system/lightday)

### Data

- **SQLite via stdlib sqlite3 (no ORM)** — DD: app.db per clinic + directory.db
- **SQLite** — CG: morning.db + countguard.db
- **JSON files** — DD lexicon data; DD owner list changes; CG prepared fixtures
- **sessionStorage** — CG role, patient, roster

### Real-time / messaging

- **SSE** — CG legacy morning stream only
- **WebSocket** — CG legacy camera stream (no caller)
- **None (synchronous)** — CG ops agent runs inside each request; no queue or broker anywhere

### AI / ML

- **OpenAI-compatible LLM client (openai, deepseek, groq, meta)** — DD structuring, correction, letterhead vision
- **STT: OpenAI whisper-1, Groq, AssemblyAI, Meta Muse Voice, faster-whisper** — DD
- **Meta SAM 3.1, Muse Voice Transcribe, Muse Spark 1.3** — CG (Meta API)
- **Muse Spark Open** — CG (Baseten) — legacy narrative only

### Documents & media

- **Playwright headless Chromium** — DD PDF
- **fpdf2** — CG PDFs
- **segno (QR), Pillow, pillow-heif, pypdfium2** — DD
- **ffmpeg** — Both (audio/video conversion)

### Infrastructure

- **Docker + docker-compose, Caddy 2** — DD only
- **Ubuntu VPS scripts, fail2ban, age backups, rclone** — DD only
- **Makefile (root + per app)** — Both
- **None** — CG has no container or deploy assets

### Testing

- **pytest** — DD 3,338 · CG 704 collected
- **node:test** — CG ≈420 logic tests + 47 demo-harness; DD frontend via node fake-DOM
- **playwright-core + system Chrome** — CG demo-check (32 beats)
- **Load harness** — DD tests/load/run_load.py

### External integrations

- **Doctor Dictation HTTP API** — Consumed by CG rx/import
- **WhatsApp / QR share** — DD patient link (link only, no API)
- **Healthchecks ping, rclone off-site** — DD backup (optional)

## External integrations

| Integration | Used by | Config (names only) | Status |
| --- | --- | --- | --- |
| OpenAI-compatible LLM (openai, deepseek, groq, meta) | Doctor Dictation | LLM_PROVIDER, LLM_MODEL, LLM_VISION_MODEL, *_API_KEY, *_BASE_URL | Implemented; vendors mocked in tests |
| STT: OpenAI, Groq, AssemblyAI, Meta Muse, faster-whisper | Doctor Dictation | STT_CHAIN, STT_ENGINE, WHISPER_* | Implemented; ONNX stub |
| Meta API: SAM 3.1, Muse Voice, Muse Spark 1.3 | Count Guard | MODEL_API_KEY or META_API_KEY, META_API_BASE, SAM_MODEL, VOICE_MODEL, SPARK_MODEL | Coded; never called with a real key per README |
| Baseten: Muse Spark Open | Count Guard (legacy narrative) | BASETEN_API_KEY, SPARK_OPEN_BASE, SPARK_OPEN_MODEL | POC |
| Doctor Dictation HTTP API | Count Guard rx/import | DD_BASE_URL / DD_PORT | Implemented |
| Headless Chromium (Playwright) | Doctor Dictation PDF; Count Guard demo-check | — | Implemented |

## Authentication and authorisation

- **Doctor Dictation, multi-clinic mode:** scrypt passwords and an HMAC-signed `dd_session` cookie (12 h, HttpOnly, SameSite=Lax). Lockout is 5 failures per 300 s. Logout and `session_version` revoke sessions. A `X-DD-Client` header guards against CSRF. Per-clinic DB scoping uses a ContextVar. Roles are admin, author and owner (`doctor-dictation/doctor_dictation/policy.py:20-44`).
- **Doctor Dictation, single mode (default):** no authentication; CORS `*` (`doctor-dictation/doctor_dictation/api/app.py:81-87`).
- **Count Guard:** no authentication. The actor is a free-text `by` field, and the role is client-side state. CORS allows localhost only (`count-guard/backend/app/main.py`).

## Deployment

- **Doctor Dictation:** Dockerfile (Python 3.12, Chromium, ffmpeg, non-root), docker-compose with Caddy 2 auto-HTTPS, and VPS harden, deploy, backup and restore-drill scripts. `02-deploy.sh` clones a separate upstream repo. A live pilot is described in `doctor-dictation/docs/working/2026-10-18-deployment/` and cannot be verified from code.
- **Count Guard:** local development only (`make dev`). No container or production configuration exists.

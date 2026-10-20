# 02 — Architecture (shared; hackathon and product deltas marked)

## 1. Summary

Keep the shape the app already has: a **pure core** (`doctor_dictation/core/`, no I/O, enforced by
`tests/test_core_purity.py`) surrounded by **adapters** (`providers/`, `db/`, `api/`, `pdf/`). Arrows
point inward: adapters call the core; the core never imports an adapter.

The extension adds three things:

1. Two new **ports** (interfaces): `VisionPort` and `VitalsPort`. Speech and LLM ports already exist.
2. One new **store**: the append-only `timeline_events` table.
3. New **rule cores**, one per module, each a pure function from events (and inputs) to new events.

## 2. Layers

```
┌──────────────────────────── frontend (vanilla JS, no build) ─────────────────────────────┐
│  existing Rx workspace           hx/ot.html: camera · vitals strip · timeline · card     │
└───────────────▲───────────────────────────────▲──────────────────────────────────────────┘
          HTTP JSON                        SSE stream (server → browser)
┌───────────────┴───────────────── api/ (FastAPI routers) ─────────────────────────────────┐
│ existing: /api/transcribe /api/format /api/v1/*      new: /api/hx/* (hackathon)          │
└──────┬──────────────┬───────────────┬────────────────┬───────────────────┬───────────────┘
       │              │               │                │                   │
┌──────▼─────┐ ┌──────▼──────┐ ┌──────▼──────┐ ┌───────▼───────┐ ┌─────────▼─────────┐
│ SttProvider│ │ LlmProvider │ │ VisionPort  │ │ VitalsPort    │ │ TimelineStore     │
│ (exists)   │ │ (exists)    │ │ NEW         │ │ NEW           │ │ NEW (sqlite)      │
└──────┬─────┘ └──────┬──────┘ └──────┬──────┘ └───────┬───────┘ └─────────┬─────────┘
       └──────────────┴───────┬───────┴────────────────┴───────────────────┘
                     ┌────────▼─────────────────────────────────────┐
                     │ core/ (pure)                                 │
                     │  timeline: Event, fold, validate             │
                     │  count: ledger, zones, reconcile             │
                     │  druglog: parse, ground                      │
                     │  vitals: trend rules                         │
                     │  context: collect facts, check LLM wording   │
                     │  brownbag: ground strips, duplicate (gated)  │
                     │  discharge: fold to sections                 │
                     └──────────────────────────────────────────────┘
```

## 3. Ports

All ports follow the existing pattern: a `Protocol` in `base.py`, an error type whose `str()` is safe to
show (≤ 300 chars), a factory that reads `Settings`, and a stub or replay adapter for tests.

### 3.1 VisionPort (new)

```python
@dataclass(frozen=True)
class Detection:
    track_id: str          # stable across frames while the tracker holds the object
    label: str             # concept prompt that matched, e.g. "surgical gauze"
    box: tuple[float, float, float, float]   # x0, y0, x1, y1, normalised 0..1
    score: float
    t: float               # seconds from episode start (frame timestamp)

class VisionPort(Protocol):
    name: str              # "sam-api" | "replay" | "sam-local" (product)
    def available(self) -> bool: ...
    async def track(self, frames: Sequence[Frame], prompt: str) -> list[Detection]: ...
    async def read_text(self, image: bytes) -> str: ...   # brown-bag strips; may delegate to a vision LLM
```

| Adapter | Hackathon | Product | Notes |
|---|---|---|---|
| `sam-api` | Yes, if spike S1 passes | Optional | Cloud. Synthetic data only. |
| `replay` | **Yes, always** | Tests only | Reads a recorded `detections.jsonl`. Guarantees the demo. |
| `sam-local` | No | Yes | Open weights on clinic GPU; no image leaves the site. |

### 3.2 VitalsPort (new)

```python
@dataclass(frozen=True)
class VitalReading:
    t: float                     # seconds from episode start
    bp_sys: int | None; bp_dia: int | None
    hr: int | None; spo2: int | None
    source: str                  # "sim" | "hl7" | "screen"

class VitalsPort(Protocol):
    name: str
    def readings(self, episode_id: str) -> AsyncIterator[VitalReading]: ...
```

| Adapter | Hackathon | Product |
|---|---|---|
| `sim` — plays a scenario file (`hx/scenarios/*.json`) on a controllable clock | Yes | Training and tests |
| `hl7` — reads the monitor's HL7 v2 ORU feed through the hospital interface engine | No | Yes (phase P4) |
| `screen` — camera reads the monitor screen | No (misread digits are a safety risk) | Only if no data port; needs validation |

### 3.3 Clock

Every rule takes `now` as an argument. The simulator and tests drive a fake clock. No rule calls
`time.time()`. This keeps the core deterministic and lets the demo replay identically.

## 4. Timeline store

### 4.1 Table (migration `011_timeline.sql`; renumber when porting to `main`)

```sql
CREATE TABLE timeline_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    patient_id    INTEGER NOT NULL REFERENCES patients(id),
    encounter_id  INTEGER REFERENCES encounters(id),
    episode_id    TEXT    NOT NULL,              -- one OPD→OT→discharge journey
    module        TEXT    NOT NULL CHECK (module IN ('rx','brownbag','count','druglog','vitals','discharge')),
    kind          TEXT    NOT NULL,              -- e.g. 'count.item_out'
    tier          TEXT    NOT NULL CHECK (tier IN ('doc','decision')),
    source        TEXT    NOT NULL CHECK (source IN ('voice','camera','monitor','manual','derived')),
    at            TEXT    NOT NULL,              -- clinical time, ISO-8601 UTC
    recorded_at   TEXT    NOT NULL,              -- when the row was written
    actor_id      INTEGER REFERENCES users(id),
    payload       TEXT    NOT NULL,              -- JSON, shape fixed by (kind, payload_v)
    payload_v     INTEGER NOT NULL DEFAULT 1,
    evidence      TEXT    NOT NULL DEFAULT '{}', -- frame refs, transcript sha, photo ref
    supersedes_id INTEGER REFERENCES timeline_events(id),
    confirmed_by  INTEGER REFERENCES users(id),
    confirmed_at  TEXT
);
CREATE INDEX idx_tl_episode ON timeline_events(episode_id, at);
CREATE INDEX idx_tl_patient ON timeline_events(patient_id, at);
```

### 4.2 Rules

- **Append-only.** No `UPDATE` of `payload`, no `DELETE`. A correction is a new event with
  `supersedes_id`. The fold ignores superseded events. (Only `confirmed_by`/`confirmed_at` may be set once.)
- **Every write also writes `audit_log`** with `entity='timeline_event'`, the same as documents today.
- **Clinical time ≠ write time.** `at` is when it happened; `recorded_at` is when we stored it.

### 4.3 Event kinds and payloads (v1)

| kind | tier | payload |
|---|---|---|
| `rx.saved` | doc | `{document_id}` |
| `brownbag.med_found` | doc | `{as_read, generic, strength, drug_class, grounded: bool, photo_ref}` |
| `brownbag.duplicate` | decision | `{generic, event_ids: [..]}` |
| `count.pack_opened` | doc | `{item: "swab", qty}` |
| `count.item_out` | doc | `{item, track_id, frame_ref}` |
| `count.closing` | doc | `{item, in, out, missing, last_seen: [{track_id, frame_ref, t}]}` |
| `druglog.given` | doc | `{as_heard, drug, strength, amount, unit, route, grounded: bool}` |
| `vitals.reading` | doc | `{bp_sys, bp_dia, hr, spo2}` (sampled: store 1 per 15 s, not every beat) |
| `vitals.change` | decision | `{rule, metric, from, to, pct, window_s}` |
| `vitals.card` | decision | `{facts: [Fact], text, wording: "llm"|"template", checklist_id}` |
| `discharge.drafted` / `.signed` | doc | `{document_id}` |

`Fact` is `{kind, text, event_id, at}`. Every fact points at the event it came from. That pointer is what
lets the card say "(voice log)" or "(OPD medicine review)".

## 5. Rule cores (pure)

### 5.1 Count ledger

```
state per item type:  in_count, out_tracks: set[track_id], last_seen: dict[track_id → (t, frame_ref)]
on detection d:       last_seen[d.track_id] = (d.t, frame)
                      if centre(d.box) inside bucket_zone and d.track_id not in out_tracks for ≥ DWELL frames:
                          emit count.item_out
on closing(now):      missing = in_count − len(out_tracks)
                      emit count.closing with the tracks seen in the field but never counted out
```

- `DWELL` (e.g. 3 consecutive frames) stops a hand waving a swab over the bucket from counting it.
- A track that splits or re-appears with a new ID is the main risk. Spike S1 measures it.
- The manual "+1 out" button is always there. Manual events have `source='manual'`.

### 5.2 Vitals trend rules

Rules run on every reading, in milliseconds, before any LLM call.

| Rule | Fires when | Default |
|---|---|---|
| `bp_drop_pct` | systolic falls ≥ X% versus the max of the last W minutes | X = 20, W = 5 |
| `bp_low_abs` | systolic < threshold for 2 readings | 90 mmHg |
| `hr_not_compensating` | `bp_drop_pct` fired and HR rose < 10% in the same window | flag on the card, not an alert |

A rule fires once per episode per cooldown (default 3 min) so the card does not flicker.

### 5.3 Context collector and the wording check

```
collect(change_event, timeline, now) → facts:
    druglog.given        in the last 10 min  → "lignocaine 5 ml given 3 min ago (voice log)"
    brownbag.med_found   with a tracked drug_class in {beta-blocker, …}  → "on metoprolol (OPD medicine review)"
    count.item_out       in the last 10 min  → "6 swabs into the bucket in the last 10 min (Count Guard)"
```

1. Render the card **immediately** from a fixed template using these facts. The alert never waits.
2. Ask the LLM to rephrase the same facts in ≤ 35 words, with a hard timeout (2 s hackathon, 1 s product).
3. **Wording check** (pure): every number, drug name and time in the LLM text must appear in the facts.
   No verbs from a banned list ("give", "start", "administer", "increase", "reduce", "consider"). If the
   check fails or times out, keep the template text. Record `wording: "template"`.

The LLM can make the card read better. It can never make it say more.

### 5.4 Drug-log parser

Regex-first, like `core/vitals.py`: amount + unit (`ml`, `mg`, `mcg`, `units`), strength (`2 percent`),
route words (`IV`, `IM`, `local infiltration`, `subcut`). The drug name goes through the existing
grounding (`core/drugnames.py`). If the regex cannot find a drug and an amount, ask the LLM for JSON and
validate it the same way `/api/format` does. Ungrounded names need a confirm tap.

### 5.5 Discharge fold

`fold(events) → {opd_meds, drugs_given, count_result, vitals_events, procedure_note}`. Superseded events are
dropped. Decision-tier events are dropped unless the tier switch is on. The sections render through
`pdf/sections.py` helpers (`list_section`, `bullet_section`, `prose_section`).

## 6. Real-time path

```
camera (browser getUserMedia) ──JPEG @ 2 fps──► POST /api/hx/count/frames ─► VisionPort ─► count ledger
simulator clock ───────────────────────────────────────────────────────────► VitalsPort ─► trend rules
                                     all writes ─► TimelineStore ─► in-process bus ─► SSE /api/hx/episodes/{id}/stream
```

- **SSE, not WebSocket.** One direction is enough, it passes through Caddy without config, and the browser
  reconnects by itself (`Last-Event-ID` = timeline `id`).
- **Worker gotcha:** production runs `WEB_CONCURRENCY=2` (two processes). An in-process bus would miss
  events written by the other worker. Hackathon: run one worker. Product: the stream polls
  `timeline_events WHERE id > last_id` every 500 ms (SQLite is enough at OT scale), or uses a broker.
- **Frame budget:** 2 fps × ~60 KB JPEG ≈ 120 KB/s per OT. Fine on a LAN; the cloud API latency decides the
  real rate (spike S1).

## 7. Tier switch

| Layer | Behaviour when decision tier is OFF (default) |
|---|---|
| Config | `DECISION_TIER=0` (hackathon env) → product: per-clinic setting, admin only, audited |
| API | Decision-tier routes are **not mounted**. Calls return 404, not 403, so nothing leaks. |
| Core | `collect()` and `duplicate()` still exist; nothing calls them |
| Store | Existing decision events stay in the table; `fold(tier_enabled=False)` drops them |
| UI | Decision panels hidden. When ON, a fixed banner: "Research demo — not for clinical use" |
| PDF | Decision events never print on the discharge draft in either mode |

## 8. Package layout

**Hackathon** (everything new under `hx/`; one-line mount in `api/app.py` behind `HACKATHON=1`):

```
doctor_dictation/hx/
  ports.py            VisionPort, VitalsPort, Detection, VitalReading, Clock
  vision_sam.py       vision_replay.py      vitals_sim.py
  store.py            timeline table access + SSE bus
  rules/              timeline.py  count.py  trend.py  context.py  druglog.py  brownbag.py  discharge.py
  api.py              /api/hx/* routes
  scenarios/          one_morning.json  detections_demo.jsonl
doctor_dictation/db/migrations/011_timeline.sql
frontend/hx/          ot.html  ot.js  ot.css  timeline.js  card.js  brownbag.html
tests/hx/             rule tests only
```

**Product** (ported in phases, see `05`): `hx/rules/*` → `core/timeline/`, `core/count/`, …;
`hx/ports.py` → `providers/vision/base.py`, `providers/vitals/base.py`; `hx/api.py` → one router per module
under `api/`. The `hx/` package is deleted when the last module is ported.

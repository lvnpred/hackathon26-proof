# Count Guard v4 UX: AI moments in every workflow, Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task stands alone: read the Global Constraints, the Rulings, the Shared Contracts and your own task before you start. The Shared Contracts section holds everything two tasks share; do not read other tasks for instructions.

**Goal:** Every AI or rules result in the care flow shows as one AI moment line (chip · finding · status · Inspect), Inspect opens one Inspector drawer with interactive detail per capability, one Record & evidence list replaces three chart cards, and the AI activity page shows what the AI did today. `make demo-check MODEL_API_KEY=` stays green after every task.

**Architecture:**
- The backend builds every moment from the events it already holds, in one pure module (`journey/ai_moments.py` + `journey/moment_text.py`). The chart view gains `ai_moments`. No new model call and no new route except the rebuilt strip-photo reader.
- The frontend puts every decision in pure, tested helpers (`moments.js`, `inspect.js`, `orders.js`). JSX renders what they return. `AiMoment` is the line; `Inspector` is the drawer, hosted once in `CareShell` and driven by the `?inspect=` URL parameter. The Inspector's `visual` and `photo_read` kinds reuse today's `Evidence`, `Stage` and `evidence.js` helpers.
- The AI activity page is built client-side from the roster views' `ai_moments`, which `useWard` already loads.

**Tech Stack:** FastAPI + pytest (backend). React 18 + Vite + react-router (frontend). `node --test` for care and demo tests (pure helpers plus source-regex checks of JSX). The playwright-core demo runner.

**Spec (binding):** `docs/superpowers/specs/2026-10-31-count-guard-v4-ux-ai-moments-design.md`.

**Builds on:** v3 (`2026-10-30-count-guard-v3-ai-showcase.md`), on branch `count-guard-ops-agent`. The ops agent plan (`2026-10-31-count-guard-ops-agent.md`) runs after this one. It reuses `AiMoment`, `useInspector().openInspector(momentId)` and the Inspector's `KIND_VIEWS` map, where it adds an `agent` kind. Keep those three names exactly.

All paths are relative to `count-guard/` unless they start with `docs/`. The demo document is `docs/demo/count-guard-v2-video-script.md` at the repo root.

## Global Constraints

- Records only, no medical advice. The no-advice regex `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i` (`frontend/scripts/demo/beats.mjs:3`, `backend/tests/test_flow_states.py:9`) applies to **all new copy**. Every task's tests assert it on that task's new strings.
- A finding sentence is built from numbers and record fields, **never from model text** (no strip name as read, no transcript words, no Spark reply).
- No new model calls. Never call live models in tests or `make demo-check`. Tests fake adapters with `monkeypatch` and keep the `no_network` fixture.
- Files stay under 500 lines. Validate input at boundaries: the `?inspect=` parameter (frontend) and the strip-photo upload (backend).
- macOS file system is case-insensitive: never create `foo.js` beside `Foo.jsx`. Import every `.jsx` with its extension. This plan's pairs: `moments.js` / `AiMoment.jsx`, `inspect.js` / `Inspector.jsx`. They differ in base name.
- Every `/journey/<segment>` the frontend calls must be in the Vite proxy allow-list (`frontend/vite.config.js:17`); `src/care/ai.test.js:44` enforces it. This plan adds no new segment (all calls stay under `/journey/episodes` and `/journey/ai`).
- Ports 8200/5273 only (`make demo-check` starts its own). Never touch 8100/5173.
- `make demo-check MODEL_API_KEY=` stays green after **every** task. A task that changes a visible string, a click or an accessible name updates `frontend/scripts/demo/beats.mjs`, `steps.mjs` and the demo document in the same commit. `doc.test.mjs` requires each `expect` string and each `say` verbatim in the document. Beats stay 32; roles stay 58/58/58 s.
- `waitText` reads `document.querySelector(".app").innerText` (`frontend/scripts/demo/helpers.mjs:6`). The Inspector must render inside `.app`.
- Commit once per task: `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. No Co-Authored-By line. Never push or merge.

Commands (from `count-guard/`):
- Backend: `.venv/bin/pytest -q` (baseline about 493)
- Frontend: `cd frontend && node --test src/care/*.test.js scripts/demo/*.test.mjs` (baseline about 297)
- Build: `cd frontend && npm run build`
- Demo: `make demo-check MODEL_API_KEY=`; `CG_DEMO_UNTIL=<beat id>` stops before a beat.

Measure both suites before Task 1. Each task ends at or above the measured counts plus its own new tests.

## Rulings

Format: `Ruling: <decision> — <why> — <cost if wrong>`. They bind all tasks.

- **R1.** Ruling: moments are built on the backend (`ai_moments.moments(events)`) and shipped in the chart view; only the role-dependent status label is computed on the frontend — the events, the evidence links and `stories.plain` live there, and one builder serves the chart, MyCare, the Inspector and AI activity — two places know the status vocabulary (backend `status` + `owner`, frontend `statusLabel`).
- **R2.** Ruling: a moment id is its anchor event id. Exceptions: the day plan is `dayplan:<rx.ordered id>`; a strip-photo batch is the id of its first `brownbag.med_found`. The frontend accepts `^[A-Za-z0-9:_-]{1,80}$` for `inspect` and `focus` — event ids are already unique and linkable — an id scheme change breaks saved `?inspect=` links.
- **R3.** Ruling: backend `status` is one of `matches | flagged | open | failed | recorded`, plus `owner` (`doctor | nurse | patient | null`). The frontend shows `Needs you` when `owner === role` and status is `open` or `flagged` — the spec's "needs you" depends on the viewer, the backend does not know the viewer — none.
- **R4.** Ruling: the chip is `chipFor({calls, handmade, source})` (C4): model names in call order joined by ` → `, ` → Rules` appended when a rules word built the result without a Spark call, then ` · ` and the worst mode. It replaces "(Prepared demo result)", "Heard by: …", "Rules (no model)" and "SAM 3.1 · Sample" captions — the spec says the chip carries that information — a viewer who relied on the long sentence sees a shorter word.
- **R5.** Ruling: the visual finding is a Python twin of the first sentence of `evidence.js` `explain()` (`Saw 2 of 3 needle holders.`, `Saw every planned item: 15 of 15.`), built from the event's `rows`; with nothing seen it reads `Nothing seen in the clip.` (the backend has no frames or threshold) — the moment line must not fetch a sidecar — the line and the Inspector's "Why:" can word the empty case differently.
- **R6.** Ruling: non-AI rows that the removed cards listed are moments of kind `record` with no Inspect: reference and wound photos, typed signed orders, healing-photo reviews — Record & evidence replaces Photos, Video checks and Orders-and-tasks without losing a row — `record` is a kind outside the spec's table.
- **R7.** Ruling: the Inspector is `<section className="inspector" aria-label="Inspector">`, rendered in `CareShell`'s `<main>`, no portal and no `role="dialog"`; Esc and **Close** close it; it opens on the **What the AI found** tab; URL changes use `replace: true` — the demo reads `.app` innerText and finds regions by name (`helpers.mjs:24`) — Back does not close the drawer, and it does not trap focus.
- **R8.** Ruling: one host in `CareShell`. The episode comes from the `episode` parameter, else the `/chart/:episodeId` route, else the patient role's own episode. `openInspector(momentId, { episodeId, focus } = {})` sets `inspect`, plus `episode` only when given — every page (chart, Today, MyCare, Ask, AI activity) can open it, and `useWard` holds every roster view — a moment of a patient outside the roster cannot be inspected.
- **R9.** Ruling: word spans exist for order dictation only. `dictation.order_spans(transcript, items)` is a rules function run on every order draft (rules or model items); its offsets index `digits(transcript)`, stored as `spans.text`. Discharge, task and answer voice moments show the transcript unhighlighted, as do drafts written before this change — the rules parser normalises numbers first (`dictation.py:67`), so offsets into the raw transcript would drift — the Found tab shows "every 6 hours" where the doctor said "every six hours".
- **R10.** Ruling: "AI drafted → signed" compares `order.drafted.items` with `order.signed.items` by index; a row only in one list reads `Added at signing` or `Removed at signing` — signed items carry no row identity — a reordered row reads as two edits.
- **R11.** Ruling: "the `/ask/medicines` reader" means the reader function `live.read_photo("strip", …)` + `keep_photo_evidence`, not the route. `POST /strips/photo` is rebuilt on it (moved to `media_api.py`), keeps its path, works offline from a prepared fixture, takes `by` (default `patient`) and reuses `ask_api.MEDICINES_LIVE` — `/ask/medicines` is gated to `clinic_done`/`home` (`ask_api.py:183`), writes `medicines.read` (which drives no nudge) and takes the patient label as `by` — two strip readers stay (photo of strips, medicines photo).
- **R12.** Ruling: in a strip-photo batch only the first `brownbag.med_found` carries `calls`; every row carries `photo_id`, `evidence_id` and `source` — `ai_summary._rows` counts one row per call (`ai_summary.py:22`) — a reader of one row alone sees no calls.
- **R13.** Ruling: the demo strip photo is a new handmade fixture `prepared/strip-amlodipine.json` (one region, `Amlodipine 10 mg`) and a new `eval/p4/strip-amlodipine.png` drawn by `eval/p4/make_photos.py` — `das-strip` must show the clinic photo path offline — one more generated asset.
- **R14.** Ruling: nudges gain `says_staff`, written at raise time; old nudges fall back to `says`. Only the two strip kinds word it differently: `Strip reads {read}; prescription says {strength}.` and `Strip reads {read}; not on the prescription from {by}.` — the spec's staff example — a nudge raised before the change keeps patient wording on staff screens.
- **R15.** Ruling: for the doctor, a check-in is unseen while no `checkin.seen` has a `by` starting `Dr. `; the doctor's chart posts Seen on open, like the nurse's (v3 R22); precedence in `PHOTO_STATES` is reviews, then questions, then check-ins — only nurses post Seen today, so "not seen" for the doctor would never clear — the doctor's card flips as soon as the chart opens.
- **R16.** Ruling: a moment is patient-visible when `patient_finding` is not null; voice drafts, handover, staff-addressed nudges and typed orders have none. The patient lens shows Input and What the AI found only — the spec's patient lens — a patient cannot inspect their own handover.
- **R17.** Ruling: `Photos.jsx`, `VideoChecks.jsx` and `OrderTasks.jsx` are deleted; MyCare's patient Photos and Video-checks cards become `RecordEvidence` with the patient lens — they have no other user once the chart list exists — patient wording comes from `patient_finding`, not `patientCheckLine`.
- **R18.** Ruling: done-step collapse. A done tray step shows its AI moment, plus a compact `Check the tray again` file input while the tray can still be recorded; the full viewer lives only in the Inspector. An open count (missing > 0) keeps its panel. A nurse task row shows its last proof as an AI moment. The orders panel shows the last signed dictation as one AI moment above the empty form — the spec's P3 — the demo must click Inspect to see the tray viewer (R20).
- **R19.** Ruling: AI activity is built client-side from `ward.patients[*].view.ai_moments`; no new backend route; the model cards keep `/journey/ai/summary` — the views are already loaded — the page cannot list patients outside the roster.
- **R20.** Ruling: `kumar-tray` adds the click `Button "Inspect" in "Theatre steps"` and `kumar-count` starts with `Button "Close" in "Inspector"`; seconds are unchanged — it shows the Inspector in the film without moving the timing — two clicks inside 6 s.
- **R21.** Ruling: the care-chart handover card shows for the nurse in state `ward`, with From `Nurse Meena (synthetic)` and To `Nurse Kavya (synthetic)` (the `DAY`/`NIGHT` names, `screens/NurseHandover.jsx:4-5`), the model checkbox off by default — the model takes 30–50 s — none.
- **R22.** Ruling: the AI activity nav item replaces the demo-dock link "AI at work" — the spec wants a staff nav item; two links would duplicate it — `helpers.dockLink` loses its only caller (kept).
- **R23.** Ruling: finding sentences are fixed per capability in `moment_text.py` (C5); word counts use `len(transcript.split())`; audio length is not stored, so the spec's "14 s of speech" becomes "25 words" — numbers only — the line differs from the mockup.

## Shared Contracts

**C1. Moment** (Task 1 builds it; every later task reads it). `view.ai_moments` is a list, newest first (`at_ms` desc, ties by record order desc):

```json
{
  "id": "<event id> | dayplan:<rx id>",
  "kind": "visual | photo_read | voice | answer | rule | draft | record",
  "capability": "orders | discharge | task_voice | answer_voice | monitor | dose_strip | medicines | strips | tray | setup | swabs | healing_photo | record_bot | nudge | handover | discharge_card | day_plan | photo | typed_orders",
  "title": "Tray check",
  "at_ms": 0,
  "calls": [{"model": "sam", "model_id": "sam-3.1", "source": "prepared", "ms": null}],
  "source": "prepared",
  "handmade": false,
  "finding": "Saw 2 of 3 needle holders.",
  "patient_finding": "The tray was checked by camera before your surgery.",
  "status": "flagged",
  "owner": "doctor",
  "filter": "video",
  "evidence_id": "<32 hex> | null",
  "photo_id": "<event id> | null",
  "refs": {},
  "written": [{"event_id": "…", "type": "tray.checked", "when": "Day 0 09:20", "by": "Nurse Asha (synthetic)", "plain": "…", "read": 14, "saved": 15}]
}
```

`refs` for `record_bot` also carries `question_id` (the asked question's event id, used by the frontend to find the question). A flagged `tray`/`setup`/`swabs` moment becomes `recorded` with `owner: null` once resolved: swabs when a later closing count equals the pack opened; tray/setup when the patient has left theatre or a later check of the same kind matches. A `proof.checked` with nothing read is a `photo` moment titled "Proof photo". `written` lists the anchor and its follow-up events, oldest first; `read`/`saved` appear only when present. Follow-ups: `order.signed`/`discharge.signed` by `draft_id`; events whose payload `evidence_id` equals the moment's; `brownbag.marked` by `read_id`; `nudge.seen` by `nudge_id`; `handover.accepted` by `handover_id`; `question.answered` by `question_id`; `review.answered` by `review_id`.

`title`, `filter` and `owner` by capability:

| Capability | Kind | Title | Filter | Owner while open/flagged |
|---|---|---|---|---|
| orders, discharge | voice | Order dictation, Discharge dictation | voice | doctor |
| task_voice, answer_voice | voice | Task by voice, Doctor's spoken answer | voice | — |
| monitor, dose_strip | photo_read | Monitor photo, Strip photo | photos | nurse |
| medicines | photo_read | Medicines photo | photos | doctor |
| strips | photo_read | Photo of strips | photos | — |
| tray | visual | Tray check | video | doctor |
| setup, swabs | visual | Set-up check, Swab camera count | video | nurse |
| healing_photo, photo | record | Healing photo, Reference photo / Wound photo | photos | doctor / — |
| typed_orders | record | Orders | — | — |
| record_bot | answer | Record bot answer | answers | — |
| nudge | rule | Alert | alerts | the nudge's `to` |
| handover | draft | Shift handover | — | nurse |
| discharge_card, day_plan | draft | Discharge card, Day plan | — | — |

`refs` by kind:
- `visual`: `{"check": {"check", "rows", "missing", "match", "why", "media", "unchecked"}}`
- `photo_read`: `{"reader": "monitor|strip|medicines", "regions": [...], "values_read": {...}|null, "rows": [...]|null, "match", "why"}`
- `voice`: `{"transcript", "heard_by", "spans": {"text", "marks": [{"start", "end", "item", "field"}]}|null, "items": [...]|null, "signed_items": [...]|null, "sections": [...]|null}`
- `answer`: `{"question", "answer", "found", "sources": [{"id", "text"}]}`
- `rule`: `{"says", "says_staff", "to", "kind", "intent": Line|null, "fact": Line|null, "rule": str}`
- `draft`: `{"lines": [{"text", "evidence": [Line]}]}`; day plan adds `{"rows": [{"key", "medicine", "text", "region"}], "photo_id", "evidence_id"}`; handover adds `{"text", "wording", "from", "to"}`
- `record`: `{}`

**C2. Line** (Task 1): `{"id", "type", "when", "by", "plain"}`, built by `ai_moments.line_of(event)`; `plain` is `stories.plain(event)`.

**C3. Status labels** (Task 2, `moments.js` `statusLabel(moment, role) -> {text, tone}`):

| Status | Owner equals role | Text | Tone |
|---|---|---|---|
| open, flagged | yes | `Needs you` | `blue` |
| flagged | no | `Flagged` | `amber` |
| open | no | `` `Waiting for ${WHO[owner]}` `` (`the doctor`, `the nurse`, `the patient`) | `grey` |
| matches | — | `Matches` | `green` |
| recorded | — | `Recorded` | `green` |
| failed | — | `Failed` | `grey` |

**C4. Chip** (Task 2, `moments.js`): `chipFor({calls, handmade, source}) -> string`. Vectors (all in `moments.test.js`):

| calls | handmade | source | chip |
|---|---|---|---|
| `[voice prepared]` | false | `rules` | `Muse Voice → Rules · prepared` |
| `[]` | false | `rules` | `Rules` |
| `[sam prepared, spark prepared]` | true | `prepared` | `SAM 3.1 → Muse Spark 1.3 · Sample` |
| `[voice muse-voice-transcribe, spark muse-spark-1.3]` | false | `muse-spark-1.3` | `Muse Voice → Muse Spark 1.3 · live` |
| `[voice prepared]` | false | `` | `Muse Voice · prepared` |
| `[spark failed]` | false | `failed` | `Muse Spark 1.3 · failed` |

Mode order, worst first: `failed`, `prepared`, `live` (words from `evidence.js` `modeWord`). Two wrappers for results that have no event yet: `heardChip(heardBy)` = `chipFor({calls: [{model: "voice", source: heardBy}]})`, and `draftChip(heardBy, source)`, which adds a voice call unless `heardBy` is empty or `typed`, and a Spark call when `source` is `muse-spark-1.3` or `rules (model reply not usable)`.

**C5. Finding sentences** (Task 1, `moment_text.py`; `n`, `w` are counts; plural adds `s` when ≠ 1):

| Capability | Staff `finding` | `patient_finding` |
|---|---|---|
| tray, setup, swabs | R5 twin of `explain` | tray: `The tray was checked by camera before your surgery.`; swabs: `The swabs were counted by camera.`; setup: `The set-up was checked by camera.` |
| monitor | `Read SBP 88, DBP 54, HR 112.` (present keys of `values_read`, order SBP, DBP, HR) | `Your observations were read from a monitor photo.` |
| dose_strip | `Strip photo matches the task.` / `Strip photo does not match the task.` / `Photo kept, not checked.` | `Your dose was checked against a strip photo.` |
| medicines | `Read {n} strips: {k} on the prescription, {f} flagged.` | `{n} medicines read from your photo.` |
| strips (Task 8) | `Read {n} strip: {d} differs from the prescription.`; parts `{d} differ(s) from the prescription`, `{u} not on the prescription`, joined `, `; neither → `all match the prescription` | `{n} strips read from your photo.` |
| orders | `{n} orders drafted from {w} words.` | — |
| discharge | `{n} sections drafted from {w} words.` | — |
| task_voice | `Task recorded by voice from {w} words.` | — |
| answer_voice | `Answer recorded by voice from {w} words.` | `Dr. Rao answered by voice.` |
| record_bot | `Answered from {n} record lines.` / `Not found in the record.` | `Answered from {n} lines of your record.` / `Not found in your record.` |
| nudge | `says_staff` | `says` when `to == "patient"`, else — |
| handover | `Handover of {n} lines from {e} recorded events.` | — |
| discharge_card | `Discharge card with {s} warning signs and {r} schedule rows.` | `Your discharge card.` |
| day_plan | `Day plan of {k} medicines; {c} matched to the medicines photo.` | `Your day plan lists {k} medicines.` |
| healing_photo | `Healing photo waiting for review.` / `Reviewed: {label}.` | same |
| photo | `Reference photo.` / `Wound photo.` | same |
| typed_orders | `{n} orders signed.` | — |

`RULE_TEXT` (Inspector `rule` kind, "the rule in words"), keyed by nudge kind:
`strip_strength_differs`: `The strength read from a strip is compared with the prescription row for the same medicine.` · `strip_not_prescribed`: `Each strip read is looked up in the prescription.` · `dose_overdue`: `An ordered dose is due every set number of hours, with 30 minutes' grace.` · `dose_logged_early`: `A dose logged sooner than its ordered interval, less 30 minutes, is flagged.` · `dose_not_ordered`: `A logged dose is looked up in the ward orders.` · `obs_past_limit`: `Each reading is compared with the limits the doctor set.` · `obs_overdue`: `Observations are due at the ordered interval, with 30 minutes' grace.` · `count_open`: `The closing swab count is compared with the pack opened.` · `help_requested`: `A Need-help press from the patient is always shown.` · `warning_sign_ticked`: `A ticked check-in sign is compared with the discharge list.`

**C6. Inspector API** (Task 2, `Inspector.jsx`):
- `useInspector() -> { momentId, episodeId, focus, openInspector(momentId, { episodeId, focus } = {}), closeInspector() }`
- `KIND_VIEWS = { visual, photo_read, voice, answer, rule, draft }`: each value is `{ Input, Found }`, components taking `{ moment, episodeId, view, role, lens, focus, setFocus }`. Tasks 3–5 fill it. The ops agent adds `agent`.
- `<AiMoment moment role lens episodeId thumb quiet />` (`AiMoment.jsx`, default export). `quiet` drops the finding where it is already on screen. The Inspect button's accessible name is exactly `Inspect` (the `›` is `aria-hidden`). Root: `<div className="ai-moment" data-moment={moment.id}>`.

**C7. Copy** shared by more than one task: tabs `Input`, `What the AI found`, `Record`, `Model`; `Inspect`, `Close`; `Nothing to inspect with that id.`; `No model call.`; `No raw output is kept for this result.`; `Record & evidence`; filters `All`, `Needs you`, `Photos`, `Video`, `Voice`, `Answers`, `Alerts`; `Nothing here for this filter.`; `AI activity`.

## Review Focus

| # | Input or condition a person will meet | Expected behaviour | Pinned by |
|---|---|---|---|
| 1 | A stale or hand-edited `?inspect=` (after Reset, another patient's id, `<script>`, 200 chars) | The drawer shows `Nothing to inspect with that id.` with Close; nothing crashes; a patient never sees a staff-only moment through it | Task 2 `readInspect rejects bad ids`, `a patient lens never resolves a staff-only moment` |
| 2 | An old check with no sidecar, or an evidence GET that 404s | The moment line renders; the visual Found tab falls back to today's count table (`evidenceView` fallback); the Model tab says `No raw output is kept for this result.` | Task 1 `test_old_check_without_evidence_is_still_a_moment`; Task 3 `visual Found falls back without a sidecar` |
| 3 | A model-drafted order whose values are not in the transcript, number words, or overlapping matches | Missing fields get no mark; marks never overlap; the segments reassemble the text exactly | Task 4 `test_spans_skip_missing_and_never_overlap`, `test_spans_from_number_words`; `segments reassemble the text` |
| 4 | A strip photo that reads nothing (unknown file offline, unparsable reply, failed call) or a non-image upload | 422 `No strips were read from the photo. Type them instead.` with nothing written; 400 for a bad file; never a 500 | Task 8 `test_strips_photo_reads_nothing_is_422`, `test_strips_photo_refuses_bad_file` |
| 5 | Patient lens leakage: the patient opens Inspect from Today, MyCare or Ask | Only Input and What the AI found; no raw output, no event codes (`/\b[a-z]+\.[a-z_]+\b/`), no staff-only moments | Task 1 `test_staff_only_moments_have_no_patient_finding`; Task 2 `tabsFor`; Task 6 `filterMoments patient lens` |

---

### Task 1: Moments in the chart view, staff nudge wording, truthful home next step · 1 d

**Files:**
- Create: `backend/app/journey/ai_moments.py` (builders per kind, `moments`, `line_of`), `backend/app/journey/moment_text.py` (C5 sentences, `RULE_TEXT`, `TITLE`, `FILTER`, `OWNER`), `backend/tests/test_ai_moments.py`, `backend/tests/test_p8_wording.py`
- Modify: `backend/app/journey/api.py:155-185` (`view` adds `"ai_moments": moments(events)`), `backend/app/journey/nudges.py:36-79` (`_nudge` gains `says_staff`), `backend/app/journey/ask.py` (`unseen_by_doctor`), `backend/app/journey/states.py:252-309` (`_next_step`, `next_role`), `frontend/src/care/alerts.js` (`nudgeText`), `frontend/src/care/AlertBanner.jsx`, `frontend/src/care/Chart.jsx:43-52` (the doctor posts Seen), `frontend/src/care/alerts.test.js`, `frontend/scripts/demo/beats.mjs` (`das-strip.expect`), the demo document

**Interfaces:**
- Produces: `moments(events: list[dict]) -> list[dict]` (C1); `line_of(event: dict) -> dict` (C2); `visual_finding(rows: list[dict]) -> str` (R5); `unseen_by_doctor(events) -> list[dict]` (check-in payloads with `id`, oldest first); nudge dicts gain `"says_staff": str`; frontend `nudgeText(nudge, role) -> string` (`role === "patient" ? says : says_staff || says`).
- Consumes: `stories.plain`, `stories.clock`, `nudges.open_nudges`, `medicines.day_plan`, `visible_events`.

- [ ] **Step 1: Write the failing backend tests.** `test_ai_moments.py` builds events by hand with `_ev(eid, kind, ts, **payload)` (`{"id", "event_type", "ts_ms", "payload", "episode_id": "e1", "supersedes_id": None}`):

```python
def test_tray_check_is_a_flagged_visual_moment():
    rows = [{"concept": "needle holder", "planned": 3, "seen": 2}, {"concept": "retractor", "planned": 2, "seen": 2}]
    m = _one(moments([_ev("t1", "tray.checked", 10, rows=rows, match="mismatch", why="w", media="video",
                         source="prepared", calls=[SAM], by=ASHA, evidence_id=EID, frame_ids=[])]))
    assert (m["kind"], m["capability"], m["status"], m["owner"], m["filter"]) == ("visual", "tray", "flagged", "doctor", "video")
    assert m["finding"] == "Saw 2 of 3 needle holders."
    assert m["evidence_id"] == EID and m["calls"] == [SAM]

def test_order_draft_is_open_until_signed():
    drafted = _ev("d1", "order.drafted", 10, items=[DOSE, OBS], transcript=KUMAR_SAID, heard_by="prepared", source="rules", calls=[VOICE], by=RAO)
    assert _one(moments([drafted]))["status"] == "open"
    m = _one(moments([drafted, _ev("s1", "order.signed", 20, items=[DOSE, OBS], draft_id="d1", by=RAO)]))
    assert m["finding"] == "2 orders drafted from 25 words."
    assert m["status"] == "recorded" and [w["type"] for w in m["written"]] == ["order.drafted", "order.signed"]
    assert m["refs"]["signed_items"] == [DOSE, OBS] and m["patient_finding"] is None
```

  Also in this file:
  - `test_nudge_moment_links_intent_and_fact`: `refs.intent.id`/`refs.fact.id` equal the nudge's ids; `refs.fact.plain` is not empty; `owner` is the nudge's `to`; after `nudge.seen` the status is `recorded`.
  - `test_record_bot_answer_cites_lines`: `finding == "Answered from 1 record line."`; `patient_finding == "Answered from 1 line of your record."`; `calls == []`.
  - `test_handover_lines_keep_evidence`: `refs.lines[0].evidence[0].id` is the cited event; status `open`, owner `nurse`; after `handover.accepted` it is `recorded`.
  - `test_day_plan_moment_id`: `rx.ordered` `r1` plus `medicines.read` give one moment with id `dayplan:r1`, kind `draft`.
  - `test_reference_photo_is_a_record_row`: finding `Reference photo.`, filter `photos`. A `frame` photo gives no moment.
  - `test_old_check_without_evidence_is_still_a_moment`: no `evidence_id`, so `evidence_id is None` and the finding still comes from the rows.
  - `test_findings_have_no_advice_and_no_model_text`: a `proof.checked` with `read="Zzzdrug 5 mg"` gives a finding without `Zzzdrug`; every finding and patient finding passes `ADVICE`.
  - `test_staff_only_moments_have_no_patient_finding`: voice drafts, handover, typed orders and a nurse-addressed nudge.
  - `test_moments_newest_first`.
  - `test_view_has_ai_moments`: an API test with `_client`/`_seed` from `tests.test_care_demo`; `GET /journey/episodes/{eid}` has a list `ai_moments`.

  `test_p8_wording.py`:

```python
def test_strip_nudge_has_staff_wording():
    out = strips_vs_rx([_rx("amlodipine", "Amlodipine", "5 mg"), _strip("Amlodipine", "10 mg")])
    assert out[0]["says_staff"] == "Strip reads amlodipine 10 mg; prescription says 5 mg."
    assert "Show both to your pharmacist or doctor." in out[0]["says"]

def test_unprescribed_strip_staff_wording():
    out = strips_vs_rx([_rx("amlodipine", "Amlodipine", "5 mg"), _strip("Ibuprofen", "400 mg")])
    assert out[0]["says_staff"] == "Strip reads ibuprofen 400 mg; not on the prescription from Dr. A. Rao (synthetic)."

def test_home_next_step_names_unseen_checkin():
    events = _home_events() + [_checkin("c1", day=1)]
    assert now_next(events)["next_mine"] == "Day 1 check-in not seen."
    assert now_next(events)["next"] == "Day 1 check-in not seen by the doctor."
    assert now_next(events)["you_next"] == "Dr. Rao has not seen your day 1 check-in yet."
    assert now_next(events)["next_role"] == "doctor"
    assert now_next(events + [_seen("c1", "Nurse Meena (synthetic)")])["next_role"] == "doctor"
    assert now_next(events + [_seen("c1", "Dr. A. Rao (synthetic)")])["next"] == "The patient is home. No further steps."
```

  Add `test_reviews_and_questions_come_before_checkins`: with an open healing-photo review and an unseen check-in, `next_mine == "Review the healing photo."`. With an open doctor question and an unseen check-in, it is `"Answer the question."`. In both files, other nudge kinds keep `says_staff == says`, and every new string passes `ADVICE`. `KUMAR_SAID` is the `kumar-orders.json` transcript (25 words).
- [ ] **Step 2: Write the failing frontend test** (`alerts.test.js`): `nudgeText({says: "a", says_staff: "b"}, "doctor") === "b"`, `"patient"` gives `"a"`, and a nudge with no `says_staff` gives `"a"` for every role.
- [ ] **Step 3: Run both suites.** Expected: the new tests FAIL (`ImportError: ai_moments`, `KeyError: 'says_staff'`, `nudgeText is not a function`).
- [ ] **Step 4: Implement.**
  - `moments`: walk `visible_events(events)` once and dispatch on `event_type` to one small builder per C1 capability. `task.done` is a voice moment only when `via == "voice"`. `question.answered` is `answer_voice` when `source == "doctor"` and `via == "voice"`, `record_bot` when `source != "doctor"`, else no moment. A `proof.checked` with `values_read` is `monitor`, otherwise `dose_strip`. Typed `brownbag.med_found` rows (no `evidence_id`) give no moment. Anchors:
    - `healing_photo`: `review.requested`;
    - `photo`: `photo.added` with purpose `reference` or `wound`;
    - `typed_orders`: `order.signed` without `draft_id`;
    - `discharge_card`: `discharge.card`;
    - `handover`: `handover.drafted`;
    - `nudge`: `nudge.raised`; a nudge closed by a correction (`nudges.CORRECTABLE`) reads `recorded`.
  - `api.py`: one import and one dict entry. Keep the file under 500 lines.
  - `_nudge(key, kind, to, says, intent, fact, at_ms, says_staff=None)` writes `says_staff or says`.
  - `_next_step` and `next_role`: after the reviews and questions branches, the oldest `unseen_by_doctor` check-in sets mine `f"Day {d} check-in not seen."`, staff `f"Day {d} check-in not seen by the doctor."`, you `f"Dr. Rao has not seen your day {d} check-in yet."` and role `doctor`.
  - `AlertBanner`: the read-only row shows `nudgeText(nudge, role)`; answerable rows pass `{...nudge, says: nudgeText(nudge, role)}` to `Nudge`.
  - `Chart.jsx`: the Seen effect also runs for `ward.role === "doctor"` with `DOCTOR` from `DoctorActions.jsx`.
- [ ] **Step 5: Update the demo.** The doctor's banner now shows the staff wording.
  - `das-strip.expect` becomes `["Strip reads amlodipine 10 mg; prescription says 5 mg."]`.
  - Update the document's `das-strip` "On screen" line to match.
- [ ] **Step 6: Run the backend and frontend suites, then `make demo-check MODEL_API_KEY=`.** Expected: all pass; "DEMO CHECK PASSED: 32 beats".
- [ ] **Step 7: Commit** with the message `Count Guard: the chart view lists every AI moment, staff see staff wording on strip alerts, and an unseen check-in is the doctor's next step`.

---

### Task 2: `AiMoment` and the Inspector shell · 1 d

**Files:**
- Create: `frontend/src/care/moments.js`, `moments.test.js`, `inspect.js`, `inspect.test.js`, `AiMoment.jsx`, `Inspector.jsx`
- Modify: `frontend/src/care/CareShell.jsx` (host `<Inspector ward={ward} />` in `<main>`), `care.css` (`.ai-moment`, `.chip`, tone pills, `.inspector` drawer 480 px right; full-screen sheet under 600 px), `styles.test.js`

**Interfaces:**
- Produces, `moments.js` (pure):
  - `chipFor`, `heardChip`, `draftChip` (C4); `statusLabel` (C3).
  - `momentFor(view, id) -> Moment | null`: matches `id`, `photo_id`, `evidence_id` or any `written[].event_id`.
  - `findingFor(moment, lens) -> string`; `canInspect(moment) -> boolean` (`kind !== "record"`).
  - `INSPECT_ID = /^[A-Za-z0-9:_-]{1,80}$/`.
- Produces, `inspect.js` (pure):
  - `TABS = [["input","Input"],["found","What the AI found"],["record","Record"],["model","Model"]]`; `tabsFor(lens) -> string[]`.
  - `readInspect(params: URLSearchParams) -> {momentId, episodeId, focus} | null`.
  - `modelRows(calls, handmade) -> [{name, id, mode, ms}]`; `ms` reads `"—"` when null, else `` `${ms} ms` ``.
  - `recordLine(w, lens) -> string`: staff `` `${w.type} · ${hhmm} · ${displayName(w.by)} · ${w.plain}` ``; patient `` `${hhmm} · ${w.plain}` ``.
  - `stepFrame(i, delta, n) -> number`: clamps to `0..n-1`.
  - `resolveMoment(moments, id, lens) -> Moment | null`: null for an unknown id, and for a moment whose `patient_finding` is null in the patient lens.
- Produces, components: `Inspector.jsx` exports default `Inspector`, plus `useInspector` and `KIND_VIEWS` (C6, empty kinds for now; an unknown kind renders the finding only). `AiMoment.jsx` per C6.
- Inspector layout:
  - Header: `title`, chip, status pill, `Close`.
  - `role="tablist"` buttons with `role="tab"` and `aria-selected`; only the active `role="tabpanel"` renders.
  - Record tab: `recordLine` per `written` entry, plus `correctionLine(read, saved, by)` when both are present. Staff lines link to `/chart/${episodeId}?line=${event_id}`.
  - Model tab (staff only): a `modelRows` table, or `No model call.` when there are no calls (rule kind: `No model call.` then `refs.rule`), then `No raw output is kept for this result.` (Task 3 replaces it for evidence moments).
  - Esc closes it. Lens: `ward.role === "patient" ? "patient" : "staff"`. A patient lens on a moment whose `patient_finding` is null resolves to `Nothing to inspect with that id.`

- [ ] **Step 1: Write the failing tests.**

```js
test("chip vectors", () => { for (const [input, want] of CHIP_VECTORS) assert.equal(chipFor(input), want); }); // C4 table
test("status labels follow the viewer", () => {
  assert.deepEqual(statusLabel({ status: "flagged", owner: "doctor" }, "doctor"), { text: "Needs you", tone: "blue" });
  assert.deepEqual(statusLabel({ status: "flagged", owner: "doctor" }, "nurse"), { text: "Flagged", tone: "amber" });
  assert.deepEqual(statusLabel({ status: "open", owner: "nurse" }, "doctor"), { text: "Waiting for the nurse", tone: "grey" });
});
test("readInspect rejects bad ids", () => {
  assert.deepEqual(readInspect(new URLSearchParams("inspect=dayplan:abc&focus=amlodipine")), { momentId: "dayplan:abc", episodeId: null, focus: "amlodipine" });
  for (const bad of ["inspect=%3Cscript%3E", `inspect=${"a".repeat(81)}`, "", "inspect="]) assert.equal(readInspect(new URLSearchParams(bad)), null);
});
test("a patient sees two tabs", () => {
  assert.deepEqual(tabsFor("patient"), ["input", "found"]);
  assert.deepEqual(tabsFor("staff"), ["input", "found", "record", "model"]);
});
```

  Also:
  - `momentFor` matches by id, `photo_id`, `evidence_id` and written id.
  - `a patient lens never resolves a staff-only moment`: a pure `resolveMoment(moments, id, lens)` in `inspect.js` returns null for `patient_finding: null`.
  - `recordLine` patient output has no `/\b[a-z]+\.[a-z_]+\b/`.
  - All C7 copy passes `ADVICE`.
  - Source regexes:
    - `Inspector.jsx` contains `aria-label="Inspector"` and `Nothing to inspect with that id.`, and neither `createPortal` nor `role="dialog"`.
    - `AiMoment.jsx` contains `aria-hidden="true">›`.
    - `CareShell.jsx` imports `./Inspector.jsx`.
- [ ] **Step 2: Run the frontend suite.** Expected: FAIL (modules missing).
- [ ] **Step 3: Implement** the helpers and components above. `openInspector` and `closeInspector` call `setSearchParams(…, { replace: true })` (R7).
- [ ] **Step 4: Run the frontend suite, `npm run build` and `make demo-check MODEL_API_KEY=`.** Expected: pass. There is no beat change: nothing opens the drawer yet.
- [ ] **Step 5: Commit** with the message `Count Guard: one AI moment line and one Inspector drawer with Input, What the AI found, Record and Model`.

---

### Task 3: Inspector kinds `visual` and `photo_read`; chips on checks · 1 d

**Files:**
- Create: `frontend/src/care/InspectVisual.jsx` (exports `VisualInput`, `VisualFound`, `PhotoFound`, `RawOutput`)
- Modify:
  - `Inspector.jsx`: registers the kinds; the Model tab uses `RawOutput` when `evidence_id` is set.
  - `inspect.js`: `REGION_FIELD`, `regionFieldLine`.
  - `evidence.js`: `isFocusRegion`.
  - `EvidenceStage.jsx`: accepts `focus.region`.
  - `VideoCheck.jsx:35-43`: `CheckResult` shows the moment chip instead of `({sourceLabel(check.source)})`.
  - `TaskProof.jsx:60-64`: the photo line shows the chip.
  - `MyCare.jsx:44`: shows the chip.
  - `TheatreChecklist.jsx`, `NurseTasks.jsx`: pass `moment={momentFor(view, check.id)}` to `VideoCheck`.
  - `inspect.test.js`, `evidence.test.js`, `beats.mjs` (`kumar-tray.expect`), the demo document.

**Interfaces:**
- Consumes: `useEvidence`, `evidenceView`, `Evidence` (`Evidence.jsx:13,69`), `Stage` (`EvidenceStage.jsx:70`), `checkLabel` (`video.js:48`), `KIND_VIEWS` (C6), `momentFor`, `chipFor`.
- Produces:
  - `REGION_FIELD = { monitor: { SBP: "Obs · systolic", DBP: "Obs · diastolic", HR: "Obs · pulse" }, strip: "Dose · medicine", medicines: "Medicines from home" }`.
  - `regionFieldLine(region, reader) -> string`, for example `"SBP 88 → Obs · systolic"` or `"Amlodipine 10 mg → Dose · medicine"`; an unread region gives `"SBP not read"` (reuse `regionLabel`).
  - `isFocusRegion(i, focus) -> boolean`.
- Tabs:
  - Visual Input: the kept images, with `Previous` / `Next` and `Frame {n} of {N}` (`stepFrame`).
  - Visual Found: `checkLabel(refs.check)` in a status line, then the existing `<Evidence episodeId evidenceId check={refs.check} />`, which keeps "What the AI saw", tap-to-highlight and Expand.
  - Photo_read Found: `Stage` with `regions` and `focus={{region: i}}`, then one button per region (`aria-pressed`) with `regionFieldLine`, then `Why:` + `explainRegions`. Medicines rows reuse `stripLabel` (`brownbag.js`).
  - `RawOutput`: staff only; a `<pre>` of the sidecar's `raw`; a missing sidecar gives `No raw output is kept for this result.`

- [ ] **Step 1: Write the failing tests:**
  - `regionFieldLine` gives `{label:"SBP", value:"88"}` monitor → `"SBP 88 → Obs · systolic"`, `{label:"HR", value:null}` → `"HR not read"`, and the strip vector.
  - `isFocusRegion(1, {region: 1})` is true, `(0, {region: 1})` false, `(0, null)` true.
  - `visual Found falls back without a sidecar`: `evidenceView(null, check).fallback === true` (existing contract).
  - The R5 twin vector: `explain([{concept:"needle holder", planned:3, seen:2}], null, 0.45, "photos")[0] === "Saw 2 of 3 needle holders."`, the same string as backend `visual_finding`.
  - Source regex: `VideoCheck.jsx` no longer contains `sourceLabel(`.
- [ ] **Step 2: Run the suite.** Expected: FAIL.
- [ ] **Step 3: Implement** the kinds and the chip swaps. `VideoCheck` gains a `moment` prop; when it is absent, it shows no chip.
- [ ] **Step 4: Update the demo.**
  - `kumar-tray.expect` drops `"Prepared demo result"`: the check now shows the chip, `SAM 3.1 · Sample` with today's handmade fixture. Do not pin the chip; Task 5 of v3 may re-record (v3 R13).
  - Update the document's On screen line.
- [ ] **Step 5: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 6: Commit** with the message `Count Guard: the Inspector shows video and photo checks with boxes, values and the form field each value filled`.

---

### Task 4: Voice: word spans ↔ order chips · 1 d

**Files:**
- Create: `backend/tests/test_order_spans.py`, `frontend/src/care/InspectVoice.jsx`
- Modify:
  - `backend/app/journey/dictation.py`: `order_spans`.
  - `backend/app/journey/media_api.py:96-114`: `dictate_orders` writes `spans`.
  - `frontend/src/care/orders.js`: `orderSentence`, `sentenceText`, `PROOF_WORD`, `obsLabel`, `rowItem`.
  - `inspect.js`: `segments`, `fieldDiffs`, `FIELD_LABEL`.
  - `Inspector.jsx`: registers `voice`.
  - `Dictate.jsx:102`: `heardChip`.
  - `OrderForm.jsx:28-33`: an `AiMoment` replaces the `heardLine` note.
  - `DoctorActions.jsx:128-133`: the discharge note likewise; `OrdersDictation` passes `moment`.
  - `TaskProof.jsx:48-53`: `draftChip`.
  - `askText.js:85-91`: `answerSourceLine` returns `heardChip(answer.heard_by)`.
  - `drafts.js`: `heardLine` removed once unused.
  - Tests: `orders.test.js`, `inspect.test.js`, `drafts.test.js`, `askText.test.js`.
  - Demo: `beats.mjs` (`HEARD`, new `HEARD_ONLY`, `kumar-orders`, `kumar-paracetamol`, `kumar-discharge`, `kumar-review`), `beats.test.mjs`, the demo document.

**Interfaces:**
- Produces, backend: `order_spans(transcript: str, items: list[dict]) -> dict` returns `{"text": digits(transcript), "marks": [{"start": int, "end": int, "item": int, "field": str}]}`.
  - Fields: `name`, `amount`, `every_h`, `proof`, `limits.sbp_min`, `limits.sbp_max`.
  - Algorithm, per item `i`:
    1. Find the clause window: the first case-insensitive occurrence of `item["text"]` in `text`; when it is absent (a model paraphrase), use the whole text.
    2. Inside the window, find `name` as a whole word, `amount` with `_AMOUNT`, `every_h` with `_EVERY`, each limit value as `\b{v}\b` after `_SBP_MIN`/`_SBP_MAX`, and `proof` as `photo|picture|video`.
    3. Drop a field that is not found.
    4. Sort the marks by start and drop any mark overlapping an earlier one.
  - `dictate_orders` adds `"spans": dictation.order_spans(meta["transcript"], result["items"])` to the payload.
- Produces, frontend:
  - `orderSentence(item) -> [{field, text}]`:
    - dose: `[name capitalised, amount, `every ${h} h`, `proof: ${PROOF_WORD}`]`;
    - obs: `[obsLabel(text) as field "text", `every ${h} h`, `alert if systolic < ${min}`, `alert if systolic > ${max}`]`;
    - procedure, check and other: `[text]`, plus proof.
    - Absent fields are skipped. `PROOF_WORD`: dose photo → `strip photo`, obs photo → `monitor photo`, any video → `video`; `none` gives no chip.
  - `sentenceText(item)` joins with ` · `.
  - `obsLabel(text)` cuts before `/,|\s+every\b/i`.
  - `rowItem(row)` returns `orderRowsToItems([row]).items[0] ?? {kind: row.kind, text: row.text}`.
  - `segments(text, marks) -> [{text, mark}]` (pure; drops marks out of range or overlapping).
  - `fieldDiffs(drafted, signed) -> [{item, field, drafted, signed}]` (R10). `FIELD_LABEL`: `name` Medicine, `amount` Amount, `every_h` Every, `proof` Proof, `text` Order, `limits.sbp_min` Systolic min, `limits.sbp_max` Systolic max.
- Tabs:
  - `VoiceInput`: `refs.transcript`, the chip and the word count.
  - `VoiceFound`:
    - Orders: the segments as `<button className="mark">` (marked) or text. Beside them, each item's `orderSentence` chips as buttons. Focus `{item, field}` lights both sides (`.lit`).
    - Then `AI drafted → signed` lines `` `${FIELD_LABEL[field]}: ${drafted} → ${signed}` `` (or `Added at signing: …` / `Removed at signing: …`).
    - No spans: the transcript unhighlighted and `No word links for this draft.`
    - Discharge: the sections. Task and answer: the transcript only.

- [ ] **Step 1: Write the failing backend tests.**

```python
KUMAR = "Admit for open hernia repair. Paracetamol 1 g every 6 hours, strip photo as proof. BP and pulse every 1 hour, lower systolic limit 90."

def test_spans_for_demo_transcript():
    spans = order_spans(KUMAR, parse_order_text(KUMAR)["items"])
    got = {(m["item"], m["field"]): spans["text"][m["start"]:m["end"]] for m in spans["marks"]}
    assert got[(0, "name")].lower() == "paracetamol" and got[(0, "amount")] == "1 g"
    assert got[(0, "every_h")] == "every 6 hours" and got[(0, "proof")] == "photo"
    assert got[(1, "every_h")] == "every 1 hour" and got[(1, "limits.sbp_min")] == "90"
```

  Add:
  - `test_spans_from_number_words`: `"Paracetamol one gram every six hours"` gives `text == "Paracetamol 1 gram every 6 hours"` and marks for name, amount and every_h.
  - `test_spans_skip_missing_and_never_overlap`: a model item named `ibuprofen` gives no name mark; the marks are sorted and pairwise disjoint.
  - `test_dictate_orders_writes_spans`: the API with form `text=KUMAR`; the `order.drafted` payload has `spans.text == KUMAR`.
- [ ] **Step 2: Write the failing frontend tests:**
  - `sentenceText(dose)` is `"Paracetamol · 1 g · every 6 h · proof: strip photo"` and `sentenceText(obs)` is `"BP and pulse · every 1 h · alert if systolic < 90"` (the items `parse_order_text(KUMAR)` returns).
  - `segments reassemble the text`: `segments(t, marks).map(s => s.text).join("") === t`, including overlap and out-of-range cases.
  - `fieldDiffs` vectors: an amount edit, an added row, a removed row.
  - `draftChip("prepared", "rules") === "Muse Voice → Rules · prepared"`; `draftChip("typed", "rules") === "Rules"`; `heardChip("prepared") === "Muse Voice · prepared"`.
  - Every new string passes `ADVICE`.
- [ ] **Step 3: Run both suites.** Expected: FAIL.
- [ ] **Step 4: Implement** the backend function, the voice kind and the chip swaps.
  - The order and discharge notes keep `Draft from dictation.` then `Check each row, then sign.` / `Check the summary, then sign.`; the `AiMoment` sits above that note.
- [ ] **Step 5: Update the demo** (`beats.mjs`, `beats.test.mjs`, the document). Today's strings are read right after the last click (`run.mjs:71-72`), so they stay what is on screen at that moment:
  - `const HEARD = "Muse Voice → Rules · prepared"`, used by `kumar-orders`, `kumar-paracetamol` and `kumar-discharge` (`expect` and `before`).
  - `const HEARD_ONLY = "Muse Voice · prepared"`: `kumar-review.before` becomes `[HEARD_ONLY]`.
  - `kumar-orders.expect`: `["Draft from dictation", HEARD, "2 orders drafted from 25 words.", "Paracetamol"]`.
  - `kumar-review.expect`: `"by voice · Prepared demo result"` becomes `"by voice · Muse Voice · prepared"`.
  - Keyed lines: replace "Heard by reads Muse Voice" with "The chip reads Muse Voice → Muse Spark 1.3 · live".
  - If `kumar-discharge` fails on `HEARD` (the draft note can unmount after Sign), use `HEARD_ONLY`, the Dictate chip that stays mounted.
- [ ] **Step 6: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 7: Commit** with the message `Count Guard: a voice draft links each heard word to the order field it became, and shows what changed before signing`.

---

### Task 5: Inspector kinds `answer`, `rule` and `draft` · 0.75 d

**Files:**
- Create: `frontend/src/care/InspectText.jsx` (exports `AnswerInput`, `AnswerFound`, `RuleInput`, `RuleFound`, `DraftInput`, `DraftFound`)
- Modify: `Inspector.jsx` (register), `inspect.js` (`ruleCards`), `Thread.jsx:40-46` (the record-bot answer shows an `AiMoment` in the patient lens), `askText.js:59-62` (`answerByLine` for the bot returns `Record bot`), `askText.test.js`, `inspect.test.js`, `beats.mjs` (`das-ask.expect`), the demo document

**Interfaces:**
- Consumes: `questionText(role, q)` (`askText.js`, which keeps the patient's words hidden from non-doctors); `cropStyle` and the day-plan crop helpers (`DayPlan.jsx`, `brownbag.js`).
- Produces: `ruleCards(refs, lens) -> [{heading, line}]`, headings `Ordered / prescribed` (intent) and `Recorded / read` (fact). A missing side reads `Not recorded`. The patient lens drops `type`.
- Tabs:
  - Answer Input: the question through `questionText(role, {text: refs.question})`; the patient sees their own words.
  - Answer Found: the answer, then the cited lines as buttons that navigate to `/chart/${episodeId}?line=${id}` (staff), or as quotes (patient).
  - Rule Input: `No input: this check compares two records.`
  - Rule Found: two cards side by side (stacked under 600 px), then `` `Rule: ${refs.rule}` ``.
  - Draft Input: the source lines.
  - Draft Found: handover, the model text (when `wording` is Spark) then each line with its evidence lines as links. Day plan: rows with the crop, and the row `focus` lit and scrolled into view. Card: its lines.

- [ ] **Step 1: Write the failing tests:**
  - `ruleCards` with both sides, with the fact missing, and patient-lens output with no `/\b[a-z]+\.[a-z_]+\b/`.
  - `answerByLine({source: "rules"}) === "Record bot"`.
  - The existing `Record bot · Rules (no model)` assertion in `askText.test.js` is replaced.
  - Every new string passes `ADVICE`.
- [ ] **Step 2: Run the suite.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Update the demo.**
  - `das-ask.expect` becomes `["Here is what your record says.", "Amlodipine", "Answered from your record"]`. The last string is the thread status (`thread.js` `threadStatus`).
  - `das-ask.keyed`: "The label reads Rules" in place of "Rules (no model)".
  - Update the document.
- [ ] **Step 5: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 6: Commit** with the message `Count Guard: the Inspector shows a record answer's cited lines, an alert's two records and its rule, and each handover line's sources`.

---

### Task 6: Record & evidence, and finished steps collapse · 1.25 d

**Files:**
- Create: `frontend/src/care/RecordEvidence.jsx`
- Delete: `frontend/src/care/Photos.jsx`, `VideoChecks.jsx`, `OrderTasks.jsx`, plus any `video.js` / `drafts.js` export left with no importer (grep first) and its tests
- Modify:
  - `Chart.jsx:85-91`: `RecordEvidence` replaces the three cards, after `MedicinesFromHome`, before `History`.
  - `MyCare.jsx:55-56`: `RecordEvidence lens="patient"`.
  - `TheatreChecklist.jsx:50-60`: R18.
  - `NurseTasks.jsx:41`: an `AiMoment` replaces `EvidenceThumb`.
  - `DoctorActions.jsx:57-64`: the last signed dictation shows as an `AiMoment`.
  - `moments.js`: `FILTERS`, `filterMoments`, `lastSigned`.
  - `moments.test.js`, `theatre.test.js`, `care.css`, `beats.mjs` (`kumar-tray`, `kumar-count`), `steps.mjs`, the demo document.

**Interfaces:**
- Produces:
  - `FILTERS = [["all","All"],["needs","Needs you"],["photos","Photos"],["video","Video"],["voice","Voice"],["answers","Answers"],["alerts","Alerts"]]`.
  - `filterMoments(moments, filter, role, lens) -> Moment[]`. `needs` keeps rows whose `statusLabel` reads `Needs you`. The patient lens drops `patient_finding === null`.
  - `lastSigned(moments, capability) -> Moment | null`.
- `<RecordEvidence view role lens episodeId />`:
  - `<section className="card" aria-label="Record and evidence">` with the label `Record & evidence`.
  - The filter chips are buttons with `aria-pressed`, staff only.
  - One `AiMoment` per row, with a 40 px thumbnail `/journey/episodes/${episodeId}/photos/${photo_id}` when `photo_id` is set.
  - Empty: `Nothing here for this filter.`

- [ ] **Step 1: Locate `15 of 15`.** It is a `kumar-discharge` expect and before string; its renderer was not found in source.
  - Run `CG_DEMO_UNTIL=kumar-home make demo-check MODEL_API_KEY=` and read `demo-shots/` for `kumar-discharge`.
  - If the string sits in Photos, Video checks or Orders and tasks, keep that exact figure visible: carry it into that moment's finding, or keep the line it came from.
  - Do not edit the beat for it.
- [ ] **Step 2: Write the failing tests:**
  - `filterMoments` vectors: one each for photos, video, voice, answers, alerts, `needs` with role doctor, and the patient lens.
  - `lastSigned` returns the newest `recorded` orders moment.
  - Source regexes: `Chart.jsx` imports none of `Photos`, `VideoChecks`, `OrderTasks`; `fs.existsSync(new URL("./Photos.jsx", import.meta.url)) === false` (and the other two); `TheatreChecklist.jsx` has no `hideUpload` and contains `Check the tray again`.
- [ ] **Step 3: Run the suite.** Expected: FAIL.
- [ ] **Step 4: Implement** R17 and R18.
  - In `TheatreChecklist`, a done tray step renders `<AiMoment moment={momentFor(view, view.tray.latest.id)} role={role} episodeId={episodeId} />`.
  - While `canRecord(view, "tray")`, it adds `<label className="field">Check the tray again<input type="file" …/></label>`.
- [ ] **Step 5: Update the demo** (R20; `beats.mjs`, `steps.mjs`, the document):
  - `kumar-tray`: append the click `'Button "Inspect" in "Theatre steps"'` (step: `await H.click("Inspect", "Theatre steps")`).
  - `kumar-tray.expect`: `["Flagged: not everything planned was seen. The surgeon decides.", "Needle holder", "1 missing", "Saw 2 of 3 needle holders.", "What the AI found"]`.
  - `kumar-tray.say`: `"Nurse Asha films the tray; the check finds one needle holder missing and flags it for the surgeon, and Inspect shows what SAM 3.1 saw."`
  - `kumar-count`: prepend the click `'Button "Close" in "Inspector"'` (step: `await H.click("Close", "Inspector")` first).
- [ ] **Step 6: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 7: Commit** with the message `Count Guard: one Record & evidence list per chart, and a finished step folds to its AI moment`.

---

### Task 7: Orders as sentences · 0.75 d

**Files:**
- Create: `frontend/src/care/OrderSentence.jsx`
- Modify: `OrderForm.jsx` (sentence view by default; the form grid behind `Edit all fields`), `NurseActions.jsx:21-29` (acknowledge list uses `sentenceText`), `orders.js` (`chipEdit`, `CHIP_INPUT`), `orders.test.js`, `beats.mjs` (`kumar-orders.expect`), the demo document

**Interfaces:**
- Consumes: `orderSentence`, `sentenceText`, `rowItem`, `FIELD_LABEL` (Task 4).
- Produces:
  - `chipEdit(row, field, value) -> row`: `limits.sbp_min` → `row.sbp_min`, `limits.sbp_max` → `row.sbp_max`, other fields by name.
  - `CHIP_INPUT = { proof: "select" }`; others are text.
  - `<OrderSentence row index onChange />`: each chip is a button. Tapping it shows an inline input labelled `` `${FIELD_LABEL[field]} of order ${index + 1}` ``; Enter or blur commits through `chipEdit`; Esc cancels. Proof opens a select (`none`, `photo`, `video`).
  - `OrderForm` keeps its rows state. `Edit all fields` (`aria-expanded`) shows today's grid. The Add buttons stay. A row error from `orderRowsToItems` shows under its sentence.

- [ ] **Step 1: Write the failing tests:**
  - `chipEdit` vectors for amount, every_h and `limits.sbp_min`.
  - `sentenceText(rowItem(PREFILL.dose()))` is `"Paracetamol · 1 g · every 6 h"`.
  - Source regexes: `OrderForm.jsx` contains `Edit all fields`; `NurseActions.jsx` uses `sentenceText(`.
- [ ] **Step 2: Run the suite.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Update the demo.**
  - Append `"Paracetamol · 1 g · every 6 h · proof: strip photo"` to `kumar-orders.expect`.
  - Update the document. `kumar-admit` still clicks `Sign orders`, which is unchanged.
- [ ] **Step 5: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 6: Commit** with the message `Count Guard: a drafted order reads as a sentence with chips, and a chip edits its field in place`.

---

### Task 8: Capabilities in the flow · 1.5 d

**Files:**
- Create: `backend/app/journey/prepared/strip-amlodipine.json`, `backend/tests/test_strips_photo.py`, `frontend/src/care/StripPhoto.jsx`, `frontend/src/care/HandoverCard.jsx`
- Modify:
  - `backend/app/journey/api.py:250-273`: remove `/strips/photo` and its now-unused imports.
  - `backend/app/journey/media_api.py`: add `/strips/photo` (R11, R12).
  - `backend/app/journey/ai_moments.py`: `strips` builder.
  - `eval/p4/make_photos.py:63-90`: draw `strip-amlodipine.png`; `--write-fixtures` covers it.
  - `frontend/src/care/DoctorActions.jsx:18-32,87-97`: `StripPhoto` replaces `StripCheck`.
  - `NurseActions.jsx`: `HandoverCard` in state ward.
  - `askText.js:31-39`: `inboxItems` adds answered `bot` items.
  - `AskInbox.jsx`: `RecordBotItem`.
  - `AlertBanner.jsx`: each row is an `AiMoment`.
  - `DayPlan.jsx`: an Inspect per row.
  - `MedicinesFromHome.jsx`: an `AiMoment` heads the card.
  - Tests: `askText.test.js`, `moments.test.js`.
  - Demo: `beats.mjs` (`das-strip`, `MEDIA`), `steps.mjs`, the demo document (the beat block, the Keyed row, the media list under "Before filming").

**Interfaces:**
- Produces, backend: `POST /journey/episodes/{episode_id}/strips/photo`, multipart `file`, `by: str = Form("patient", min_length=1, max_length=80)`, `at_ms: int | None = Form(None, ge=0)`.
  1. `read_upload_photo(file)` validates the image: 400 for a wrong type, size or magic bytes.
  2. `read = live.read_photo(settings, "strip", raw, file.filename or "", kind, live_ok=MEDICINES_LIVE)`; `strips = strips_from(read["text"] or "")`.
  3. No strips → 422 `No strips were read from the photo. Type them instead.`, with nothing written.
  4. Otherwise `write_photo(… {"purpose": "strips", "by": by} …)` and `keep_photo_evidence(settings, eid, "strip", photo_id, read, read["regions"])`.
  5. Append one `brownbag.med_found` per strip: `{**strip, "by", "source", "photo_id", "evidence_id"?}`, with `"calls"` on the first only. Then `raise_nudges` and return the view.
- Produces, the `strips` moment: anchor = the first row of a batch (rows sharing `evidence_id`); finding per C5; status `flagged` when a strip nudge cites a batch row as `fact_id`, else `matches`. `prepared/strip-amlodipine.json`:

```json
{"text": "{\"strips\": [{\"name\": \"Amlodipine\", \"strength\": \"10 mg\"}]}",
 "regions": [{"bbox": [0.0556, 0.25, 0.8889, 0.5], "label": "Amlodipine 10 mg", "value": "Amlodipine 10 mg", "row": 0}],
 "handmade": true}
```

- Produces, frontend:
  - `<StripPhoto view busy upload act />`: `<section className="card" aria-label="Photo of strips">`, the label `Photo of strips`, `<input type="file" accept="image/*" capture="environment">`, upload `upload("/strips/photo", file, { by: DOCTOR })`. The quiet button `Type instead` (`aria-expanded`) reveals today's textarea and `Check these strips`. Below them: an `AiMoment` for each `strips` moment, then each strip nudge moment.
  - `<HandoverCard view busy act />`: the label `Shift handover`; From and To fields (R21); the checkbox `Ask Muse Spark 1.3 to word it`; `Draft handover` posts `/handover`. Then the handover `AiMoment`, and `Accept as {To}` posting `/handover/{id}/accept` with `by: To` until accepted.
  - `inboxItems` adds `{kind: "bot", id, atMs, open: false}` for questions with `to === "bot"`. `RecordBotItem` renders `Answered by record bot`, `questionText(role, q)` and the `answer` `AiMoment`.
  - `AlertBanner`: a read-only row is `<AiMoment moment={momentFor(view, nudge.id)} />`; an answerable row keeps `Nudge` and adds `<AiMoment … quiet />`.
  - `DayPlan` rows: `Inspect` calls `openInspector("dayplan:" + rxId, { focus: row.key })`. `rxId` is the day-plan moment's id suffix, from `momentFor`.
  - Patient `Strips` (`screens/TodayPanel.jsx:102`): no code change; its call now runs on the reader and works offline.

- [ ] **Step 1: Write the failing backend tests** (`_client`/`_seed` from `tests.test_care_demo`, `PNG` from `tests.test_p4_ask`, keep `no_network`):

```python
def test_strips_photo_offline_uses_fixture(tmp_path):
    client, eid = _das_with_rx(tmp_path)
    r = client.post(_url(eid, "strips/photo"), files={"file": ("strip-amlodipine.png", PNG, "image/png")}, data={"by": RAO})
    assert r.status_code == 200
    rows = _rows(client, eid, "brownbag.med_found")
    assert len(rows) == 1 and rows[0]["payload"]["evidence_id"] and rows[0]["payload"]["source"] == "prepared"
    assert [c["model"] for c in rows[0]["payload"]["calls"]] == ["sam", "spark"]
    nudge = r.json()["nudges"][0]
    assert nudge["says_staff"] == "Strip reads amlodipine 10 mg; prescription says 5 mg."
    strips = [m for m in r.json()["ai_moments"] if m["capability"] == "strips"]
    assert strips[0]["finding"] == "Read 1 strip: 1 differs from the prescription." and strips[0]["status"] == "flagged"
```

  Add:
  - `test_strips_photo_reads_nothing_is_422`: an unknown file name offline gives 422 with the C5 detail, and the events are unchanged.
  - `test_strips_photo_refuses_bad_file`: `text/plain` gives 400.
  - `test_strips_photo_calls_counted_once`: `ai_summary` gives spark `calls == 1` for a 2-strip fixture (write a temp fixture through `monkeypatch` of `live.prepared`).
  - `test_prepared_schema.py` already checks the new fixture's keys; run it.
- [ ] **Step 2: Write the failing frontend tests:**
  - `inboxItems` includes a `bot` item, never open, and `inboxHeader` counts are unchanged.
  - Source regexes:
    - `DoctorActions.jsx` has no `One strip per line: name then strength` outside `StripPhoto.jsx`;
    - `StripPhoto.jsx` contains `aria-label="Photo of strips"` and `Type instead`;
    - `NurseActions.jsx` renders `HandoverCard`;
    - `DayPlan.jsx` calls `openInspector(`.
  - Every new string passes `ADVICE`.
- [ ] **Step 3: Run both suites.** Expected: FAIL.
- [ ] **Step 4: Implement**, then regenerate the media: `.venv/bin/python eval/p4/make_photos.py`.
- [ ] **Step 5: Update the demo:**
  - `MEDIA["strip-amlodipine.png"] = "eval/p4"`.
  - `das-strip.clicks`: `['File eval/p4/strip-amlodipine.png into "Photo of strips"']`; `files: ["strip-amlodipine.png"]`.
  - `das-strip.say`: `"A photo of the pharmacy strip is read and checked against the prescription, and the mismatch is named."`
  - `das-strip.keyed`: `"1 SAM 3.1 image call (strip regions) and 1 Spark vision call. Switch: MEDICINES_LIVE."`
  - `das-strip.expect` stays `["Strip reads amlodipine 10 mg; prescription says 5 mg."]`.
  - Step: `await H.file("Photo of strips", "eval/p4/strip-amlodipine.png")`.
  - In the document, add `strip-amlodipine.png` to the "Before filming" file list.
- [ ] **Step 6: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 7: Commit** with the message `Count Guard: the clinic strip check is a photo, the handover sits on the care chart, staff see the record bot's answers, and alerts and the day plan open the Inspector`.

---

### Task 9: AI activity page and staff nav · 1 d

**Files:**
- Create: `frontend/src/care/ModelCards.jsx` (`ModelCard` and the Try-sample flow, moved from `AiDashboard.jsx:11-23,60-96`), `frontend/src/care/ActivityList.jsx`
- Modify: `AiDashboard.jsx` (rebuilt page), `ai.js` (`STAFF_ONLY`, `storyLine`, `activityRows`, `storyCounts`, `PIPELINE_KIND`, `emptyLine`), `ai.test.js`, `CareShell.jsx:14-17` (`STAFF_TABS`), `DemoDock.jsx:53` (link removed, R22), `beats.mjs` (`ai`), `steps.mjs` (`ai`), the demo document

**Interfaces:**
- Produces, in `ai.js`:
  - `activityRows(patients) -> [{episodeId, patient, moment}]`: newest first, kinds other than `record`, `patient` = `shortName(p.name)`.
  - `storyCounts(rows) -> {transcribed, photos, videos, flags, decided}`: voice, photo_read and visual moments; rule moments; rule moments with status `recorded`.
  - `storyLine(counts) -> string`: non-zero parts of `transcribed {n} note(s)`, `read {n} photo(s)`, `counted {n} video(s)`, `raised {n} flag(s)`, joined with `, ` and ` and ` before the last, prefixed `Today the AI `. When flags > 0, append `; staff decided ` + (`it` when 1 of 1, `all {f}` when all, else `{d} of {f}`), then `.`. All zero gives `""`.
  - `PIPELINE_KIND = { Voice: "voice", Photo: "photo_read", Video: "visual" }`, keyed by the first word of each `PIPELINES` entry (`ai.js:4`).
  - `emptyLine(name) -> string` = `` `Nothing yet today. Open ${name} to follow the demo.` ``.
  - `STAFF_ONLY = "AI activity is a staff view. Switch to Doctor or Nurse."`
- Page order: `PageLead` title `AI activity`; the story strip; the pipeline buttons (`aria-pressed`, a filter); `<ActivityList>`; then `<ModelCards>`. Each row is `patient · title · AiMoment` (Inspect opens with `episodeId`). With no rows, `emptyLine(shortName(ward.patients[0].name))` links to that chart. `Try sample` gets class `quiet`.
- `STAFF_TABS.doctor = [["/patients","My patients"],["/ai","AI activity"]]`; nurse = `[["/queue","My queue"],["/patients","Patients"],["/ai","AI activity"]]`.

- [ ] **Step 1: Write the failing tests:**
  - `storyLine({transcribed:3, photos:4, videos:2, flags:3, decided:3})` is `"Today the AI transcribed 3 notes, read 4 photos, counted 2 videos and raised 3 flags; staff decided all 3."`
  - `storyLine({transcribed:1, photos:0, videos:1, flags:1, decided:1})` is `"Today the AI transcribed 1 note, counted 1 video and raised 1 flag; staff decided it."`
  - `storyLine({transcribed:0, photos:2, videos:0, flags:2, decided:1})` is `"Today the AI read 2 photos and raised 2 flags; staff decided 1 of 2."`; all zero gives `""`.
  - `activityRows` order and record exclusion; `storyCounts`.
  - Replace the v3 test at `ai.test.js:69` with:
    - `canSeeAi` is unchanged;
    - the new `STAFF_ONLY`;
    - `DemoDock.jsx` does not match `to="/ai"`;
    - `CareShell.jsx` contains `["/ai", "AI activity"]`;
    - in `AiDashboard.jsx`, `<ActivityList` comes before `<ModelCards`.
  - Every new string passes `ADVICE`.
- [ ] **Step 2: Run the suite.** Expected: FAIL.
- [ ] **Step 3: Implement.** Each file stays under 500 lines.
- [ ] **Step 4: Update the demo:**
  - `ai.clicks`: `['Tab "AI activity"', 'Button "Try sample" in "SAM 3.1"']`.
  - `ai.expect`: `["AI activity", "Muse Voice", "Muse Spark 1.3", "SAM 3.1", "Muse Spark Open", "Saw 2 of 3 needle holders.", "1 missing"]`.
  - `ai.say`: `"The AI activity page shows what the AI did on this ward and the four Muse models; a sample tray photo shows SAM 3.1 boxes, the counts and a plain explanation."`
  - Step: `await H.tab("AI activity"); await H.click("Try sample", "SAM 3.1");`.
  - In the document: the block, plus the Summary phrase "intro, AI at work and close" becomes "intro, AI activity and close".
- [ ] **Step 5: Run both suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: pass.
- [ ] **Step 6: Commit** with the message `Count Guard: AI activity is a staff page of what the AI did today, by patient and pipeline, each row opening the Inspector`.

---

### Task 10: Sweep and the five-second test · 0.5 d

**Files:**
- Modify: only files that a failure below points to, in the owning task's files
- Scratch (not committed): `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-hackathon-hackathon26/9c2f4abf-956d-48ef-93f1-f23a07ae1f69/scratchpad/sweep-v4.mjs`

- [ ] **Step 1: Run every suite.**
  - Backend and frontend pass at or above the Task 1 baseline plus every task's new tests; `npm run build` is clean.
  - `wc -l backend/app/journey/*.py frontend/src/care/*.js frontend/src/care/*.jsx frontend/src/care/care.css`: every file is under 500 lines.
- [ ] **Step 2: Run `make demo-check MODEL_API_KEY=`.** Expected: `DEMO CHECK PASSED: 32 beats; filmed doctor 58 s, nurse 58 s, patient 58 s, total 200 s`.
- [ ] **Step 3: Browser sweep.**
  - Start `make dev CG_API_PORT=8200 CG_WEB_PORT=5273 MODEL_API_KEY=`.
  - With playwright-core (`findChrome` from `frontend/scripts/demo/chrome.mjs`), walk the demo at 1200 px and at 390 × 844. At each beat:
    - `document.documentElement.scrollWidth <= innerWidth`;
    - no console errors;
    - each `AiMoment` Inspect opens the Inspector, and every tab renders;
    - at 390 px the drawer fills the screen, with Close reachable at the top.
  - Then `?inspect=nope` shows `Nothing to inspect with that id.`
  - Stop the servers.
- [ ] **Step 4: Five-second test (spec §6).** For six screens, write one line each in the commit body: what the AI looked at, what it found, what was recorded, who decided. If any answer needs scrolling or the Inspector, fix it in the owning task's files. The screens:
  - the clinic chart after the strip photo;
  - the theatre chart after the tray check;
  - the ward chart with an open voice draft;
  - the nurse chart with handover;
  - the home chart with an unseen check-in;
  - `/ai`.
- [ ] **Step 5: Coverage check.** Every Appendix B row 1–17 has a moment capability (C1 table) and an Inspector kind, except row 12, which is a `record` row per R6. Row 18 is Task 9.
- [ ] **Step 6: Commit** any fixes, with the message `Count Guard: v4 sweep, every AI moment inspectable at 1200 and 390 px`. List the changed files in the body.

---

## Estimate

| Task | What | Days |
|---|---|---|
| 1 | Moments in the chart view, staff wording, truthful next step | 1 |
| 2 | `AiMoment` + Inspector shell | 1 |
| 3 | Visual and photo kinds, chips on checks | 1 |
| 4 | Voice spans ↔ order chips | 1 |
| 5 | Answer, rule and draft kinds | 0.75 |
| 6 | Record & evidence, finished steps collapse | 1.25 |
| 7 | Orders as sentences | 0.75 |
| 8 | Capabilities in the flow | 1.5 |
| 9 | AI activity page and staff nav | 1 |
| 10 | Sweep and five-second test | 0.5 |
| | **Total** | **9.75** |

The spec says about 9 days. The extra 0.75 d is the strip-photo route rebuild and its fixture (R11, R13), which the spec's P5 row needs because `/ask/medicines` cannot serve the clinic.

Order: 1 → 2 → 3, 4, 5 (any order) → 6 → 7 → 8 → 9 → 10. Task 7 needs Task 4's `orderSentence`. Task 8 needs Tasks 2 and 5 (`draft` kind for handover and day plan).

## Self-review against the spec

**Coverage:**

| Spec item | Task |
|---|---|
| P1 AI moment: chip from `calls` + mode, finding from numbers, four statuses, "(Prepared demo result)" and "Heard by" removed | 1 (C1, C5), 2 (C3, C4), 3, 4, 5 |
| P2 Inspector: drawer 480 px, phone sheet, `?inspect=`, four tabs, Model tab for every kind, patient lens | 2 (R7, R8, R16) |
| P2 kinds: visual, photo_read, voice, answer, rule, draft | 3, 4, 5 |
| P2 `agent` kind | Ops agent plan (C6 `KIND_VIEWS`) |
| P3 finished steps collapse (theatre, nurse tasks, doctor draft review) | 6 (R18) |
| P4 Record & evidence: replaces three cards, filters, 40 px thumbnails, newest first; timeline stays as History | 6 (R6, R17) |
| P5 clinic strip photo with Type instead | 8 (R11–R13) |
| P5 handover on the care chart | 8 (R21) |
| P5 record-bot answers visible to the doctor | 8 |
| P5 alerts with Inspect | 8 |
| P5 day plan Inspect | 8 |
| P5 patient strip photo onto the reader | 8 (R11) |
| P6 orders as sentences, chip edits a field, Edit all fields, words ↔ chips | 4, 7 |
| P7 AI activity: staff nav, story strip, clickable pipelines, activity list into the Inspector, model cards below, empty state | 9 (R19, R22) |
| P8 truthful home next step; staff and patient nudge wording | 1 (R14, R15) |
| §6 tests: five-second test, coverage, steps, demo, 390 px sweep | 10 |
| §7 constraints | Global Constraints |
| F1–F12 | F1 → 2–5; F2 → 3–5; F3 → 8; F4 → 8; F5 → 6; F6 → 6; F7 → 7; F8 → 1; F9 → 1; F10 → 9; F11 → 8; F12 → 5, 8 |

**Name consistency.** Each name is defined once:
- Task 1: `moments`, `line_of`, `visual_finding`, `says_staff`, `nudgeText`, `unseen_by_doctor`.
- Task 2: `chipFor`, `heardChip`, `draftChip`, `statusLabel`, `momentFor`, `findingFor`, `canInspect`, `resolveMoment`, `readInspect`, `tabsFor`, `modelRows`, `recordLine`, `stepFrame`, `useInspector`, `openInspector`, `closeInspector`, `KIND_VIEWS`, `AiMoment`.
- Task 3: `regionFieldLine`, `REGION_FIELD`, `isFocusRegion`, `RawOutput`.
- Task 4: `order_spans`, `orderSentence`, `sentenceText`, `rowItem`, `obsLabel`, `PROOF_WORD`, `segments`, `fieldDiffs`, `FIELD_LABEL`, `HEARD`, `HEARD_ONLY`.
- Task 5: `ruleCards`.
- Task 6: `FILTERS`, `filterMoments`, `lastSigned`, `RecordEvidence`.
- Task 7: `chipEdit`, `CHIP_INPUT`, `OrderSentence`.
- Task 8: `StripPhoto`, `HandoverCard`, `RecordBotItem`.
- Task 9: `activityRows`, `storyCounts`, `storyLine`, `PIPELINE_KIND`, `emptyLine`, `ActivityList`, `ModelCards`.

**Demo changes per task:**

| Task | Beats touched |
|---|---|
| 1 | `das-strip.expect` (staff wording) |
| 3 | `kumar-tray.expect` drops "Prepared demo result" |
| 4 | `HEARD`, `HEARD_ONLY`; `kumar-orders`, `kumar-paracetamol`, `kumar-discharge`, `kumar-review` |
| 5 | `das-ask.expect`, `das-ask.keyed` |
| 6 | `kumar-tray` (Inspect click, expect, say); `kumar-count` (Close click) |
| 7 | `kumar-orders.expect` +1 |
| 8 | `das-strip` clicks, files, say, keyed; `MEDIA` +1 |
| 9 | `ai` clicks, expect, say; Summary phrase |
| 2, 10 | None |

Beats stay 32; roles 58/58/58 s; film 200 s.

**Deliberately left out:**
- The older screens (`/ot`, `/opd`, `/morning`, `/count`, `/case`, `/nurse`): `screens/NurseHandover.jsx` stays as it is.
- The operations agent and its `agent` kind.
- Word spans for discharge, task and answer dictation (R9).
- Audio length on voice findings (R23).
- Tracking who saw a record-bot answer: the Record tab shows asked and answered only.

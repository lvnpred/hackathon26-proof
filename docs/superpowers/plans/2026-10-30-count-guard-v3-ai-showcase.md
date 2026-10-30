# Count Guard v3 AI Showcase (Parts 1–2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task stands alone: read the Global Constraints, the Rulings, the Shared Contracts and your own task before you start. Do not read other tasks for instructions; the Shared Contracts section holds everything two tasks share.

**Goal:** Patients and staff see full two-way threads (Part 1). An "AI at work" dashboard opens the demo, and one evidence viewer shows boxes, values read and a plain explanation for every image or video a Muse model touched. Values read become prefilled, confirmable values in the action that uses them, and the brown-bag medicines get a day plan (Part 2). `make demo-check MODEL_API_KEY=` stays green after every task.

**Architecture:**
- Every model result written to the record carries one `calls` list: `[{model, model_id, source, ms}]`. A photo read is two calls (SAM finds the regions, Spark reads them, D1(b)).
- Detections and regions are too big for an event, so they live in a JSON **sidecar** next to the media, `journey_media/<episode>/<evidence_id>.evidence.json`. The event holds `evidence_id`. One GET route returns a sidecar, with the image URLs and the events that cite it.
- The frontend puts every decision in pure, tested helpers (`thread.js`, `evidence.js`, `ai.js`, `capture.js`, `brownbag.js`). JSX only renders what they return. One `Evidence` component draws boxes on a canvas from normalised bboxes, and `EvidenceThumb` is its 48 px form.
- A pure `ai_summary.py` folds the `calls` of the roster's events into four model cards and a recent-events list.

**Tech Stack:** FastAPI + pytest (backend). React 18 + Vite + react-router (frontend). `node --test` for care and demo tests. A playwright-core demo runner. Pillow + ffmpeg for the stand-in media in `eval/`.

**Spec (binding):** `docs/superpowers/specs/2026-10-30-count-guard-v3-ai-showcase-design.md`, Parts 1–2 (Part 3 is estimate only). Owner decisions: D1(b) SAM finds regions and Spark reads them; D2 re-record the fixtures live, once; D3 a 20 s opening demo beat.

**Builds on:** the UX mockups M1–M7 (`2026-10-30-count-guard-v3-ux-mockups.md`), already on `count-guard-v3`. Use the current code, not the outline this plan replaces: `NextCard`, `History` (fold), `NurseTasks` (row mics), `TheatreChecklist` + `theatre.js` (`canRecord`), `AskInbox` (cards), `MyPatients` + `patientGroups.js`, `Today.jsx` + `today.js`, `DemoDock` + `dock.js`, `names.js` (`displayName`, `shortName`, `displayView`).

All paths are relative to `count-guard/` unless they start with `docs/`. The demo document is `docs/demo/count-guard-v2-video-script.md` at the repo root. Its per-beat block has a heading `` #### `id` · m:ss · role · N s ``, a `Clicks:` line (numbered, mirrors `clicks`), an `On screen:` line (backticked, mirrors `expect`) and a `> ` narration line (mirrors `say`). Its "Keyed" table has one row per model beat (mirrors `keyed`). `frontend/scripts/demo/doc.test.mjs` checks ids, expected strings, narration, media names and switch names.

## Global Constraints

From the spec, verbatim in substance:

- Records only, no medical advice. The no-advice regex `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i` (`frontend/scripts/demo/beats.mjs:3`, `backend/tests/test_flow_states.py:9`) applies to **all new copy and all model text shown**. Every task's tests assert it on that task's new strings.
- Never call live models in tests or `make demo-check`. Live calls happen only in the one-time fixture recording (Task 5) and the owner's live demo. Tests fake adapters with `monkeypatch` and keep the `no_network` fixture (`backend/tests/test_p3_video.py:20`).
- Until the owner runs Task 5, fixtures are hand-made and marked `"handmade": true`. The UI labels them **Sample**.
- Files stay under 500 lines. Validate input at API boundaries: an `evidence_id` must belong to the episode, and the brown-bag mark route is doctor-only.
- Never touch ports 8100/5173 in checks. `make demo-check` starts its own servers on 8200/5273.
- `make demo-check MODEL_API_KEY=` stays green after **every** task. A task that changes a selector, a click or a visible string updates `frontend/scripts/demo/beats.mjs`, `steps.mjs`, `helpers.mjs` and the demo document in the same commit.

House rules for this plan:
- Test baselines on `count-guard-v3` at `55e93a8`: backend 384, care 187, demo 36. Another agent may land fixes on the branch, so each task states "at least" counts above whatever you measure first.
- Commit with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Add no Co-Authored-By line. Never push.
- How the demo checks text: `waitText` reads `document.querySelector(".app").innerText` (`frontend/scripts/demo/helpers.mjs:6`). Text inside a closed `<details>`, a `display:none` node or a `<canvas>` is **not** in `innerText`. Every expected string must stay in visible DOM text.

Commands (run from `count-guard/`; the venv is `count-guard/.venv`):
- Backend: `.venv/bin/python -m pytest backend/tests -q`
- Care: `cd frontend && node --test src/care/*.test.js`
- Demo unit tests: `cd frontend && node --test scripts/demo/*.test.mjs`
- Build: `cd frontend && npm run build`
- Full demo: `make demo-check MODEL_API_KEY=`. Use `CG_DEMO_UNTIL=<beat id>` to stop before a beat while you debug.

## Rulings on spec ambiguities

These rulings bind all tasks.

| # | Question | Ruling |
|---|---|---|
| R1 | The outline says `detections_id` in one place and `evidence_id` in another. | One term: `evidence_id`, everywhere (events, sidecar, routes, props). |
| R2 | The spec says "add `ms` and `model` to every model-result payload", but a photo read is two models (D1(b)). | Every model-result payload gets a list `calls: [{model, model_id, source, ms}]`. `model` is the card key (`voice`, `spark`, `sam`, `spark-open`); `model_id` is the settings value; `source` is the existing source word. The old scalar `source` fields stay for the existing labels. |
| R3 | Latency of a prepared result | A prepared call carries the fixture's recorded `ms` when the fixture has one (after Task 5), else `null`. Medians ignore `null`. |
| R4 | A voice result confirmed in a later request (task done by voice, the doctor's spoken answer) | The later write records the call with the source the server named (`heard_by`, checked against `HEARERS`) and `ms: null`. Latency is only measured where the call and the write share one request. |
| R5 | Is "rules" a Spark call? | No. `rules` (no key) writes no call. `rules (model reply not usable)` is a Spark call in mode `failed`. `source: "none"` (nothing read, no fixture) writes no call. |
| R6 | Mode words | `muse-voice-transcribe`, `muse-spark-1.3`, `sam-3.1` → `live`; `prepared` → `prepared`; `prepared (live call failed)`, `failed`, `unreadable`, `rules (model reply not usable)` → `failed`. A sidecar or fixture with `handmade: true` shows **Sample** in place of the mode. |
| R7 | What does the dashboard count? | Model calls written to the record of the roster patients, whose ids the page passes (`?ids=`), as `/journey/staff/doctor-status` does. Not every episode in the database. "Try sample" writes nothing and is not counted. |
| R8 | Muse Spark Open has no call site on the ward (it is used only by the v1 camera case screens). | Its card shows its role, `0` calls and the mode from `spark_open_configured`. "Try sample" shows a fixture reply (`prepared/spark-open-sample.json`, handmade). The live ward agent is Part 3. |
| R9 | What does "Try sample" run? | `POST /journey/ai/try/{model}` on an allow-listed bundled asset, through the same `live.py` seam: SAM → `eval/p3/tray-hernia.png` (photo check against the hernia tray plan); Spark → `eval/p2/monitor-88-54.png` (monitor read, D1(b)); Voice → `eval/p2/kumar-orders.wav`; Spark Open → the fixture text. It writes no event. SAM and Spark open the viewer; Voice and Spark Open show their text in the card. |
| R10 | A fixture stem is shared by a clip and its still (`tray-hernia.mp4`, `tray-hernia.png`). | A fixture may hold `frames` (the clip) and `stills` (the still, one frame with `t: null`). `segment_clip` reads `frames`; `segment_photos` reads `stills`. |
| R11 | Video clips are not kept (D11), so there is no image for most sampled frames. | The viewer's images are the kept frames (≤ 6, `video.frame_times`). Boxes are the sidecar frame with the same `t`. The per-concept sparkline uses every sidecar frame (≤ 120). The cap keeps each concept's best frame. |
| R12 | "Raw output" for SAM is megabytes of mask tokens. | The sidecar keeps SAM's parsed box records without `mask_token`, and Spark's reply text verbatim. If `raw` is over 200 000 characters as JSON, it is replaced by `{"note": "Raw output over 200 KB; not kept."}`. |
| R13 | Re-recording live (D2) may change the demo story: drawn stand-in clips give poor live SAM results (video script, P3-R24). | `eval/record_fixtures.py` overwrites a fixture only when the live counts (or values read) equal the fixture's. Otherwise it writes `prepared/<stem>.live.json` (never loaded: `prepared()` reads `<stem>.json` only) and exits 2 with the differences. The owner decides. |
| R14 | Which SAM concepts find reader regions? | One constant `READER_CONCEPTS = {"strip": ["blister strip"], "monitor": ["digital display"]}` in `journey/regions.py`. Task 5 prints how many regions each concept found, so the owner can change it. |
| R15 | Where does the nurse capture a monitor photo? | In the existing "Confirm task" panel. Obs rows get a quiet button "Read from monitor photo" that opens it. Its "Add photo" reads the monitor and fills **only empty** fields. The panel keeps its "Confirm" button (beats `iyer-bp` and `iyer-recheck` click it); the inline row keeps "Save readings". |
| R16 | Where does a task completion get its `evidence_id`? | From the server: `complete_task` copies `evidence_id` from the `proof.checked` of the `proof_id`. The client never sends it. Only `count.closing` takes an `evidence_id` from the client. |
| R17 | Who decides `read` versus `saved`? | The server, from the evidence holder (`values_read` of the proof check, `count` of the swab camera count). The client sends only what is saved. |
| R18 | The swab camera count (§2.5) | `POST /video` gains `check: "swabs"` (one clip or 1–6 photos of the returned swabs, concept `gauze swab`). It writes `swabs.counted`. "Count by camera" uploads in the chart instead of navigating to `/count`. The v1 live camera screen stays under Older screens. A switch `SWABS_LIVE` mirrors `TRAY_LIVE`. |
| R19 | The spec says `to` of `record` or `doctor`. Events say `bot`. | Keep `bot`. `ask_view` already returns record-bot asks; a rename would break `inboxItems` and tests for no gain. |
| R20 | Statuses the spec does not word | Record ask not found: `Not in your record`. Medicines photo: `Checked against your prescription`. Check-in not seen: `Sent HH:MM · not seen yet`. |
| R21 | Unread | Doctor answers, healing-photo decisions and brown-bag marks with `at_ms` greater than `lastOpenedMs` (demo-clock ms, stored per episode in `localStorage` key `cg-ask-opened:<episodeId>`, written when Ask opens). Never opened means every such answer is unread. |
| R22 | Who sends "Seen"? | The nurse's chart, on open: one `POST …/checkins/{id}/seen` per check-in this nurse has not seen. Idempotent per nurse and check-in on the server. |
| R23 | The staff side | Every staff role sees the whole conversation (open and answered). Only the doctor can answer. The patient's own words stay hidden from non-doctors (`questionText`, `noteText`). Answered items sit in a `<details>` "Answered (N)", **open when nothing is waiting**, so a just-answered item stays visible (beat `kumar-review`). |
| R24 | The patient's Ask page | "My messages" replaces the answer lists inside the Ask cards. The cards keep their forms only. |
| R25 | Where is the day plan? | In Today's "My medicines" fold (its M6 home), replacing the schedule table. Not on My care. |
| R26 | An unreadable dose code (not `a-b-c`, not SOS) | It goes to an "As written" list. Its text is the doctor's dose code, then timing, days and note joined by `"; "`. Only `SOS`, `PRN` and `as needed` (any case) go to "As needed". |
| R27 | The record bot's medicine rule | It runs before the model. A known prescription key in the question (1- and 2-word windows, `key_of` equality) → answer `Here is what your record says.` with that prescription's record line(s) as sources (the line holds `schedule_text(row)` verbatim). A key read from the patient's medicines photo but not prescribed → `"<Name> is not on your prescription. Ask Dr. Rao."`, `found: false`. Else the existing flow. No model call for a matched medicine. |
| R28 | "Restricted to the doctor" with no login in the app | The mark route checks `by`: it must start with `Dr. `. Otherwise 403. |
| R29 | Nurse capture of medicines at admission | Deferred. "Medicines from home" shows on the doctor and nurse chart in every state once a medicines photo exists. The capture route stays the patient's. |
| R30 | The prefilled "Ask Dr. Rao" question would contain "take". | `About <read> from my medicines photo: it is not on my prescription.` |
| R31 | Where is the dashboard linked? | A link "AI at work" in the demo dock, for every role. It is a showcase view, not a ward tool. |
| R32 | Modal or inline viewer? | Inline `<section aria-label="Evidence">`, so its table and sentences are in `innerText`. |
| R33 | Brown-bag marks | The latest mark per (read, row) stands. They are record marks, not orders. |
| R34 | The opening beat (D3) | Beat `ai`, path `intro`, role `none`, 20 s, second after `intro`. Beats become 32; film 200 s (3:20); roles stay 58 s each. |
| R35 | The obs value source (§2.5 "source: muse-spark-1.3") | `obs.recorded` keeps `by` (the nurse) and gains `evidence_id` and `source` copied from the proof check, only when the completion has evidence. |

## Shared Contracts

Defined once here. Tasks reference them by name.

**C1. Call** (Task 2): `{"model": "voice"|"spark"|"sam"|"spark-open", "model_id": str, "source": str, "ms": int | None}`. Built by `live.call_of(model, settings, source, ms)`. `model_id` is `settings.voice_model`, `spark_model`, `sam_model` or `spark_open_model`.

**C2. Mode** (Task 2): `live.mode_of(source) -> "live" | "prepared" | "failed" | None` per R6 (`None` for `rules`, `typed`, `none`, `""`). The frontend twin is `evidence.js` `modeWord(source, handmade)`.

**C3. Model names** (frontend `evidence.js` `MODEL_NAME`, backend `ai_summary.MODELS`): `voice` "Muse Voice", `spark` "Muse Spark 1.3", `sam` "SAM 3.1", `spark-open` "Muse Spark Open".

**C4. Sidecar** (Task 3; Task 4 adds `regions`), file `<data_dir>/journey_media/<episode_id>/<evidence_id>.evidence.json`:

```json
{
  "id": "<32 hex>",
  "kind": "tray | setup | swabs | monitor | strip | medicines",
  "media": "video | photos",
  "images": [{"photo_id": "<event id>", "t": 1.5, "index": 0}],
  "frames": [{"t": 0.5, "index": 1, "objects": [{"id": "1", "label": "retractor", "bbox": [0.1, 0.2, 0.08, 0.05], "score": 0.91, "kept": true}]}],
  "regions": [{"bbox": [0.1, 0.2, 0.3, 0.1] , "label": "SBP", "value": "88", "row": null}],
  "expected": [{"concept": "retractor", "planned": 4}],
  "min_score": 0.45,
  "fps": 2,
  "calls": [],
  "raw": {"sam": [], "spark": ""},
  "handmade": false
}
```

`frames` is `null` for photo reads; `regions` is `null` for counts; `fps` is `null` for photos. `bbox` is normalised `[x, y, w, h]`, rounded to 4 places.

**C5. Evidence GET** (Task 3; Task 8 adds `read`/`saved`): `GET /journey/episodes/{episode_id}/evidence/{evidence_id}` returns the sidecar plus `images[].url` (`/journey/episodes/{eid}/photos/{photo_id}`) and `cited_by: [{event_id, type, when, by}]` (every event of this episode whose payload `evidence_id` equals the id, oldest first). 404 when the id is not 32 lower-case hex, when no event of this episode holds it, or when the file is missing.

**C6. Fixture schema** (Task 3 writes it, Task 4 extends, Task 5 records): a `journey/prepared/<stem>.json` may hold `transcript`, `text`, `detections`, `frames`, `stills`, `regions`, `raw`, `ms`, `model_id`, `handmade`. No other keys. `detections` stays: `eval/p3/make_clips.py` draws the stand-in clips from it.

**C7. Copy** used by more than one task (each passes the no-advice regex):
- Viewer: `Expected`, `Seen`, `Status`, `Why:`, `Raw output`, `Show ignored`, `Captured to record:`, `Nothing found above confidence 0.45.`
- Chips: `SAM 3.1 · live`, `· prepared`, `· failed`, `· Sample`.
- Dashboard: `AI at work`, `Try sample`, `Recent AI events`, `No calls yet`, `No timing yet`.

## Review Focus

| # | Failure mode the spec implies | Pinned by |
|---|---|---|
| 1 | A clip or photo with 0 detections, or every detection under the threshold: the viewer shows the image with no boxes and the sentence "Nothing found above confidence 0.45.", never an error. | Task 3 `test_frames_from_empty_and_all_low`; Task 6 `explain` "nothing found" test |
| 2 | SAM regions and Spark values differ in number: an unpaired region reads "not read"; an unpaired value is listed with no box; a failed SAM call still saves the values. | Task 4 `test_pair_more_regions`, `test_pair_more_values`, `test_read_photo_sam_fails_values_kept`; Task 6 `regionLabel` test |
| 3 | An event from before this change has no sidecar: the check still renders its count table, and the GET is a 404, not a 500. | Task 3 `test_old_check_without_sidecar_still_renders`, `test_evidence_get_404s`; Task 6 `evidenceView(null, check)` test |
| 4 | Boundary validation: an `evidence_id` from another episode, from another kind of check, unknown, or malformed is refused (422); a non-doctor brown-bag mark is refused (403). | Task 8 `test_closing_refuses_foreign_evidence`; Task 9 `test_mark_is_doctor_only` |
| 5 | Medicine questions: "Amlo" never matches Amlodipine (key equality, not substring); a prescribed medicine is answered by quoting its prescription row verbatim; a photographed, unprescribed medicine gets the fixed sentence; no generated sentence matches the advice regex. | Task 9 `test_medicine_rule_is_key_equality`, `test_medicine_rule_quotes_the_row`, `test_medicine_rule_not_prescribed`, `test_brownbag_copy_has_no_advice` |

---

### Task 1: Two-way threads (Part 1) · 1.5 d (12 h)

**Files:**
- Modify: `backend/app/journey/ask.py` (`ask_view` adds `checkins`), `backend/app/journey/ask_api.py` (seen route), `backend/app/journey/stories.py` (`plain` and `patient_line` for `checkin.seen`)
- Create: `backend/tests/test_threads.py`, `frontend/src/care/thread.js`, `frontend/src/care/thread.test.js`, `frontend/src/care/Thread.jsx`
- Modify: `frontend/src/care/Ask.jsx`, `AskCards.jsx`, `AskInbox.jsx`, `askText.js` (+ `askText.test.js`), `Today.jsx`, `CareShell.jsx`, `Chart.jsx`, `care.css`, `styles.test.js`

**Interfaces:**
- Backend:
  - `ask_view(events)` adds `"checkins": [{"id", "at_ms", "day", "feels", "signs", "note", "seen": [{"by", "at_ms"}]}]`, oldest first. `seen` holds the first `checkin.seen` per `by`, in order.
  - `POST /journey/episodes/{episode_id}/checkins/{checkin_id}/seen`, body `SeenCheckinIn(At)`: `by: str` (1–80). 404 `Check-in not found` unless `checkin_id` is a `checkin.recorded` event of this episode. When this `by` already saw it, write nothing and return the view (200). Else append `checkin.seen {"checkin_id", "by"}` and return the view.
  - `plain(checkin.seen)`: `f"{p['by']} saw a check-in."`. `patient_line`: `f"{short_name(p['by'])} saw your check-in."`
- Frontend `thread.js` (pure):
  - `threadItems(view) -> Item[]`, newest first by `at_ms`, ties by kind order `checkin, medicines, photo, doctor, record`. `Item = { kind: "record"|"doctor"|"photo"|"medicines"|"checkin", id, atMs, title, said, answer, raw }`:
    - `record` from questions with `to === "bot"`; title `Question to your record`; `said` the question text.
    - `doctor` from questions with `to === "doctor"`; title `Question to Dr. Rao`.
    - `photo` from `ask.reviews`; title `Healing photo`; `said` the note.
    - `medicines` from `ask.medicines`; title `Medicines photo`.
    - `checkin` from `ask.checkins`; title `` `Check-in day ${day}` ``; `said` `feels`, then `; ` and the signs joined by `, ` when any.
  - `threadStatus(item, nowMs) -> string`:

    | Item | Condition | Wording |
    |---|---|---|
    | doctor, photo | no answer | `` `Waiting for Dr. Rao · ${waitedText(nowMs - atMs)}` `` |
    | doctor, photo | answered | `` `Answered ${hhmm(answer.at_ms)}` `` |
    | record | `answer.found` | `Answered from your record` |
    | record | not found | `Not in your record` (R20) |
    | medicines | always | `Checked against your prescription` (R20) |
    | checkin | seen | `` `Seen by ${displayName(seen[0].by)}` `` |
    | checkin | not seen | `` `Sent ${hhmm(atMs)} · not seen yet` `` (R20) |
  - `unreadCount(view, lastOpenedMs) -> number` and `unreadLine(view, lastOpenedMs) -> string` (R21). Counted: doctor answers (`answer.source === "doctor"`), review decisions, and (Task 9) brown-bag marks, each with `at_ms > lastOpenedMs`; `lastOpenedMs == null` counts all. `unreadLine` is `Dr. Rao answered your question` when an unread doctor answer exists, else `Dr. Rao reviewed your healing photo`, else `Dr. Rao marked your medicines photo`, else `""`.
  - `unseenCheckins(view, by) -> string[]`: ids of check-ins with no `seen` entry whose `by` equals `by`.
  - `readOpened(episodeId) -> number | null` and `markOpened(episodeId, ms)`: `localStorage` key `cg-ask-opened:<episodeId>`, each wrapped in `try/catch` (null on any failure).
- `askText.js`:
  - `inboxItems(view, role, nowMs)`: drop the role filter (R23). Every role gets open and answered items, in today's order (open oldest first, then answered oldest first).
  - Add `inboxGroups(items) -> { open, answered }` and `checkinLine(c) -> string`: `` `Day ${c.day} check-in: ${c.feels}; ${signs || "no listed signs"} · ${seen ? `Seen by ${displayName(first.by)}` : "not seen yet"}` ``.
- `<Thread view nowMs onAskDoctor />` renders `<section className="card" aria-label="My messages">` with `<p className="label">My messages</p>` and `<ul className="thread">`. Each row is `<li className="thread-row" data-line={id}>`: the title, a `<span className="pill">{status}</span>`, the quoted `said`, then the answer:
  - record: the answer text (`answer.text || NOT_FOUND`), the quoted `sources` as `<ul><li><q>…</q></li></ul>`, and `answerByLine(answer)`; when not found, the button `Ask Dr. Rao` calls `onAskDoctor(text)`.
  - doctor: the answer text and `answerByLine`.
  - photo: a 96 px thumbnail, then `label` (and ` · note`) and the doctor's name.
  - medicines: one `<li>` per row with `medicineLine(row)` (a flagged row as `pill sun`), then `why` and `(sourceLabel(source))`.
  - checkin: nothing more than the status.
  - Empty: `<p className="empty small">Nothing sent yet. Ask your record or Dr. Rao above.</p>`
- `Ask.jsx` renders the forms (`BotCard`, `DoctorCard`, `ReviewCard`, `MedicinesCard`), then `<Thread>`, and calls `markOpened(patient.id, ward.nowMs)` in a `useEffect` keyed on `patient.id`. `AskCards.jsx` drops every answer list and result block (R24), keeping forms, hints and Faults; `BotCard` keeps `onAskDoctor` only to pass it on.
- `AskInbox.jsx` ("Conversation with the patient"): the header line as now; open cards; then `<details className="answered-fold" key={open.length ? "some" : "none"} open={open.length === 0}>` with `<summary>Answered ({n})</summary>` holding answered cards and one `<p className="small">{checkinLine(c)}</p>` per check-in (R23). Return `null` only when there are no items and no check-ins.
- `Chart.jsx`: when `ward.role === "nurse"`, a `useEffect` on `[episodeId, view?.ask?.checkins?.length]` posts `/checkins/{id}/seen` with `by: "Nurse Meena (synthetic)"` (the ward nurse, `NurseActions.jsx:6`) for each `unseenCheckins` id, one after the other.
- `Today.jsx`: the status card adds `<p className="note">{unreadLine(view, readOpened(patient.id))}</p>` when the line is not empty.
- `CareShell.jsx`: the patient's `Ask` tab gets `<span className="dot" aria-hidden="true" />` when `unreadCount(...) > 0`. The span holds no text, so the link name stays "Ask" (`helpers.tab`).

- [ ] **Step 1: Write the failing backend tests** (`backend/tests/test_threads.py`; reuse `_client`, `_seed` from `tests.test_care_demo`, `_home` from `tests.test_p4_ask`, `_url` from `tests.test_flow_tasks`, keep the `no_network` fixture):

```python
NURSE, OTHER = "Nurse Meena (synthetic)", "Nurse Asha (synthetic)"

def _kumar_home(tmp_path):
    client = _client(tmp_path)
    eid = {p["bed"]: p["id"] for p in _seed(client)}["4"]
    _home(client, eid)
    return client, eid

def _checkin(client, eid):
    body = {"day": 3, "feels": "Better", "signs": [], "note": "", "at_ms": 5000}
    assert client.post(_url(eid, "checkin"), json=body).status_code == 200
    return client.get(f"/journey/episodes/{eid}").json()["ask"]["checkins"][0]["id"]

def test_checkin_seen_is_idempotent_per_nurse(tmp_path):
    client, eid = _kumar_home(tmp_path)
    cid = _checkin(client, eid)
    for _ in range(2):
        assert client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": NURSE, "at_ms": 6000}).status_code == 200
    client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": OTHER, "at_ms": 7000})
    seen = client.get(f"/journey/episodes/{eid}").json()["ask"]["checkins"][0]["seen"]
    assert seen == [{"by": NURSE, "at_ms": 6000}, {"by": OTHER, "at_ms": 7000}]
    rows = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "checkin.seen"]
    assert len(rows) == 2

def test_checkin_seen_unknown_or_foreign_is_404(tmp_path):
    client, eid = _kumar_home(tmp_path)
    other = {p["bed"]: p["id"] for p in _seed(client)}["7"]
    cid = _checkin(client, eid)
    assert client.post(_url(other, f"checkins/{cid}/seen"), json={"by": NURSE}).status_code == 404
    assert client.post(_url(eid, "checkins/nope/seen"), json={"by": NURSE}).status_code == 404
    assert client.post(_url(eid, f"checkins/{cid}/seen"), json={"by": ""}).status_code == 422

def test_thread_view_holds_record_and_doctor_asks(tmp_path):
    client, eid = _kumar_home(tmp_path)
    client.post(_url(eid, "ask/bot"), json={"text": "When is my wound check?", "at_ms": 1000})
    client.post(_url(eid, "ask/doctor"), json={"text": "Is the swelling normal?", "at_ms": 2000})
    ask = client.get(f"/journey/episodes/{eid}").json()["ask"]
    assert [(q["to"], q["answer"] is not None) for q in ask["questions"]] == [("bot", True), ("doctor", False)]

def test_seen_lines_have_no_advice(tmp_path):
    from app.journey.stories import plain, patient_line
    e = {"event_type": "checkin.seen", "payload": {"checkin_id": "c", "by": NURSE}}
    for s in (plain(e), patient_line(e, {})):
        assert not ADVICE.search(s)
```

- [ ] **Step 2: Write the failing frontend tests** (`thread.test.js`; update `askText.test.js`):

```js
const M = 60_000;
const ok = { text: "Here is what your record says.", found: true, source: "rules", sources: [{ id: "L1", text: "Prescription from Dr. A. Rao: Tab. Amlodipine 5 mg — 1 in the morning." }], at_ms: M, by: "Record bot" };
const view = { ask: {
  questions: [
    { id: "b1", to: "bot", text: "When do I take amlodipine?", at_ms: M, answer: ok },
    { id: "d1", to: "doctor", text: "Is the swelling normal?", at_ms: 2 * M, answer: null },
    { id: "d0", to: "doctor", text: "Old", at_ms: 0, answer: { text: "Yes.", by: "Dr. A. Rao", via: "voice", source: "doctor", at_ms: 64 * M } },
  ],
  reviews: [{ id: "r1", at_ms: 3 * M, note: "Day 3", photo: { url: "/p" }, answer: null }],
  medicines: [],
  checkins: [
    { id: "c1", at_ms: 4 * M, day: 3, feels: "Better", signs: [], seen: [{ by: "Nurse Meena (synthetic)", at_ms: 5 * M }] },
    { id: "c2", at_ms: 6 * M, day: 4, feels: "Same", signs: ["Redness"], seen: [] },
  ],
} };
const at = (id) => threadItems(view).find((i) => i.id === id);
test("one row per thing sent, newest first", () => {
  assert.deepEqual(threadItems(view).map((i) => i.id), ["c2", "c1", "r1", "d1", "b1", "d0"]);
  assert.deepEqual(threadItems({}), []);
});
test("status wording", () => {
  assert.equal(threadStatus(at("d1"), 8 * M), "Waiting for Dr. Rao · 6 min");
  assert.equal(threadStatus(at("r1"), 8 * M), "Waiting for Dr. Rao · 5 min");
  assert.equal(threadStatus(at("d0"), 8 * M), "Answered 10:04");
  assert.equal(threadStatus(at("b1"), 8 * M), "Answered from your record");
  assert.equal(threadStatus({ ...at("b1"), answer: { ...ok, found: false } }, 8 * M), "Not in your record");
  assert.equal(threadStatus(at("c1"), 8 * M), "Seen by Nurse Meena");
  assert.equal(threadStatus(at("c2"), 8 * M), "Sent 09:06 · not seen yet");
  assert.equal(at("c2").said, "Same; Redness");
});
test("unread counts answers after the last open", () => {
  assert.equal(unreadCount(view, null), 1);
  assert.equal(unreadCount(view, 64 * M), 0);
  assert.equal(unreadLine(view, 63 * M), "Dr. Rao answered your question");
  assert.equal(unreadLine(view, 64 * M), "");
});
test("unseenCheckins is per nurse", () => {
  assert.deepEqual(unseenCheckins(view, "Nurse Meena (synthetic)"), ["c2"]);
  assert.deepEqual(unseenCheckins(view, "Nurse Asha (synthetic)"), ["c1", "c2"]);
});
test("thread copy has no advice words", () => {
  for (const s of ["My messages", "Question to your record", "Question to Dr. Rao", "Checked against your prescription", "Not in your record", "Sent 09:06 · not seen yet", "Nothing sent yet. Ask your record or Dr. Rao above.", "Dr. Rao reviewed your healing photo", "Dr. Rao marked your medicines photo", "Answered (2)"]) assert.doesNotMatch(s, ADVICE);
});
// askText.test.js: replace "others see answered only" with
//   assert.deepEqual(inboxItems(v, "nurse", 30 * M).map((i) => i.id), ["q1", "r1", "q2", "q0"]);
//   assert.deepEqual(inboxGroups(inboxItems(v, "doctor", 30 * M)).answered.map((i) => i.id), ["q0"]);
//   assert.equal(checkinLine({ day: 3, feels: "Better", signs: [], seen: [] }), "Day 3 check-in: Better; no listed signs · not seen yet");
```

Add to `styles.test.js`: `assert.match(css, /\.thread-row/)` and `assert.match(css, /\.dot \{/)`.

- [ ] **Step 3: Run** `.venv/bin/python -m pytest backend/tests/test_threads.py -q` and `cd frontend && node --test src/care/thread.test.js src/care/askText.test.js src/care/styles.test.js`. Expected: FAIL (`KeyError: 'checkins'`, module not found).

- [ ] **Step 4: Implement** the backend, then the helpers, then the components. CSS: `.thread { list-style: none; padding: 0 }`, `.thread-row { border-top: 1px solid var(--line); padding: 8px 0 }`, `.dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: var(--sun); margin-left: 4px }`. Confirm the token names exist in `styles.css` first.

- [ ] **Step 5: Demo.** No click changes. Check that these strings stay visible after the lists move into the thread:
  - `das-ask`: "Here is what your record says.", "Amlodipine", "Rules (no model)" (record row).
  - `kumar-ask`: "Waiting for Dr. Rao" (doctor row status, now "Waiting for Dr. Rao · 2 min").
  - `kumar-review`: "No visit needed" and "by voice · Prepared demo result" (answered fold, open because nothing waits).
  - `kumar-answers`: "The wound looks as expected for day 3.", "No visit needed".
  - `iyer-meds`: "Ibuprofen", "Pantoprazole 40 mg:" (medicines row).
  The regions `Ask Dr. Rao`, `Ask your record`, `Healing photo` and `Medicines photo` stay the form cards; thread rows are list items, not regions.

- [ ] **Step 6: Run** every suite, the build and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 388, care ≥ 192, demo 36, the demo green at 31 beats, 58/58/58.

- [ ] **Step 7: Commit** (`backend frontend/src`). Message: "Count Guard: patients see every question, photo and check-in they sent, with its status and answer".

---

### Task 2: A `calls` list on every model result · 0.5 d (4 h)

**Files:**
- Modify: `backend/app/journey/live.py`, `media_api.py` (`_heard`, `_structure`, `_dictate`, `_check_photo`), `ask_api.py` (`ask_bot`, `answer_question`, `ask_medicines`), `video_api.py` (payload), `flow_api.py` (`DoneIn.heard_by`), `tasks.py` (`complete_task` stores `heard_by`, `calls`), `handover.py` (`draft`)
- Modify: `frontend/src/care/drafts.js` (`doneBody` adds `heard_by`), `drafts.test.js`, `TaskProof.jsx` (passes `session.heardBy`)
- Test: `backend/tests/test_ai_calls.py`

**Interfaces:**
- Produces C1 and C2 in `live.py`:
  - `call_of(model, settings, source, ms) -> dict` (C1).
  - `mode_of(source) -> str | None` (R6).
  - `MODEL_IDS = {"voice": "voice_model", "spark": "spark_model", "sam": "sam_model", "spark-open": "spark_open_model"}` (attribute names on `Settings`).
  - `transcribe`, `read_photo`, `segment_clip`, `segment_photos` each return `"calls"`: one call per model asked. A live call measures `ms` with `time.monotonic()` around the adapter call only. A prepared result uses `found.get("ms")` (R3). `source: "none"` gives `[]` (R5).
  - `spark_text` is unchanged. `media_api._structure` returns `(result, source, calls)`: `[]` for `rules`, one spark call otherwise, `ms` timed around `live.spark_text`.
  - `_heard` returns `calls`: the transcribe calls; for typed text with an accepted `heard_by` in `HEARERS`, one voice call with `ms: None` (R4); else `[]`.
- Payloads that gain `calls`: `order.drafted`, `discharge.drafted` (heard + structure), `question.answered` (bot: structure; doctor: voice call from `heard_by` when `via == "voice"`, R4), `tray.checked`, `setup.checked`, `proof.checked`, `medicines.read`, `task.done` (voice call from `heard_by` when `via == "voice"`), `handover.drafted` (one spark call when the model was asked: `muse-spark-1.3` when used, `failed` when not, `ms` timed around `reword`).
- `DoneIn` gains `heard_by: str = Field("", max_length=40)`. `complete_task(..., heard_by="")` stores it only when it is in `media_api.HEARERS`.
- `drafts.doneBody` adds `heard_by` to the body when `via === "voice"` and a `heardBy` is given (new arg `heardBy`).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_ai_calls.py`; reuse `_no_key`, `_keyed` from `tests.test_p3_video`, keep `no_network`):

```python
def test_transcribe_carries_one_voice_call(tmp_path, monkeypatch):
    out = live.transcribe(_no_key(tmp_path), b"x", "kumar-orders.wav", "audio/wav")
    assert out["calls"] == [{"model": "voice", "model_id": "muse-voice-transcribe-1.0", "source": "prepared", "ms": None}]
    monkeypatch.setattr(live, "to_wav", lambda raw, kind: raw)
    monkeypatch.setattr(VoiceAdapter, "transcribe", lambda self, path, offset, kind: [{"text": "hi", "t0_ms": 0, "t1_ms": 1}])
    call = live.transcribe(_keyed(tmp_path), b"x", "a.wav", "audio/wav")["calls"][0]
    assert call["source"] == "muse-voice-transcribe" and isinstance(call["ms"], int) and call["ms"] >= 0

def test_nothing_read_is_no_call(tmp_path):
    assert live.segment_clip(_no_key(tmp_path), tmp_path / "x.mp4", "unknown.mp4", ["scissors"])["calls"] == []
    assert live.read_photo(_no_key(tmp_path), "strip", b"x", "unknown.png", "image/png")["calls"] == []

def test_mode_of():
    assert [live.mode_of(s) for s in ("sam-3.1", "prepared", live.FALLBACK, "failed", "rules (model reply not usable)", "rules", "typed")] == ["live", "prepared", "failed", "failed", "failed", None, None]

def test_dictated_orders_record_the_voice_call_and_no_rules_call(tmp_path):
    client, eid = _new(tmp_path)  # tests.test_flow_states
    r = client.post(f"/journey/episodes/{eid}/dictate/orders", data={"by": "Dr. A. Rao (synthetic)", "at_ms": "0"},
                    files={"file": ("kumar-orders.wav", b"RIFF0000WAVE", "audio/wav")})
    assert r.status_code == 200
    drafted = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "order.drafted"][-1]
    assert [(c["model"], c["source"]) for c in drafted["payload"]["calls"]] == [("voice", "prepared")]

def test_task_done_by_voice_records_heard_by(tmp_path):
    # sign a dose task, then POST /tasks/{id}/done with via="voice", transcript="x", heard_by="prepared"
    # assert task.done payload heard_by == "prepared" and calls == [{"model": "voice", ..., "source": "prepared", "ms": None}]
    # and heard_by="made-up" stores "" with calls == []
```

In `drafts.test.js`: `doneBody({ task, via: "voice", transcript: "x", heardBy: "prepared" }).body.heard_by === "prepared"`; with `via: "tap"` there is no `heard_by` key.

- [ ] **Step 2: Run** the new tests. Expected: FAIL (`KeyError: 'calls'`).
- [ ] **Step 3: Implement.** Keep every existing `source` value and label unchanged; the existing tests must stay green.
- [ ] **Step 4: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 393, care ≥ 193, the demo unchanged and green.
- [ ] **Step 5: Commit** (`backend frontend/src/care`). Message: "Count Guard: every model result names its model, source and time".

---

### Task 3: Detections kept as an evidence sidecar · 1 d (8 h)

**Files:**
- Create: `backend/app/journey/evidence.py`, `backend/app/journey/ai_api.py` (router `evidence_router`; Task 7 adds more routes), `backend/tests/test_evidence.py`, `backend/tests/test_prepared_schema.py`
- Modify: `backend/app/journey/video.py` (`frames_from`, `records_of`; `checks_view` adds `evidence_id`), `live.py` (`segment_clip`, `segment_photos` return `frames` and `raw`), `video_api.py` (write the sidecar), `backend/app/main.py` (include the router)
- Modify: `eval/p3/make_clips.py` (`boxes_for`, `--write-fixtures`), the fixtures `backend/app/journey/prepared/{tray-hernia,tray-hernia-full,saline-setup}.json`

**Interfaces:**
- `video.frames_from(records, fps, min_score, cap=120, photos=False) -> list[dict]` (C4 `frames`):
  - One frame per distinct `frame_index`, ordered by index. `t = round(index / fps, 3)`, or `None` with `photos`. `index` is the frame index.
  - Each object `{"id": object_id, "label", "bbox": [round(v, 4)…], "score", "kept": score is None or score >= min_score}`. Records whose label is `None` are dropped.
  - Over `cap` frames: keep every `ceil(n / cap)`-th frame, plus each concept's best frame (the frame `summarize` reports), then sort and trim to `cap`.
- `video.records_of(frames) -> list[dict]`: the inverse, for tests and the fixture check (`frame_index`, `object_id`, `label`, `bbox`, `score`).
- `evidence.py`:
  - `EVIDENCE_ID = re.compile(r"^[0-9a-f]{32}$")`
  - `save(settings, episode_id, body) -> str`: a new `uuid4().hex`, writes C4 with `id` set, applies the R12 cap, returns the id.
  - `load(settings, episode_id, evidence_id) -> dict | None`
  - `held_by(events, evidence_id) -> list[dict]`: events whose `payload.get("evidence_id") == evidence_id`, oldest first.
- `live.segment_clip` / `segment_photos` add `"frames"` and `"raw"`:
  - live: `frames_from(records, …)`, `raw = {"sam": [records without mask_token, frame_w, frame_h]}`;
  - prepared: the fixture's `frames` (clip) or `stills` (photos), else `None` (R10); `raw` from the fixture or `None`;
  - also `"handmade": bool(found.get("handmade"))`.
- `video_api.add_video`: when `found["frames"] is not None`, save a sidecar (`kind` = check, `media`, `images` from the kept frame ids, `t` from `frame_times(result["rows"])` in order for a clip and `None` for photos, `frames`, `expected` = `[{concept, planned}]` from the rows, `min_score = settings.low_confidence`, `fps = settings.sam_fps` or `None`, `calls`, `raw`, `handmade`) and put `evidence_id` in the payload.
- `GET /journey/episodes/{episode_id}/evidence/{evidence_id}` per C5.
- `eval/p3/make_clips.py`:
  - `boxes_for(detections, t) -> [(concept, k, (x1, y1, x2, y2))]`, the same rectangles `draw_frame` draws. `draw_frame` uses it.
  - A concept with more than 6 items wraps to a new 36 px row every 6 (only the swab clip of Task 8 needs it).
  - `--write-fixtures` (never run by `make demo-check`) writes `frames` (12 frames, `t` 0.0–5.5, score 0.9, ids `1..n` per concept) and `stills` (one frame, `t: null`, everything present) normalised by `SIZE`, plus `"handmade": true`, into each STEM's fixture.
  - For `tray-hernia` only, it also adds two ignored needle-holder boxes (score 0.32 at t 2.0 and 2.5, ids `9`) where the third needle holder would be, so "Show ignored" has something to show.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_evidence.py`; reuse `_upload`, `_events`, `fake_frames` from `tests.test_p3_tray`, `_new`, `_to_theatre` from `tests.test_flow_states`):

```python
def _r(f, oid, label="needle holder", score=0.9, x=0.1):
    return {"frame_index": f, "object_id": oid, "label": label, "bbox": [x, 0.2, 0.1, 0.1], "score": score}

def test_frames_from_marks_low_scores_not_kept():
    frames = video.frames_from([_r(0, "1"), _r(0, "2", score=0.3)], fps=2, min_score=0.45)
    assert frames == [{"t": 0.0, "index": 0, "objects": [
        {"id": "1", "label": "needle holder", "bbox": [0.1, 0.2, 0.1, 0.1], "score": 0.9, "kept": True},
        {"id": "2", "label": "needle holder", "bbox": [0.1, 0.2, 0.1, 0.1], "score": 0.3, "kept": False}]}]

def test_frames_from_caps_at_120_and_keeps_the_best_frame():
    recs = [_r(f, "1") for f in range(300)] + [_r(251, "2")]
    frames = video.frames_from(recs, fps=2, min_score=0.45)
    assert len(frames) <= 120 and 125.5 in [f["t"] for f in frames]

def test_frames_from_empty_and_all_low():
    assert video.frames_from([], fps=2, min_score=0.45) == []
    frames = video.frames_from([_r(0, "1", score=0.2)], fps=2, min_score=0.45)
    assert [o["kept"] for o in frames[0]["objects"]] == [False]
    assert video.summarize(video.records_of(frames), 2, 0.45, ["needle holder"]) == {"needle holder": {"count": 0, "at_s": None}}

def test_frames_from_photos_have_no_time():
    assert video.frames_from([_r(1, "1")], fps=1, min_score=0.45, photos=True)[0]["t"] is None

def test_tray_check_writes_a_sidecar_the_get_returns(tmp_path):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200
    payload = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]
    body = client.get(f"/journey/episodes/{eid}/evidence/{payload['evidence_id']}").json()
    assert body["kind"] == "tray" and body["handmade"] is True and body["min_score"] == 0.45
    assert [i["url"] for i in body["images"]] == [f"/journey/episodes/{eid}/photos/{p}" for p in payload["frame_ids"]]
    assert [c["type"] for c in body["cited_by"]] == ["tray.checked"]

def test_evidence_get_404s(tmp_path):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    _upload(client, eid)
    good = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]["evidence_id"]
    other = client.post("/morning/episodes", json={"label": "Synthetic demo, B"}).json()["id"]
    for path in (f"{eid}/evidence/..%2Fx", f"{eid}/evidence/{'0' * 32}", f"{other}/evidence/{good}"):
        assert client.get(f"/journey/episodes/{path}").status_code == 404

def test_old_check_without_sidecar_still_renders(tmp_path):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    client.app.state.morning.append(eid, "tray.checked", {"rows": [], "missing": [], "match": "none", "why": "x", "source": "none", "frame_ids": [], "by": "N"}, ts_ms=1)
    check = client.get(f"/journey/episodes/{eid}").json()["video_checks"][-1]
    assert check["evidence_id"] is None and check["rows"] == []
```

`backend/tests/test_prepared_schema.py`:

```python
ALLOWED = {"transcript", "text", "detections", "frames", "stills", "regions", "raw", "ms", "model_id", "handmade"}

def test_every_fixture_uses_known_keys_and_counts_match_frames():
    for path in sorted(PREPARED_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        assert set(data) <= ALLOWED, path.name
        for key, photos in (("frames", False), ("stills", True)):
            if data.get(key) is None:
                continue
            concepts = list(data["detections"])
            counts = video.summarize(video.records_of(data[key]), 1 if photos else 2, 0.45, concepts)
            assert {c: v["count"] for c, v in counts.items()} == {c: v["count"] for c, v in data["detections"].items()}, path.name
            for frame in data[key]:
                for o in frame["objects"]:
                    assert all(0 <= v <= 1 for v in o["bbox"]) and isinstance(o["kept"], bool)
```

(`*.live.json` files are not fixtures; glob `*.json` and skip names ending `.live.json`.)

- [ ] **Step 2: Run** the two new test files. Expected: FAIL.
- [ ] **Step 3: Implement**, then run `.venv/bin/python eval/p3/make_clips.py --write-fixtures` once and commit the three updated fixtures. Re-run `.venv/bin/python eval/p3/make_clips.py` (no flag) and check with `git status` that it changes no tracked file.
- [ ] **Step 4: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 400, the demo unchanged and green (the sidecar is not shown yet).
- [ ] **Step 5: Commit** (`backend eval/p3/make_clips.py`). Message: "Count Guard: video and photo checks keep their boxes in an evidence sidecar".

---

### Task 4: Photo regions: SAM finds, Spark reads (D1(b)) · 1 d (8 h)

**Files:**
- Create: `backend/app/journey/regions.py`, `backend/tests/test_regions.py`
- Modify: `backend/app/journey/live.py` (`read_photo`), `media_api.py` (`_check_photo` saves a sidecar), `ask_api.py` (`ask_medicines` saves a sidecar), `proof.py` (`photos_view` check adds `evidence_id`, `regions`), `ask.py` (medicines entries add `regions`, `evidence_id`)
- Modify: `eval/p2/make_media.py` and `eval/p4/make_photos.py` (`--write-fixtures`), fixtures `monitor-88-54.json`, `strip-paracetamol.json`, `meds-kumar.json`, `meds-iyer.json`
- Demo: `frontend/scripts/demo/beats.mjs` (`keyed` of `kumar-paracetamol`, `iyer-meds`), the demo document's Keyed table

**Interfaces:**
- `regions.py` (pure):
  - `READER_CONCEPTS` (R14).
  - `pair_regions(boxes, values) -> list[dict]`. `boxes = [{bbox, score}]`; `values = [{label, value}]`. Sort boxes by `(round(y / 0.05), x)` (top to bottom, then left to right), then zip with the values in order. Each result is `{"bbox", "label", "value", "row": i}`, where `row` is the value's index. Leftover boxes get `label: None, value: None, row: None`. Leftover values get `bbox: None`.
  - `monitor_values(read: dict) -> list[dict]`: always three, in reading order: `SBP`, `DBP`, `HR`. `value` is `str(n)` or `None`.
  - `strip_values(strips) -> list[dict]`: `{"label": f"{name_as_read} {strength}".strip(), "value": same}` per strip, in read order.
- `live.read_photo(...)` returns `{"text", "source", "regions", "calls", "raw", "handmade"}`:
  - Live (key and `live_ok`): first `SamAdapter.segment_images([data_url], READER_CONCEPTS[reader])`. Its boxes are the frame-0 records with score `None` or `>= settings.low_confidence`, timed as one `sam` call. A SAM error gives no boxes and a `sam` call with source `failed`. Then the Spark read as today (a `spark` call). Then `regions = pair_regions(boxes, values)`, where `values` come from `monitor_values(parse_monitor_text(text))` or `strip_values(strips_from(text))`. `raw = {"sam": [...records], "spark": text}`.
  - Prepared: `regions = fixture["regions"]` when present, else `pair_regions([], values)`. Calls: a prepared `sam` call only when the fixture has `regions`, plus a prepared `spark` call.
  - Nothing read: `regions: []`, `calls: []`.
- `_check_photo` and `ask_medicines` save a sidecar (`kind` `monitor`, `strip` or `medicines`; `media: "photos"`; `images: [{photo_id, t: None, index: 0}]`; `frames: None`; `regions`; `calls`; `raw`; `handmade`) when `regions` is not empty, and add `evidence_id`, `regions` and `calls` to `proof.checked` / `medicines.read`.
  - Strip proof regions get `match`: `ok` when `key_of(name)` equals the task's key, else `mismatch` (the same rule as `check_strip`).
  - Medicines regions keep `row` (the index into `rows`); Task 9 colours them.
- Fixtures (written by `--write-fixtures`, `handmade: true`), boxes taken from the generator's own drawing:
  - `monitor-88-54`: three regions over the value texts drawn at y 70, 160 and 250 (use `ImageDraw.textbbox`), labels SBP/DBP/HR, values `"88"`, `"54"`, `"112"`.
  - `strip-paracetamol`: one region, the card `(60, 90, 580, 310)` on `(640, 400)`, label `Paracetamol 500 mg`.
  - `meds-kumar` / `meds-iyer`: one region per card, `(40, top, 680, top + 130)` on `(720, 40 + 150 n)`, labels from the `text` strips, `row` 0..n−1.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_regions.py`):

```python
B = lambda x, y: {"bbox": [x, y, 0.2, 0.1], "score": 0.9}
V = lambda s: {"label": s, "value": s}

def test_pair_equal_counts_reads_top_to_bottom_then_left_to_right():
    out = pair_regions([B(0.5, 0.5), B(0.6, 0.1), B(0.1, 0.12)], [V("a"), V("b"), V("c")])
    assert [(r["bbox"][:2], r["label"], r["row"]) for r in out] == [([0.1, 0.12], "a", 0), ([0.6, 0.1], "b", 1), ([0.5, 0.5], "c", 2)]

def test_pair_more_regions():
    out = pair_regions([B(0.1, 0.1), B(0.1, 0.5)], [V("a")])
    assert [(r["label"], r["row"]) for r in out] == [("a", 0), (None, None)]

def test_pair_more_values():
    out = pair_regions([B(0.1, 0.1)], [V("a"), V("b")])
    assert [(r["bbox"] is None, r["label"]) for r in out] == [(False, "a"), (True, "b")]

def test_pair_zero_regions():
    assert [r["bbox"] for r in pair_regions([], [V("a")])] == [None]

def test_monitor_values_always_three():
    assert monitor_values({"sbp": 88, "dbp": 54}) == [{"label": "SBP", "value": "88"}, {"label": "DBP", "value": "54"}, {"label": "HR", "value": None}]

def test_read_photo_prepared_monitor_has_boxes(tmp_path):
    out = live.read_photo(_no_key(tmp_path), "monitor", b"x", "monitor-88-54.png", "image/png")
    assert [(r["label"], r["value"]) for r in out["regions"]] == [("SBP", "88"), ("DBP", "54"), ("HR", "112")]
    assert all(r["bbox"] for r in out["regions"]) and out["handmade"] is True
    assert [c["model"] for c in out["calls"]] == ["sam", "spark"]

def test_read_photo_live_pairs_sam_with_spark(tmp_path, monkeypatch):
    recs = [{"frame_index": 0, "object_id": str(i), "label": "digital display", "bbox": [0.4, y, 0.2, 0.1], "score": 0.9} for i, y in enumerate((0.7, 0.1, 0.4))]
    monkeypatch.setattr(SamAdapter, "segment_images", lambda self, urls, concepts: recs)
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: '{"sbp": 118, "dbp": 76, "hr": 80}')
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")
    assert [(r["bbox"][1], r["label"]) for r in out["regions"]] == [(0.1, "SBP"), (0.4, "DBP"), (0.7, "HR")]
    assert [(c["model"], c["source"]) for c in out["calls"]] == [("sam", "sam-3.1"), ("spark", "muse-spark-1.3")]

def test_read_photo_sam_fails_values_kept(tmp_path, monkeypatch):
    def boom(*a, **k): raise httpx.ConnectError("no")
    monkeypatch.setattr(SamAdapter, "segment_images", boom)
    monkeypatch.setattr(SparkAdapter, "read_monitor", lambda self, url: '{"sbp": 118, "dbp": 76, "hr": 80}')
    out = live.read_photo(_keyed(tmp_path), "monitor", b"x", "a.png", "image/png")
    assert [r["bbox"] for r in out["regions"]] == [None, None, None] and out["calls"][0]["source"] == "failed"

def test_proof_photo_saves_a_sidecar(tmp_path):
    # sign an obs task (tests.test_flow_tasks OBS), ack, POST /photos purpose=proof with ("monitor-88-54.png", PNG)
    # assert proof.checked payload evidence_id matches EVIDENCE_ID and GET evidence returns 3 regions, kind "monitor"
```

- [ ] **Step 2: Run** `pytest backend/tests/test_regions.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement**, then run `eval/p2/make_media.py --write-fixtures` and `eval/p4/make_photos.py --write-fixtures` once. Re-run both with no flag and check that `git status` shows no tracked change.
- [ ] **Step 4: Demo** (keyed text only, no click or expect change). The photo read now also makes a SAM image call:
  - `kumar-paracetamol.keyed`: "1 Voice call and 1 Spark text call, plus 1 SAM 3.1 image call and 1 Spark vision call for the strip photo. Labels read Muse Voice and Muse Spark; Heard by reads Muse Voice. No switch."
  - `iyer-meds.keyed`: "1 SAM 3.1 image call (strip regions) and 1 Spark vision call. The label reads Muse Spark. Switch: MEDICINES_LIVE."
  - Update the two Keyed table rows in the demo document to the same words.
- [ ] **Step 5: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 409, the demo green.
- [ ] **Step 6: Commit** (`backend eval frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: photo reads box each region with SAM 3.1 and pair it with what Spark read".

---

### Task 5: Re-record the fixtures live, once (D2) · 0.5 d (4 h), the owner runs it

**Files:**
- Create: `eval/record_fixtures.py`, `backend/tests/test_record_fixtures.py`
- Modify: the demo document's "Owner handover" section (how to run it)

**Interfaces:**
- `ASSETS`, a fixed table of `(stem, path, kind)`:
  - `tray-hernia` (`eval/p3/tray-hernia.mp4` clip and `.png` still);
  - `tray-hernia-full` (clip and still);
  - `saline-setup` (clip);
  - `swabs-closing` (clip; skipped with a note until Task 8 adds it);
  - `monitor-88-54` (monitor photo);
  - `strip-paracetamol` (strip photo);
  - `meds-kumar`, `meds-iyer` (strip photos).
  Voice fixtures are not re-recorded: they hold transcripts, not boxes.
- Pure functions, tested:
  - `candidate(old, live_result, kind) -> dict`: the new fixture (C6), with `frames`/`stills`/`regions`, `raw`, `ms` (the sum of the call times), `model_id`; `handmade` removed; `detections`, `text` and `transcript` kept from `old` when they agree.
  - `differences(old, live_result, kind) -> list[str]`: empty when the counts per concept (or the values read) equal the fixture's; else one line per difference, such as `needle holder: fixture 2, live 3`.
- `main(argv)`:
  - Refuses without `MODEL_API_KEY` (exit 1). Refuses without `--spend` (exit 1), and prints the `make cost` bill for the three clips first.
  - Calls the same `live.segment_clip` / `segment_photos` / `read_photo` seam with `live_ok=True`.
  - Per asset, writes `prepared/<stem>.json` when `differences` is empty, else `prepared/<stem>.live.json` (R13). Prints the region count per reader concept (R14).
  - Exits 2 when any asset differed, else 0.
- The request count: the clips are 7 + 7 + 4 + 1 SAM concept calls, the stills 7 + 7, and the photos 4 SAM + 4 Spark. That is about 41 model requests for 10 assets (the spec's "about 10 calls" counted assets). The script prints the total before it starts.

- [ ] **Step 1: Write the failing tests** (`test_record_fixtures.py`; import the module by path with `importlib.util.spec_from_file_location`; no network):

```python
def test_same_counts_overwrite_and_drop_handmade():
    old = {"detections": {"scissors": {"count": 3, "at_s": 2.0}}, "frames": [], "handmade": True}
    live_result = {"detections": {"scissors": {"count": 3, "at_s": 1.5}}, "frames": [{"t": 1.5, "index": 3, "objects": []}], "raw": {"sam": []}, "calls": [{"ms": 900}, {"ms": 100}]}
    assert rec.differences(old, live_result, "clip") == []
    new = rec.candidate(old, live_result, "clip")
    assert "handmade" not in new and new["ms"] == 1000 and new["detections"] == old["detections"]

def test_different_counts_are_reported_not_written():
    old = {"detections": {"needle holder": {"count": 2, "at_s": 1.5}}}
    live_result = {"detections": {"needle holder": {"count": 3, "at_s": 1.5}}}
    assert rec.differences(old, live_result, "clip") == ["needle holder: fixture 2, live 3"]

def test_refuses_without_key_or_spend(monkeypatch, capsys):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    assert rec.main(["--spend"]) == 1
    monkeypatch.setenv("MODEL_API_KEY", "k")
    assert rec.main([]) == 1
```

- [ ] **Step 2: Run** it. Expected: FAIL.
- [ ] **Step 3: Implement.** Add to the demo document's "Owner handover" section: "Re-record the boxes once: `MODEL_API_KEY=… .venv/bin/python eval/record_fixtures.py --spend`. A fixture whose live counts differ is left alone; the run writes `<stem>.live.json` beside it and exits 2. Until then the viewer labels results Sample." (Write `MODEL_API_KEY=…` with the ellipsis; `doc.test.mjs` forbids a value.)
- [ ] **Step 4: Run** every suite and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 412, the demo green. Do **not** run the script; the owner does.
- [ ] **Step 5: Commit** (`eval/record_fixtures.py backend/tests ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: a one-time script records the real model boxes as fixtures, without changing the demo story".

---

### Task 6: The evidence viewer · 2 d (16 h)

**Files:**
- Create: `frontend/src/care/evidence.js`, `evidence.test.js`, `Evidence.jsx` (exports `Evidence`, `EvidenceThumb`, `useEvidence`)
- Modify: `VideoCheck.jsx` (`CheckResult`), `VideoChecks.jsx`, `Thread.jsx` (medicines row), `TaskProof.jsx` (photo line), `Photos.jsx` (proof photos), `care.css`, `styles.test.js`
- Demo: `beats.mjs` (`kumar-tray.expect`), the demo document

**Interfaces:**
- `evidence.js` (pure):
  - `MODEL_NAME` (C3).
  - `PALETTE`: 8 hex colours that read on both light and dark surfaces.
  - `colourFor(concept)`: djb2 hash of the string, mod 8. Stable.
  - `modeWord(source, handmade)` (C2/R6): `Sample` when handmade, else `live` / `prepared` / `failed`, or `""`.
  - `chipText(calls, handmade) -> string`: `` `${MODEL_NAME[c.model]} · ${modeWord(c.source, handmade)}` `` for the first call whose model is `sam`, else the first call. `""` with no calls.
  - `boxesAt(frames, at, showIgnored) -> objects`: the frame whose `t === at` (or `index === at` when `t` is null). Kept objects only, unless `showIgnored`. `[]` when there is no such frame.
  - `countSeries(frames, concept) -> [{ t, n }]`: kept, distinct ids per frame.
  - `boxLabel(o) -> string`: `` `${o.label} ${o.id} ${o.score.toFixed(2)}` ``, or without the score when `score == null`.
  - `seenCell(row) -> string`: `"not checked"` when `seen == null`, `` `${seen} (missing)` `` when short, else `String(seen)`. Moved from `VideoCheck.jsx:46`, wording unchanged.
  - `plural(concept, n)`: the concept when `n === 1` or it ends in `s`, else concept + `s`.
  - `explain(rows, frames, minScore, media) -> string[]` (1–3 sentences):
    1. No kept object in any frame and no row seen: `` `Nothing found above confidence ${minScore}.` ``, followed only by sentence 4 when it applies.
    2. Else the first row with `seen < planned`: `` `Saw ${seen} of ${planned} ${plural(concept, planned)}.` ``; with none short: `` `Saw every planned item: ${sumSeen} of ${sumPlanned}.` ``
    3. For `media === "video"` and that row's `at_s != null`: `` `The best frame was ${at_s} s.` ``
    4. When `k` objects are not kept: `1 detection under confidence 0.45 was ignored.` or `` `${k} detections under confidence ${minScore} were ignored.` ``
  - `regionLabel(r) -> string`: `not read` when `label == null`; `` `${label} not read` `` when `value == null` and the label is a monitor field; else `` `${label} ${value}` `` for monitor fields and `label` for strips. Monitor fields are `SBP`, `DBP`, `HR`.
  - `explainRegions(regions) -> string[]`: `` `Read ${v} values from ${b} regions.` ``, then `` `${k} region(s) had no value read.` `` / `` `${j} value(s) were read with no box.` `` when non-zero, singular when 1.
  - `capturedLine(cited) -> string`: `` `Captured to record: ${type} · ${when.slice(-5)} · ${displayName(by)}` ``
  - `evidenceView(sidecar, check) -> { fallback, title, chip, images, rows, regions, sentences, raw, cited }`: with `sidecar == null`, `{ fallback: true, rows: check?.rows || [] }` (Review Focus 3). `title` is `{ tray: "Tray check", setup: "Set-up check", swabs: "Swab camera count", monitor: "Monitor photo", strip: "Strip photo", medicines: "Medicines photo" }[kind]`.
- `Evidence.jsx`:
  - `useEvidence(episodeId, evidenceId)`: fetches C5 with `call()` from `../journey`, cached in a module `Map`. Returns `{ data, error }`; `null` while loading.
  - `<Evidence episodeId evidenceId check sample? />` renders `<section className="evidence" aria-label="Evidence">` (R32). It uses `sample` (a C4 object with `images[].url`) when given and does not fetch. In order:
    - the header `<p className="label">{title} · {chip}</p>`;
    - the stage `<div className="ev-stage"><img/><canvas/></div>`, where the canvas matches the image's displayed size and draws each box from `boxesAt` (solid in `colourFor(label)` when kept, dashed grey when ignored) with `boxLabel` above it. Regions draw in grey with `regionLabel`; Task 9 colours strips;
    - a filmstrip of the images as buttons `aria-label={`Frame ${t ?? index + 1}`}`, `aria-pressed` on the shown one;
    - a `<label><input type="checkbox"/> Show ignored</label>`;
    - for counts, a table `Expected | Seen | Status` (`planned`, `seenCell(row)`, `✓` or `missing ${planned - seen}`) and one inline SVG sparkline per concept from `countSeries`, with a dot on the kept image times;
    - for regions, a list of `regionLabel` lines;
    - `<p className="small">Why: {sentences.join(" ")}</p>`;
    - `<details><summary>Raw output</summary><pre>{JSON.stringify(raw, null, 2)}</pre></details>`;
    - one `capturedLine` per `cited` entry, as a link to `/chart/${episodeId}?line=${event_id}` for staff roles and plain text for the patient (prop `linkLines`).
  - While loading or on error it renders the `fallback` table, so nothing jumps.
  - `<EvidenceThumb episodeId evidenceId />`: a 48 px square, the first image with its kept boxes drawn, and `chipText` as `title` plus a `<span className="small muted">` under it. It is a button that toggles a full `<Evidence>` below it.
- Wiring:
  - `VideoCheck` `CheckResult`: the pill line and `why` stay. When `check.evidence_id`, `<Evidence>` replaces the old table and frames row. Without it, the old table and frames row stay as they are (fallback).
  - `VideoChecks`: each check row gets `<EvidenceThumb>` when it has an `evidence_id`.
  - `Thread` medicines row and `TaskProof`'s photo line: `<Evidence>` for the medicines read, `<EvidenceThumb>` for the proof photo.
  - `Photos`: proof photos with `check.evidence_id` show `<EvidenceThumb>` in place of the plain 72 px image.

- [ ] **Step 1: Write the failing tests** (`evidence.test.js`):

```js
const o = (id, label, score, kept = true) => ({ id, label, bbox: [0.1, 0.1, 0.1, 0.1], score, kept });
const F = [{ t: 0, index: 0, objects: [] }, { t: 0.5, index: 1, objects: [o("1", "towel clip", 0.9), o("2", "towel clip", 0.3, false)] }, { t: 1, index: 2, objects: [o("1", "towel clip", 0.9), o("3", "towel clip", 0.8)] }];
test("boxesAt and countSeries", () => {
  assert.deepEqual(boxesAt(F, 0.5, false).map((b) => b.id), ["1"]);
  assert.deepEqual(boxesAt(F, 0.5, true).map((b) => b.id), ["1", "2"]);
  assert.deepEqual(boxesAt(F, 7, false), []);
  assert.deepEqual(countSeries(F, "towel clip"), [{ t: 0, n: 0 }, { t: 0.5, n: 1 }, { t: 1, n: 2 }]);
});
test("explain: short concept, best frame, ignored", () => {
  const rows = [{ concept: "scissors", planned: 3, seen: 3, at_s: 0.5 }, { concept: "towel clip", planned: 4, seen: 3, at_s: 1 }];
  assert.deepEqual(explain(rows, F, 0.45, "video"), ["Saw 3 of 4 towel clips.", "The best frame was 1 s.", "1 detection under confidence 0.45 was ignored."]);
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 3, at_s: 0.5 }], [{ t: 0.5, index: 1, objects: [o("1", "scissors", 0.9)] }], 0.45, "photos"), ["Saw every planned item: 3 of 3."]);
});
test("explain: nothing found is a sentence, not an error", () => {
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 0, at_s: null }], [], 0.45, "video"), ["Nothing found above confidence 0.45."]);
  assert.deepEqual(explain([{ concept: "scissors", planned: 3, seen: 0, at_s: null }], [{ t: 0, index: 0, objects: [o("1", "scissors", 0.2, false)] }], 0.45, "video"), ["Nothing found above confidence 0.45.", "1 detection under confidence 0.45 was ignored."]);
});
test("regionLabel and explainRegions", () => {
  assert.equal(regionLabel({ label: "SBP", value: "88" }), "SBP 88");
  assert.equal(regionLabel({ label: "HR", value: null }), "HR not read");
  assert.equal(regionLabel({ label: null, value: null }), "not read");
  assert.deepEqual(explainRegions([{ bbox: [0, 0, 1, 1], label: "SBP", value: "88" }, { bbox: [0, 0, 1, 1], label: null, value: null }, { bbox: null, label: "HR", value: "80" }]),
    ["Read 2 values from 2 regions.", "1 region had no value read.", "1 value was read with no box."]);
});
test("mode, chip and colour", () => {
  assert.deepEqual([["sam-3.1", false], ["prepared", false], ["prepared", true], ["prepared (live call failed)", false]].map(([s, h]) => modeWord(s, h)), ["live", "prepared", "Sample", "failed"]);
  assert.equal(chipText([{ model: "spark", source: "prepared" }, { model: "sam", source: "prepared" }], true), "SAM 3.1 · Sample");
  assert.equal(colourFor("retractor"), colourFor("retractor"));
  assert.ok(PALETTE.includes(colourFor("towel clip")));
});
test("a missing sidecar falls back to the count table", () => {
  assert.deepEqual(evidenceView(null, { rows: [{ concept: "x" }] }), { fallback: true, rows: [{ concept: "x" }] });
  assert.equal(seenCell({ planned: 3, seen: 2 }), "2 (missing)");
});
test("viewer copy has no advice words", () => {
  for (const s of ["Expected", "Seen", "Status", "Why:", "Raw output", "Show ignored", "Captured to record: tray.checked · 09:18 · Nurse Asha", "Nothing found above confidence 0.45.", "The best frame was 3.5 s.", "2 detections under confidence 0.45 were ignored.", "Read 3 values from 3 regions."]) assert.doesNotMatch(s, ADVICE);
});
```

`styles.test.js`: `assert.match(css, /\.ev-stage \{[^}]*position:\s*relative/)` and `assert.match(css, /\.ev-thumb \{[^}]*48px/)`.

- [ ] **Step 2: Run** `node --test src/care/evidence.test.js src/care/styles.test.js`. Expected: FAIL.
- [ ] **Step 3: Implement.** CSS: `.ev-stage { position: relative; max-width: 640px }`, `.ev-stage img { width: 100%; display: block }`, `.ev-stage canvas { position: absolute; inset: 0; width: 100%; height: 100% }`, `.ev-thumb { width: 48px; height: 48px }`. Redraw the canvas on image `load` and on window `resize`. Check that `wc -l` stays under 500 for every file touched.
- [ ] **Step 4: Demo.**
  - `kumar-tray.expect` adds `"Saw 2 of 3 needle holders."`. The hernia tray plans 3 needle holders and the fixture sees 2. Every existing string stays: the pill, `needle holder`, `2 (missing)` (now `seenCell`), `Prepared demo result`.
  - Add the string to the `kumar-tray` `On screen:` line of the demo document.
- [ ] **Step 5: Run** the care, demo-unit and build checks and `make demo-check MODEL_API_KEY=`. Expected: care ≥ 199, demo 36, the demo green. Open `demo-shots/*-kumar-tray.png` and check by eye that the boxes sit on the drawn rectangles.
- [ ] **Step 6: Commit** (`frontend/src/care frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: one evidence viewer shows the boxes, counts and a plain explanation for every model check".

---

### Task 7: The "AI at work" dashboard · 1.5 d (12 h)

**Files:**
- Create: `backend/app/journey/ai_summary.py`, `backend/tests/test_ai_summary.py`, `backend/app/journey/prepared/spark-open-sample.json` (`{"text": "...", "handmade": true}`), `frontend/src/care/ai.js`, `ai.test.js`, `AiDashboard.jsx`
- Modify: `backend/app/journey/ai_api.py` (summary, try, samples), `backend/app/main.py` (an `ai_router` if separate), `frontend/src/App.jsx` (route `/ai` inside `CareRoutes`), `DemoDock.jsx` (link, R31), `care.css`

**Interfaces:**
- `ai_summary.py` (pure):
  - `MODELS = [{"key": "voice", "name": "Muse Voice", "role": "Writes down what staff say: orders, discharges, answers and task updates."}, {"key": "spark", "name": "Muse Spark 1.3", "role": "Reads photos and drafts orders and answers from the record."}, {"key": "sam", "name": "SAM 3.1", "role": "Finds and counts instruments, swabs and photo regions."}, {"key": "spark-open", "name": "Muse Spark Open", "role": "Explains a count discrepancy on the camera screen; ward questions come later."}]`
  - `summary(roster, configured) -> {"models": [...], "recent": [...]}`:
    - `roster` is `[(episode, events)]`; `configured` is `{"voice": bool, "spark": bool, "sam": bool, "spark-open": bool}`.
    - Per model: `{key, name, role, model_id, mode, calls, median_ms, last}`. `calls` counts every call with that `model` in any payload. `mode` is `mode_of` of the newest call, or with no calls `"live"` when configured, else `"prepared"`. `median_ms` is the integer median of non-null `ms`, or `None`. `last` is `{at_ms, episode_id, event_id, evidence_id, text: plain(event)}` of the newest call, or `None`.
    - `recent`: one row per (event, call), newest first, ties by event order then call order, capped at 20: `{at_ms, when, model, name, mode, patient: short_name(episode["label"]), what: plain(event), episode_id, event_id, evidence_id}`.
  - Mode comes from `live.mode_of`. The handmade flag is not in events, so the frontend shows Sample from the sidecar only.
- Routes (`ai_api.py`):
  - `GET /journey/ai/summary?ids=a,b,c`: 1–10 comma-separated ids (422 otherwise), each an existing episode (404 `Episode not found`). Returns `summary(...)` plus `"live": settings.spark_configured`.
  - `POST /journey/ai/try/{model}` with `model` in `voice|spark|sam|spark-open` (422 otherwise). It writes nothing (R9):
    - `sam`: `live.segment_photos(settings, [eval/p3/tray-hernia.png], concepts, "tray-hernia.png", live_ok=TRAY_LIVE)`, compared with `expected_for_tray(tray_plan("hernia-repair"))`. Returns `{model, mode, evidence}`, where `evidence` is a C4 object with `images: [{url: "/journey/ai/samples/tray-hernia.png", t: null, index: 0}]`, `frames` (the stills), `expected`, `rows` (the compare rows), `calls`, `raw` and `handmade`.
    - `spark`: `live.read_photo(settings, "monitor", bytes, "monitor-88-54.png", "image/png")`. Returns `evidence` with `regions` and the sample image URL.
    - `voice`: `live.transcribe(...)` on `kumar-orders.wav`. Returns `{model, mode, text}`.
    - `spark-open`: the fixture `text`, mode `Sample`.
    - With a key, a missing sample file is 409 `The sample file is missing. Run make demo-check once to make it.`; without a key, the fixture is enough.
  - `GET /journey/ai/samples/{name}`: allow-list `{"tray-hernia.png": "eval/p3", "monitor-88-54.png": "eval/p2"}` under `REPO_ROOT`. 404 for anything else or a missing file. `FileResponse` with `nosniff`.
- `ai.js` (pure):
  - `PIPELINES` (the three spec lines, as arrays): `["Voice", "Draft orders", "Nurse tasks"]`, `["Photo", "SAM regions", "Spark reads", "Check against orders"]`, `["Video", "SAM per-frame tracking", "Count", "Mismatch flag"]`
  - `callsText(n)`: `"No calls yet"` / `"1 call"` / `` `${n} calls` ``
  - `latencyText(ms)`: `"No timing yet"` for null, else `` `${(ms / 1000).toFixed(1)} s median` ``
  - `modeLabel(mode)`: `{ live: "Live", prepared: "Prepared", failed: "Failed" }[mode] || mode`
  - `recentText(row)`: `` `${row.when.slice(-5)} ${row.name} · ${displayName(row.patient)} · ${row.what}` ``
- `<AiDashboard />` (route `/ai`):
  - `PageLead` kicker "Demo", title "AI at work", body "Which Muse models run this ward, and what they just did."
  - A top-right pill: `Live ●` when `live`, else `Prepared ○`.
  - The pipeline strip: `PIPELINES` rows joined by `→`.
  - Four cards, each `<section className="card model-card" aria-label={name}>`: name, role, the mode pill, `callsText`, `latencyText`, `last.text` with an `EvidenceThumb` when `last.evidence_id`, and a `Try sample` button. The button POSTs `/journey/ai/try/{key}` with `call()` and shows `<Evidence sample={evidence} />` under the cards (SAM, Spark), or the text in the card (Voice, Spark Open). A Fault-style `<p className="error">` shows on failure.
  - `<section aria-label="Recent AI events">`: one row per `recent` item. A row with `evidence_id` toggles `<Evidence episodeId evidenceId linkLines />`; one without links to `/chart/{episode_id}?line={event_id}`. Empty: "No model results yet. Run a flow and they appear here."
  - The page fetches the summary on mount and after each Try sample, with `ids = ward.patients.map((p) => p.id).join(",")`.
- `DemoDock`: `<Link to="/ai">AI at work</Link>` inside `.dock-body`, after the clock.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_ai_summary.py`):

```python
S = lambda src, ms, m="sam": {"model": m, "model_id": "x", "source": src, "ms": ms}
def ev(kind, calls, ts, evidence_id=None):
    return {"id": f"{kind}-{ts}", "episode_id": "e1", "event_type": kind, "ts_ms": ts,
            "payload": {"calls": calls, "by": "N", "why": "w", **({"evidence_id": evidence_id} if evidence_id else {})}}
EP = {"id": "e1", "label": "R. Kumar, 58 M (synthetic)"}
OFF = {"voice": False, "spark": False, "sam": False, "spark-open": False}

def test_summary_folds_calls_per_model():
    events = [ev("tray.checked", [S("sam-3.1", 3000)], 10), ev("tray.checked", [S("prepared", None)], 20, "a" * 32), ev("setup.checked", [S("sam-3.1", 1000)], 30)]
    out = summary([(EP, events)], OFF)
    assert [m["key"] for m in out["models"]] == ["voice", "spark", "sam", "spark-open"]
    sam = out["models"][2]
    assert (sam["calls"], sam["median_ms"], sam["mode"], sam["last"]["event_id"]) == (3, 2000, "live", "setup.checked-30")
    assert out["recent"][0]["patient"] == "R. Kumar" and out["recent"][1]["evidence_id"] == "a" * 32

def test_mode_without_calls_follows_the_key_and_failed_wins_when_newest():
    out = summary([(EP, [ev("tray.checked", [S("prepared (live call failed)", None)], 5)])], {**OFF, "voice": True})
    by = {m["key"]: m for m in out["models"]}
    assert (by["voice"]["mode"], by["spark"]["mode"], by["sam"]["mode"]) == ("live", "prepared", "failed")
    assert by["sam"]["median_ms"] is None

def test_recent_is_capped_and_newest_first():
    events = [ev("tray.checked", [S("sam-3.1", 1)], t) for t in range(30)]
    rows = summary([(EP, events)], OFF)["recent"]
    assert len(rows) == 20 and rows[0]["at_ms"] == 29

def test_summary_route_validates_ids(tmp_path):
    client, eid = _new(tmp_path)
    assert client.get("/journey/ai/summary").status_code == 422
    assert client.get("/journey/ai/summary?ids=nope").status_code == 404
    assert client.get("/journey/ai/summary?ids=" + ",".join([eid] * 11)).status_code == 422
    assert client.get(f"/journey/ai/summary?ids={eid}").status_code == 200

def test_try_sample_without_a_key_writes_nothing(tmp_path):
    client, eid = _new(tmp_path)
    before = len(client.app.state.morning.events(eid))
    body = client.post("/journey/ai/try/sam").json()
    assert body["mode"] == "prepared" and body["evidence"]["handmade"] is True and body["evidence"]["frames"]
    assert len(client.app.state.morning.events(eid)) == before
    assert client.post("/journey/ai/try/other").status_code == 422
    assert not ADVICE.search(client.post("/journey/ai/try/spark-open").json()["text"])

def test_samples_route_is_an_allow_list(tmp_path):
    client, _ = _new(tmp_path)
    for name in ("..%2Fsecret", "tray-hernia.mp4", "x.png"):
        assert client.get(f"/journey/ai/samples/{name}").status_code == 404
```

`ai.test.js`:

```js
test("card words", () => {
  assert.deepEqual([0, 1, 6].map(callsText), ["No calls yet", "1 call", "6 calls"]);
  assert.deepEqual([null, 2400].map(latencyText), ["No timing yet", "2.4 s median"]);
  assert.equal(modeLabel("failed"), "Failed");
  assert.equal(recentText({ when: "Day 0 09:24", name: "SAM 3.1", patient: "R. Kumar", what: "Tray check by video: x" }), "09:24 SAM 3.1 · R. Kumar · Tray check by video: x");
});
test("dashboard copy has no advice words", () => {
  for (const s of [...PIPELINES.flat(), "AI at work", "Try sample", "Recent AI events", "Which Muse models run this ward, and what they just did.", "No model results yet. Run a flow and they appear here.", "Live ●", "Prepared ○"]) assert.doesNotMatch(s, ADVICE);
});
```

Also assert no advice words in every `MODELS[*].role` (backend test).

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.** CSS: `.model-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px }`. At 390 px the cards stack, and nothing scrolls sideways.
- [ ] **Step 4: Run** every suite, the build and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 419, care ≥ 201, the demo green with no beat change (the dock gains a link; no beat reads it yet). By hand: `make dev CG_API_PORT=8200 CG_WEB_PORT=5273 MODEL_API_KEY=`, open `/ai`, press each Try sample, check the SAM boxes sit on the drawn instruments, then stop the servers.
- [ ] **Step 5: Commit** (`backend frontend/src`). Message: "Count Guard: an AI at work page shows the four models, their calls and a sample run with boxes".

---

### Task 8: What the models read becomes part of the action or note (§2.5) · 2 d (16 h)

**Files:**
- Create: `backend/app/journey/count_api.py` (move `CountIn` and the `/count` route out of `api.py`, which is at 464 lines; first `grep -rn "CountIn\|def count" backend` for imports), `backend/tests/test_capture.py`, `frontend/src/care/capture.js`, `capture.test.js`
- Modify:
  - `backend/app/journey/video_api.py` (`check: "swabs"`, `SWABS_LIVE`)
  - `video.py` (`checks_view` includes `swabs.counted` as `check: "swabs"`)
  - `states.py` (`theatre_count` adds `camera`)
  - `tasks.py` (`complete_task` copies evidence, keeps `read`/`saved`)
  - `stories.py` (`timeline_items` adds `evidence_id`, `calls`; `plain` for `swabs.counted`)
  - `ai_api.py` (`cited_by` adds `read`, `saved`)
  - `main.py`
- Modify: `frontend/src/care/TheatrePanel.jsx`, `TaskProof.jsx`, `NurseTasks.jsx`, `Timeline.jsx`, `drafts.js` (`lastDoneLine` adds `evidenceId`), `video.js` (`CHECK_LABEL.swabs`), `evidence.js` (`correctionLine`), `Evidence.jsx` (the correction line under `capturedLine`)
- Media: `eval/p3/make_clips.py` (STEM `swabs-closing`), fixture `backend/app/journey/prepared/swabs-closing.json` (`{"detections": {"gauze swab": {"count": 14, "at_s": 1.0}}}`, then `--write-fixtures`)
- Demo: `beats.mjs` (`MEDIA`, `kumar-count`), `steps.mjs`, the demo document

**Interfaces:**
- Swab camera count (R18):
  - `POST /video` accepts `check: "swabs"` with no `task_id`.
  - It is refused with 409 unless the patient is in theatre and a `count.pack_opened` exists in this stay: `Record the pack opened first.`
  - Expected rows: `[{"concept": "gauze swab", "names": ["Swab"], "planned": opened}]`. It is read through the same `_read_clip` / `_read_photos` with `live_ok=SWABS_LIVE`.
  - It writes `swabs.counted {"count": seen, "opened", "media", "source", "calls", "evidence_id", "frame_ids", "clip", "by"}`.
  - `plain`: `` f"Swab camera count: {count} seen, {opened} opened." ``
- `theatre_count(events)` adds `"camera": {"count", "evidence_id", "at_ms"} | None`: the latest `swabs.counted` in this stay, only when it is newer than the closing that stands.
- `CountIn` gains `evidence_id: str | None = Field(None, pattern=r"^[0-9a-f]{32}$")` and `via: Literal["typed", "camera"] = "typed"`. With an `evidence_id`, the closing is refused with 422 `That camera count is not from this patient's theatre stay.` unless a `swabs.counted` event **in this stay** holds it (R16, Review Focus 4). It then sets `via: "camera"`, stores `evidence_id`, and when `returned != count` stores `read: {"returned": count}` and `saved: {"returned": returned}` (R17).
- `complete_task`: when the `proof_id`'s latest `proof.checked` has `evidence_id`, copy it to `task.done`. For an obs task with `values_read`, store `read` (the read keys) and `saved` (the same keys from `values`) when any differ. The `obs.recorded` it writes gains `evidence_id` and `source` (the check's source) (R35).
- `timeline_items` adds `"evidence_id": p.get("evidence_id")` and `"calls": p.get("calls") or []` to each item.
- C5 `cited_by` entries add `read` and `saved` when present.
- `capture.js` (pure):
  - `prefillObs(regions, form) -> form`: fills `sbp`, `dbp`, `hr` from regions labelled `SBP`, `DBP`, `HR` with a value, **only where the form field is empty** (R15). Returns a new object.
  - `cameraPrefill(count, returned) -> string`: `String(count.camera.count)` when `count?.camera` and `returned === ""`, else `returned`.
  - `closingBody(count, returned, detail) -> body`: adds `evidence_id` and `via: "camera"` when `count?.camera`.
  - `correctionLine(read, saved, by) -> string`: the keys that differ, in the order `returned, sbp, dbp, hr`, values joined by `/`: `` `Read ${r}, saved ${s} by ${displayName(by)}` ``. `""` when none differ or either is missing.
- UI:
  - `TheatrePanel`:
    - Replace the "Count by camera" navigate with `<VideoCheck title="Swab camera count" kind="swabs" check={latestCheck(view, "swabs")} … onFile={(f) => upload("/video", f, { check: "swabs", by })} />`. The drop zone label is `Upload a clip or photos of the returned swabs`.
    - Add `swabs` to `CHECK_LABEL` (`ok: "Swab count matches the pack"`, `mismatch: "Flagged: fewer swabs seen than opened. The nurse decides."`, `none: "Clip kept, not counted"`).
    - When `view.count.camera` exists, show `Camera count: {n}`, prefill "Closing count (returned)" with `cameraPrefill`, and post `closingBody(...)`. The line goes once a closing is recorded (the camera count is then older than the closing), but the swab `VideoCheck` result and its viewer stay while the count step is open.
    - Under the figures, show `correctionLine` of the standing closing, when present.
  - `NurseTasks`: obs rows get a quiet button `Read from monitor photo`. It opens the confirm panel with `via: "tap"`, like "Add photo proof" does.
  - `TaskProof`: after a photo upload on an obs task, `setForm(prefillObs(photo.check?.regions || [], form))`, and remount `ObsForm` with `key={JSON.stringify(form)}` so the fields show it. The photo line shows `<EvidenceThumb>` when `photo.check.evidence_id`.
  - `NurseTasks` last-done line and `Timeline` lines show `<EvidenceThumb>` for an `evidenceId` / `evidence_id`.
  - `Evidence` shows `correctionLine` under each `capturedLine` that has `read`/`saved`.

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_capture.py`; reuse `_new`, `_to_theatre`, `_surgery` from `tests.test_flow_states`, `_upload`, `fake_frames` from `tests.test_p3_tray`, the task helpers from `tests.test_flow_tasks`):

```python
def _counted(client, eid):
    _to_theatre(client, eid)
    _surgery(client, eid, "began")
    client.post(f"/journey/episodes/{eid}/count", json={"step": "opened", "quantity": 15, "by": NURSE, "at_ms": 0})
    assert _upload(client, eid, name="swabs-closing.mp4", check="swabs").status_code == 200
    return client.get(f"/journey/episodes/{eid}").json()["count"]["camera"]

def test_swab_camera_count_prefills_the_count(tmp_path):
    client, eid = _new(tmp_path)
    camera = _counted(client, eid)
    assert camera["count"] == 14 and EVIDENCE_ID.match(camera["evidence_id"])

def test_swab_count_needs_the_pack(tmp_path):
    client, eid = _new(tmp_path); _to_theatre(client, eid)
    assert _upload(client, eid, name="swabs-closing.mp4", check="swabs").status_code == 409

def test_closing_by_camera_keeps_read_and_saved(tmp_path):
    client, eid = _new(tmp_path)
    ev = _counted(client, eid)["evidence_id"]
    client.post(f"/journey/episodes/{eid}/count", json={"step": "closing", "returned": 15, "evidence_id": ev, "by": NURSE})
    p = [e for e in client.app.state.morning.events(eid) if e["event_type"] == "count.closing"][-1]["payload"]
    assert (p["via"], p["evidence_id"], p["read"], p["saved"]) == ("camera", ev, {"returned": 14}, {"returned": 15})
    cited = client.get(f"/journey/episodes/{eid}/evidence/{ev}").json()["cited_by"]
    assert [c["type"] for c in cited] == ["swabs.counted", "count.closing"] and cited[1]["read"] == {"returned": 14}

def test_closing_refuses_foreign_evidence(tmp_path):
    client, eid = _new(tmp_path)
    other = client.post("/morning/episodes", json={"label": "Synthetic demo, B"}).json()["id"]
    ev_other = _counted(client, other)["evidence_id"]
    _to_theatre(client, eid)
    assert _upload(client, eid).status_code == 200  # a tray check, before surgery begins
    ev_tray = [e for e in _events(client, eid) if e["event_type"] == "tray.checked"][-1]["payload"]["evidence_id"]
    _surgery(client, eid, "began")
    client.post(f"/journey/episodes/{eid}/count", json={"step": "opened", "quantity": 15, "by": NURSE, "at_ms": 0})
    for bad in (ev_other, ev_tray, "f" * 32, "../x"):
        r = client.post(f"/journey/episodes/{eid}/count", json={"step": "closing", "returned": 14, "evidence_id": bad, "by": NURSE})
        assert r.status_code == 422, bad

def test_obs_done_with_a_monitor_photo_keeps_evidence_and_correction(tmp_path):
    # sign OBS, ack, add proof photo "monitor-88-54.png" for the obs task, then done with values 90/54/112 and that proof_id
    # task.done: evidence_id set, read == {"sbp": 88, "dbp": 54, "hr": 112}, saved == {"sbp": 90, "dbp": 54, "hr": 112}
    # obs.recorded: evidence_id set, source == "prepared", by == the nurse
    # the same with 88/54/112: no read/saved keys

def test_timeline_items_carry_evidence(tmp_path):
    client, eid = _new(tmp_path)
    _counted(client, eid)
    line = [t for t in client.get(f"/journey/episodes/{eid}").json()["timeline"] if t["type"] == "swabs.counted"][-1]
    assert line["evidence_id"] and line["calls"][0]["model"] == "sam" and not ADVICE.search(line["plain"])
```

`capture.test.js`:

```js
test("prefillObs fills only empty fields", () => {
  const regions = [{ label: "SBP", value: "88" }, { label: "DBP", value: "54" }, { label: "HR", value: null }, { label: null, value: null }];
  assert.deepEqual(prefillObs(regions, {}), { sbp: "88", dbp: "54" });
  assert.deepEqual(prefillObs(regions, { sbp: "90" }), { sbp: "90", dbp: "54" });
});
test("the camera count prefills the closing count and names its evidence", () => {
  const count = { opened: 15, camera: { count: 14, evidence_id: "a".repeat(32) } };
  assert.equal(cameraPrefill(count, ""), "14");
  assert.equal(cameraPrefill(count, "15"), "15");
  assert.deepEqual(closingBody(count, 14, ""), { step: "closing", returned: 14, detail: "", evidence_id: "a".repeat(32), via: "camera" });
  assert.deepEqual(closingBody({ opened: 15 }, 14, ""), { step: "closing", returned: 14, detail: "" });
});
test("correctionLine", () => {
  assert.equal(correctionLine({ sbp: 118 }, { sbp: 120 }, "Nurse Meena (synthetic)"), "Read 118, saved 120 by Nurse Meena");
  assert.equal(correctionLine({ returned: 14 }, { returned: 15 }, "Nurse Asha (synthetic)"), "Read 14, saved 15 by Nurse Asha");
  assert.equal(correctionLine(null, null, "x"), "");
});
test("capture copy has no advice words", () => {
  for (const s of ["Read from monitor photo", "Swab camera count", "Upload a clip or photos of the returned swabs", "Camera count: 14", "Swab count matches the pack", "Flagged: fewer swabs seen than opened. The nurse decides.", "Clip kept, not counted"]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Add `swabs-closing` to `make_clips.STEMS` (14 boxes wrap at 6 a row), write the fixture, and run `make_clips.py --write-fixtures`. `test_prepared_schema.py` (Task 3) must pass on it.
- [ ] **Step 4: Demo.**
  - `beats.mjs` `MEDIA` adds `"swabs-closing.mp4": "eval/p3"`.
  - `kumar-count`:
    - `clicks`: `['Button "Surgery began"', 'Button "Record pack opened" (prefilled 15)', 'File eval/p3/swabs-closing.mp4 into "Swab camera count"', 'Button "Record closing count" (prefilled 14 by the camera)', 'Field "Closing count (returned)" <- 15', 'Button "Correct the count"']`
    - `expect`: unchanged (`["Closing count: 14 of 15 back, 1 unaccounted.", "Correction recorded."]`). Once corrected to 15, nothing is missing, the count step folds to one line (mockups R11/R12), and the swab viewer goes with it, so its strings cannot be end-of-beat expectations.
    - `before`: `["Closing count: 14 of 15 back, 1 unaccounted.", "Saw 14 of 15 gauze swabs."]`, checked after "Record closing count", while the step is still open with 1 missing.
    - `beats.test.mjs:85`: allow `kumar-count`'s `"Saw 14 of 15 gauze swabs."` in `before` only, with a comment ("the count step folds once corrected").
    - `files`: `["swabs-closing.mp4"]`.
    - `say`: "Surgery begins, the pack opens at 15 swabs, the camera counts 14 back, and the count is corrected to 15 when one is found." (it passes the regex)
    - `keyed`: "SAM 3.1 video call for the swab camera count. The label reads SAM 3.1. Switch: SWABS_LIVE."
  - `steps.mjs` `kumar-count`: after "Record pack opened", `await H.file("Swab camera count", "eval/p3/swabs-closing.mp4"); await H.waitText("Camera count: 14");`, then "Record closing count" with no fill, `before`, fill 15, "Correct the count".
  - The demo document: the `kumar-count` block (Clicks and narration; On screen is unchanged), a `kumar-count` Keyed row, `swabs-closing.mp4` in the media list, and `SWABS_LIVE` beside the other switches.
  - The seconds stay 9, so 58/58/58 holds.
- [ ] **Step 5: Run** every suite, the build and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 425, care ≥ 205, demo 36, the demo green at 31 beats.
- [ ] **Step 6: Commit** (`backend eval/p3/make_clips.py frontend ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: camera and photo reads arrive as prefilled values, and the record keeps the evidence and any correction".

---

### Task 9: Brown bag: the day plan and record answers (§2.6) · 2.5 d (20 h)

**Files:**
- Modify: `backend/app/journey/medicines.py` (rows add `name`, `key`, `rx_strength`; add `day_plan`), `record.py` (prescription lines carry `key`; add `medicine_answer`), `ask_api.py` (rule before the model; mark route), `ask.py` (medicines entries add `marks`), `api.py` (`view` adds `day_plan`, one line), `stories.py` (`plain`, `patient_line` for `brownbag.marked`)
- Create: `backend/tests/test_brownbag.py`, `frontend/src/care/brownbag.js`, `brownbag.test.js`, `frontend/src/care/MedicinesFromHome.jsx`, `frontend/src/care/DayPlan.jsx`
- Modify: `frontend/src/care/Today.jsx` (the medicines fold), `Ask.jsx` (prefill from router state), `AskCards.jsx` (`BotCard` shows `answer.text || NOT_FOUND`), `Thread.jsx` (marks), `thread.js` (marks count as unread), `Evidence.jsx` (strip colours), `Chart.jsx`, `care.css`
- Demo: `beats.mjs` (`das-ask.keyed`, `iyer-meds.expect`), the demo document

**Interfaces:**
- `match_medicines` rows add `"name": strip["name_as_read"]`, `"key": key_of(name)`, and `"rx_strength"` (the prescription or ward-order strength, `""` for an unprescribed row). The existing `why` texts stay.
- `day_plan(rx, read) -> dict | None` (`None` without a prescription). `read` is the latest `medicines.read` payload or `None`.
  - Returns `{"slots": {"morning": [], "afternoon": [], "night": []}, "as_needed": [], "as_written": [], "not_prescribed": [], "photo_id": str | None, "evidence_id": str | None}`.
  - Each plan item is `{"key", "medicine", "text", "region"}`. `text` is exactly `schedule_text(built_row)`, except in `as_written`, where it is the doctor's dose code, then timing, days and note joined by `"; "` (R26).
  - `region` is the index of the first region whose `row` points at a read row with the same `key`, else `None`.
  - `not_prescribed`: `[{"name", "read", "region"}]` for read rows with `flag == "not_prescribed"`.
  - A slot gets the item when the slot amount is not `""`. `as_needed` holds doses matching `^(sos|prn|as needed)$` (any case); any other unreadable code goes to `as_written`.
- `record_lines`: prescription lines add `"key": row["key"]`. Other lines have no `key`.
- `medicine_answer(question, lines, read_rows) -> dict | None` (R27):
  - Take the lower-case alphabetic tokens of the question, and their 1- and 2-token windows, each through `key_of`.
  - Prescription lines whose `key` is in that set → `{"answer": FOUND, "sources": those lines[:3], "found": True}`.
  - Else read rows with `flag == "not_prescribed"` whose `key` is in the set → `{"answer": f"{row['name'].capitalize()} is not on your prescription. Ask Dr. Rao.", "sources": [], "found": False}`.
  - Else `None`.
  - `ask_bot` calls it first. A non-None result is written with `source: "rules"` and `calls: []`.
- `POST /journey/episodes/{episode_id}/medicines/{read_id}/mark`, body `MarkIn(At)`: `row: int ≥ 0`, `mark: Literal["noted", "discuss"]`, `by: str` (1–80).
  - 403 `Only the doctor marks medicines from home.` unless `by.startswith("Dr. ")` (R28).
  - 404 `Medicines photo not found` unless `read_id` is a `medicines.read` of this episode.
  - 422 `No such row in that photo.` when `row >= len(rows)`.
  - Writes `brownbag.marked {"read_id", "row", "mark", "name", "read", "by"}`.
- `ask_view` medicines entries add `"marks": [{"row", "mark", "by", "at_ms"}]` (latest per row, R33) and `"regions"`.
- `plain(brownbag.marked)`: `f"{by} marked {read}: {'noted' if mark == 'noted' else 'discuss with the patient'}."`. `patient_line`: noted → `f"{short_name(by)} noted {read}."`; discuss → `f"{short_name(by)} will talk to you about {name}."`
- `brownbag.js` (pure):
  - `stripMatch(row) -> "prescribed" | "strength_differs" | "not_prescribed" | "not_read"`.
  - `stripTone(match)`: `{ prescribed: "green", strength_differs: "amber", not_prescribed: "red", not_read: "grey" }`.
  - `stripLabel(region, rows)`:
    - `not read` when `region.row == null`;
    - prescribed `` `${read} ✓` ``;
    - strength differs `` `${read} · prescribed ${rx_strength}` ``;
    - not prescribed `` `${read} · not prescribed` ``.
  - `cropStyle(bbox, url)`: `{ backgroundImage: `url("${url}")`, backgroundSize: `${100 / w}% ${100 / h}%`, backgroundPosition: `${pos(x, w)}% ${pos(y, h)}%` }`, with `pos(v, s) = s >= 1 ? 0 : +(v / (1 - s) * 100).toFixed(2)`. `null` for a null bbox.
  - `askAboutText(read)`: `` `About ${read} from my medicines photo: it is not on my prescription.` `` (R30).
  - `markLine(mark)`: `` `Noted by ${displayName(by)}` `` / `` `Discuss with patient · ${displayName(by)}` ``.
- UI:
  - `DayPlan({ plan, photoUrl, onAsk })` in the Today "My medicines" fold (R25), replacing `Medicines`; keep `Reminders`. It shows a 4-row grid, `Morning`, `Afternoon`, `Night`, `As needed`, then `As written` when non-empty. Each item shows the medicine, `text`, and a 48 px crop `<span className="crop" style={cropStyle(...)} />` when `region != null`. Under the grid: `Not on your prescription: {names joined by ", "}`, with one `Ask Dr. Rao` button per name; it navigates to `/ask` with `state: { ask: askAboutText(read) }`.
  - `Ask.jsx` reads `useLocation().state?.ask` once and fills the "Ask Dr. Rao" box through the existing `fill` (the patient presses send).
  - Empty plan: "Your medicines appear here once the doctor's prescription is in."
  - `MedicinesFromHome({ view, role, act })` on the chart, after `Photos`, when `view.ask.medicines` is not empty (R29): `<section className="card" aria-label="Medicines from home">`. It shows one row per read row: the tone dot, a crop, `stripLabel`, the prescription line (`row.medicine: row.schedule` or `row.why`), and the mark line. For the doctor it adds `Noted` and `Discuss with patient` buttons (`by: DOCTOR`).
  - `Evidence` colours medicines regions by `stripTone` and labels them with `stripLabel` (green `#2e7d32`, amber `#b26a00`, red `#c62828`, grey `#757575`).
  - `Thread` medicines row lists `markLine` per marked row. `thread.js` `unreadCount` counts marks (Task 1 contract).

- [ ] **Step 1: Write the failing tests** (`backend/tests/test_brownbag.py`; use `KUMAR_STRIPS` from `tests.test_p4_medicines`, `_home` and `_patients` from `tests.test_p4_ask`):

```python
RX = from_document(document_for("R. Kumar, 58 M (synthetic)"), source="demo")

def _read():
    strips = [{"name_as_read": s["name"], "strength": s["strength"]} for s in KUMAR_STRIPS]
    rows = match_medicines(strips, RX)["rows"]
    return {"rows": rows, "regions": [{"bbox": [0, i / 4, 1, 0.2], "label": r["read"], "value": r["read"], "row": i} for i, r in enumerate(rows)], "photo_id": "p", "evidence_id": "e" * 32}

def test_day_plan_slots_quote_schedule_text():
    plan = day_plan(RX, _read())
    built = {r["key"]: r for r in build(RX)}
    assert [i["key"] for i in plan["slots"]["morning"]] == ["metoprolol", "amlodipine", "pantoprazole"]
    assert [i["key"] for i in plan["slots"]["night"]] == ["metoprolol"] and plan["slots"]["afternoon"] == []
    assert [i["key"] for i in plan["as_needed"]] == ["paracetamol"]
    for item in plan["slots"]["morning"] + plan["as_needed"]:
        assert item["text"] == schedule_text(built[item["key"]])
    assert plan["slots"]["morning"][0]["region"] == 0 and plan["as_needed"][0]["region"] is None
    assert plan["not_prescribed"] == [{"name": "Cetirizine", "read": "Cetirizine 10 mg", "region": 3}]

def test_day_plan_unreadable_dose_is_as_written():
    rx = {**RX, "rows": [{**RX["rows"][0], "dose": "1 tab thrice", "duration": "5 days"}]}
    plan = day_plan(rx, None)
    assert plan["as_written"][0]["text"] == "1 tab thrice; After food; for 5 days" and plan["as_needed"] == []
    assert day_plan(None, None) is None

def test_medicine_rule_quotes_the_row():
    lines = [l for l in record_lines([{"id": "rx", "episode_id": "e", "event_type": "rx.ordered", "ts_ms": 0, "payload": RX}])]
    out = medicine_answer("When do I take amlodipine?", lines, [])
    amlo = next(l for l in lines if l.get("key") == "amlodipine")
    assert out == {"answer": "Here is what your record says.", "sources": [amlo], "found": True}
    assert schedule_text({r["key"]: r for r in build(RX)}["amlodipine"]) in amlo["text"]

def test_medicine_rule_is_key_equality():
    lines = record_lines([{"id": "rx", "episode_id": "e", "event_type": "rx.ordered", "ts_ms": 0, "payload": RX}])
    assert medicine_answer("What about amlo?", lines, []) is None
    assert medicine_answer("What about amlodipines?", lines, []) is None

def test_medicine_rule_not_prescribed():
    lines = record_lines([{"id": "rx", "episode_id": "e", "event_type": "rx.ordered", "ts_ms": 0, "payload": RX}])
    out = medicine_answer("Can I take the cetirizine?", lines, _read()["rows"])
    assert out == {"answer": "Cetirizine is not on your prescription. Ask Dr. Rao.", "sources": [], "found": False}

def test_bot_answers_a_medicine_question_with_no_model_call(tmp_path, monkeypatch):
    # keyed client (_keyed settings); monkeypatch SparkAdapter.write to raise AssertionError
    # POST ask/bot "When do I take amlodipine?" -> 200, answer source "rules", calls == []

def test_mark_is_doctor_only(tmp_path):
    # Kumar home, POST ask/medicines with ("meds-kumar.png", PNG) -> read_id
    # by "Nurse Meena (synthetic)" -> 403; unknown read -> 404; row 9 -> 422; mark "maybe" -> 422
    # by "Dr. A. Rao (synthetic)", row 3, "discuss" -> 200; ask.medicines[0].marks == [{"row": 3, "mark": "discuss", ...}]
    # patient timeline line == "Dr. A. Rao will talk to you about Cetirizine."
    # a second mark on row 3 "noted" -> marks holds only the "noted" one

def test_brownbag_copy_has_no_advice():
    rows = _read()["rows"]
    lines = record_lines([{"id": "rx", "episode_id": "e", "event_type": "rx.ordered", "ts_ms": 0, "payload": RX}])
    said = [medicine_answer(q, lines, rows) for q in ("When do I take amlodipine?", "Can I take the cetirizine?")]
    texts = [s["answer"] for s in said] + [l["text"] for s in said for l in s["sources"]]
    plan = day_plan(RX, _read())
    texts += [i["text"] for slot in plan["slots"].values() for i in slot] + [i["text"] for i in plan["as_needed"]]
    for t in texts:
        assert not ADVICE.search(t), t
```

`brownbag.test.js`:

```js
const rows = [
  { read: "Metoprolol 25 mg", prescribed: true, flag: null, rx_strength: "25 mg" },
  { read: "Amlodipine 10 mg", prescribed: true, flag: "strength_differs", rx_strength: "5 mg" },
  { read: "Cetirizine 10 mg", prescribed: false, flag: "not_prescribed", rx_strength: "" },
];
test("strip labels and tones", () => {
  assert.deepEqual([0, 1, 2, null].map((row) => stripLabel({ row }, rows)), ["Metoprolol 25 mg ✓", "Amlodipine 10 mg · prescribed 5 mg", "Cetirizine 10 mg · not prescribed", "not read"]);
  assert.deepEqual(rows.map((r) => stripTone(stripMatch(r))), ["green", "amber", "red"]);
});
test("cropStyle shows the box", () => {
  assert.deepEqual(cropStyle([0.1, 0.2, 0.5, 0.25], "/p"), { backgroundImage: 'url("/p")', backgroundSize: "200% 400%", backgroundPosition: "20% 26.67%" });
  assert.equal(cropStyle([0, 0, 1, 1], "/p").backgroundPosition, "0% 0%");
  assert.equal(cropStyle(null, "/p"), null);
});
test("brown-bag copy has no advice words", () => {
  for (const s of [askAboutText("Cetirizine 10 mg"), "Not on your prescription: Cetirizine 10 mg", "Morning", "Afternoon", "Night", "As needed", "As written", "Noted", "Discuss with patient", "Medicines from home", markLine({ mark: "discuss", by: "Dr. A. Rao (synthetic)" })]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run** the new tests. Expected: FAIL.
- [ ] **Step 3: Implement.** Check `wc -l` stays under 500 for `api.py`, `ask_api.py` and `record.py`.
- [ ] **Step 4: Demo.**
  - `das-ask.keyed` becomes "No model call: a medicine question is answered by quoting the prescription row. The label reads Rules (no model) with or without a key." The expected strings do not change ("Here is what your record says.", "Amlodipine", "Rules (no model)").
  - `iyer-meds.expect` adds `"Ibuprofen 400 mg · not prescribed"` (the region list in the thread's viewer).
  - The demo document: the `das-ask` Keyed row, the `iyer-meds` On screen line.
- [ ] **Step 5: Run** every suite, the build and `make demo-check MODEL_API_KEY=`. Expected: backend ≥ 433, care ≥ 208, demo 36, the demo green. By hand at 390 px: Kumar at home, after a medicines photo, the "My medicines" fold shows the grid with crops and the Cetirizine line, and nothing scrolls sideways.
- [ ] **Step 6: Commit** (`backend frontend ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: the patient's medicines become a day plan from the prescription, and medicine questions quote the prescription row".

---

### Task 10: The opening demo beat (D3) and the verification sweep · 1.5 d (12 h)

**Files:**
- Modify: `frontend/scripts/demo/beats.mjs`, `beats.test.mjs`, `steps.mjs`, `helpers.mjs` (`dockLink`), the demo document (new block, every later timestamp +0:20, the Summary totals, the Keyed table)
- Scratch (not committed): `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-hackathon-hackathon26/9c2f4abf-956d-48ef-93f1-f23a07ae1f69/scratchpad/sweep-ai.mjs`

**Interfaces:**
- New beat, second in `BEATS` (R34):

```js
{
  id: "ai", path: "intro", role: "none", seconds: 20, film: true,
  say: "The AI at work page lists the four Muse models on this ward; a sample tray photo shows SAM 3.1 boxes, the counts and a plain explanation.",
  clicks: ['Link "AI at work" in the demo dock', 'Button "Try sample" in "SAM 3.1"'],
  expect: ["AI at work", "Muse Voice", "Muse Spark 1.3", "SAM 3.1", "Muse Spark Open", "Saw 2 of 3 needle holders.", "2 (missing)"],
  keyed: "Try sample makes live calls with a key: SAM 3.1 runs one image call per tray concept (7). The chip reads live in place of Sample or prepared.",
}
```

  The expected strings avoid the words Sample and prepared, so the beat holds before and after Task 5 (R13 keeps the counts).
- `helpers.mjs`: `dockLink: (name) => page.getByRole("region", { name: "Demo" }).getByRole("link", { name, exact: true }).click()`.
- `steps.mjs`: `async ai(H) { await H.dockLink("AI at work"); await H.click("Try sample", "SAM 3.1"); }`. The next beat `das-rx` opens the chart from the main nav, which `/ai` keeps.
- `beats.test.mjs`:
  - `BEATS.length` is 32.
  - The path test: the leading beats are `["intro", "intro"]`; the middle runs das, kumar, iyer; close is last.
  - Film is at most 200 s; `roleSeconds(BEATS).none === 26`; each role 54–62 s.
  - `by.ai.expect` includes `"Saw 2 of 3 needle holders."`.
- The demo document:
  - the block `` #### `ai` · 0:03 · none · 20 s `` with Clicks, On screen and narration;
  - every later heading's start time +0:20 (`das-rx` 0:23 … `close` at its old time + 0:20);
  - Summary: "The film is three paths and an opening in 3:20" and "Totals: doctor 58 s, nurse 58 s, patient 58 s, intro, AI at work and close 26 s, film 3:20.";
  - a Keyed row for `ai`.

- [ ] **Step 1: Write the failing demo tests** (the `beats.test.mjs` changes above). Run `node --test scripts/demo/*.test.mjs`. Expected: FAIL (31 beats, no `ai` step).
- [ ] **Step 2: Implement** the beat, the step, the helper and the document. Run the demo unit tests. Expected: demo ≥ 37 pass.
- [ ] **Step 3: Run `make demo-check MODEL_API_KEY=`.** Expected: "DEMO CHECK PASSED: 32 beats; filmed doctor 58 s, nurse 58 s, patient 58 s, total 200 s".
- [ ] **Step 4: Sweep every suite.** Backend, care and demo pass at or above 433 / 208 / 37, and `npm run build` is clean. Check sizes with `wc -l backend/app/journey/*.py frontend/src/care/*.js frontend/src/care/*.jsx frontend/src/care/care.css`; every file is under 500 lines.
- [ ] **Step 5: Browser sweep.** Start `make dev CG_API_PORT=8200 CG_WEB_PORT=5273 MODEL_API_KEY=` (never 8100/5173). Write `sweep-ai.mjs` with playwright-core (reuse `findChrome` from `frontend/scripts/demo/chrome.mjs`). At 1200 px and at 390 × 844, check:
  - `/ai`: four cards; each Try sample works; `document.documentElement.scrollWidth <= 390` at phone width.
  - A tray check, a set-up check, the swab camera count, a strip proof, a monitor proof and a medicines photo each show boxes on the right objects; "Show ignored" shows the two dashed needle-holder boxes on the tray.
  - A chip reads `· Sample` while fixtures are handmade.
  - Each timeline thumbnail opens the viewer, and "Captured to record" links to its line.
  - Ask → My messages lists everything sent; the Ask tab dot appears after a doctor answer and clears on opening Ask.
  - Today → My medicines shows the day plan with crops.
  - No console errors and no failed requests other than deliberate 409s, each shown inside its card.
  Stop the servers.
- [ ] **Step 6: Fix** any failure in the owning task's files, then run Steps 3–4 again.
- [ ] **Step 7: Commit** (`frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`, plus any fixes). Message: "Count Guard: the demo opens on AI at work, with a sample run of SAM 3.1 (3:20 in all)". List the changed files in the body.

---

## Estimate

| Task | What | Days | Hours |
|---|---|---|---|
| 1 | Two-way threads (Part 1) | 1.5 | 12 |
| 2 | `calls` on every model result | 0.5 | 4 |
| 3 | Evidence sidecar for video and photo checks | 1 | 8 |
| 4 | Photo regions, SAM finds and Spark reads (D1(b)) | 1 | 8 |
| 5 | Fixture recording script (D2), owner runs it | 0.5 | 4 |
| 6 | Evidence viewer | 2 | 16 |
| 7 | AI at work dashboard | 1.5 | 12 |
| 8 | Capture into actions and notes, incl. the swab camera count | 2 | 16 |
| 9 | Brown bag day plan, record answers, doctor marks | 2.5 | 20 |
| 10 | Opening beat (D3) and verification sweep | 1.5 | 12 |
| | **Total** | **14** | **112** |

The spec estimated 13 days (Part 1 1.5 + Part 2 11.5). The difference is the swab camera count (R18, +0.5 d), which the spec's §2.5 table needs and the current chart did not have, and the browser sweep folded into Task 10 (+0.5 d). The owner's recording run (Task 5) is about 41 model requests across 10 assets; it does not block Tasks 6–10, which build and test on handmade fixtures.

Order and dependencies: 1 stands alone. 2 → 3 → 4 → 5. 3 and 4 → 6 → 7, 8, 9. 7 and 8 → 10.

## Self-review against the spec

**Coverage:**

| Spec item | Task |
|---|---|
| P1 patient "My messages", newest first, one row per thing sent (record ask, doctor ask, healing photo, medicine photo, check-in) | 1 (`threadItems`, `Thread`) |
| P1 statuses `Waiting for Dr. Rao · 6 min`, `Answered 10:04`, `Answered from your record`, `Seen by Nurse Meena` | 1 (`threadStatus`, R20 for the unworded ones) |
| P1 answer with who answered and how; quoted record lines | 1 (`answerByLine`, sources) |
| P1 unread dot on Ask and a line on the Today status card; read state per viewer, local | 1 (`unreadCount`, `unreadLine`, R21) |
| P1 staff "Conversation with the patient": open on top, answered in a fold; nurse read-only; "Seen by" | 1 (`inboxGroups`, `checkinLine`, R22, R23) |
| P1 `checkin.seen`, idempotent; `ask_view` returns record asks with a `to`; only the seen endpoint is new | 1 (R19) |
| P1 tests: waiting, answered, record-answered, seen, unread | 1 |
| 2.1 four model cards (role, mode, calls, median latency, last result thumbnail with boxes), Try sample, recent AI events opening the viewer, Live/Prepared indicator | 7 (R7, R8, R9) |
| 2.1 `GET /journey/ai/summary`; latency recorded at each call site | 7, 2 (R2, R3, R4) |
| 2.2 one viewer: boxes with concept, id, score; one colour per concept; dashed ignored; Show ignored | 6 |
| 2.2 frame scrubber, count sparkline, jump to best frame; filmstrip for photos | 6 (R11) |
| 2.2 values read on monitor regions and strips (coloured by match) | 4, 6, 9 |
| 2.2 explanation: 1–3 template sentences, no-advice, Raw output | 6 (R12) |
| 2.2 Captured to record link | 3 (`cited_by`), 6, 8 |
| 2.3 frames sidecar capped at 120; read_photo regions via SAM + Spark; fixtures with raw and regions/frames; ms and model | 3, 4, 5, 2 |
| D1(b) SAM regions then Spark reads | 4 (R14) |
| D2 re-record once with the owner's key; tests read fixtures only | 5 (R13) |
| 2.5 monitor photo prefills obs fields, saved event keeps evidence and source; proof thumbnail | 4, 8 (R15, R16, R35) |
| 2.5 tray check line and alert unchanged, evidence on the event | 3, 6 |
| 2.5 swab camera count prefills Back; closing keeps `evidence_id` and `via: camera` | 8 (R18) |
| 2.5 medicine photo boxes coloured by match into the brown-bag list and "Medicines from home" | 4, 9 (R29) |
| 2.5 wound photo unchanged | 1 (healing photo row shows the photo only) |
| 2.5 timeline and audit 48 px thumbnail with model chip | 6 (`EvidenceThumb`), 8 (`timeline_items`) |
| 2.5 corrections keep `read` and `saved`; "Read 118, saved 120 by Nurse Meena" | 8 (`correctionLine`, R17) |
| 2.6 capture: strips boxed and coloured green/amber/red/grey with the spec's labels | 4, 9 (`stripLabel`) |
| 2.6 day plan from the prescription only; Morning/Afternoon/Night + As needed; schedule text beside the patient's own crop | 9 (`day_plan`, `cropStyle`, R25, R26) |
| 2.6 "Not on your prescription" with Ask Dr. Rao that fills (not sends) a question | 9 (R30) |
| 2.6 record bot quotes the prescription row; fixed sentence for unprescribed; key_of, never substring | 9 (R27) |
| 2.6 staff Medicines from home; Noted / Discuss; patient-visible note; record marks | 9 (R28, R33) |
| 2.6 thread shows each brown-bag photo and its marks | 1, 9 |
| 2.7 opening beat with Live/Prepared visible; Try sample on SAM opens the viewer | 10 (R34) |
| 2.7 tray and swab beats open the viewer | 6 (`kumar-tray`), 8 (`kumar-count`) |
| 2.7 beats, steps and video script change together; demo-check green offline | every task |
| D3 20 s opening beat; roles stay 58 s; total about 3:20 | 10 |
| Constraints: no advice; no live calls in tests; files < 500; validated input; ports; commits only when asked | Global Constraints; each task's tests |

**Name consistency across tasks.** Each name is defined once and used with the same spelling everywhere:
- `calls`, `call_of`, `mode_of` come from Task 2. They are used in Tasks 3, 4, 7 and 8.
- `evidence_id`, `EVIDENCE_ID`, `held_by` and the C4/C5 shapes come from Task 3. They are used in Tasks 4, 6, 7, 8 and 9.
- `frames_from` and `records_of` come from Task 3. They are used in Task 5.
- `pair_regions`, `READER_CONCEPTS`, `monitor_values` and `strip_values` come from Task 4. They are used in Tasks 5 and 7.
- `Evidence`, `EvidenceThumb`, `explain`, `regionLabel`, `chipText`, `seenCell` and `capturedLine` come from Task 6. They are used in Tasks 7, 8 and 9.
- `threadItems`, `unreadCount` and `unseenCheckins` come from Task 1. Task 9 extends `unreadCount` with marks.
- `swabs.counted`, `count.camera` and `SWABS_LIVE` come from Task 8. Task 5's asset table names `swabs-closing`, and records it once Task 8 has added it.

**Demo safety per task:**

| Task | Demo change |
|---|---|
| 1 | None (strings stay visible in the thread) |
| 4 | `keyed` of `kumar-paracetamol` and `iyer-meds` |
| 5 | Owner handover section only |
| 6 | `kumar-tray.expect` +1 |
| 8 | `MEDIA` +1, `kumar-count` clicks, before, say and keyed; `beats.test.mjs` before-exception |
| 9 | `das-ask.keyed`, `iyer-meds.expect` +1 |
| 10 | New beat `ai`, `beats.test.mjs`, `dockLink`, the document timings and totals |
| 2, 3, 7 | None; each still runs `make demo-check` |

Roles stay 58/58/58 s throughout. The film grows from 180 s to 200 s in Task 10 only.

**Deliberately left out:** Part 3 (the ask bar, the monitoring board, the live Spark Open agent on the ward, R8); nurse capture of home medicines at admission (R29); re-recording the voice fixtures (they carry transcripts, not boxes).

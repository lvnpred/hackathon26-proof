# Count Guard v3 AI showcase: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use superpowers:subagent-driven-development to implement this plan task by task.

**Goal:** Patients and staff see full two-way threads. A model dashboard and an evidence viewer (boxes, values, explanations) show what each Muse model did.

**Architecture:**
- Model results keep their raw detections in a JSON sidecar next to the media file.
- The event holds a pointer to the sidecar, plus model, latency and mode.
- One React `Evidence` component draws boxes on a canvas from normalised bboxes.
- A summary endpoint folds model events into per-model cards.

**Spec:** `docs/superpowers/specs/2026-10-30-count-guard-v3-ai-showcase-design.md` (Parts 1–2; Part 3 is estimate only).

**Owner decisions, decided 30 Oct:**
- D1(b): SAM finds the regions and Spark reads the values.
- D2: re-record the fixtures live, once.
- D3: a 20 s opening beat.

Build order: the UX mockups plan (`2026-10-30-count-guard-v3-ux-mockups.md`) first, then this plan, Task 1 to Task 10.

## Global constraints

- `make demo-check MODEL_API_KEY=` stays green. Beats, steps and the video script change together.
- Backend, care and demo node tests stay green, and every behaviour change gets a test.
- No live model calls in tests or checks. Files stay under 500 lines. The no-advice regex applies to new copy.

## Review focus

1. A video with 0 detections, or every detection below threshold: the viewer shows the frame with no boxes and the sentence "Nothing found above confidence 0.45", not an error.
2. Photo regions and Spark values that differ in number: unpaired regions show "not read", and unpaired values are listed without a box.
3. A sidecar missing (old events from before this change): the viewer falls back to the count table only.
4. The patient thread with 0 items: an empty state that names how to ask.
5. Large videos: frames are capped at 120, and the scrubber stays responsive.

---

### Task 1: Patient and staff threads (Part 1), 1.5 d

**Files:**
- `backend/app/journey/ask.py` (`ask_view` adds record asks and check-ins with `seen_by`)
- `ask_api.py` (`POST …/checkins/{id}/seen`)
- `frontend/src/care/AskCards.jsx`, a new `Thread.jsx`, `AskInbox.jsx` (answered fold), `Today.jsx` (answer line)
- `askText.js` (status wording)
- Tests: `backend/tests/test_threads.py`, `askText.test.js`

**Status wording**, produced by `threadStatus(item, nowMs)` in `askText.js`:

| Status | Wording |
|---|---|
| waiting | `Waiting for Dr. Rao · 6 min` |
| answered | `Answered 10:04` |
| answered from the record | `Answered from your record` |
| seen | `Seen by Nurse Meena` |

**Tests:**
- every status above;
- unread is computed from a `lastOpenedMs` argument;
- `seen` is idempotent (a second POST adds no event).

### Task 2: Model metadata on every result, 0.5 d

- `journey/live.py`: `transcribe`, `spark_text`, `read_photo`, `segment_clip` and `segment_photos` each return `ms` (wall time measured around the adapter call) and `model`.
- The call sites in `media_api.py`, `video_api.py` and `ask_api.py` copy both into the event payload.
- Test: fake adapters return a fixed result. Assert that `ms` is an int ≥ 0 and `model` equals the settings value.

### Task 3: Keep detections as a sidecar, 1 d

- `journey/video.py`: add `frames_from(records, fps, min_score, cap=120) -> list[{t, objects:[{id,label,bbox,score,kept}]}]`.
- `video_api.py` writes `<media_id>.detections.json` beside the media file and stores `detections_id` on the check event.
- Add `GET /journey/episodes/{id}/detections/{detections_id}`.
- Tests:
  - the cap of 120 frames;
  - `kept=false` below `min_score`;
  - a 404 for an unknown id;
  - old events with no sidecar still render the count.

### Task 4: Photo regions, SAM finds and Spark reads (D1b), 1 d

- `journey/live.py`: `read_photo` also calls `segment_photos` with `READER_CONCEPTS = {"strip": ["blister strip"], "monitor": ["digital display"]}`.
- `pair_regions(regions, values) -> list[{bbox, label, value}]` sorts regions top to bottom, then left to right, and zips them with the values. Leftover regions get `value: None`; leftover values get `bbox: None`.
- Tests: equal counts, more regions, more values, and zero regions.

### Task 5: Re-record fixtures with boxes (D2), 0.5 d, needs the owner's key

- `scripts/record_fixtures.py` runs each demo asset once live and writes `journey/prepared/<asset>.json` with `raw`, `frames`/`regions`, `ms` and `model`.
- It is never run by tests. The fixture schema is checked by `test_prepared_schema.py`.
- The owner runs it once. About 10 calls.

### Task 6: Evidence viewer, 2 d

- `frontend/src/care/Evidence.jsx` holds the canvas overlay and the side table.
- `evidence.js` holds pure helpers, each with tests:
  - `boxesAt(frames, t)`;
  - `countSeries(frames, concept)`;
  - `explain(expected, detections, minScore)`, which returns 1–3 template sentences and passes the no-advice regex;
  - `colourFor(concept)`, which is stable.
- Features: a frame scrubber, "Show ignored", "Raw output", and a "Captured to record" link.
- Wired into `VideoCheck.jsx`, `VideoChecks.jsx`, the medicine photo card and the monitor photo result.

### Task 7: AI dashboard, 1.5 d

- Backend: `journey/ai_summary.py` provides `summary(events) -> {models:[{key,name,role,mode,calls,median_ms,last}], recent:[…]}`. The route is `GET /journey/ai/summary`.
- Frontend: `/ai` route, `AiDashboard.jsx`, a pipeline strip, model cards, and "Try sample" (POSTs the bundled asset through the existing upload endpoints, then opens `Evidence`).
- Tests: the summary folds the mode (live, prepared or failed) and computes the median correctly. The dashboard renders four cards from a fixture.

### Task 8: Capture into actions and notes (spec §2.5), 1.5 d

**Backend:**
- `obs.recorded`, `count.closing` and `tray.checked` accept an optional `evidence_id`.
- When the saved value differs from the model's read, the event keeps both, as `read: {...}` and `saved: {...}`.
- `count.closing` accepts `via: "camera"`.
- Tests:
  - the evidence id is stored;
  - an evidence id from another episode returns 422 (validated at the boundary);
  - `read` and `saved` are both kept when they differ.

**Frontend:**
- `ObsForm.jsx`: "Read from monitor photo" prefills the fields from `regions` and remembers `evidence_id`.
- The theatre count step prefills **Back** from the camera count.
- `Timeline.jsx` and `TaskProof.jsx` show `EvidenceThumb` (48 px, boxes and a model chip) for events with `evidence_id`.
- Pure helper `prefillObs(regions) -> {sbp,dbp,hr,spo2,temp}`, with tests for missing and unreadable regions.

### Task 9: Brown bag day plan and record answers (spec §2.6), 2.5 d

**Backend:**
- `medicines.read` stores `regions` (bbox, read, match, prescribed) and `evidence_id`.
- `journey/medicines.py`: `day_plan(rx, strips) -> {slots:{morning:[…],afternoon:[…],night:[…]}, as_needed:[…], not_prescribed:[…]}`. Each item is `{medicine, text, region_index|None}`, and `text` is exactly `schedule_text(row)`.
- The record bot (`ask_api.py` record route) adds a medicine-question rule:
  - if a known `key_of` name appears in the question, answer by quoting the prescription row;
  - a name read from the photo but not on the prescription gets the fixed sentence "<Name> is not on your prescription. Ask Dr. Rao.";
  - add no other wording.
- New `brownbag.marked` event `{read_id, row, mark: noted|discuss, by}` from `POST …/medicines/{read_id}/mark`, restricted to the doctor.
- Tests:
  - `day_plan` for 1-0-1, SOS and an unreadable dose;
  - matching is key equality (no substring match, so "Amlodipine" does not match "Amlo");
  - the record answer quotes `schedule_text` verbatim;
  - the no-advice regex passes on every generated sentence;
  - only the doctor may mark.

**Frontend:**
- `MyCare.jsx`: a day plan grid with strip crops. The crop is a CSS `object-position`/`clip-path` taken from the bbox; there is no server crop.
- A "Not on your prescription" list with "Ask Dr. Rao", which prefills the question box.
- Doctor chart and nurse admission: a `MedicinesFromHome.jsx` card with Noted / Discuss buttons.
- The patient thread shows the marks.
- Pure helper `cropStyle(bbox)` with tests.

### Task 10: Demo update (D3), 1 d

- Add a new beat 0, "AI at work". The tray and count beats open the evidence viewer.
- Update `beats.mjs`, `steps.mjs` and the video script, keeping the doc test aligned.
- `make demo-check` passes offline.

**Total for Parts 1–2: about 13.5 working days** (Task 1: 1.5 d; Tasks 2–7: 6.5 d; Tasks 8–9: 4 d; Task 10: 1 d; final review and fixes: 0.5 d). This comes after M1–M7 (5.5 d). The fixture recording (Task 5) waits on the owner's key and the filmed tray video. Until then, Tasks 6–10 build and test against hand-made fixtures marked `"handmade": true`, which the dashboard labels "Sample".

### Part 3 (later): milestones only

1. Agent tools and role scoping (3 d).
2. Ask bar UI with citations (3 d).
3. Rule watcher and monitoring board (3 d).
4. Offline eval set (2 d).
5. Demo beat (1 d).

Write a full plan when Part 3 is scheduled.

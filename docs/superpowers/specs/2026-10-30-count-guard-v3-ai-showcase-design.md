# Count Guard v3: AI showcase, two-way conversations, AI-native ward (design)

Owner request (30 Oct):
- Patients should see their own questions and the answers. The same applies wherever someone sends something and waits for a reply.
- The most important part of the demo is showing what the Muse models can do (Count Guard, actions and the rest).
- A dashboard screen should present this before the flows.
- Images need proper bounding boxes and explanations. Values tracked from images should be shown visually and captured into the record.
- Later: an AI-native interface for asking about a patient's status by voice or text, plus AI-native monitoring. For now, only a spec, a plan and an estimate.

## Summary

| Part | What | When | Estimate |
|---|---|---|---|
| 1 | **Two-way threads.** Whoever sends a question, photo or check-in sees it with its status and answer. Staff see the answered history, not only the open items. | Build now | 1.5 days |
| 2 | **AI showcase.** An "AI at work" dashboard opens the demo. One evidence viewer shows bounding boxes, values read and a plain explanation for every image or video the models touch. The values read are captured into actions and notes (§2.5). Brown-bag medicines get a day plan (§2.6). | Build now | 11.5 days |
| 3 | **AI-native ward.** An ask bar (voice or text) answers questions about any patient, citing record lines. A monitoring board watches the event stream and explains each alert. | Later | 12 days |
| — | UX mockups M1–M7 from the UX review (artifact TbgLk4v2j8u9hoeD9y31gc) | Separate | 5.5 days |

Estimates are working days for one developer using the subagent workflow, including tests and demo-check updates. Part 2 is the demo-critical one.

### Owner decisions (decided 30 Oct: "go with recommendations")

Build order: the UX mockups M1–M7 (`2026-10-30-count-guard-v3-ux-mockups-design.md`) first, then Part 1, then Part 2. The owner also added, the same day:
- Bounding boxes appear **on the uploaded image or video itself**.
- The values read are **captured into the actions and notes** where they apply (§2.5).
- The patient **brown-bag** flow is in scope: capture the medicines, then answer "when do I take them?" from the prescription (§2.6).

Part 3 is now discussed in `2026-10-30-count-guard-ai-native-clinic-options.md`.

| # | Question | Decided |
|---|---|---|
| D1 | Where do boxes on **photo reads** (medicine strips, monitor) come from? (a) Ask Spark for values and boxes in one JSON reply. (b) SAM 3.1 finds the regions, then Spark reads the values. | **(b)**. SAM is the segmentation model, so its boxes are reliable. It also shows two Muse models working together, which makes a stronger demo. |
| D2 | Prepared (offline) results need real boxes. They currently hold counts only (`journey/prepared/tray-hernia.json`). | Run each demo asset **once live** with the owner's key, save the raw model output as the fixture, then stay offline. Cost: about 10 calls. |
| D3 | The dashboard adds an opening demo beat. Should the video stay at 58/58/58 s, or grow? | Add a **20 s opening beat** and keep each role at 58 s. Total runs about 3:20. |

---

## Part 1: Two-way threads

**Problem.**
- `ask_view` (`backend/app/journey/ask.py:30`) already returns every question, review and medicine read with its answer, but each side sees only part of it:
  - The patient's Ask page (sweep screen 33) shows only the latest record-bot answer. Doctor answers sit at the bottom of the "Ask Dr. Rao" card, with no waiting or answered status.
  - Healing-photo decisions and check-ins have no status the patient can see on Today.
  - The doctor sees only *open* items (`doctorOpenItems`). Once answered, an item disappears from the chart.

**Design.**
- **Patient: "My messages" thread** on Ask, newest first. One row per thing the patient sent: a question to the record, a question to Dr. Rao, a healing photo, a medicine photo or a check-in. Each row shows:
  - status: `Waiting for Dr. Rao · 6 min`, `Answered 10:04`, `Answered from your record` or `Seen by Nurse Meena`;
  - the answer, with who answered and how (typed or by voice);
  - for record answers, the quoted record lines.
- **Unread marker.** An answer the patient has not opened shows a dot on the Ask tab and a line on the Today status card ("Dr. Rao answered your question"). Read state is per viewer and local to the browser; it is not a clinical record.
- **Staff side.** The doctor chart's inbox becomes "Conversation with the patient": open items on top (as now), answered items below in a fold. The nurse sees the same thread read-only. Check-ins show "Seen by" once a nurse opens the chart.
- **Backend.**
  - Add a `checkin.seen` event (idempotent per nurse and check-in).
  - Return record-bot asks in `ask_view` alongside doctor questions, each with a `to` of `record` or `doctor`.
  - No new endpoints beyond `POST …/checkins/{id}/seen`.

**Done when:**
- A patient sees each of their own questions with its status and answer.
- The doctor still sees answered items.
- Tests cover waiting, answered, record-answered, seen and unread.

---

## Part 2: AI showcase

### 2.1 "AI at work" dashboard (new route `/ai`, first screen of the demo)

The dashboard answers one question for the audience: **which Muse models run this ward, and what did they just do?**

```
┌ AI at work ─────────────────────────────── Live ● / Prepared ○ ┐
│  Voice ──► Draft orders ──► Nurse tasks         (pipeline strip)│
│  Photo ──► SAM regions ──► Spark reads ──► Check against orders │
│  Video ──► SAM per-frame tracking ──► Count ──► Mismatch flag   │
├──────────────┬──────────────┬──────────────┬───────────────────┤
│ Muse Voice   │ Spark 1.3    │ SAM 3.1      │ Spark Open agent  │
│ transcribe   │ read, draft  │ find & count │ explain & verify  │
│ 6 calls      │ 9 calls      │ 4 checks     │ 2 summaries       │
│ last: "Para… │ last: SBP 88 │ [thumb+boxes]│ last: 3 sentences │
│ 1.2 s median │ 2.4 s        │ 14/15 swabs  │ all cited         │
│ [Try sample] │ [Try sample] │ [Try sample] │ [Try sample]      │
├──────────────┴──────────────┴──────────────┴───────────────────┤
│ Recent AI events (newest first): time · model · patient · what │
│ 09:24 SAM 3.1 · Kumar · counted 14 of 15 swabs · 1 missing [▸]  │
└─────────────────────────────────────────────────────────────────┘
```

- **One card per model** (`config.py:90-97`): Muse Voice transcribe, Muse Spark 1.3 (vision reads and drafting), SAM 3.1 (segmentation and counting), Muse Spark Open (the agent behind explanations). Each card shows:
  - what the model does *in this ward*;
  - its mode: live, prepared or failed;
  - the number of calls in this demo run;
  - median latency;
  - the last result as a thumbnail, with boxes where it has them.
- **"Try sample"** runs the model on a bundled asset and opens the evidence viewer. With no key it shows the prepared result, labelled "Prepared".
- **Recent AI events.** Every model call already produces an event with a `source` field. The dashboard lists them, and each row opens the evidence viewer.
- **Backend.** Add `GET /journey/ai/summary`, built from events (counts, last result and latency per model). Record latency as `ms` on the event at each call site in `journey/live.py`.

### 2.2 Evidence viewer (one component, used everywhere a model looked at media)

The same viewer opens from the dashboard, the tray check, the swab count, the medicine photo and the monitor photo.

```
┌ Tray check · SAM 3.1 · live · 3.1 s ───────────────────────────┐
│ ┌──────────── frame 3.0 s ───────────┐  Expected   Seen  Status │
│ │  [retractor 1 0.91] [retractor 2]  │  retractor   4     4  ✓  │
│ │        [scissors 3 0.88]           │  scissors    3     3  ✓  │
│ │  [towel clip …]                    │  towel clip  4     3  ✗  │
│ └────────────────────────────────────┘                          │
│ ◄ ▮▮▮▮▮▮▮▮▮▮▮▮▮▯▯▯ ►  count over time (sparkline per concept)   │
│ Why: "Saw 3 of 4 towel clips. The best frame was 3.5 s. Two      │
│ detections under confidence 0.45 were ignored." [raw output ▸]  │
│ Captured to record: tray.checked · 09:18 · Nurse Asha     [▸]   │
└─────────────────────────────────────────────────────────────────┘
```

- **Boxes.**
  - Normalised `bbox` [x, y, w, h] per object per frame, already parsed by `parse_sam_text` (`adapters/sam.py:29`), drawn on a canvas over the image or frame.
  - Each label shows the concept, the object id and the score.
  - Each concept gets one colour; boxes under the threshold are drawn dashed and greyed.
  - "Show ignored" toggles low-confidence boxes.
- **Frames.**
  - For video, show a scrubber over the sampled frames (`sam_fps`, default 2) and a per-concept count sparkline. Jump to the "best frame" each count came from (`at_s`, `journey/video.py:57`).
  - For a set of photos, show them as a filmstrip.
- **Values read.**
  - For a monitor photo: boxes around each display region, labelled with the value read (`SBP 88`, `DBP 54`, `HR 112`).
  - For medicine strips: one box per strip, labelled with the name and strength read, and coloured by match (on prescription, on ward orders, not found).
- **Explanation.**
  - One to three plain sentences built from the numbers by template (never free model text in the default view):
    - what was expected;
    - what was seen;
    - what was ignored and why.
  - The no-advice regex applies.
  - "Raw output" shows the model's exact reply for the technical audience.
- **Captured to record.** A link to the event the result wrote, showing that the value went into the timeline (for example `obs.recorded` with source `muse-spark-1.3` from photo X).

### 2.3 Data changes (what makes boxes possible)

| Today | Change |
|---|---|
| `summarize()` (`journey/video.py:40`) keeps only `{count, at_s}` per concept and drops every box | Keep the filtered records too: `frames: [{t, objects: [{id, label, bbox, score, kept}]}]`, capped at 120 frames. Store them as a JSON sidecar next to the media (they are too big for the event payload); the event holds the sidecar id. |
| `read_photo()` (`journey/live.py:108`) returns text only | Per D1(b): run `segment_photos` with reader-specific concepts (`"blister strip"`; `"digital display"` for monitor regions), then Spark reads values. Pair regions with values in reading order. The result holds `regions: [{bbox, label, value, match}]`. |
| Prepared fixtures hold counts or text only | Re-record every demo asset once live (D2) and store `raw` plus `regions`/`frames`. Tests read fixtures only. |
| Model events carry no latency | Add `ms` and `model` to every model-result payload. |

### 2.5 What the models read becomes part of the action or note

**Rule.** A model result never lives only in a "results" card. It also arrives where the person acts, as a **prefilled, confirmable value**, and the saved event keeps `evidence_id` (the sidecar) so every timeline line, task proof and audit row can open the boxed image.

| Upload | Boxes drawn on it | Captured into | Who confirms |
|---|---|---|---|
| Monitor photo (nurse, obs task) | One box per display region, labelled `SBP 118`, `DBP 76`, `HR 80` | The obs task's fields are prefilled, then the nurse presses **Save readings**, which writes `obs.recorded` with `evidence_id` and `source: muse-spark-1.3`. The task proof shows a thumbnail with the boxes. | Nurse |
| Tray video or photos (theatre step 1) | Per-frame boxes per instrument, labelled with concept, id and score | The `tray.checked` event plus the checklist line "Tray: 25 of 26 seen · towel clip 3 of 4". A mismatch raises the existing tray alert, whose text names the missing concept. | Recorded automatically; the surgeon decides |
| Swab camera count (step 3) | Per-frame swab boxes, with the best frame marked | The **Back** count is prefilled with the camera count. "Record closing count" writes `count.closing` with `evidence_id` and `via: camera`. | Nurse |
| Medicine photo (patient or nurse) | One box per strip, coloured by match | The brown-bag list (§2.6) and the admission checklist "Medicines from home" | Patient sees it; doctor marks it |
| Wound or healing photo | None. There is no model read, and the record shows the photo as sent. | Unchanged | — |

- **Timeline and audit.** Any event with `evidence_id` shows a 48 px thumbnail with its boxes and a model chip (`SAM 3.1 · live`). Clicking it opens the evidence viewer.
- **Corrections.** If the person edits a prefilled value, the event keeps both `read` and `saved`. The viewer then shows "Read 118, saved 120 by Nurse Meena".

### 2.6 Brown bag: the medicines a patient brings, and when to take them

The patient (or the nurse at admission) photographs every medicine they have at home.

1. **Capture.** SAM 3.1 boxes each strip, and Spark 1.3 reads the name and strength in each box (D1). Each box is coloured:

   | Colour | Meaning | Box label |
   |---|---|---|
   | green | on the prescription | `Metoprolol 25 mg ✓` |
   | amber | strength differs | `Amlodipine 10 mg · prescribed 5 mg` |
   | red | not on the prescription or ward orders | `Cetirizine 10 mg · not prescribed` |
   | grey | could not read | `not read` |

   The result is the existing `medicines.read` event, with `regions` and `evidence_id` added.
2. **"When do I take them?"** My medicines becomes a **day plan** built only from the prescription (`journey/schedule.py:31` `build`):
   - columns Morning / Afternoon / Night, plus an "As needed" row;
   - each cell shows the doctor's wording (`schedule_text`, `schedule.py:50`) next to a **crop of the patient's own strip** from the photo, so they recognise it.
   - Medicines in the photo that are not on the prescription are listed under the plan as "Not on your prescription: Cetirizine 10 mg". One tap on "Ask Dr. Rao" fills a question (the patient presses send).
3. **Ask by text or voice.** In "Ask your record", questions like "When do I take amlodipine?" or "Can I take the cetirizine?" are answered by **quoting the prescription row** for that medicine. A medicine not on the prescription gets a fixed sentence: "Cetirizine is not on your prescription. Ask Dr. Rao." The record bot matches medicine names by `key_of` (`journey/medicines.py`), never a substring, and never adds advice.
4. **Staff side.**
   - The doctor chart and the nurse admission checklist show **Medicines from home**: one row per strip, with its colour, the crop and the prescription line.
   - Per row, the doctor can mark **Noted** or **Discuss with patient**. "Discuss" creates a patient-visible note ("Dr. Rao will talk to you about Cetirizine").
   - These are record marks, not orders.
5. **Patient visibility (Part 1 thread).** Each brown-bag photo appears in "My messages" with its result and any doctor mark.

### 2.7 Demo

- A new opening beat (D3): the dashboard with Live/Prepared visible.
- The beat clicks "Try sample" on SAM, the evidence viewer opens with boxes, then the flows start.
- The tray-check and swab-count beats open the viewer instead of reading counts from a list.
- `beats.mjs`, `steps.mjs` and `docs/demo/count-guard-v2-video-script.md` change together, and `make demo-check` stays green offline.

**Done when:**
- Every media check in the demo shows boxes, values and an explanation, from fixtures with no key.
- The dashboard shows four model cards and recent AI events.
- `make demo-check` is green.

---

## Part 3: AI-native ward (later; estimate only)

**Ask bar.**
- One input on every staff screen and the patient app, by text or by 🎙 through Muse Voice. Example questions:
  - "How is bed 4 doing?"
  - "Who is overdue for obs?"
  - "What changed since 08:00?"
  - patient: "When is my wound check?"
- The **Spark Open agent** answers with tools over the event store. It extends `agent/tools.py` with `patient_status`, `due_tasks`, `events_since`, `obs_trend` and `open_items`.
- Every sentence passes the existing verifier (`agent/verifier.py:17`) against the rows it cites. A sentence that fails is dropped and replaced by its template sentence, the same pattern as `reconciler.py:130`.
- Answers show citations as chips that open the timeline line.
- Role scoping: a patient's tools see only their own episode, and staff see their ward.

**Monitoring board.**
- A ward-wide view with one tile per bed: state, next due, and risk chips. Rules come first and are deterministic:
  - obs overdue;
  - systolic falling across the last 3 readings;
  - swab count mismatch not cleared;
  - patient question waiting more than 30 min;
  - check-in with red flags.
- The model only writes the one-line "why" for a chip, verified against the rows, and never advises.
- New alerts arrive by polling every 15 s; there is no websocket in the demo.

**Out of scope:**
- clinical advice or prediction scores;
- text-to-speech replies;
- multi-ward.

| Part 3 item | Days |
|---|---|
| Agent tools over the journey store, plus role scoping | 3 |
| Ask bar UI (text and voice), citations, patient variant | 3 |
| Rule watcher, monitoring board, model-written "why" with verifier | 3 |
| Eval set: 40 questions with expected cited rows, run offline with recorded replies | 2 |
| Demo beat and docs | 1 |
| **Total** | **12** |

## Constraints (all parts)

- Records only, no medical advice. The no-advice regex applies to all new copy and all model text shown.
- Never call live models in tests or `demo-check`. Live calls happen only in the one-time fixture recording (D2) and the owner's live demo.
- Files stay under 500 lines, with input validated at API boundaries.
- Never touch ports 8100/5173 in checks.
- Commits only when the owner asks.

# Care App Clarity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every model step in Count Guard and Doctor Dictation says what is happening (recording, uploading %, checking with the model, done live/prepared, failed + Retry), every model result can be expanded to show what was captured and what a person did, no feature card is hidden by patient state, dictation fills real fields, and My care can check a medicine.

**Architecture:** A `ModelStep` component + `useModelStep` hook replaces the bare global `busy` for model calls; uploads move to XHR for progress. A generalised `ModelExpand` (four parts: captured, model returned, how used, what a person did) and a `Provenance` mark (AI proposed / accepted by) are used at every model point. Backend gets small payload additions (`evidence`) and dictation fixes; state gates become disabled-with-reason.

**Tech Stack:** React 19 + Vite, `node --test` (src `*.test.js`, scripts `*.test.mjs`), FastAPI + pytest; Doctor Dictation vanilla JS + pytest.

**Spec:** `docs/superpowers/specs/2026-11-03-care-app-clarity-design.md` (§ numbers below). Main at c377969 (includes PR #1 `care/CameraSheet.jsx`, `care/PhotoInput.jsx` Take photo / Upload dialog — build on it).

## Global Constraints

- Paths relative to `count-guard/` unless they start with `doctor-dictation/`. CG: `.venv/bin/pytest -q`; `cd frontend && node --test $(find src -name "*.test.js") && node --test $(find scripts -name "*.test.mjs") && npm run build`; `make demo-check` (ports 8200/5273, DD 8300; never 8100/5173/8000). DD: `cd doctor-dictation && .venv/bin/python -m pytest tests/ -q` (4 known pre-existing failures).
- Branch `care-clarity` from main. Implementers don't commit; the controller commits per task with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`, no Co-Authored-By.
- Files under 500 lines; add modules rather than grow near-limit files (`journey/states.py` 464, `journey/api.py` 414, `journey/ai_moments.py` 358, `frontend/src/care` files > 300 lines).
- Tests never call live models. No secrets anywhere.
- count_gate (`backend/app/journey/states.py:95-110`) unchanged; `test_route_sweep.py`, `test_count_gate_paths.py`, `test_archive.py` stay green; person-only confirms and the photo-check gate unchanged.
- Step copy (exact): `Recording {m:ss} — tap the mic to finish`, `Uploading {what}… {n}%`, `Checking with {Model}… {s} s` (staff) / `Reading your photo… {s} s`, `Listening to your recording… {s} s` (patient), `Done · live ({Model}, {t} s)`, `Done · Prepared (no live model)`, `Didn't work: {reason}` + button `Retry`. Model display names: `SAM 3.1`, `Spark 1.3`, `Spark Open`, `Muse Voice`.
- Provenance copy (exact): `Proposed by AI`, `Accepted by {name} {HH:MM}`, `Changed by {name} {HH:MM}`, `Overridden by {name} {HH:MM}`.
- Disabled-reason copy pattern: `Opens when the patient is {state words}` (e.g. "in theatre", "admitted").
- Model names may appear on staff screens **only** inside `.model-step` and the Expand view (C2); patient screens never show model names; `frontend/scripts/demo/scan.mjs` is updated to allow exactly that.
- Patient copy keeps the ADVICE rule (no instructions/advice words).

## Review Focus

1. **A model call that never returns** (network drop, server stuck). Expected: the step shows elapsed seconds, then after the timeout (60 s photo, 120 s audio/video) "Didn't work: no answer in {n} s" + Retry; nothing stays greyed forever. Pinned in Task 1 (`modelStep times out`).
2. **Two uploads at once in two cards.** Expected: each card shows its own step; one failing does not show in the other. Pinned in Task 2.
3. **Navigating away mid-upload.** Expected: the request is aborted, no stale result lands on another patient's chart. Pinned in Task 1 (`abort on unmount`).
4. **Patient lens on an Expand.** Expected: plain words, no model names, no raw JSON. Pinned in Task 4.
5. **Heard text edited before Send.** Expected: still marked "From voice" until saved; saved shows "Changed by {name}". Pinned in Task 2/5.

---

### Task 1: `ModelStep`, `useModelStep`, XHR uploads, styles

**Files:**
- Create: `frontend/src/care/modelStep.js` (pure state machine + copy), `frontend/src/care/ModelStep.jsx`, `frontend/src/care/useModelStep.js`
- Modify: `frontend/src/journey.js` (`uploadJourney(id, path, file, fields, { onProgress, signal, timeoutMs } = {})` via XMLHttpRequest; `postJourney(id, path, body, { signal, timeoutMs } = {})`), `frontend/src/care/ward.js` (`upload`/`act`/`ask` accept and pass `opts`), `frontend/src/care/care.css` (`.model-step`, `.model-step .bar`, `@keyframes cg-pulse`, `@keyframes cg-indeterminate`, reduced-motion off), `frontend/scripts/demo/scan.mjs` (allow model names inside `.model-step` and `[data-expand]`)
- Test: `frontend/src/care/modelStep.test.js`, `frontend/src/journey.test.js` (XHR fake), `frontend/scripts/demo/scan.test.mjs`

**Interfaces — Produces:**
- `stepText(step, { lens: "staff"|"patient" }) -> string` for `step = { stage: "idle"|"recording"|"uploading"|"checking"|"done"|"failed", what, model, percent, seconds, mode: "live"|"prepared", reason }`.
- `modelOf(capability) -> "SAM 3.1"|"Spark 1.3"|"Spark Open"|"Muse Voice"` (map: tray/setup/swabs/camera → SAM 3.1; voice/hear/dictation audio → Muse Voice; photo verdict/strips/medicines/monitor/review/wording/card/handover/discharge/orders → Spark 1.3; reconciler with Baseten → Spark Open).
- `modeFrom(result) -> "live"|"prepared"|"failed"` reusing `source.js` `isPrepared` and the unavailable source.
- `useModelStep({ capability, lens }) -> { step, run(fn: (opts) => Promise<any>, { what }) -> Promise<any|null>, retry(), startRecording(), stopRecording(), reset() }`; `run` passes `{ onProgress, signal, timeoutMs }` to `fn`, ticks `seconds` every 1 s while checking, sets `done` with `mode`/`seconds` from the result, `failed` with the error message, aborts on unmount.
- `<ModelStep step lens onRetry onExpand />` renders `role="status" aria-live="polite"`, class `model-step stage-{stage}`.

- [ ] **Step 1: Failing tests:** `stepText` for every stage × lens with the exact Global Constraints copy (e.g. `stepText({stage:"checking", model:"SAM 3.1", seconds:3},{lens:"staff"}) === "Checking with SAM 3.1… 3 s"`, patient photo → `"Reading your photo… 3 s"`, `stepText({stage:"done",mode:"prepared"}) === "Done · Prepared (no live model)"`); `modelStep times out` (fake timers: a never-resolving fn → `failed`, reason `no answer in 60 s`); `abort on unmount` (signal aborted); `uploadJourney` reports progress 0→100 through a fake XHR and rejects with the server's detail on 4xx; scan allows `Checking with SAM 3.1… 3 s` inside `.model-step` text and still flags `SAM 3.1` elsewhere.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** **Step 4: Run** all frontend tests + build + `make demo-check` — PASS (no beat changes yet).

### Task 2: Wire `ModelStep` into every model call site; per-card failures

**Files:** Modify `care/Dictate.jsx` (recording timer via `startRecording`; `transcribing` = checking with Muse Voice; hear failure → failed + Retry; keep the "From voice" mark until Send even after edits — show `From voice · edited` when text differs), `care/TheatreDrugs.jsx` (hear through the hook, not raw), `care/TaskProof.jsx`, `care/ProofItem.jsx`, `care/HomeMedicines.jsx`, `care/MedicinesFromHome.jsx`, `care/VideoCheck.jsx`, `care/CameraAdvice.jsx`, `care/AskCards.jsx`, `care/Handover.jsx`, `care/ContextCard.jsx`/`TheatrePanels.jsx`, `care/DischargeDraft.jsx`, `care/DoctorActions.jsx` (orders/discharge dictate), `care/NurseTasks.jsx`, `care/CountPanel.jsx` (camera read gets the Prepared mark).
- Test: `care/modelStepSites.test.js` (each site file renders `<ModelStep` and passes `onRetry`), `care/dictate.test.js`.

**Interfaces:** Consumes Task 1. Each site uses `useModelStep({ capability })` and calls `ward.upload/act/ask(..., opts)`.
- [ ] **Steps:** failing tests (`two uploads at once`: two hooks fail/succeed independently; Dictate shows `Recording 0:03 — tap the mic to finish` with fake timers, then `Checking with Muse Voice… 1 s`, then the text; edited heard text shows `From voice · edited`) → implement → frontend tests, build, demo-check PASS (update `beats.mjs`/`steps.mjs` expects only where copy changed; keep 20 beats/180 s).

### Task 3: Backend evidence for every model point

**Files:** Create `backend/app/journey/evidence_payload.py` (`evidence_of(kind, *, inputs, reply, used, calls) -> dict` with keys `captured`, `returned`, `used`). Modify the routes that lack it so their events carry `evidence`: theatre card (`theatre_api.py`), proof verdict (`verdict_api.py`), theatre drug + heard pack (`theatre_api.py`), `/ask/hear` and `/dictate/*` (`media_api.py`: keep the audio in the data dir via existing media store, add `audio_id` + transcript), handover (`api.py` route → write via a helper module, not grow api.py). Add `GET /journey/episodes/{id}/audio/{audio_id}` (same-episode only).
- Test: `backend/tests/test_evidence_payload.py`: each route's event has `evidence.captured`/`returned`/`used`; audio route serves only its own episode's file (404 cross-patient); no evidence carries a secret or a full key.
- [ ] **Steps:** failing tests → implement → backend suite PASS (route sweep unchanged sets: update pinned sets only if a new write route is added — the audio route is a GET).

### Task 4: `ModelExpand` everywhere (four parts)

**Files:** Create `care/ModelExpand.jsx` (wraps `EvidenceExpand` for images/frames; adds audio player + transcript, text in, model/mode/time, raw reply folded, "How the app used it", "What a person did" from Task 5), `care/expandModel.js` (pure: `expandParts(event, view, lens) -> { captured, returned, used, people }`). Add an **Expand** button with `data-expand` at all §4.2 points (list in spec). Doctor Dictation: `doctor-dictation/frontend/expand.js` + a button on the draft showing audio (from the existing recording blob), transcript, engine, the first draft vs current fields.
- Test: `care/modelExpand.test.js` (`expandParts` for voice, photo, video, text-wording, verdict, camera; patient lens has no model names and no raw reply), `doctor-dictation/tests/test_frontend_expand.py` (static checks like the existing frontend tests).
- [ ] **Steps:** failing tests → implement → tests, build, demo-check PASS (one beat asserts an Expand opens and shows "Captured").

### Task 5: `Provenance` — AI proposed vs person accepted

**Files:** Create `care/Provenance.jsx`, `care/provenance.js` (`provenanceOf(item, events) -> { kind: "proposed"|"accepted"|"changed"|"overridden", by, at_ms, before, after }`). Apply to order drafts/signed, discharge draft/signed, handover accepted, heard drug/pack confirmed, photo verdict override, camera advice ack/resolve, dictated obs values saved. CSS: `.prov-proposed` dashed border, `.prov-accepted` solid + person icon.
- Test: `care/provenance.test.js` with the exact copy; a signed order whose items differ from the draft → `changed` with before/after.
- [ ] **Steps:** failing tests → implement → tests, build, demo-check PASS.

### Task 6: Nothing hidden by state

**Files:** Modify `care/DoctorActions.jsx:221-224` (Clinic cards incl. home medicines in every state; Theatre card shows outside theatre disabled with `Opens when the patient is in theatre`), `care/journey.js:55-64`, `care/NurseActions.jsx:76-79`, `care/AskCards.jsx:63,84`, `care/AlertBanner.jsx:12-13`, `care/Today.jsx:45`; backend `journey/media_api.py:129,156` (`/dictate/discharge`, `/dictate/task` accept `admitting`, `ward`, `theatre`, `discharging`; 409 elsewhere with the reason).
- Test: `care/visibility.test.js` — for every state × role the listed cards render (enabled or with the reason); `backend/tests/test_dictate_states.py` — the two routes accept the four admitted states.
- [ ] **Steps:** failing tests → implement → suites + demo-check PASS. Hard-stop tests stay green.

### Task 7: Dictation fills fields

**Files:** `backend/app/journey/dictation.py` → move number words to a new `journey/spoken_numbers.py` (`words_to_digits(text) -> str` handling "hundred", "a hundred and five", "one twenty" → 120 for BP context); per-item grounding in orders (`items_from_reply` keeps grounded items, marks the rest `{"kind":"unclear","heard": clause}`); discharge unmatched sentence → `unplaced`; theatre drug no-name → 422 detail `Heard: '{text}' — no drug name`. Frontend: `care/NurseTasks.jsx` row mic fills that row's `ObsForm` in one step (task voice → `/dictate/task` → values into the row form state; TaskProof stays for photos); `care/OrderForm.jsx` shows unclear items as `Not understood — not added: "{heard}"`; discharge draft shows unplaced sentences with a section chooser.
- Test: `backend/tests/test_spoken_numbers.py` ("one hundred twenty over eighty" → "120 over 80"; "a hundred and five" → 105; "seventy two" → 72); `test_dictation_fill.py` (K7: one unknown item keeps the others' fields; discharge unplaced); `care/nurseVoice.test.js` (K6: values land in the row form).
- [ ] **Steps:** failing tests → implement → suites + demo-check PASS.

### Task 8: Check a medicine — My care and doctor every state

**Files:** Create `care/CheckMedicine.jsx` (patient: photo via `PhotoInput` or typed name → `/ask/medicines` or `/strips` with `by: patient`; ModelStep; Expand; rows with `On your prescription` / `Strength differs from your prescription` / `Not on your prescription — ask your doctor`). Modify `care/MyCare.jsx` (render it; My care stays read-only otherwise). Backend: ensure the patient path writes `brownbag.med_found` with `by: patient` and works in every state incl. `home`.
- Test: `care/checkMedicine.test.js` (copy, no advice words beyond the fixed "ask your doctor" line — add it to the ADVICE allow-list explicitly), `backend/tests/test_patient_medicine_check.py` (home state accepted; rows matched to latest rx).
- [ ] **Steps:** failing tests → implement → suites + demo-check PASS.

### Task 9: Doctor Dictation clarity

**Files:** `doctor-dictation/frontend/app.js` (two lines max: call `stepInfo` hooks), create `doctor-dictation/frontend/stepinfo.js` (elapsed seconds ticker on the status line during transcribe/structure: `Transcribing with Muse Voice… {s} s`, `Structuring with Spark… {s} s` using the engine from `/api/health`), Expand from Task 4.
- Test: `doctor-dictation/tests/test_frontend_stepinfo.py`.
- [ ] **Steps:** failing tests → implement → DD suite PASS (4 known failures only).

### Task 10: Demo, docs, final

- [ ] Update `frontend/scripts/demo/beats.mjs`/`steps.mjs` to assert a step line and an Expand in the video path (keep 20 beats, scene seconds unchanged), `docs/demo/dd-cg-flow-video-script.md` narration where copy changed (doc test green), `count-guard/README.md` one paragraph on the step line/Expand/Provenance.
- [ ] Whole-branch review on the most capable model with the adversarial hard-stop probe and a copy/lens check (patient never sees model names; staff only in step lines/Expand).

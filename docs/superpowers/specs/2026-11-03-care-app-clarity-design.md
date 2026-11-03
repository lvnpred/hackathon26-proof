# Clarity: every model step visible, every AI result expandable, nothing hidden (design)

Date: 2026-11-03 · Status: draft · Scope: `count-guard/frontend/src/care` (+ small backend fixes), `doctor-dictation/frontend`

## 1. Summary

Today a user presses the mic or uploads a photo and cannot tell whether anything is happening, whether the
model (SAM, Spark, Muse Voice) ran, or whether it failed. Results from models can only be inspected in five
places. Some cards vanish depending on the patient's state. Dictation sometimes only adds a note instead of
filling the fields the user expected.

This design adds one visible pattern for every model step, an **Expand** view at every point a model is used,
a clear "AI proposed / person accepted" marking, cards that are never hidden by state, and dictation that fills
real fields. It also puts the medicine-from-home check in the patient's **My care**.

## 2. Decisions by the person asking (2026-11-02/03)

| # | Decision |
|---|---|
| C1 | Every screen must say what is happening: recording, uploading, waiting for the model, done, failed. |
| C2 | Show whether SAM / Spark / Voice worked or not. |
| C3 | **Expand** shows what was captured at every point an LLM or vision/voice model is used. |
| C4 | Make clear what a person accepted, versus what the AI proposed. |
| C5 | Features surface everywhere they are useful, "even if they go against anything"; and they must work. |
| C6 | The medicine-from-home check is in the patient's **My care** (he buys medicine and wants to check it). |
| C7 | Dictation must fill the details, not just add a note. |

## 3. Current state (audit, file:line in count-guard/frontend/src unless noted)

- Pending: `ward.act/upload/ask` only flip one global `busy` boolean (`care/ward.js:171-222`); no per-card text,
  spinner, progress or `aria-busy` anywhere in care. No `@keyframes` in the app.
- Upload: `uploadJourney` uses `fetch` (`journey.js:47`), so no upload progress; no timeout, no abort.
- Failure: `<Fault>` is scoped by route; unclaimed faults fall to the bottom of the chart (`care/Chart.jsx:97`),
  far from the card that failed.
- Theatre drug voice calls `/ask/hear` outside `ward.ask` (`care/TheatreDrugs.jsx:14`), so nothing is even disabled.
- Model shown: staff see `<Source>` words + "· Prepared", never "live" or "failed"; model names only in the
  Inspector Model tab. Camera read on the count panel has no Prepared label (`care/CountPanel.jsx:114`).
- Expand: only where `<Evidence>`/`EvidenceThumb` is used, or via the Inspector from `<AiMoment>`. No Expand for
  verdicts (`ProofItem`), context card, nurse task voice, theatre drug, camera count read.
- AI vs person: exists piecemeal (`heard_by`, order sign diffs, `confirmed_by`, `accepted_by`, override, History
  `isAiBy`) but no consistent visual.
- Hidden by state: `DoctorActions.jsx:221-224` (Clinic only in clinic — home medicines live here; Theatre only in
  theatre), `journey.js:55-64` (doctor blocks, quiet row), `NurseActions.jsx:76-79`, `AskCards.jsx:63,84`,
  `AlertBanner.jsx:12-13`, `Today.jsx:45`; backend `/dictate/discharge`, `/dictate/task` ward-only (409).
- Dictation fill:
  - Nurse task voice parses BP/HR correctly but the values go to the TaskProof "Confirm task" card rendered
    above the task list (`NurseTasks.jsx:115`), not the row's own `ObsForm` (`NurseTasks.jsx:70`); it needs a
    second step ("Use this"); `dictation.digits()` has no "hundred" (`backend/app/journey/dictation.py:28-35`),
    so "one hundred twenty over eighty" reads sbp 20.
  - Orders: model output is all-or-nothing (`dictation.py:276-297`) — one ungrounded item sends the whole reply
    to the rules, where any unmatched clause becomes `kind:"other"` (a note, `dictation.py:114`).
  - Discharge rules put any unmatched sentence under "Course on the ward" (`dictation.py:198`).
- Doctor Dictation already has a 4-step tracker and status line (`doctor-dictation/frontend/steps.js:24-27`,
  `app.js:106,523`); its engine name shows only in the status line.

## 4. The pattern

### 4.1 `ModelStep` — one line for every model step

A small component (and a hook `useModelStep`) that every card with a model call uses, in place of the bare
`busy` flag. One step has a stage:

| Stage | Text (staff; patient wording in parentheses) | Visual |
|---|---|---|
| `recording` | "Recording 0:07 — tap the mic to finish" | red dot, pulsing (reduced-motion: static) |
| `uploading` | "Uploading photo… 42%" / "Uploading recording…" | thin progress bar |
| `checking` | "Checking with SAM 3.1… 3 s" / "Transcribing with Muse Voice… 2 s" / "Wording with Spark… 4 s" ("Reading your photo… 3 s") | indeterminate bar + elapsed seconds |
| `done` | "Done · live (SAM 3.1, 2.1 s)" or "Done · Prepared (no live model)" + **Expand** | green tick; Prepared in the existing Prepared style |
| `failed` | "Didn't work: model unavailable — Retry" / the server's reason + **Retry** | danger style; Retry repeats the same call with the same file |

- Staff see the model name (SAM 3.1, Spark 1.3, Muse Voice) in the step line — this deliberately changes the
  earlier rule that model names appear only on the AI page and the Model tab (C2 overrides it). The patient sees
  plain words ("Reading your photo").
- The step line sits inside the card that started it (never at the bottom of the chart). Its fault is its own,
  not the global scoped fault.
- `role="status"` + `aria-live="polite"`; the card gets `aria-busy` while checking.
- Upload progress needs `XMLHttpRequest` with `upload.onprogress` in `uploadJourney` (keep the same signature;
  add an optional `onProgress`). Add a timeout (60 s photo, 120 s video/audio) and abort on unmount.
- The global `busy` stays only to stop double submits on the same card.

### 4.2 Expand everywhere a model is used

Every model result gets an **Expand** button (the existing `EvidenceExpand`, generalised). The expanded view
always has four parts:

1. **Captured** — what went in: the photo(s) with boxes, the video frames, the audio (playable) and its
   transcript, or the text that was sent.
2. **Model returned** — the model, live/prepared/failed, time taken, and the raw reply (folded).
3. **How the app used it** — what was read or drafted from it (rows, values, items, verdict), and anything the
   app ignored or replaced with rules ("Spark reply not usable — drafted by rules").
4. **What a person did** — accepted / changed / overrode / signed, by whom and when, with the before→after.

Points that must have it (from the audit): voice transcription (all Dictate uses), orders draft, discharge
draft, nurse task voice, handover wording, context card, theatre drug, Ask bot answer, Ask photo review, home
medicines/strips, monitor read, proof verdicts, tray/setup video, swab camera clip, camera count read, the
discrepancy explanation, model "Try sample". Doctor Dictation: the transcript and the structured draft get an
Expand showing the audio, the transcript, the engine and the draft before the doctor's edits.

Backend: each of these responses already carries `calls`, `source`, `heard_by`, a photo/evidence id or
transcript; where one doesn't (context card, verdict, theatre drug), add `evidence` with the input reference and
the raw reply so Expand has something to show. Audio is kept for playback in the existing media store (data
dir, git-ignored).

### 4.3 AI proposed vs person accepted

One visual pair, used everywhere:

- **AI proposed** — the existing `AiMark` + "Proposed by AI" in the AI tone; the item is shown as a draft
  (dashed border).
- **Accepted by {name}** — solid border, a person icon, the name and time. If the person changed it, "Changed
  by {name}" with the before→after in Expand.

Applies to: order drafts → signed, discharge draft → signed, handover → accepted, heard drug/pack → confirmed,
photo verdict → override, camera advice → acknowledged/resolved, dictated values → saved. Text the person edits
after it was heard keeps the "From voice" mark until it is saved, then shows "Changed by {name}" (today the mark
disappears when the text is edited — `Dictate.jsx:103`).

### 4.4 Never hidden by state (C5)

Every feature card renders in every state. Where the action cannot run now, the card shows and says why, with
the button disabled: "Opens when the patient is in theatre", "Signed — reopen to change". Backend refusals that
remain (the swab hard stop, ward-only dictation routes) still answer 409, and the card shows that reason in its
step line. Specifically:

- Doctor **Photo of medicines from home** shows in every state (today clinic only).
- `/dictate/task` and `/dictate/discharge` accept every state where the patient is admitted (admitting, ward,
  theatre, discharging); a 409 remains for clinic/clinic_done/home where there is nothing to attach to.
- Nurse cards (tasks, dose, handover) show in every admitted state.
- Safety rules do not change: count_gate, person-only confirms, photo-check gate.

### 4.5 Dictation fills fields (C7)

- Nurse task voice: the parsed values fill the **same row's** form (BP, HR, SpO2, RR, temp) in one step — the
  mic on the row records, transcribes, parses, and fills the row's `ObsForm`, which the nurse then saves. The
  separate "Confirm task" card is kept only for photo proofs.
- `digits()` learns "hundred" ("one hundred twenty" → 120, "a hundred and five" → 105); test with BP and HR.
- Orders: grounding is per item, not all-or-nothing — grounded items keep the model's fields; only the
  ungrounded item falls back (and is marked "not understood — check"). An item that stays `other` is shown as
  "Not understood — not added as an order" with the heard words, never silently as a note.
- Discharge: an unmatched sentence is shown as "Not placed — choose a section", not appended to "Course".
- Theatre drug: when the phrase has no drug name, the step line says so ("Heard: '…' — no drug name") instead of a
  bare 422.

### 4.6 Medicines from home in My care (C6)

My care gets a **Check a medicine** card: photo or typed name → each medicine is matched to the latest
prescription ("On your prescription", "Strength differs from your prescription", "Not on your prescription —
ask your doctor"), with the ModelStep line and Expand. It works in every state including after going home. It
writes `brownbag.med_found` rows by the patient (`by: patient`), so staff see it on the chart. No advice wording
(the existing ADVICE rule).

### 4.7 Doctor Dictation

Keep its tracker. Add: the engine and model name in the status line ("Transcribing with Muse Voice… 3 s"),
elapsed seconds while waiting, and an **Expand** on the draft showing audio, transcript, engine and the draft as
first produced, plus the doctor's edits. Admit push already shows sending/sent/not yet.

## 5. Non-goals

New models; changing the swab hard stop; a full redesign of layouts; changing the video beats beyond what these
changes require.

## 6. Acceptance checks

| # | Check |
|---|---|
| K1 | Every model call site in §4.2 shows recording/uploading/checking/done/failed in its own card (component test per site, and one demo-check beat asserts "Checking with" then "Done"). |
| K2 | Upload shows a % (XHR progress) for photo and video; a failed call shows the reason and Retry, and Retry re-sends. |
| K3 | Every §4.2 point has Expand with the four parts; a test per point that the parts render. |
| K4 | AI-proposed and accepted-by marks render on every item in §4.3; editing heard text keeps "From voice" until saved. |
| K5 | No feature card is removed by state; the disabled reason shows (test over every state × role). |
| K6 | "BP one hundred twenty over eighty, pulse seventy two" on a nurse obs task fills the row's form 120/80/72 in one step. |
| K7 | An order dictation with one unknown item keeps the other items' fields; the unknown one is flagged, not a note. |
| K8 | My care Check a medicine works for the patient in every state including home. |
| K9 | count_gate unchanged; route sweep and A6 tests still pass; make demo-check passes; DD suite unchanged except new tests. |
| K10 | Staff screens may name models in the step line; the copy scan (`scan.mjs`) is updated to allow them there only. |

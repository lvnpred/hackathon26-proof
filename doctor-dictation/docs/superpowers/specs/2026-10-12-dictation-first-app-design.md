# Dictation-first prescription app — design

Date: 2026-10-12
Status: draft (awaiting review + approval)

## Intent and why

The current app is a demo: a doctor fills four fields by hand, picks an STT
model from a dropdown, presses "Format", and only then sees a prescription.
The user of the product is a **doctor**, and the guiding value is **simplicity**:
she should never type, configure, or pick anything to get a prescription.

So we invert it. The doctor opens the app, presses one button, and **dictates the
whole visit**. Everything — patient details and clinical content — comes out of
that dictation. The app turns it into a prescription she can correct and print.
The screen stays nearly empty until she speaks.

## Goals

- **Dictation-first, one screen.** Nearly empty on open; one mic control.
- **Dictate the entire encounter**, including patient demographics (name, age,
  sex, OP number) — not typed up front.
- **Cloud STT by default** (OpenAI Whisper). No model picker, no engine choice
  in the UI. Offline fallback fixed to `small.en`, overridable in `.env`.
- **The output is an always-editable form** — patient header + diagnosis +
  chief complaints/history + investigations + Rx + advice + review — rendered
  with the existing grounding check marks (✓ / ? / ! / ±).
- **Corrections two ways:** type directly into the form, or press dictate again
  and speak. A spoken correction changes **only what she mentioned**, leaving
  the rest of the form exactly as it was. Editable at any point.
- **Save & Print** as the finish action: persist user + patient + form data to
  SQLite, generate a PDF and save it as a file, and print.
- Keep the deterministic pipeline (`normalize → ground → repair → validate`) and
  the "AI draft — doctor must verify" disclaimer.

## Non-goals

- **No cloud storage / sharing in this phase.** SMB, Drive, SharePoint, S3 are a
  later phase (the existing plans already stage these).
- **No STT model selection UI** and no per-user engine choice.
- **No local/ONNX inference.** Explicitly deferred earlier; the stub stays.
- No redesign of the prescription content itself (sections and check marks stay).

## Anti-goals (what would make this a failure even if it works)

- A screen the doctor has to configure or read before she can dictate.
- Silently dropping or altering a dictated medicine — unverified items must be
  **kept and flagged**, never removed by the app.
- Losing her corrections: a dictated correction must not clobber unrelated rows.
- Declaring a prescription "final" without the verify step.

## Constraints

- Target machine is Windows on **ARM64** (Snapdragon X Elite). Python 3.12 in
  `.venv-arm64` (arm64) and `.venv-stt` (x64 for faster-whisper). Any new
  dependency must have an ARM64 (or pure-Python) path.
- The deterministic pipeline is a **hard invariant** — production work wraps
  around it and must not change its behavior.
- Offline tests must keep passing (rules + lexicon fallback, keys cleared).
- **Audio + PHI (decided 2026-10-12):** cloud STT sends dictation **audio** off
  the machine to OpenAI. **Accepted for v1** — the app will not promise "audio
  never leaves the machine" (the README's current claim gets corrected). The
  **audio is never saved/persisted**. A local-only option is a later phase.

## Decisions the human made

- The user is the **doctor**; simplicity is the priority.
- Layout **C**: a bare dictation bar; nothing on screen until she speaks.
- Demographics are **dictated**, not entered by hand.
- The form is **always editable**; corrections by typing or by re-dictating.
- Spoken corrections **merge** — only what is mentioned changes.
- STT: **cloud default**, picker removed, offline fallback `small.en`
  (env-configurable).
- **SQLite stores the user + patient information + the form data.**
- The **PDF is generated and saved as a file.**
- **Save & Print** is the finish action.
- Storage is **local now**; cloud storage is a later phase.

## The builder's calls (made here, vetoable)

- **Date** defaults to today (not dictated).
- **PDF rendering:** prefer headless Chromium over WeasyPrint, because WeasyPrint
  pulls GTK/native libs that are painful on Windows-ARM64. Confirm on target.
- **Correction merge:** send the current form + the new dictation to the LLM with
  an "apply only what the new dictation changes; leave everything else
  byte-identical" instruction, then re-run grounding/validation on the result.
- **Existing `/api/models` + `/api/model`:** remove their UI; keep or retire the
  endpoints as a small cleanup.
- **User identity:** SQLite `users` exists; full login/roles (Phase 0 P0-3) is
  out of scope here unless a clinic login is required. Assume a single local
  doctor for now.
- **Grounding marks on hand-edit:** when the doctor types into a row, that row's
  check pill is invalidated (cleared) and re-grounded on the next pass — a
  hand-edited medicine never keeps a stale ✓.

## Left to the builder

- Exact prompt changes so demographics (name, age, sex, OP) are extracted and
  grounded alongside the clinical sections.
- The correction/merge algorithm details and how it interacts with the
  ground → repair loop and the sha cache.
- The PDF pipeline and where PDFs are stored on disk; the `documents` row that
  records the file path/hash.
- DB schema additions for the PDF artifact and the dictated demographics.
- The full frontend rebuild to layout C, including the inline-edit behavior and
  the two-state mic control.
- Any migration/cleanup of the removed model-selector code paths.

## Resolved with the human (2026-10-12)

The builder review raised four questions; all are settled.

1. **Patient/encounter identity.** On Save & Print, match an existing patient by
   OP number (name as a tiebreak); if none matches, create a new patient. After a
   save, the next dictation starts a **new encounter**; provide an explicit "New
   patient" affordance. No blocking patient picker.
2. **Verify gate (human's decision).** Save & Print **enforces** it: any Rx row
   that is not ✓-verified must be confirmed before the document is finalized —
   by tapping/typing, **by confirming via voice**, or by re-dictating the
   correction. Each confirmation is recorded in `audit_log`.
3. **Long dictation.** Keep the one-shot path for v1, raising the client and
   server timeouts to cover a full visit (~5 min) with a visible elapsed timer.
   The background-job refactor stays a Phase 1 item.
4. **PDF.** Server-side render to a saved file is required; target headless
   Chromium. If ARM64 Chromium proves unviable during the spike, fall back to
   browser print-to-PDF for v1 and revisit.

## Open question carried forward

None blocking.

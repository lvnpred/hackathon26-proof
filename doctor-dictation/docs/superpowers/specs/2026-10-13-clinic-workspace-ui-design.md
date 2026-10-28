# Clinic workspace UI + clinic profile + today's list — design

Date: 2026-10-13
Status: draft (awaiting review + approval)
Builds on: `docs/superpowers/specs/2026-10-12-dictation-first-app-design.md` (the dictation-first app)

## Intent and why

The app works, but it looks dated and hides the fact that an assistant is doing the
work. The goal is a **professional, modern ("agentic") workspace**: the doctor sees
their patients for the day on the left, dictates in the middle with the assistant's
work visible, and reads the prescription document on the right. Plus two new wants:
an **updatable clinic/doctor profile** printed on every prescription, and a **list of
the patients done today**.

## Goals

- **Two-pane workspace (the approved "A + B" combination):**
  - **Top bar:** clinic name · doctor · a live assistant-status chip.
  - **Left sidebar — "Today":** the patients completed today; click one to reopen
    its prescription.
  - **Middle pane:** the dictation orb + timer, the **assistant step list**, and the
    live transcript.
  - **Right pane:** the prescription document (doctor/clinic block, patient row,
    section bars, Rx table with ✓/? pills, Save & Print).
- **Assistant step list is real, not decoration:** Listening → Transcribing →
  Extracting → Verifying → Ready, each driven by the actual pipeline stage.
- **Clinic profile:** doctor name, qualifications, registration number, clinic name,
  address, phone. Entered once from a small settings panel, **updatable anytime**,
  printed at the top of every prescription.
- **Today's patients:** a list of encounters completed today; selecting one loads
  that prescription back onto the sheet.
- **Preserve everything that works:** dictate → format → spoken correction →
  Save & Print, the verify gate, the ✓/?/!/± pills, the "AI draft — doctor must
  verify" disclaimer.
- **Print fidelity:** the `@page` boundary and the section-bar bleed fix made on
  2026-10-13 stay; the doctor/clinic block prints at the top.

## Non-goals

- No cloud storage/sharing (SMB/Drive/S3) — still a later phase.
- No auth/login/roles — still the single local doctor.
- No multi-day history, search, or filtering — "today" only, for now.
- No changes to the deterministic pipeline's behavior.

## Anti-goals (what would make this a failure even if it works)

- Losing the verify gate or the disclaimer in the restyle.
- A step list that lies (shows "Verifying" when nothing is verifying).
- A clinic profile that silently fails to save or print.
- Hiding errors behind the new chrome (the visible error + Retry must survive).
- A printout that bleeds off the page again.

## Constraints

- Windows ARM64; Python 3.12; stdlib-only DB (`backend/db/`); vanilla JS, no build step.
- New DB access goes through `backend/db/__init__.py` helpers; no raw SQL in endpoints.
- Tests stay offline; the suite must pass.
- Keep the disclaimer verbatim and the grounding pills.

## Decisions the human made

- **Combine A + B**: two-pane professional workspace with the assistant visible.
- **Clinic profile**: one-time entry, **updatable**, from a small settings panel,
  printed on every prescription.
- **Add a "patients done for the day" list.**
- Full written-design + plan treatment (not a quick change).

## The builder's calls (made here, vetoable)

- **Real step chips** driven by pipeline stages (`/api/transcribe` → `/api/format`'s
  grounding → save), not faked.
- **Click a "today" patient to reopen** its prescription on the sheet (re-print).
- **Clinic profile stored in SQLite** (a single-row settings/profile record), edited
  via `GET`/`PUT /api/v1/profile`.
- **"Today" = the local calendar day**, derived from `documents.created_at`.
- **One new endpoint** `GET /api/v1/encounters/today` returning today's saved
  encounters (patient name, OP, time, document id) for the sidebar.
- **Clinic profile is a single-row settings record** (not tied to the `users`
  table); the "New patient" reset affordance is kept.
- **"Today" = the server machine's local calendar day**, computed from
  `documents.created_at` (UTC) converted to local time.
- **The clinic profile is optional**: Save & Print is not blocked when it is
  blank; the header prints placeholder lines and a first-run hint nudges the
  doctor to fill it in.

## Left to the builder

- The clinic-profile schema/table and its migration; the settings-panel UX.
- The "today" query shape and how a selected encounter is loaded back (which
  document fields to re-render).
- The full frontend restructure into the workspace layout, and the step-chip wiring.
- Print stylesheet updates for the new header block.

## Resolved with the human (2026-10-13)

1. **Reopening a "today" patient is editable, and re-saving UPDATES the existing
   document** (not a new insert). The save path needs an update branch; the verify
   gate still applies.
2. **Transcription stays one-shot.** "Live transcript" means the transcript is
   displayed in the middle pane *after* the doctor stops — no streaming.
3. **Assistant steps stay coarse** for now (no backend progress channel):
   Listening → Working → Ready, truthful but not per-stage.
4. **The clinic profile appears in the server-rendered PDF too.** A render uses
   the **current** profile; re-saving/reprinting may therefore show a changed
   letterhead (accepted).



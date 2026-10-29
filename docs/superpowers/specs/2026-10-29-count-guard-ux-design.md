# Count Guard UX: one record, two views

**Status:** Draft, 29 Oct 2026. From a brainstorm with the project owner. Synthetic data only. Research demo,
not for clinical use. Builds on `docs/hackathon/07-care-journey.md`, which stays the source for the rules,
the nudge wording and the backend.

## One-page summary

Count Guard today is three apps behind eight tabs: the **morning** steps (`/opd`, `/ot`, `/ward`,
`/morning`), the **camera count** (`/count` → `/case/:id` → close), and the **care journey** (`/journey`,
`/doctor`, `/nurse`, `/patient`, `/audit`). Three things appear twice: strip checks, the discharge
document and the swab count. A judge watching a 3-minute video cannot tell which screen is "the product".

The redesign keeps every backend rule and changes only how people reach them:

1. **One record per patient, shown two ways.**
   - The **chart** shows one patient's whole journey: Clinic → Theatre → Ward → Home.
   - The **queue** shows what needs *me* across all my patients.
   - Both read the same nudge events, so an answer in one appears in the other.
2. **Staff act in the chart. The queue points into it.** A queue row's "Open →" lands on the exact chart
   line, with the context above it. In the demo, queue rows keep their quick action buttons too. Later the
   queue becomes read-only.
3. **Patients are the exception.** "Today" is where the patient acts (check-in, doses, Need help). "My care"
   is the read-only timeline.
4. **Two tabs replace eight:** "My queue" and "Patients", with a role switcher. Patients get "Today" and
   "My care".
5. **A "who's waiting on whom" strip** of open handoffs sits on top of every staff screen.
6. **A demo clock** (demo builds only) jumps between stages and moves time forward, so time-based nudges fire
   on cue in the video.
7. **The video gives the doctor, the nurse and the patient roughly equal time**, about 60 s each, and shows
   the whole story.

**The line we hold is unchanged.** A nudge sets a recorded fact beside a recorded intent. It never advises.
Rules decide; models only explain.

## Decisions

| # | Decision | Who decided |
|---|---|---|
| U1 | Both views exist: per-patient chart (A) and per-role queue (B) | Owner |
| U2 | Staff act in the chart; the queue is triage and becomes read-only after the demo | Owner |
| U3 | Patient acts in "Today"; "My care" is read-only | Agreed in the brainstorm |
| U4 | In the demo, actions work from both views | Owner |
| U5 | Keep all four ideas: deep link to the chart line, waiting strip, two tabs, demo clock | Owner |
| U6 | Video: three people, roughly equal time, whole story | Owner |
| U7 | No backend rule, nudge wording or ledger behaviour changes | Follows from 07 |
| U8 | Theatre stage has both counts, manual first. The manual count (19 → 20/20) is inline. A "Count by camera" button opens the existing camera screen (`/case/:id`, SAM 3.1). Its result is filed back to the patient through `POST /morning/episodes/{id}/count/from-case` (`app/morning/routes_extra.py:118`). The video uses the manual beat; the camera is shown as the door to SAM 3.1 | Owner |

## Goals, non-goals, anti-goals

**Goals**
- A first-time viewer understands who does what within 10 s of any screen.
- Every fact lives in one place. There is one strip check, one count, one discharge card and one audit.
- The 3-minute video can be recorded in one pass by clicking through the demo clock.

**Non-goals**
- Real sign-in and permissions. The role switcher is a lens, not security.
- Live feeds such as HL7 vitals, SMS or WhatsApp. They stay "planned" as in 07.
- A full ward board. The queue covers 2–3 seeded patients; that is enough to make it real.

**Anti-goals (a failure even if it works)**
- Any screen text that reads as advice: give, take, stop, increase, reduce, start, administer, consider.
- A queue so rich that the chart is never opened. That would bring back the tension U2 resolved.
- The count disappearing from the story. It is the only feature no competitor has, apart from ZeroLeft.

## Actors

| Actor | Name in the demo | Acts in | Reads |
|---|---|---|---|
| Doctor | Dr. A. Rao | Chart (Clinic stage: prescription, orders, limits; Home stage: sign card) | Queue: to-do rows (orders not set, card not signed). No nudge is addressed to the doctor today |
| Theatre nurse | Asha | Chart → Theatre stage (count screen) | No queue needed. Theatre is a focused task |
| Ward nurse | Meena, then Kavya | Chart (Ward stage: doses, observations, answers, handover) | Queue: "Needs you now" |
| Patient | R. Kumar, 58 M | Today | My care |
| Off-screen | Pharmacist, reviewer | None | Audit lens |
| The system | Rules R1–R6 and the 10 journey nudges | Raises nudges | None |

## Screens

### Staff shell

```
┌─────────────────────────────────────────────────────────────┐
│ Count Guard   [My queue | Patients]            Nurse ▾      │
├─────────────────────────────────────────────────────────────┤
│ Waiting: Meena → BP nudge 2 h 20 · Rao → sign card 20:00 …  │  ← strip
├─────────────────────────────────────────────────────────────┤
│                     queue or chart                          │
└─────────────────────────────────────────────────────────────┘
                         [Day 1 · 18:30 | Clinic Theatre Ward Home | +1 h | Reset]  ← demo clock
```

- The role switcher offers Doctor, Nurse and Patient. Picking Patient replaces the shell with the patient
  app.
- "Patients" lists the seeded patients. Each opens the chart.
- The Guide (`/guide`) stays reachable from a small link; it is not a tab.

### Queue ("My queue")

- One row per open nudge addressed to the current role, across all patients: bed, patient, the nudge text,
  how long it has waited.
- A second kind of row, a **to-do**, is worked out in the frontend from the ledger: orders not set, discharge
  card not signed, handover not accepted. To-dos are not nudges and are not written to the ledger. They are
  the doctor's whole queue, because every nudge rule addresses `nurse` or `patient`
  (`app/journey/nudges.py:70-172`).
- "Open →" opens the chart at that nudge line, highlighted, with the lines before it in view.
- In demo builds, a row also shows the nudge's main action (Answer, Log). This is removed when the queue
  becomes read-only.
- Below the open nudges: "My patients" (one line each) and the shift handover entry.

### Chart

- Header: patient, age, procedure. Stage bar: Clinic, Theatre, Ward, Home. Each stage is marked done, now or
  later, with one key fact (for example "count 20/20").
- Body: one timeline in time order. Each line shows who, when and what. Corrections are shown struck through,
  with the replacement beside them.
- Nudges are shown inline at their time, with their actions.
- Lenses (chips): Nurse, Doctor, Patient, Everyone (audit). A lens filters and emphasises lines. It does not
  hide nudges addressed to the current role.
- Stages contain the screens that exist today:

| Stage | Absorbs | Content |
|---|---|---|
| Clinic | `/doctor` import and orders, `/opd` | Prescription, ward orders and limits. The strip check and its nudge appear here as lines, but the patient makes them from Today, because the nudge is addressed to `patient` |
| Theatre | `/ot` manual count, `/count` → `/case/:id` → close | One count screen: camera or manual input, the same rules R1–R6 and closing gate |
| Ward | `/ward`, `/nurse`, handover | Doses, observations, nudges, handover Meena → Kavya |
| Home | Discharge sheet and card, check-in, Need help | Signed card, check-ins, help requests |
| Audit lens | `/audit` | Every line, who, when, and what replaced it |

### Patient app

- **Today:** daily check-in (about 1 min), medicines for today with ticks, Scan a strip, My discharge card,
  Need help.
- **My care:** read-only timeline of the same record, in plain words.

### Mockups

Mockups for this design are in `.superpowers/brainstorm/41388-1793247102/content/`:
- `a-vs-b.html`: nurse and patient screens.
- `ideas.html`: deep link, waiting strip, two tabs, demo clock.

They are reference sketches, not specs for pixel layout.

## How the pieces connect (data)

No new storage. All views read the existing episode ledger.

- Queue rows are `open_nudges(events)` per seeded episode, filtered by the nudge's `to` field
  (`app/journey/nudges.py:192`).
- The deep link uses the nudge id. The chart scrolls to the line whose `fact_id` or event id matches.
- The waiting strip lists open nudges plus pending handovers and unsigned cards, labelled "who → what · how
  long".
- The demo clock posts the chosen time as `at_ms` to the existing actions and to `POST .../tick`. `_at`
  already accepts an explicit `at_ms` (`app/journey/api.py:131`). The ward clock already stops at discharge
  (`app/journey/nudges.py:81`).
- Multiple patients need 2–3 seeded episodes. Episodes can already be listed (`app/morning/api.py:84`).
  Today the frontend keeps a single episode in session storage (`frontend/src/episode.js`); the queue needs
  all seeded ones.
- **Seeding** is a new backend demo endpoint. It creates R. Kumar empty, at Day 0 09:00, so the video builds
  his story live. It writes two other patients through the same journey actions, so the same rules raise
  their nudges:
  - Bed 7, S. Iyer: on Ward Day 2, with an open `obs_overdue` for the nurse.
  - Bed 9, A. Das: at Home, discharge card signed, no open nudge.
- **The demo clock only moves forward.** The ledger is append-only, so a stage jump to an earlier time is
  disabled. **Reset** reseeds: it creates new episodes and points the frontend at them. Old episodes stay in
  the store. The clock drives every seeded episode, so a jump posts `tick` to each one.
- `POST .../nudges/{id}/seen` ignores `at_ms` today (`app/journey/api.py:334`). It needs to accept one, so
  an answer made under the demo clock is stamped with the demo time. This is an API parameter, not a rule
  change, so U7 holds.

## The video (≈ 3:00, equal time)

| Time | Act | Who | On screen | Ends with on the strip |
|---|---|---|---|---|
| 0:00–0:05 | Title | — | "One patient, three people" | — |
| 0:05–1:00 | Clinic | Dr. A. Rao, then R. Kumar | Prescription imported (≈ 20 s). Clock → Day 0 19:00: the patient scans strips in Today, amlodipine 10 mg ≠ 5 mg, nudge, pharmacist swaps it (≈ 15 s). Clock → Admission (Day 1 07:00): a short doctor beat sets the ward orders and BP limit 90 (≈ 20 s). The patient appears twice, so the three people still share the time equally | "Pharmacist → swap strip ✓" |
| 1:00–2:00 | Theatre → Ward | Asha, then Meena | Count: 19 of 20 → found in drape → 20/20, struck through (≈ 30 s). Clock → Ward (11:00): the nurse logs paracetamol on arrival. Clock → 16:10. Queue → Open → BP 86 nudge in the chart → Answer. Clock → 18:30: paracetamol overdue (the 6 h after the 11:00 dose), logged. Handover to Kavya | "Kavya → accept handover", "Dr. Rao → sign card" |
| 2:00–2:55 | Home | R. Kumar | Card signed 20:00. Clock → Day 2. Today: check-in ticks fever, Need help "dressing is wet". It appears in the nurse queue. Audit lens: the whole journey, both corrections struck through | All ✓ |
| 2:55–3:00 | Close | — | "It documents and nudges. People decide." | — |

`POST /journey/episodes/{id}/play` stays as the one-click fallback that writes the whole story.

## Constraints

- Frontend files stay under 500 lines each.
- Synthetic data only. Every screen keeps the "Research demo, not for clinical use" line.
- The existing tests (`backend/tests/test_journey.py` and the rest, 97 at last run) must still pass. No
  backend rule changes. The backend gets two small additions only: the demo seed endpoint and `at_ms` on
  `nudges/{id}/seen`.
- The demo clock must not exist in a non-demo build.

## Left to the builder

- Component structure, routing names and styling within the existing Lightday look (`frontend/src/styles.css`).
- How the chart scrolls to and highlights a line.
- Whether old routes redirect into the chart or are removed.
- The exact wording of the waiting-strip pills, within the nudge wording rules in 07.

## Calls made by the agent (check these)

The builder check raised these points. The agent settled them without the owner. Each is a reversible
default.

| # | Question | Call |
|---|---|---|
| C1 | No nudge is addressed to the doctor. What fills the doctor's queue? | To-do rows worked out in the frontend. No new rule |
| C2 | Who owns the strip check? | The patient, from Today, as in 07. The chart's Clinic stage shows it. Act 1 includes a 15 s patient beat |
| C3 | What are the seeded patients? | A backend demo seed: Kumar starts empty, plus Iyer (ward, open obs nudge) and Das (home, no nudge) |
| C4 | How does the clock behave on an append-only ledger? | Forward only. Reset reseeds. One clock ticks every seeded episode |
| C5 | Does an answer under the demo clock get the demo time? | Yes. `nudges/{id}/seen` accepts `at_ms` |

## Open questions

None. O1 was answered by the owner (U8).

## Appendix: where the code is

| What | File |
|---|---|
| Routes and the 8 tabs today | `count-guard/frontend/src/App.jsx:160-173` |
| Single-episode loader | `count-guard/frontend/src/episode.js` |
| Journey API client and `useJourney` | `count-guard/frontend/src/journey.js` |
| Nudge rules, `fresh`, `open_nudges` | `count-guard/backend/app/journey/nudges.py:176-196` |
| Ward clock stops at discharge | `count-guard/backend/app/journey/nudges.py:81` |
| Explicit `at_ms` and nudge raising | `count-guard/backend/app/journey/api.py:131-144` |
| Journey routes (tick, nudges seen, handover, play) | `count-guard/backend/app/journey/api.py:196-409` |
| Episode list | `count-guard/backend/app/morning/api.py:84` |
| Current script and acceptance checks | `docs/hackathon/07-care-journey.md` |

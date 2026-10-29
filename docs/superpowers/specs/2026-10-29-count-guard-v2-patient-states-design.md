# Count Guard v2: the patient's state drives the screen

**Status:** Draft, 29 Oct 2026. From the owner's browser walk of v1 and the brainstorm that followed.
Synthetic patients only. Research demo, not for clinical use. Replaces the stage bar of
`2026-10-29-count-guard-ux-design.md` (v1); the v1 queue, chart, ledger and role switcher stay.
Deadline: about 2 days from 29 Oct 2026.

## One-page summary

The owner walked v1 in the browser and could not follow it. The four-stage bar (Clinic, Theatre, Ward,
Home) showed every patient the same steps, though their paths differ. Nothing told the viewer what the
doctor had just done or what would happen next. The nurse never received the doctor's orders.
Switching role did not refresh the screen. Several buttons and selections did not do what they said.

v2 gives each patient **one state** at a time. The person who opens the patient sees that state, the
actions for it, and a plain line: *what just happened, who is next, what they will do*.

```
 CLINIC ──doctor: Admit──► ADMITTING ──nurse completes admission──► WARD ◄──────────┐
   │                                                            │    │             │
   └─doctor: Close visit ─► CLINIC DONE (clinic-only patient)   │    └─doctor: Send to theatre
                                                                │          ▼       │
                             doctor dictates discharge ◄────────┘      THEATRE ──surgery ends
                                        ▼
                                  DISCHARGING ──nurse completes discharge──► HOME
```

The work moves by itself. The doctor **dictates** orders with a record button. The orders reach the
**nurse's queue**. The nurse **acknowledges** them; each item becomes a **task**. She completes a task
with a tap or by voice, and can add a **photo** as proof, which is checked against the task. In theatre
and for ward procedures, **video** checks the tray and the count with SAM 3.1. The **patient** sees all
of it, in every state, and has their own "Ask" section: a bot that answers only from their record, a
question to the doctor, a healing photo for review, a photo of medicines to identify. Everyone sees
whether the doctor is free, so nobody waits in a corridor.

Five projects, built in order, each by an autonomous build loop:

| # | Project | Done when |
|---|---|---|
| P1 | Patient states and workflow | Three demo patients walk their paths by tap; orders reach the nurse; role switch refreshes |
| P2 | Voice and photo proof | Doctor dictates orders and discharge; nurse ticks off by voice; photos checked against tasks |
| P3 | Video detection | Tray plan from a procedure template checked by video; swab count; saline set-up on the ward |
| P4 | Patient "Ask" section and doctor status | Grounded bot, ask the doctor, healing-photo review, medicine photo, doctor availability |
| P5 | Demo run | Click-by-click video script for the three paths, checked end to end by an automated browser run |

**The line we hold is unchanged.** Rules decide; models draft, read and explain. No model output becomes
a record or a clinical decision until a person confirms it. No screen text advises.

## Decisions

| # | Decision | Who decided |
|---|---|---|
| D1 | Approve this design once; then plans and build run without stopping, except for an irreversible step, a security-sensitive step, a push or merge, or a plan broken beyond a reasoned ruling | Owner |
| D2 | Work on branch `count-guard-v2`; first commit is today's uncommitted v1 work as baseline, tagged `count-guard-ux-v1` as the backup; one commit per task; never push | Owner |
| D3 | If behind: first cut is live ward-saline video (use prepared results); second cut is live medicine-photo identification (prepared results) | Owner |
| D4 | Keep v1 (queue, chart, ledger, role switcher, waiting strip); replace the stage bar with the patient's state; the clock survives only as "skip ahead" for time-based nudges | Owner |
| D5 | Demo patients: **Kumar** clinic → admit → theatre → ward → home; **Iyer** collapses on the ward → saline → treated → home; **Das** clinic visit only | Owner |
| D6 | Theatre tray and count data come from sample data modelled on real surgeries (see "Sample data") | Owner |
| D7 | Doctor status: set automatically by where the doctor is (a patient they diagnosed goes into theatre → "In theatre with R. Kumar, expected free 12:30"), and settable by hand per doctor ("Available" / "Busy until …"); hand setting wins until it expires | Owner |
| D8 | The patient gets a new section, **Ask**, holding the bot, questions to the doctor, healing-photo review and medicine photo | Owner |
| D9 | A photo that does not match its task is flagged, never blocking; the nurse decides | Owner |
| D10 | A task is completed by a tap or by dictation, whichever is easier; dictation is shown as text and confirmed with one tap before it is saved | Owner |
| D11 | Live Muse and SAM 3.1 calls when the key is set; every call has a prepared fallback so the demo runs offline; tests and build agents never spend credits | Owner |
| D12 | The owner films the tray/swab clip and the saline set-up clip; until then P3 builds against stand-in clips and recorded results | Owner |
| D14 | A closing count that does not match never blocks leaving theatre, but leaving with an open count needs the surgeon to record a reason ("X-ray ordered", "searched, not found"); the open count stays flagged on the chart and in the queue. Server: theatre → ward with an open count and no reason is refused (409) | Owner |
| D15 | Retire `/play` from the menu (code kept). After P4, a final task **P5** writes the click-by-click video script for the three paths and an automated browser run that checks it end to end | Owner |
| D13 | Record button: browser microphone → Muse Voice Transcribe (`app/adapters/voice.py`) → Muse Spark structures the text; a typed box is the fallback. Doctor Dictation's Whisper path is not used | Owner |

## Goals, non-goals, anti-goals

**Goals**
- Anyone opening a patient knows within 5 s: the state, what just happened, who is next and what for.
- Each person sees only the actions their state allows. A clinic-only patient never shows ward actions.
- Every doctor order becomes nurse tasks that can be seen to be done, with proof where the task allows.
- Fewer round trips and less waiting: the patient asks before travelling; staff see who is free.
- The 3-minute video follows the three patients' paths and gives doctor, nurse and patient equal time.

**Non-goals**
- Real sign-in and permissions. The role switcher stays a lens.
- Live vitals feeds, SMS, WhatsApp, paging. They stay "planned".
- Dosing logic of any kind. The app records what a person ordered; it never computes a dose.

**Anti-goals (a failure even if it works)**
- Any text that advises: the v1 regex `\b(give|take|stop|increase|reduce|start|administer|consider)\b`
  still applies to every model-written and template string shown to a person, except quoted order text
  the doctor dictated and the doctor's own answers.
- A bot answer with no source line, or a source the record does not contain.
- A dictated or detected value saved without a person confirming it.
- The count disappearing from the story. It is still the feature no competitor has but ZeroLeft.

## States

| State | Entered by | Who acts | Actions in this state | Leaves when |
|---|---|---|---|---|
| `clinic` | Seed, or new clinic visit | Doctor | Diagnose note, prescription (import or dictate), strip check, reference photos, **Admit** or **Close visit** | Doctor admits or closes |
| `clinic_done` | Doctor: Close visit | Patient | Read-only record; patient Ask section | — |
| `admitting` | Doctor: Admit (with reason and first orders) | Nurse | Admission checklist (identity band, allergies, baseline obs, consent), acknowledge orders | Nurse completes admission |
| `ward` | Admission done, or theatre ends | Nurse, doctor | Nurse: tasks from orders, obs, doses, procedures (saline). Doctor: dictate orders, photos, **Send to theatre**, **Dictate discharge** | Theatre or discharge |
| `theatre` | Doctor: Send to theatre (procedure template confirmed) | Scrub/theatre nurse, doctor | Tray check by video, manual and camera counts, start/end of surgery | Surgery ended and count closed → `ward`; an open count needs a recorded reason (D14) |
| `discharging` | Doctor dictates discharge | Nurse | Discharge checklist (card signed, medicines handed over, reminders set) | Nurse completes discharge |
| `home` | Discharge complete | Patient | Daily check-in, doses, Ask section | — |

A state change is an event `patient.state {from, to, by, reason}` in the existing append-only ledger. The
server refuses a change the table does not allow (409 with a plain reason). Earlier states stay visible
as read-only history in the chart; nothing is edited after its state ends.

## Actors and what they see

**Every screen header**, for every role: patient name, state badge, and the *now / next* line, e.g.
"Dr. Rao admitted R. Kumar at 09:40 · Next: Nurse Meena completes admission". Plus the doctor-status
chip: "Dr. Rao: In theatre with R. Kumar, free about 12:30".

**Doctor (Dr. A. Rao).** Queue: their patients with what needs them (orders to sign, review requests,
questions, discharge to dictate). Opening a patient shows the details carried from earlier states and
three primary actions, wherever the state allows them:
1. **Dictate orders**: record → transcript → structured order items → doctor checks and signs.
2. **Take photos**: reference photos (a wound, a rash), kept on the chart for later comparison.
3. **Dictate discharge**: record → discharge summary draft → doctor signs → state `discharging`.

**Nurse (Meena on the ward; Asha in theatre).** Queue: new orders to acknowledge, tasks due and overdue,
admission and discharge checklists, nudges. A signed order appears in the queue immediately as
"New orders from Dr. Rao for R. Kumar". Acknowledge → each item becomes a task with a due time. A task is
`tick` (one completion) or `start_end` (saline running from 14:05 to 16:10; surgery 10:05 to 11:40).
Completing a task writes the existing fact event where one exists (`dose.given`, `obs.recorded`) so v1
nudges keep working.

**Patient (R. Kumar, S. Iyer, A. Das).** Sees their own record in every state: state, orders and whether
each was done, with proof (who, when, the photo), the discharge summary. **Today** keeps the v1 actions.
**Ask** is new (P4). Sees the doctor-status chip.

## Data: new ledger events

All events keep v1's shape (`kind`, `ts_ms`, `by`, payload) and `at_ms` demo time. Builder may rename.

| Event | Payload (essentials) | Written by |
|---|---|---|
| `patient.state` | from, to, reason | Doctor or nurse action |
| `order.drafted` | transcript, items[] (kind, text, every_h, due_ms, mode, proof) | Dictation (model) |
| `order.signed` | draft_id, items[] as edited | Doctor |
| `order.acknowledged` | order_id | Nurse |
| `task.created` | order_id, item index, title, kind (dose, obs, procedure, check, other), mode (tick, start_end), proof (none, photo, video), due_ms, every_h | Server on acknowledge |
| `task.started` / `task.done` | task_id, via (tap, voice), transcript?, proof_id?, match (ok, mismatch, none), values? | Nurse |
| `photo.added` | purpose (reference, proof, healing, medicines), media path | Anyone |
| `proof.checked` | photo_id, task_id, read (what the model saw), match, why | Model, shown to nurse |
| `tray.planned` / `tray.checked` | template, expected items / seen items, missing | Doctor / video |
| `discharge.drafted` / `discharge.signed` | summary sections | Model / doctor |
| `question.asked` / `question.answered` | to (bot, doctor), text / answer, sources[] | Patient / bot or doctor |
| `review.requested` / `review.answered` | photo_id, note / decision (no visit needed, come in, call) | Patient / doctor |
| `doctor.status` | doctor, status, until_ms, source (auto, manual) | Server or doctor |

## The four projects

**P1 · Patient states and workflow** (no models). States table and transition guard; the header with
state badge and now/next line; state-scoped action panels replacing the stage bar; Admit, Close visit,
admission checklist, Send to theatre (template pick), Surgery start/end, discharge by typed summary and
checklist; orders typed by the doctor → nurse queue → acknowledge → tasks → tap to complete, `tick` and
`start_end`; seed the three patients at their starting states; the role-switch refresh bug and every
control that misbehaves, found by a scripted browser walk and fixed. Done when the three paths in D5
complete by tapping alone, and the browser walk passes.

**P2 · Voice and photo proof.** Record button (browser mic) on doctor and nurse screens; Muse Voice
Transcribe; Muse Spark turns a transcript into order items, a discharge summary draft, or a task
completion ("gave paracetamol 1 g bed 4" → matching open task, with the value); always shown for one-tap
confirm. Photo proof: medicine strip photo checked with the existing strip reader against the dose task;
BP monitor photo read and compared with the stated value; reference photos for the doctor. Each call has
a prepared fallback (D11). Done when the doctor dictates Kumar's orders and discharge and the nurse
completes two tasks by voice, one with a matching photo and one flagged.

**P3 · Video detection.** Procedure templates from the sample data (D6); `tray.planned` when the doctor
sends a patient to theatre; tray check: video of the tray → SAM 3.1 concepts → items seen vs. planned →
missing items flagged before the start; the existing swab count stays (manual first, camera second);
ward procedure check for Iyer's saline set-up (bag, line, cannula, labels seen) as a `start_end` task
with video proof. SAM concepts extend `SAM_CONCEPTS` (`count-guard/backend/app/config.py:16`). Done when
both checks run on the stand-in clips (D12) and the results appear on the chart with the frames as proof.

**P4 · Patient Ask section and doctor status.** Bot: Muse Spark answers only from the patient's own
ledger events, orders, discharge summary and leaflets on file; every answer lists its source lines; no
source → "I can't find that in your record" plus "Ask Dr. Rao". Ask the doctor → doctor's queue → doctor
answers by voice or text. Healing photo → doctor review → doctor decides (no visit needed / come in /
call). Medicine photo → strips read → matched to the prescription → each one named with its schedule;
anything not prescribed is flagged. Doctor status (D7) shown on every screen. Done when each of the four
Ask actions completes for Kumar at home and the status chip changes when Kumar enters theatre.

## Sample data (D6)

The owner wants demo data drawn from real surgeries, not invented counts. My reading: procedure
templates (instrument tray, sponge and swab counts, expected duration) are taken from published,
public instrument-tray lists and count protocols for the real procedures in the demo (open inguinal
hernia repair for Kumar), with each source cited in the data file. Patients stay synthetic. No real
patient data. The owner also wants **openly licensed real surgical video** (for example public research
datasets) searched for the SAM 3.1 detection demo, used only where the licence allows demo use, with the
licence recorded beside each clip. The owner's own prop-tray and saline clips (D12) remain the fallback
and the clips used for the count. Confirmed by the owner.

## Demo script (the three paths)

1. **Das** (clinic only): Dr. Rao sees Das in clinic, imports the prescription, the strip check flags
   10 mg against 5 mg, the doctor closes the visit. Das, on the phone, sees the visit and asks the bot when
   to take amlodipine; the bot answers with the prescription line as its source.
2. **Kumar** (operated): clinic → Dr. Rao dictates "admit for hernia repair" and first orders → Meena's
   queue lights up → she completes admission and acknowledges → Dr. Rao sends Kumar to theatre (hernia
   template) → the doctor chip flips to "In theatre" → tray check flags a missing needle holder → count
   19 → corrected 20/20 → back to the ward → Meena ticks paracetamol by voice with a strip photo → Dr. Rao
   dictates discharge → Meena completes it → Kumar at home sends a day-3 wound photo → Dr. Rao: "no visit
   needed".
3. **Iyer** (treated): on the ward Iyer collapses; Dr. Rao dictates "saline 1 L over 2 h, BP every 15
   min" → Meena acknowledges → starts saline (video check of the set-up) → BP readings by voice → ends
   saline → discharge → home; Iyer photographs the medicines bought and gets each one named with its
   schedule.

## Constraints

- Keep files under 500 lines. Validate input at system boundaries (every new route uses pydantic models
  with bounds, as v1 does).
- Backend: FastAPI app in `count-guard/backend/app`, ledger in `app/store.py`, journey routes in
  `app/journey/`. `journey/api.py` is already 18.7 KB; new routes go in new modules.
- Frontend: React + Vite in `count-guard/frontend/src`; v1 care app in `src/care/`. Node built-in test
  runner: `node --test 'src/care/*.test.js'`.
- Models: Muse Spark 1.3 (`app/adapters/spark.py`), Muse Voice Transcribe (`app/adapters/voice.py`),
  SAM 3.1 (`app/adapters/sam.py`). Prompts carry "Do not give medical advice."
- Tests never call a model; adapters are faked. Build agents never run anything with `--spend`.
- The v1 tests (111 backend, 15 frontend) keep passing or are updated in the same task that changes
  the behaviour they pin.

## Time and seeds (my calls, from the builder check)

- **One ward clock.** All patients share one demo clock, as in v1. Every action is stamped with the
  current demo time (`at_ms`); a tap never moves the clock. "Skip ahead" (+15 min, +1 h, next due task)
  moves the whole ward forward, as real time would, so due and overdue tasks and the doctor's "free about"
  time all read from the same clock. The v1 fixed stage times (`frontend/src/care/clock.js:8`) go; the
  clock no longer knows about stages.
- **Starting seeds.** Kumar and Das start in `clinic`, with nothing recorded yet. Iyer starts in `ward`,
  already admitted the day before (admission is shown on Kumar's path, not twice), with standing orders
  (obs every 1 h, systolic BP limit 90). The v1 Das discharge-card seed (`backend/app/journey/seed.py:72`)
  is replaced. v1 seed tests are rewritten in P1.
- **Iyer's collapse** is a recorded fact, not a state change: the nurse records BP 82 (by tap in P1, by
  voice in P2); the existing limit nudge fires to the nurse and, new in P1, to the doctor's queue; the
  doctor opens Iyer and dictates the saline orders. Iyer stays in `ward` throughout.

## Left to the builder

Screen layout within the header + panel + history pattern; event names (keep the payload meaning);
how the now/next line is worded per transition (plain English, no advice); template file format; how a
voice completion picks among several open tasks (ask the nurse when more than one matches); fallback
data format; queue ordering.

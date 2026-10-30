# Count Guard v2 UX refinement: design

Owner request (30 Oct): "You are a Senior UX Design Engineer — understand the use-case, refine the UX, then check all flows work." The owner approved the findings below with "yes do all".

Branch: `count-guard-v2-clarity` (continue on it). Evidence came from:
- the 31-beat demo run;
- a 35-screen off-script sweep (doctor, nurse, patient, theatre, clinic, phone width 390 px).

## Who uses it, and what they need

| Who | Question on their mind | The app should |
|---|---|---|
| Doctor | "What is waiting on me, and can I clear it fast?" | queue → open → act → done, voice first |
| Nurse | "What is due now, and can I prove I did it?" | due first, one tap or one sentence, proof attached |
| Patient (phone) | "Where am I in my care, and who do I ask?" | plain words, what's next, one clear way to ask |

## Binding constraints (same as the clarity pass)

- **Demo check:** `make demo-check MODEL_API_KEY=` stays green with 31 beats and 58/58/58 s. Beats, steps and `docs/demo/count-guard-v2-video-script.md` change together.
- **Test suites:** backend, care and demo node tests stay green. Every behaviour change gets a test.
- **Wording:** the no-advice regex applies to all new copy. Files stay under 500 lines.
- **Models:** never call a live model in tests or checks. Never touch ports 8100/5173.
- **Commits:** commit with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com`, with no Co-Authored-By line. Never push.

## A. Wrong behaviour

**A1. Errors stay where they happen.**
- Today one ward-wide error (`care/ward.js:80`) is shown on every page (`CareShell.jsx:141`). For example, a patient's medicine-photo error appeared on the doctor's queue.
- Decision:
  - An error belongs to the patient episode and the action that raised it.
  - It shows only on that patient's pages, near the action.
  - It clears on role change, patient change and route change.

**A2. Clinic orders say what will happen to them.**
- While the patient is in clinic, an unacknowledged order reads "Starts when the patient is admitted" (not "Waiting for the nurse").
- After `clinic_done` it reads "Not started: the visit was closed."
- Same rule in the patient view.

**A3. Open items come first, and "nothing to do" is true.**
- On the doctor's chart, the Ask inbox (questions, healing photos) renders directly under NOW/NEXT, above Photos.
- "Nothing to do from this state" shows only when nothing is open for the doctor.

**A4. Plural.** `stories.py:91` "1 doses" → uses `count_of` ("1 dose", "2 doses").

**A5. The medicine photo can match signed orders.**
- Today matching reads only the prescription.
- Decision: match against prescription rows plus signed dose orders.
- If neither exists, the Medicine photo card shows the reason inside the card (A1). It also lists what the record holds instead of failing silently.

## B. UX refinements

**B1. One voice-first input.**
- Replaces the four controls (Record / choose audio file / type box / "Use this text") with one:
  - a text box with a mic button inside its top-right;
  - recording fills the box;
  - a small "upload audio" link sits below;
  - one primary button below the box, with the action's verb ("Draft orders", "Draft discharge", "Use this", "Send answer").
- Applies everywhere `Dictate` is used.
- Keep the accessible names of the controls the demo uses, or update the demo with them.

**B2. One answer box for the doctor.**
- The Ask inbox answer uses B1's input directly: voice lands in the answer box, the doctor edits it, then presses Send answer.
- The second textarea goes.

**B3. Due work looks primary; not-due work does not.**
- A nurse task that is due or overdue keeps the black "Mark done".
- A "later" task shows an outline button "Mark done early".

**B4. The patient reads "you".**
- On patient screens, NOW/NEXT speak to the patient: "You sent a healing photo at …", "Nurse Meena gave paracetamol …".
- Staff screens keep names.

**B5. Demo chrome is compact on a phone.**
- At ≤ 640 px, the patient picker, role switch, Models chip, doctor chip, research badge and demo clock fold into one slim "Demo controls" bar. It expands on tap.
- The doctor-status chip stays visible for the patient (it saves round trips).
- The desktop layout is unchanged.

**B6. Disabled never looks clickable.** Disabled buttons use an outline and low contrast, never the filled primary look.

**B7. Each role sees its own alerts first.**
- The alert strip shows the current role's pills.
- Pills for other roles collapse into one "+N for nurse" (or doctor) pill that expands on tap.

**B8. Rows are targets.**
- In My queue and My patients, the whole row opens the chart (keyboard focusable, Enter opens).
- "Open →" stays as the visible cue.

**B9. Accessible names match visible headings.**
- Card `aria-label`s equal their visible titles: "Ask your record", "Ask Dr. Rao", "Healing photo", "Medicines photo".
- Update the demo selectors to match.

## Done when

- All of A and B are built.
- The demo check is green.
- An off-script walk passes with no failed requests or console errors:
  - every role and state;
  - photo-instead-of-video;
  - clinic orders;
  - surgeon theatre buttons;
  - patient ask, healing photo, medicine photo;
  - phone width.
- Before/after screenshots are reviewed.

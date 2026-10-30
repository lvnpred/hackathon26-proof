# Count Guard v3 UX mockups M1–M7 (design)

Owner approval, 30 Oct: "mockups come before these m1-m7". Build M1–M7 first, then the AI showcase (`2026-10-30-count-guard-v3-ai-showcase-design.md`).

- Source of the designs: the UX review artifact <https://claude.ai/artifact/TbgLk4v2j8u9hoeD9y31gc>, which has twelve findings and seven mockups.
- Branch: `count-guard-v3`, committing per task. Never push or merge without asking.

## Why

The app is correct, but every screen speaks at the same volume. The review found three root causes:
1. No single "do this now".
2. Demo controls sit on top of the product.
3. The same facts appear two or three times.

Every change below removes one of those.

## Binding constraints

- `make demo-check MODEL_API_KEY=` stays green: 31 beats, 58/58/58 s. Selectors, beats, steps and `docs/demo/count-guard-v2-video-script.md` change together.
- Backend, care and demo node tests stay green. Every behaviour change gets a test.
- The no-advice regex applies to all new copy. Files stay under 500 lines.
- Never call live models in tests. Never touch ports 8100/5173.
- Keep accessible names the demo relies on, or update the demo to match.

## M1. Journey bar and next-action card (every chart, every role)

- **Journey bar** under the patient name. Its steps are taken from `STATES` (`backend/app/journey/states.py:18`), with patient-facing labels:

  | Step | States it covers |
  |---|---|
  | Clinic | `clinic`, `clinic_done` |
  | Admitted | `admitting` |
  | Ward | `ward` |
  | Theatre | `theatre` |
  | Discharge | `discharging` |
  | Home | `home` |

  - Steps before the current one are done, the current one is highlighted, and later ones are muted.
  - A patient who went to theatre and returned shows Theatre as done while on the ward.
  - A closed clinic visit (`clinic_done`) shows Clinic as current, with the label "Visit closed".
- **Next-action card.** It replaces the NOW/NEXT lines and holds the NEXT sentence in large type.
  - Eyebrow: "Next · for you" when the next step belongs to the viewing role, or "Next · for the nurse / doctor / patient" otherwise.
  - The *primary actions that NEXT names* sit inside the card, for the role that owns them:
    - doctor on the ward: the procedure select plus "Send to theatre", and "Dictate discharge";
    - nurse in admitting: the admission checklist;
    - and so on, mapped from `allowed_moves` and the existing action components.
  - Below the actions, one muted line "Last: <NOW sentence>".
  - When the next step belongs to someone else, the card shows no buttons and says who is waiting.
- Secondary actions (Dictate orders, Wound photo) become a quiet row under the card.
- **History fold.** The timeline is collapsed by default to the last 3 events plus "Show full history (N)". The role filter becomes a segmented control *inside* the fold (finding 10). The fold state is per page view; it is not stored.

## M2. Nurse: one task list with voice on each row

- Merge "Tasks" and the nurse's "Orders and tasks" into one list with two groups: **Due now** (due or overdue) and **Later today**.
- Status wording:
  - "4 min late" for overdue, "due now" for due;
  - "next at 15:10" for later, using the demo clock and `HH:MM` (drop "Day 0" inside lists);
  - in theatre: "paused while in theatre".
- Each row has a 🎙 button that opens the voice-first box (`Dictate`) *for that task*. What is said completes that task with `via: voice`. The global "Complete a task by voice" card is removed.
- Obs tasks keep their inline fields (SBP, DBP, HR, SpO2, Temp) and a primary "Save readings" button.
- A later dose shows "Give early" (outline).
- Signed orders fold under "Signed orders · Dr. A. Rao 09:02 · acknowledged" (collapsed) for the nurse. The doctor keeps the orders card (M1) with next times.

## M3. Theatre checklist

- The four `theatreSteps()` steps (`frontend/src/care/theatre.js:4`) become one vertical checklist card:
  - done steps take one line, with ✓ and time;
  - the **current** step is the first not-done step, and it alone is expanded;
  - later steps are muted and show why they wait ("after the count").
- Tray step: a drop zone with "Upload tray video or photos" replaces the raw file input.
- Swab count: three big numbers, **opened / back / missing**. Missing is coloured red when greater than 0 and green when 0.
  - "Record pack opened" shows only until the pack is opened.
  - After that, the line "Pack opened 09:22 by Nurse Asha · change" appears.
  - The closing count input and "Count by camera" follow.
- "Back to ward" stays disabled, with the text "after step 4", until surgery has ended.
- The surgeon (doctor role) sees the same checklist with their own permitted buttons ("Surgery began" and "Surgery ended", as today).

## M4. Doctor inbox: one card per item

- Each open question and each healing photo is its own card, oldest first, with a waiting time.
- Question card:
  - the question in quotes;
  - one `Dictate` box with the placeholder "Type or say your answer";
  - the verb "Send to R. Kumar", using the patient's short name.
- Healing-photo card:
  - photo and reference side by side, with labels "Day N" and "After surgery";
  - the three decision buttons;
  - a "+ add a note" link that reveals the note field.
- The header shows "From R. Kumar · 2 waiting". The banner "Waiting for your answer above." is removed.

## M5. Doctor home: one patient list

- Merge "My queue" and "My patients" into **My patients**, with two groups:
  - "Waiting on you · N": rows with an amber left edge, the reason (for example "Question + healing photo"), the state, and the waiting time as a pill;
  - "Nothing for you now · N": muted rows with the state and the next item for others ("Nurse obs due 10:00").
- The whole row opens the chart (as today).
- The doctor status buttons move into a status pill menu at the top right ("Available ▾").
- The route `/patients` stays and shows the same list. Keep `/queue` working as an alias.

## M6. Patient phone home (Today)

- Order of content:
  1. Greeting row "Hi, R. Kumar" with the doctor status chip.
  2. A status card: the journey step in words ("You are home · day 3"), the latest thing that happened to the patient (you-wording), and the next item ("Next: wound check in clinic on day 7").
  3. Today's check-in as a single "Start check-in" button that opens the existing form.
  4. Folded sections: My discharge card; My medicines; Ask Dr. Rao (with an "N answered" count).
  5. A pinned bar at the bottom of the viewport: "Feeling worse?" with a "Need help now" button, which opens the existing need-help form.
- The name is shown once (drop the eyebrow name).
- An empty "My medicines" never comes first.

## M7. Demo dock and "(synthetic)"

- One dark **demo dock** at the top holds every demo-only control:
  - the role switch, the patient picker and the demo clock (with +15 min, +1 h, Next due, Reset);
  - a "Synthetic data · models: offline (prepared)" text.
  - At ≤ 640 px it folds to one line: "DEMO · Nurse · 09:12 ▾".
- The product bar below it holds only: the brand, the role's nav, an alerts pill ("2 alerts", which expands the existing strip pills), and the doctor status for the patient.
- Remove "(synthetic)" from displayed names in the care screens. The backend keeps it; the frontend strips it in one helper, `displayName()`. The research-demo notice stays in the dock.
- The "Research demo. Not for clinical use." line stays visible on every screen (in the dock).

## Done when

- M1–M7 are built, and the demo check is green.
- An off-script walk (the scratchpad `sweep.mjs`) passes with no failed requests, no console errors and no horizontal scroll at 390 px.
- The before/after screenshots have been reviewed.

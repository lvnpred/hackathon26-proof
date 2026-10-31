# Count Guard v4 UX: AI moments in every workflow (design)

Owner ask, 31 Oct: "another UX check … use design thinking to understand the use-case and make sure the user can do it easily … include all the capabilities into the workflows and a way to look at them in detail, like making those artifacts interactive … everything should align with the concept."

The inputs for this spec:
- a fresh walk of 96 screens (all 32 demo beats, at 1200 and 390 px), saved in the scratchpad at `ux-check-v4/`;
- an inventory of all 21 AI and rules capabilities, with file:line, in Appendix B;
- the earlier review (M1–M7, already built).

This spec runs **before** the operations agent (`2026-10-31-count-guard-ops-agent-design.md`). The agent's "Why" and "AI did this" use the Inspector defined here.

## Summary (one page)

**The concept, in one line.** Count Guard makes sure nothing gets lost around one patient: instruments, swabs, medicines, words and questions. The AI does the reading, counting and writing. People decide.

**What is wrong today.** The AI does real work, but the screens hide it.
1. AI results look different in every place:
   - "(Prepared demo result)" sentences;
   - "SAM 3.1 · Sample" captions;
   - "Heard by:" lines;
   - "Rules (no model)" banners.
2. Only video and photo checks can be opened for detail. Voice drafts, record-bot answers, nudges, the day plan, handover and brown-bag rows cannot.
3. Some capabilities never reach the main workflow:
   - the strip check at clinic is **typed**, although the photo reader exists;
   - the handover draft lives only on the older `/nurse` screen;
   - staff cannot see what the record bot told a patient.
4. A finished step keeps its full viewer open. In theatre, the tray viewer fills the screen while the current step is "Surgery ended".
5. The chart repeats the same artifacts three or four times: Photos, Video checks, Orders and tasks, and Timeline.
6. `/ai` is a catalogue of model cards behind a demo-dock link. It is not a view of what the AI did for which patient.

**The fix: one pattern, used everywhere.**

| Piece | What it is |
|---|---|
| **AI moment** | One compact line wherever the AI did something: model chip · finding · status (matches / flagged / needs you) · **Inspect** |
| **Inspector** | One drawer (a full-screen sheet on a phone) with four tabs: **Input · What the AI found · Record · Model**. The content is interactive and depends on the capability: boxes ↔ list for video; values ↔ form fields for photos; transcript words ↔ order fields for voice; cited lines ↔ timeline for answers; ordered ↔ recorded for nudges. |
| **Record & evidence** | One filterable list per chart that replaces Photos, Video checks and Orders-and-tasks |
| **AI activity** | `/ai` rebuilt as a staff page: what the AI did today, by patient and pipeline, every row opening the Inspector |

**The test every screen must pass:** in five seconds a viewer can say what the AI looked at, what it found, what went into the record and who decided.

**Cost:** about 9 days over 10 tasks. Plan: `docs/superpowers/plans/2026-10-31-count-guard-v4-ux-ai-moments.md`.

---

## 1. Empathise: who uses this, and in which moment

| Person | Their moment | Job to be done | What they fear |
|---|---|---|---|
| **Dr. A. Rao** (surgeon) | Between patients, phone or desk, 30 s per decision | "Show me what needs me, let me trust it, let me sign" | Signing something the AI got wrong without noticing |
| **Nurse Asha / Meena** | Gloved, moving, a task due now | "Capture the proof without typing, close the task" | A miscount or a wrong dose that goes unseen |
| **R. Kumar** (patient at home) | Day 3, worried, on a phone | "Is this normal? What do I take now? Did the doctor see my message?" | Being ignored, or reading jargon |
| **Demo viewer / judge** | 3:20 of video, no context | "Is the AI doing real work, and can I trust it?" | Smoke and mirrors: a chatbot glued on |

## 2. Define: point of view and "how might we"

- **POV.** Clinicians will trust AI that shows its work in their own workflow. A separate AI page doesn't earn that trust, and neither does a grey caption.
- **HMW 1.** How might every AI result show what it looked at and what it changed, in one consistent place?
- **HMW 2.** How might each capability appear at the exact step where a person needs it?
- **HMW 3.** How might a finished step get out of the way, while its evidence stays one tap away?
- **HMW 4.** How might the demo viewer see the whole AI story without leaving the patient's journey?

## 3. Findings from the walk (v4)

| # | Finding | Evidence (screenshot in `ux-check-v4/`) | Root cause |
|---|---|---|---|
| F1 | AI results use five different visual languages | `1200-20`: "(Prepared demo result)", "SAM 3.1 · Sample", "Captured to record:" | No shared AI-result component |
| F2 | Voice drafts, bot answers, nudges, day plan, brown bag and handover have no detail view | `1200-11` (orders: a "Heard:" line only), `1200-41` (day plan) | Only the evidence viewer exists |
| F3 | The strip check at clinic is a typed textarea | `1200-07` "One strip per line: name then strength" | The photo reader was added later, for patients only |
| F4 | Handover is not reachable from the care chart | inventory row 15 | Built for the older `/nurse` screen |
| F5 | Done steps keep the full viewer open | `1200-20`: the tray viewer fills the card under "Surgery ended" | `VideoCheck` always renders `Evidence` |
| F6 | The same artifacts are listed 3–4 times on a chart | `1200-28`: Photos + Video checks + Orders and tasks + Timeline | Each feature added its own card |
| F7 | Orders read like a database form (Kind / Mode / Proof / Every h) | `1200-11` | The form is the review surface |
| F8 | A patient-facing nudge sentence appears on the doctor's chart | `1200-07` "Show both to your pharmacist or doctor" | One `says` text for every lens |
| F9 | Home state says "No further steps" while a check-in is unseen | `1200-28` "Day 1 check-in … not seen yet" | `next_step` ignores unseen check-ins |
| F10 | `/ai` opens with every card reading "No calls yet". Pipeline chips are not clickable. It is reachable only from the demo dock | `1200-02` | Built as a showcase, not as a workflow page |
| F11 | Staff never see the record bot's answers | inventory row 13 | The answers are filtered to the audit lens |
| F12 | Alerts carry no "why" (which order, which reading) | inventory row 14: `fact_id` / `intent_id` unused | No detail view for rules |

## 4. Ideate → decide: the patterns

### P1. AI moment (inline)

```
[SAM 3.1 · prepared]  Saw 2 of 3 needle holders      ● Flagged · surgeon decides    Inspect ›
[Muse Voice → Spark]  2 orders drafted from 31 spoken words   ● Needs your check    Inspect ›
[Rules]               Strip reads 10 mg; prescription says 5 mg   ● Flagged          Inspect ›
```

- Chip: the model or models from `calls`, plus the mode word (`live` / `prepared` / `failed` / `Sample`) from `modeWord`. "Rules" when there is no model.
- Finding: one sentence built from numbers, never from model text, as today's `explain()` already does.
- Status: `matches` (green), `flagged` (amber), `needs you` (blue, when the viewer's role owns the next action), `failed` (grey).
- The sentences "(Prepared demo result)" and "Heard by: …" are removed. The chip carries that information.

### P2. Inspector (one drawer, interactive per capability)

The drawer slides in from the right on desktop (480 px). On a phone it is a full-screen sheet. It opens with `?inspect=<moment id>`, so a link can open it directly. It has four tabs, and the content depends on the capability:

| Capability kind | Input tab | What the AI found (interactive) | Record tab |
|---|---|---|---|
| `visual` (tray, set-up, swabs) | the clip or photos with a frame stepper | today's viewer: picture with tags + "What the AI saw" list; tap an item to highlight its boxes; Expand | the events written, with any correction ("Read 14, saved 15 by Nurse Asha") |
| `photo_read` (monitor, dose strip, brown bag) | the photo | regions with read values; tap a value → its box lights up **and** the form field it filled is named ("SBP 88 → Obs · systolic") | `obs.recorded` / `task.done` with any correction |
| `voice` (orders, discharge, answer, task) | the transcript, with audio length | transcript words highlighted by the field they became; tap "every 6 hours" → the dose row's `Every h = 6` lights up; edits made before signing show as *AI drafted → signed* | `order.drafted` → `order.signed` |
| `answer` (record bot) | the patient's question | the answer, with each cited record line; tap a line → the chart timeline opens at that line | `question.answered`, and who saw it |
| `rule` (nudges, strip mismatch) | — | two cards side by side, **Ordered / prescribed** vs **Recorded / read**, linked to `intent_id` and `fact_id`, plus the rule in words | `nudge.raised`, `nudge.seen` |
| `draft` (handover, discharge card, day plan) | the source lines | each sentence with its source events (handover `evidence` ids, day plan `evidence_id` crops) | `handover.accepted` etc. |
| `agent` (later, ops agent) | the work item's inputs | the reason, level and action | the events written, with Undo |

- **Model tab, for every kind:** the model names and ids, mode, ms, and the raw output (staff only).
- **Patient lens:** the Input and Found tabs only, in you-wording, with no raw output and no event codes.

### P3. Done steps collapse

- A finished checklist step shows its AI moment line only. **Inspect** opens the drawer.
- Only the *current* step shows the full capture UI. This applies to theatre (tray, swabs), nurse tasks (proof photos) and the doctor's draft review.

### P4. Record & evidence (one list per chart)

- It replaces the Photos, Video checks and Orders-and-tasks cards. The timeline stays as History.
- Filter chips: **All · Needs you · Photos · Video · Voice · Answers · Alerts**.
- Each row is an AI moment with a 40 px thumbnail where there is one. Newest first.

### P5. Capabilities in the flow, not beside it

| Where | Change |
|---|---|
| Doctor, clinic (A. Das) | "Check strips" becomes **Photo of strips** (`/ask/medicines` reader, SAM + Spark), with "Type instead" as the fallback. The result is a P1 line per strip. |
| Nurse chart, ward | **Shift handover** card: "Draft handover" (template, optional Spark wording) → Inspector `draft` → Accept. This brings `/handover` into the care chart. |
| Doctor, "From R. Kumar" | Record-bot answers appear as "Answered by record bot · Inspect", so the doctor can check what the patient was told. |
| Alerts pill and banner | Each alert row is a P1 line of kind `rule`, with Inspect. |
| Patient Today, day plan | Each medicine row gets Inspect: the strip crop and the prescription row it matched. |
| Patient strip photo (older path) | Moves onto the `/ask/medicines` reader, so it records `calls` and shows up on AI activity. |

### P6. Orders as sentences

- A drafted order shows as a readable sentence with chips: **Paracetamol · 1 g · every 6 h · proof: strip photo**, and **BP and pulse · every 1 h · alert if systolic < 90**.
- Tapping a chip edits that field in place. "Edit all fields" opens today's form.
- The voice Inspector maps words to chips (P2).

### P7. AI activity (`/ai` for staff)

- A **staff nav item "AI activity"**, not only a demo-dock link.
- **Story strip:** "Today the AI transcribed 3 notes, read 4 photos, counted 2 videos and raised 3 flags; staff decided all 3."
- **Pipelines** are clickable filters: Voice → Draft → Tasks; Photo → Regions → Read → Check; Video → Track → Count → Flag.
- **Activity list:** patient · capability · finding · status. Each row opens the Inspector.
- **Model cards** move below. Each shows its last real result as a thumbnail; "Try sample" stays as a secondary button. Before any flow runs, the empty state links to the first demo patient instead of "No calls yet".
- This is where the ops agent's "AI did this" feed lands later.

### P8. Truthful next card and role wording

- `next_step` in the `home` state counts unseen check-ins, unanswered questions and unreviewed photos for the doctor. Example: "Next · for you: Day 1 check-in not seen".
- Nudges get a staff wording and a patient wording. Staff example: "Strip reads amlodipine 10 mg; prescription says 5 mg." The patient keeps today's wording.

## 5. Prototype

Interactive mockups of P1, P2 (with every Inspector kind switchable), P3, P4, P6 and P7 are in the review page. Its link is in the handover message.

## 6. Test: how we know it worked

| Check | Pass |
|---|---|
| Five-second test on 6 screens (chart in each state, `/ai`) | A viewer names what the AI looked at, what it found and who decided |
| Coverage | All 18 care-flow capabilities in Appendix B (rows 1–18) have an AI moment and an Inspector kind. The older-screen-only capabilities 19–21 are out of scope |
| Steps | The nurse closes the swab count, and the doctor checks a voice-drafted order, with no scrolling past finished steps at 1200 px |
| Demo | `make demo-check MODEL_API_KEY=` green; 32 beats; 58/58/58 s |
| Sweep | 390 px: no sideways scroll, no console errors, Inspector usable one-handed |

## 7. Constraints

- No new model calls. Every Inspector reads data that the events already carry: `calls`, `evidence_id`, `cited`, `intent_id` / `fact_id`, handover `evidence`, `day_plan.evidence_id`. Where a link is missing (voice word spans), the rules parser adds it. A model draft that has no spans shows the transcript unhighlighted.
- Records only. The no-advice regex applies to all copy. A finding sentence is built from numbers.
- Files stay under 500 lines. Never call live models in tests. Ports 8200/5273 only.
- Accessible names the demo uses either stay or change together with the beats, steps and video script.

## 8. Out of scope

- The older screens (`/ot`, `/opd`, `/morning`, `/count`, `/case`). They stay reachable from "Older screens".
- The operations agent. It plugs in through the `agent` Inspector kind afterwards.

## Appendix A: order with the ops agent

UX v4 (this spec) comes first. The ops agent plan then:
- uses `AiMoment` and `openInspector`;
- adds the `agent` kind;
- puts its "AI is handling" strip under the next-action card.

## Appendix B: capability inventory (21 rows, condensed)

The care flow covers rows 1–18. Rows 19–21 are older screens.

| # | Capability · models | UI today | Detail today | P-pattern |
|---|---|---|---|---|
| 1 | Order dictation · Voice + Spark 1.3 | DoctorActions.jsx:57 | partial | P1, P2 voice, P6 |
| 2 | Discharge dictation · Voice + Spark 1.3 | DoctorActions.jsx:104 | partial | P1, P2 voice |
| 3 | Spoken task completion · Voice + Spark | NurseTasks.jsx:33 | partial | P1, P2 voice |
| 4 | Doctor's spoken answer · Voice | AskInbox.jsx:24 | partial | P1, P2 voice |
| 5 | Monitor photo read · SAM + Spark | TaskProof.jsx:19 | yes | P1, P2 photo_read |
| 6 | Dose strip proof · SAM + Spark | TaskProof.jsx | yes | P1, P2 photo_read |
| 7 | Brown bag · SAM + Spark + rules | AskCards.jsx:87, MedicinesFromHome.jsx:29 | patient yes, staff no | P1, P2 photo_read, P5 |
| 8 | Patient strip photo (older path) · Spark | screens/TodayPanel.jsx:102 | no | P5 (move to row 7's reader) |
| 9 | Tray check · SAM | TheatreChecklist.jsx:17 | yes | P1, P2 visual, P3 |
| 10 | Set-up check · SAM | NurseTasks.jsx:55 | yes | P1, P2 visual, P3 |
| 11 | Swab camera count · SAM | TheatrePanel.jsx:91 | yes | P1, P2 visual, P3 |
| 12 | Healing photo review · human | AskInbox.jsx:42 | n/a | P1 (status only) |
| 13 | Record bot · Spark 1.3 / rules | AskCards.jsx:21 | partial | P1, P2 answer, P5 |
| 14 | Nudges · rules | AlertBanner.jsx:7 | no | P1, P2 rule, P8 |
| 15 | Handover · template + Spark | older NurseHandover.jsx | partial | P5, P2 draft |
| 16 | Discharge card · rules | screens/PatientCard.jsx:5 | no | P2 draft |
| 17 | Day plan · rules + crops | DayPlan.jsx:15 | no | P2 draft, P5 |
| 18 | AI dashboard · all four models | AiDashboard.jsx:39 | partial | P7 |
| 19–21 | Older reconciler, camera count, morning tools | older screens | partial | out of scope |

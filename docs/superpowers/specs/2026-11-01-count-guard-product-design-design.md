# Count Guard: from demo to ward product — design

**Date:** 2026-11-01
**Source:** Claude Design review canvas, https://claude.ai/artifact/TjPfuE8jwuJV9tqn2thEep (boards: Overview, Small design system, Constraints, changes 1–10). Brief and screens: https://claude.ai/artifact/QY8nzNWU11TVeEQ17rK26N.
**Owner decisions (2026-11-01):** all 10 changes in one plan; swab count is a hard stop with no camera prefill; AI rows fold once every Undo window has closed; clock times replace "Day 0 09:14" in the product, and every staff screen shows who is signed in.

## 1. Summary

Today every block on every screen has the same weight, so no screen tells its reader the one next thing to do. This redesign spends visual weight and colour on clinical meaning only:

- **One "Now" area per screen**, filled by a fixed priority rule, holding the only filled button.
- **Status colour = the clinical finding**, never the save state. "Recorded" stops being a status.
- **Safety surfaces look the most careful**: the swab count becomes its own panel and a hard stop.
- **The product and the demo tool are visibly separate**: the safety strip belongs to the product; demo controls live in a dashed dark dock.
- **AI is a label, not a colour**: a small outlined "AI" mark, Undo + Why while the window is open, folded after.

No new palette or font. The app already uses the Lightday tokens and Figtree (`frontend/src/styles.css:3-29`). The work is hierarchy, semantics and copy.

## 2. Goals, non-goals, anti-goals

**Goals**
1. A ward nurse, a doctor and a patient can each tell, within one glance, what they must do next and why.
2. Fix the three constraint breaks found in review (section 4).
3. The swab count cannot be closed past without a person's saved, reconciled count.
4. The demo still runs: 32 beats, each filmed role ≤ 58 s, offline, no live model calls.

**Non-goals**
- No new features beyond what the ten changes need (no real login, no real authorisation; "signed in" is the demo role's fixed person).
- No change to the AI agent's levels, rules or what it may do.
- No dark-theme redesign beyond keeping the existing dark tokens working.

**Anti-goals (a failure even if it works)**
- Green on anything a person still has to think about.
- The AI looking like an alert, or louder than the patient's own next step.
- A patient seeing AI bookkeeping, model names or staff task words.
- A demo that gets slower or needs more clicks on the main path (the one allowed exception is the count reason, section 5.3).

## 3. Constraints (from the brief, as sharpened by the owner)

1. The research and synthetic-data notice is visible on every screen at every width, as part of the product frame.
2. Every AI action keeps Undo (while its window is open) and Why. After all windows close, rows may fold; Why stays one tap away.
3. The patient never sees AI bookkeeping or model names.
4. A person always saves the swab count. The camera's number sits beside the field, never inside it.
5. The AI may quote the patient's record and compare against it. It may not interpret, recommend or reassure. (Sharpened wording; today's behaviour already complies.)
6. No extra clicks on the 32-beat main path, except the count reason when numbers differ.
7. Works at 390 px with no sideways page scroll.
8. Plain words for the reader: patient screens fully plain; staff screens may use standard clinical short forms (BP, HR, SpO2). Banned everywhere: internal event names (`task.assigned`), snake_case, model names outside the Inspector Model tab and the AI page.
9. **New:** every staff screen shows who is signed in and the ward.
10. **New:** records show clock times. "Day N" appears only in the demo dock's clock.

## 4. Constraint breaks to fix first (verified in code)

| Break | Where | Fix |
|---|---|---|
| Patient sees "Acknowledged by AI (on behalf of Ward 4)" | `frontend/src/care/tasklist.js:90` (`orderStatus`), rendered by `MyCare.jsx` | Patient lens drops the acknowledgement entirely; shows "Ordered by Dr. A. Rao". |
| "Synthetic data" hidden on phone | Collapsed demo dock (`DemoDock.jsx`, `.dock-summary`) | Safety strip moves into the product frame (change 6). |
| Patient sees model names | Record rows on My care and medicines photo | Plain source words; none on patient rows (change 7). |
| Swab field pre-filled with camera count | `frontend/src/care/capture.js:19` `cameraPrefill`, used at `TheatrePanel.jsx:23` | Field starts empty; camera value shown beside it (change 3). |
| "Surgery ended" not gated on the count | `backend/app/journey/flow_api.py:70` checks only that surgery began | Server refuses `ended` until a reconciled closing count is saved (change 3). |

## 5. The ten changes

### 5.1 Change 1 — One next thing for every role (lead principle)

**The rule: what fills "Now"** (top match wins, per viewer):

| Rank | Kind | Example | Pill |
|---|---|---|---|
| 1 | Danger | Systolic BP 82, limit 90; swab unaccounted | danger "Below limit" |
| 2 | Blocked | Count not saved; step locked until you act | check "Count not saved" |
| 3 | Late | Observations late, oldest first | check "Late 2 h 8 min" |
| 4 | Due now | Next scheduled task | waiting "Due 13:15" |
| 5 | Review | AI actions still in their Undo window | AI mark + "Undo · 8 min" |
| 6 | Nothing | "Nothing needs you. Next: Nurse Meena admits." | waiting |

- The winner fills **Now** with the only filled (primary) button on the screen. The next two show as "Next after this". Everything else folds with a count; nothing is hidden.
- **Nurse:** "My queue" is one list across all the nurse's patients, sorted by the rule.
- **Doctor chart:** order is patient band → Now → attention items → AI admin → orders and evidence (folded, with count) → history (folded, with count). The doctor's own actions (Dictate orders, Reference photo) are buttons inside Now.
- **Patient:** a "What happens next" card first, three cases only: something you must do; what staff will do next and when; nothing to do. No AI bookkeeping, no staff tasks, no "late" words aimed at the patient.
- The rule is a pure function of the view and the viewer (role + person), so it is unit-tested and the same everywhere.

### 5.2 Change 2 — Status colour shows the clinical finding

Five roles, each a word plus an icon shape (works in greyscale):

| Role | Tokens | Use |
|---|---|---|
| Fine | `--leaf` on `--leaf-soft`, check icon | Matches, count complete, reading in range |
| Waiting | `--sky` on `--sky-soft`, dash-circle | Someone else's turn; paused in theatre; due |
| Check this | `--sun-text` on `--sun-soft`, clock | Late; AI finding a person must decide ("Surgeon to decide") |
| Danger | `--record` on `--record-soft`, warning triangle | Past a limit; swab or instrument missing. Nothing else. |
| Done | `--ink-muted` on `--surface-sunk`, no icon | "Signed 09:12", "Saved 10:30" |

- "Recorded" is never a status. A flag stays amber/red until a person closes it; the row then says who.
- Examples: "Closing count: 14 of 15 back" → danger "1 swab unaccounted"; "Saw 2 of 3 needle holders" → check "Surgeon to decide"; "2 orders drafted" → done "Signed 09:12"; a superseded camera count → done "Replaced by count".

### 5.3 Change 3 — Swab count panel, saved by a person (hard stop)

- Theatre shows 5 numbered steps: Tray check, Surgery began, Swab count, Surgery ended, Back to ward. The current step is open; done steps fold to one line; later steps show "Locked".
- The count panel: three display-size numbers (Opened, Back, Unaccounted). Unaccounted is computed, red until 0. The camera's reading sits beside "Back" with the AI mark ("Camera read 14"); the Back field starts empty.
- When Back ≠ Opened, or Back ≠ the camera's reading, a reason is required ("What did the team do?"). The primary button reads "Save count as Nurse Asha".
- **Server rule:** `POST …/surgery {step:"ended"}` returns 409 "Save the swab count first." unless a closing count exists, is not superseded, and either unaccounted = 0 or a reason is recorded. The closing-count endpoint returns 422 when the reason is missing in those cases.
- Native "Choose Files" becomes a "Check the tray again" button.
- The saved count carries the person's name: "Saved by Nurse Asha · 10:30 · camera read 14 · found under the drape".

### 5.4 Change 4 — One alert pattern

- Each alert is one card tinted by severity (danger above check), sorted by severity then age. No nested grey boxes, no red stripe.
- Headline is the reading ("Systolic BP 82"); under it the limit, who set it, how long ago.
- "Answer" becomes "Save response"; the field has a real placeholder ("What did you do?") that does not read as saved text.
- A late task links straight to its form: "Take observations now".
- The most severe alert holds the view's primary button.

### 5.5 Change 5 — Pause AI in the product, and who is signed in

- Product header (staff): mark, ward ("Ward 4"), "AI admin: on/paused" with Pause/Resume, alerts, and the signed-in person with role and initials.
- Signed-in person per demo role (owner-approved, from the synthetic data): Doctor → Dr. A. Rao; Nurse → the nurse the demo already plays (confirmed in the plan from `names.js`/`steps.mjs`). Patient screens show no staff identity.
- Pause is available to staff roles (doctor and nurse). The demo dock's Pause becomes a shortcut that calls the same control.
- When paused: a ward-wide banner "AI admin is paused for Ward 4. Paused by {name} at {time}. New orders and tasks wait for a person." with Resume. Each "AI admin" block becomes a staff to-do with the work the AI would have done (e.g. "Acknowledge order"). Earlier actions keep Why; open Undo windows keep running.
- The backend records who paused (it already stores `by`; the header supplies the signed-in person).

### 5.6 Change 6 — Demo controls apart from the product

- One thin product strip on top of every screen, every width: "Research demo · Synthetic data · Not for clinical use".
- Demo tools move into a floating dock at the bottom: dark (Dusk ground `#14120E`), dashed edge, the word "Demo". It holds role switch, demo clock (the only place "Day N" appears), +15 min / +1 h / Next due / Reset, model mode, AI shortcut, patient picker, "Use the demo prescription", "Guide", "Older screens".
- Phone: the dock folds to one round "Demo" button that opens as a bottom sheet.

### 5.7 Change 7 — Plain source words instead of model badges

- Staff rows: the AI mark plus how it was made: "Read by camera", "Drafted from voice", "Read from photo", "Checked against the order". Rule-only rows get no chip.
- Patient rows: no AI mark, no model names; what happened to them in their words ("Your 10:38 paracetamol was checked against a photo of the strip.").
- Model names, versions and "sample / prepared" live only in the Inspector's Model tab and the AI page.
- The AI page splits into "What the AI did today" (staff) and "How it works" (pipelines and model cards).

### 5.8 Change 8 — Inspector: Why first, plain audit trail

- Tabs: **Why · Evidence · History · Model**. Opening from a Why button lands on Why.
- Why answers, in order: What it did; Because; How it chose (the actual rule, e.g. "the nurse on shift with the fewest open tasks"); Made by ("A fixed rule, not a model" or the model).
- History: time · who · what, as a sentence. The actor is defined once ("AI = AI admin acting for Ward 4"). No underlines unless it navigates.
- Internal event names sit behind a quiet "Copy event IDs" button.
- Undo sits in the Inspector header beside its countdown, on every tab.

### 5.9 Change 9 — One rule for buttons, links and photo inputs

- Changes the record → button (one filled primary per view; others secondary). Shows more here → quiet button. Goes to another page → link (sky). Removes something → destructive (record red, names the thing).
- Loose text-link actions ("Dictate orders", "Reference photo") become buttons with icons inside the card they act on.
- Every native file input becomes "Take photo" (camera capture on phones) with "or upload a file" beneath.
- Undo and Why always appear together, Undo first, same size.
- Clinic: "Admit to Ward 4" is the primary; "Close visit" is secondary.

### 5.10 Change 10 — Phone rows

- Each record row is one button ≥ 56 px tall; tapping opens the Inspector, so "Inspect ›" goes away (desktop keeps a quiet "Details").
- Two lines per row at most: what happened; then status pill and time.
- The seven filter tabs become one "Show" select.
- Phone header shrinks to mark, alerts bell and initials (44 px targets). The doctor's availability moves into Now.
- The stage rail becomes a slim six-segment bar with one line of text.

### 5.11 Smaller items (in scope)

- Slim stage rail on desktop too (~40 px). After theatre show "Ward · back from theatre", not a ticked Theatre ahead of the current stage. "Skipped" instead of strikethrough.
- Nurse view: Due now above Shift handover.
- Copy: "Answer" → "Save response"; "Inspect ›" → "Details"; drop the "Rules" chip.
- Demo data: the patient question that mentions "day 3" must be asked on a matching day, or reworded.

## 6. Design system (lives in code)

- **Tokens:** keep `styles.css` tokens. Add role aliases: `--status-fine(-soft)`, `--status-wait(-soft)`, `--status-check(-soft)`, `--status-danger(-soft)`, `--status-done(-soft)`, `--dusk` (demo dock), each mapped to existing Lightday values in light and dark.
- **Type scale:** display 40/44/800 (count numbers only, tabular figures); title 26/32/800 (patient name); heading 19/26/800 (Now action, card headings); body 15/22/400; body-strong 15/22/700; body-sm 14/20/400 muted; label 13/18/800 caps; caption 12/16/700 (pills, times). Nothing under 12 px.
- **Cards, four levels:** Now (white, 2 px ink border, one per screen); Attention (status-tinted, icon + word); Standard (white, hairline); Archive (not a card: rows on paper, folded, with a count).
- **Components:** `StatusPill` (role + word + icon), `AiMark`, `NowCard`, `Fold` (label + count + Show), `PhotoInput`, `ProductStrip`, `ProductHeader`.

## 7. Demo and verification

- `frontend/scripts/demo/beats.mjs` expectations and `steps.mjs` selectors are updated where copy changes; still 32 beats; each filmed role ≤ 58 s (`make demo-check`).
- The swab-count beat types the Back value and the reason (the reason already exists in the demo: "Found under the drape").
- The browser walk (desktop 1200 and phone 390) finds 0 failed requests, 0 console errors, no sideways scroll, no "Recorded" pill, no "Day N" outside the dock, no model names or AI bookkeeping on patient screens.
- Backend and frontend test suites stay green; new tests cover the Now rule, status mapping, time formatting, count gating, patient lens.

## 8. Left to the builder

- Exact icon drawings (inline stroke SVG; no emoji, no icon font).
- Component file split, as long as every file stays under 500 lines.
- Exact wording of fold labels and empty states, following section 3 rule 8.
- Animation: none required; respect `prefers-reduced-motion` if any is added.

## 9. Calls made by the author (owner can override)

| Call | Choice | Cost if wrong |
|---|---|---|
| Who may pause | Doctor and nurse roles | One string/condition to change |
| Clock-time format | Same day "09:14"; previous day "Yesterday 09:14"; older "Mon 2 Nov, 09:14", anchored to a fixed demo Day 0 date | One formatter |
| Staff short forms | BP, HR, SpO2 allowed on staff screens | Copy only |
| "Advice" wording | Adopt the sharpened wording in constraint 5 | None; no behaviour change |
| Rule-only rows | No source chip | Rows lose a cue engineers liked |

# Count Guard Product Design Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Count Guard read as ward software: one "Now" per screen, status colour = clinical finding, a hard-stop swab count, product and demo visibly apart, AI as a quiet label.

**Architecture:** Mostly frontend (`count-guard/frontend/src/care`): new pure helpers (`finding.js`, `now.js`, `when.js`, `source.js`) feed small new components (`StatusPill`, `AiMark`, `Fold`, `PhotoInput`, `ProductStrip`, `ProductHeader`, `NowCard`, `AlertCard`, `CountPanel`). Backend changes are narrow: a `finding` field on moments, clock-time formatting, and the swab-count gate.

**Tech Stack:** React 18 + Vite, plain CSS with Lightday tokens (`frontend/src/styles.css`), `node --test` unit tests; FastAPI + pytest backend; Playwright demo harness (`frontend/scripts/demo`).

**Spec:** `docs/superpowers/specs/2026-11-01-count-guard-product-design-design.md` (read it first; section numbers below refer to it). Code map with every file:line, string and test that each area touches: `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-hackathon-hackathon26/9c2f4abf-956d-48ef-93f1-f23a07ae1f69/scratchpad/redesign-map.md` (items 1–15; cite it in task briefs).

## Global Constraints

- Paths are relative to `count-guard/`. Run backend tests with `.venv/bin/pytest -q`, frontend with `cd frontend && npm test`, build with `cd frontend && npm run build`, demo with `make demo-check` (ports 8200/5273 only; never 8100/5173).
- Never call live models in tests. Keep every file under 500 lines.
- Colour roles only from tokens; no literal colours in components. Dark theme keeps working (`styles.css:38-58`).
- Copy rules (spec §3): patient screens fully plain; staff may use BP/HR/SpO2; no event names, snake_case, or model names outside the Inspector Model tab and `/ai`.
- The research + synthetic notice is visible at every width (spec §5.6). The patient never sees AI bookkeeping or model names.
- Demo: `BEATS.length === 32`, each filmed role 54–62 s, total ≤ 200 s (`frontend/scripts/demo/beats.test.mjs:8,25`). The `.app` root, regions "Demo", "Role", "Demo clock", "Main", "Inspector", "Theatre steps", "Tray check", "Swab camera count", "SAM 3.1" and every other region/label listed in map item 15 stay unless the task that removes one updates `steps.mjs` in the same commit.
- Every task that changes a visible string asserted by `beats.mjs`, `steps.mjs`, `beats.test.mjs` or a src-test (map item 15 and "OTHER TESTS") updates those in the same commit, and ends with `make demo-check` passing.
- Commit per task with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`, no Co-Authored-By. Work on branch `count-guard-product-design`. Never push.

## Review Focus

1. **A flag a person has not closed turns green.** Expected: any count with unaccounted > 0, any obs past limit, any tray "not all seen" stays danger/check until a person resolves it, and the resolved row names who. Pinned in Task 2.
2. **"Surgery ended" reachable with an unsaved or unreconciled count via a stale page.** Expected: server 409 regardless of the UI. Pinned in Task 6.
3. **Times across midnight and multi-day stays** (Kumar goes home, patient asks days later). Expected: "Yesterday 22:10", "Wed 4 Nov, 09:14", never "Day N" outside the dock. Pinned in Task 3.
4. **AI paused while Undo windows are open.** Expected: open windows keep their Undo; the paused banner and staff to-dos appear; folding never hides a live Undo. Pinned in Task 11.
5. **Phone 390 px with long names and many alerts.** Expected: no sideways page scroll; rows stay two lines; Now card buttons wrap. Pinned in Task 15 and the final walk.

---

### Task 1: Status tokens and shared primitives

**Files:**
- Modify: `frontend/src/styles.css` (tokens block 2-58; pills ~135-160)
- Create: `frontend/src/care/StatusPill.jsx`, `frontend/src/care/AiMark.jsx`, `frontend/src/care/Fold.jsx`, `frontend/src/care/icons.jsx`
- Modify: `frontend/src/care/care.css`
- Test: `frontend/src/care/primitives.test.js`, `frontend/src/care/styles.test.js`

**Interfaces — Produces:**
- CSS tokens `--status-{fine,wait,check,danger,done}` and `--status-{…}-soft` mapped to leaf/sky/sun-text/record/ink-muted (+ soft: leaf-soft/sky-soft/sun-soft/record-soft/surface-sunk), in light AND dark blocks; `--dusk: #14120E`.
- `<StatusPill role="fine|wait|check|danger|done" text="…" />` → `span.status-pill.s-{role}` with an `aria-hidden` icon (check / dash-circle / clock / warning / none) then text.
- `<AiMark />` → `span.ai-mark` text "AI" with `title="Done by the AI"`.
- `<Fold label="History" count={10} open={bool} onToggle={fn}>children</Fold>` → header row `label · count` + `button.quiet` "Show"/"Hide" with `aria-expanded`; children rendered only when open.
- `icons.jsx` exports `IconCheck, IconWait, IconClock, IconWarn, IconCamera, IconMic, IconUndo, IconWhy` (inline stroke SVG, `aria-hidden="true"`, `currentColor`).
- Type-scale classes: `.t-display` 40/44/800 tabular, `.t-heading` 19/26/800, `.t-caption` 12/16/700 (spec §6).

- [ ] **Step 1: Failing tests.** `primitives.test.js`: StatusPill source maps each of the five roles to class `s-{role}` and only `done` has no icon; Fold source contains `aria-expanded={open}` and renders children only when open. `styles.test.js`: each `--status-*` token defined in `:root` and redefined in the dark block; `.status-pill {` has `min-height: 26px` and `white-space: nowrap`; `.ai-mark {` uses `border: 1px solid var(--line-control)`; `.t-display` has `font-variant-numeric: tabular-nums`.
- [ ] **Step 2: Run** `cd frontend && node --test src/care/primitives.test.js src/care/styles.test.js` → FAIL.
- [ ] **Step 3: Implement** tokens, the four files, CSS. Remove dead CSS named in map item 14 (`.stage-bar`, `.stage-btn*`, `.demo-dock .dock-body a`, `.quiet-row` only if no test asserts it — `styles.test.js` asserts `.quiet-row`, so delete that assertion with it).
- [ ] **Step 4: Run** `npm test` → PASS.
- [ ] **Step 5: Commit** "Count Guard design: status tokens, status pill, AI mark and fold".

### Task 2: Status shows the clinical finding (spec §5.2)

**Files:**
- Create: `backend/app/journey/finding.py`; Test: `backend/tests/test_finding.py`
- Modify: `backend/app/journey/ai_moments.py:92-105` (`_moment` adds `finding_role`, `finding_text`)
- Create: `frontend/src/care/finding.js`; Test: `frontend/src/care/finding.test.js`
- Modify: `frontend/src/care/AiMoment.jsx`, `Inspector.jsx:122`, `moments.js:10-19`, `moments.test.js:31-37`

**Interfaces:**
- Backend `finding.classify(cap: str, status: str, moment: dict, ix) -> tuple[str, str]` returning `(role, text)` with role in `fine|wait|check|danger|done`. Rules (exact texts):

| Moment | Role | Text |
|---|---|---|
| closing count, unaccounted n > 0, not superseded | danger | `"{n} swab unaccounted"` / `"{n} swabs unaccounted"` |
| closing count, unaccounted 0 | fine | `"Count complete"` |
| camera swab count superseded by a person's count | done | `"Replaced by count"` |
| visual check status flagged and not resolved | check | `"Surgeon to decide"` (tray) / `"Check this"` (other visual) |
| visual check resolved by a person | fine | `"Checked by {name}"` |
| rule/nudge: obs past limit, open | danger | `"Below limit"` or `"Above limit"` |
| rule/nudge: overdue, open | check | `"Late {h} h {m} min"` (or `"Late {m} min"`) |
| any open with another owner | wait | `"Waiting for the {owner}"` |
| matches | fine | `"Matches"` |
| order/discharge draft signed | done | `"Signed {HH:MM}"` |
| other recorded | done | `"Saved {HH:MM}"` |
| undone | done | `"Undone"` |

- Frontend `findingPill(moment, role)` → `{role, text}`: uses `moment.finding_role/finding_text`; when the moment is open and owned by the viewer, text becomes `"Needs you"` only for role `wait` (danger/check keep their words). `statusLabel` is deleted; every caller uses `<StatusPill {...findingPill(m, role)} />`.

- [ ] **Step 1: Failing tests.** `test_finding.py`: one test per table row, including `test_unaccounted_count_is_danger_until_corrected` (14 of 15 → danger "1 swab unaccounted"; after a superseding count of 15 → the camera row is done "Replaced by count" and the new count fine "Count complete") and `test_resolved_flag_names_person`. `finding.test.js`: no input ever yields text "Recorded"; open+owner===viewer+wait → "Needs you"; danger stays "Below limit" for the owner.
- [ ] **Step 2: Run** `.venv/bin/pytest -q backend/tests/test_finding.py` and `node --test src/care/finding.test.js` → FAIL.
- [ ] **Step 3: Implement.** Keep `status` on moments unchanged (other code reads it); only add the two fields.
- [ ] **Step 4: Run** full backend + frontend suites → PASS; `make demo-check` → PASS.
- [ ] **Step 5: Commit** "Count Guard design: pills name the finding; green only when a person can stop thinking".

### Task 3: Clock times in the product (spec §3 rule 10)

**Files:**
- Create: `backend/app/journey/clocktext.py`; Test: `backend/tests/test_clocktext.py`
- Modify: every backend user of `stories.clock` listed in map item 11 (product text), keeping `stories.clock` only for the dock and check-in day numbers.
- Create: `frontend/src/care/when.js`; Test: `frontend/src/care/when.test.js`
- Modify: frontend users listed in map item 11 ("Full 'Day N HH:MM' shown").

**Interfaces:**
- Constant `DAY0 = date(2026, 11, 2)` (Monday) in `clocktext.py` and `when.js` (`DAY0 = "2026-11-02"`); ts_ms 0 = Day 0 09:00 as today.
- `when_text(ts_ms: int, now_ms: int | None) -> str` / `whenText(tsMs, nowMs)`: same demo day → `"09:14"`; previous day → `"Yesterday 09:14"`; else → `"Wed 4 Nov, 09:14"`; `now_ms is None` → `"Mon 2 Nov, 09:14"` form. Never contains "Day ".
- Backend callers that build a view use the request's clock (`ts` already passed to `view()`/`flow_view`); handover and "Last:" text use the same `now`.
- Demo dock keeps `clock.js label()` "Day N HH:MM" (only place).

- [ ] **Step 1: Failing tests.** `test_clocktext.py` (helper `ms(day,h,m)`): `when_text(ms(0,9,0), ms(0,10,0))=="09:00"`; `when_text(ms(0,22,10), ms(1,9,0))=="Yesterday 22:10"`; `when_text(ms(day=2,h=9,m=14), ms(day=5,h=9))=="Wed 4 Nov, 09:14"`; `when_text(ms(0,9,14), None)=="Mon 2 Nov, 09:14"`. `when.test.js`: same three cases. Plus a scan test: `test_view_has_no_day_n_text` builds the seeded demo view for each patient and asserts no string value matches `\bDay \d+ \d\d:\d\d` (check-in "Day 3 check-in" text is allowed: regex requires the time).
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement**; update the tests listed in map item 11 to the new strings.
- [ ] **Step 4: Run** suites + `make demo-check` → PASS.
- [ ] **Step 5: Commit** "Count Guard design: clock times in the record; Day N stays in the demo clock".

### Task 4: Patient lens: no AI bookkeeping, no model names (spec §4)

**Files:** Modify `frontend/src/care/tasklist.js:89-94`, `MyCare.jsx:29,43,45`, `AiMoment.jsx`; Test: `frontend/src/care/patientLens.test.js`, `tasklist.test.js:100`.

**Interfaces:** `orderStatus(order, state, you)`: when `you` is true never mentions acknowledgement or "nurse"; returns `"Ordered by {displayName(order.by)}"` lines only (state words: "Starts when you are admitted", "Not started: the visit was closed", or `""`). Patient-lens `AiMoment` renders no chip and no AiMark. "Done by"/"Ordered by" names go through `displayName`.

- [ ] **Step 1: Failing tests.** `orderStatus({acknowledged_by:"AI (on behalf of Ward 4)", by:"Dr. A. Rao (synthetic)"}, "ward", true)` contains neither "AI" nor "Acknowledged"; MyCare src contains no `chipFor(`; a patient-lens AiMoment render contains no `chip` class.
- [ ] **Step 2–4:** FAIL → implement → suites + demo-check PASS (das-mycare `absent` regex still holds).
- [ ] **Step 5: Commit** "Count Guard design: the patient sees no AI bookkeeping or model names".

### Task 5: Product frame, signed-in person, Pause in the product, demo dock apart (spec §5.5, §5.6)

**Files:**
- Create: `frontend/src/care/ProductStrip.jsx`, `ProductHeader.jsx`, `useOpsPaused.js`, `people.js` (+ `people.test.js`)
- Modify: `CareShell.jsx` (brand L111-128, footer L135-138), `DemoDock.jsx`, `dock.js`, `App.jsx:25-39` (Banner), `screens/ClinicPanel.jsx:55`, `care.css` demo dock + 640px rules, `styles.test.js:45-57`, `dock.test.js`, `ai.test.js:81-87`
- Modify: `frontend/scripts/demo/beats.mjs` intro expect

**Interfaces:**
- `people.js`: `SIGNED_IN = { doctor: {name:"Dr. A. Rao", role:"Doctor"}, nurse: {name:"Nurse Meena", role:"Ward nurse"} }`; `initials(name)` → "AR"/"NM". (Call: the theatre panel keeps recording as Nurse Asha, as today.)
- `ProductStrip`: `p.product-strip role=note` text exactly `"Research demo · Synthetic data · Not for clinical use"`, first child of `.app`, every width. Replaces `<Banner/>` and the dock's "Synthetic data" text.
- `ProductHeader` (staff): mark + "Count Guard", "Ward 4", nav (unchanged `aria-label="Main"` links), alerts pill, `AI admin: on|paused` + `button` "Pause"/"Resume", person block `{initials} {name} · {role}`. Patient header: mark, nav, no person, no AI state.
- `useOpsPaused()` → `{paused, by, busy, error, toggle}` posting `{by: SIGNED_IN[role].name}`; DemoDock's AI button calls the same hook (shortcut).
- Paused banner (staff, all pages): `div.paused-banner role=status` "AI admin is paused for Ward 4. Paused by {by} at {whenText}. New orders and tasks wait for a person." + Resume.
- DemoDock: fixed bottom, `background: var(--dusk)`, `border: 1px dashed`, label "Demo"; contains role switch, Patient select, demo clock, AI shortcut, models text (`modelsText(live)` without "Synthetic data"), and links "Guide", "Older screens". The clinic "Use the demo prescription" button renders inside the dock when the doctor is on a clinic patient (it keeps its exact name). Phone (≤640px): folded to `button.dock-summary` round "Demo" (keeps `.dock-summary` and `aria-expanded`); opens as a bottom sheet.

- [ ] **Step 1: Failing tests.** `people.test.js` (initials). `dock.test.js`: ProductStrip src contains the exact strip text; CareShell renders `<ProductStrip` before the header; DemoDock no longer contains "Research demo"; `useOpsPaused` posts `by: SIGNED_IN`; paused banner text. `styles.test.js`: `.demo-dock {…var(--dusk)…dashed}`; `.product-strip` not hidden in any media query.
- [ ] **Step 2–3:** FAIL → implement. Update beats intro `expect` to `["Research demo · Synthetic data · Not for clinical use", "models: offline (prepared)"]`. Phone checks of the dock happen in Task 17.
- [ ] **Step 4:** suites + build + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: the product owns its safety strip, header and Pause; demo tools sit apart".

### Task 6: Swab count is a hard stop on the server (spec §5.3)

**Files:** Modify `backend/app/journey/flow_api.py:61-72`, `backend/app/journey/count_api.py:47-69`, `backend/app/journey/states.py` (add `count_reconciled(events) -> bool` beside `theatre_count` L333). Test: `backend/tests/test_count_gate.py`; update `test_flow_states.py`, `test_care_story.py:91-97`, `test_p3_story.py:72-80`, `test_p4_story.py:64`, `test_ops_api.py:82`, `test_p4_status.py:83` to save a reconciled count before ending surgery.

**Interfaces:**
- `count_reconciled(events)`: True when the latest non-superseded `count.closing` this stay has `unaccounted == 0` or a non-empty `detail` (reason).
- `POST …/surgery {step:"ended"}`: 409 `"Save the swab count first."` when no closing count this stay; 409 `"The swab count does not add up. Record what the team did first."` when not reconciled.
- `POST …/count {step:"closing"}`: 422 `"Say what the team did: the count does not match."` when `detail` is empty and (`returned != opened` or (camera evidence present and `returned != camera count`)).
- Leaving theatre (`check_move`, states.py:125-130) unchanged.

- [ ] **Step 1: Failing tests** `test_count_gate.py`: `test_end_refused_without_count`, `test_end_refused_when_unaccounted_without_reason`, `test_end_allowed_after_reconciled_count`, `test_end_allowed_with_reason_and_unaccounted`, `test_closing_needs_reason_when_camera_differs` (camera 14, returned 15, no detail → 422; with "Found under the drape" → 200), `test_superseded_count_does_not_count`.
- [ ] **Step 2–4:** FAIL → implement → full backend PASS.
- [ ] **Step 5: Commit** "Count Guard design: surgery cannot end on an unsaved or unexplained swab count".

### Task 7: Theatre: five steps and the count panel (spec §5.3)

**Files:** Create `frontend/src/care/CountPanel.jsx` (replaces `TheatrePanel.jsx`; delete it). Modify `TheatreChecklist.jsx`, `theatre.js` (add step 5 "Back to ward"; `canRecord("ended")` needs `countReconciled`), `capture.js` (delete `cameraPrefill`; `closingBody` unchanged), `capture.test.js`, `theatre.test.js`, `names.test.js:20-26`, `frontend/scripts/demo/steps.mjs` (kumar-count), `beats.mjs` (kumar-count, kumar-back), `beats.test.mjs`.

**Interfaces:**
- `theatreSteps` returns 5 steps; later steps' `wait` text is `"Locked"`; `countReconciled(view)` mirrors the server rule from `view.count`.
- CountPanel (`section aria-label="Swab count"`): three `.t-display` figures Opened / Back / Unaccounted (Unaccounted computed, `s-danger` until 0, caption "Worked out, not typed"); Back field label stays `"Closing count (returned)"`, starts empty; beside it `<AiMark/> "Camera read {n}"`; reason field label `"What did the team do?"` (required when the server rule needs it; placeholder "Found under the drape"); primary button `"Save count as {displayName(by)}"`; saved line `"Saved by {name} · {HH:MM} · camera read {n} · {detail}"`. Keep the "Pack opened" field/button and the `VideoCheck` titled "Swab camera count".
- "Surgery ended" button disabled until reconciled, with note "Surgery ended unlocks when the count is saved."
- Demo kumar-count becomes: upload swab clip (camera 14) → fill "Closing count (returned)" 15 → fill "What did the team do?" "Found under the drape" → click "Save count as Nurse Asha". Expect `"Count complete"`, `"camera read 14"`, `"Found under the drape"`. Rebalance beat `seconds` to keep the nurse role 54–62 s.

- [ ] **Step 1: Failing tests.** theatre.test.js: 5 steps, step 4 locked until reconciled; capture.test.js: `cameraPrefill` gone; CountPanel src: Back input has no camera default (`useState("")` and no `camera.count` in its `value`), contains "Worked out, not typed".
- [ ] **Step 2–4:** FAIL → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: the swab count is its own panel, typed and saved by a person".

### Task 8: One alert pattern (spec §5.4)

**Files:** Create `frontend/src/care/AlertCard.jsx`; modify `AlertBanner.jsx`, `alerts.js` (sort), `Queue.jsx:38` (use AlertCard instead of `screens/WardPanel.jsx` Nudge; leave the old screen untouched), `alerts.test.js`, `moments.test.js:155`, `steps.mjs:191-193`, `beats.mjs` iyer-recheck.

**Interfaces:**
- `bannerAlerts` sorts danger (SAFETY kinds) before check (late), then oldest first.
- AlertCard (`article.alert-card.s-{role}` with `aria-label="Alert: {headline}"`): headline = reading ("Systolic BP 82"), sub-line "Limit 90, set by Dr. A. Rao · {whenText} · {age}"; response field label `"What did you do?"` (placeholder "e.g. Called the doctor, repeated the reading"); primary `"Save response"` (only the most severe alert's button is `primary`; others secondary); quiet "Details" opens Inspector; late alert shows a link-button "Take observations now" that scrolls/opens the task form; footer "Assigned to {name}". Posts `/nudges/{id}/seen` as today.
- Steps iyer-recheck: locate `article` by `aria-label` starting "Alert: Systolic BP 82", fill "What did you do?", click "Save response".

- [ ] **Step 1: Failing tests.** alerts.test.js sort order; AlertCard src contains "Save response" and not "Answer", placeholder does not equal "Called the patient back".
- [ ] **Step 2–4:** FAIL → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: one alert pattern with the reading, the limit and a response".

### Task 9: The Now rule (spec §5.1)

**Files:** Create `frontend/src/care/now.js` (+ `now.test.js`), `NowCard.jsx`, `NextUp.jsx` (patient "What happens next"); modify `StatePanel.jsx`, `NextCard.jsx` (delete once unused), `journey.js:69-82`, `derive.js:166` (`queueRows` sort), `Queue.jsx`, `Today.jsx`, `MyCare.jsx`, `StateHeader.jsx:13`, `patientLens.test.js:31-33`, `journey.test.js`, `derive.test.js`.

**Interfaces:**
- `pickNow(view, viewer, nowMs) -> {now, next: [item, item], rest: number}` where viewer = `{role, name}` and item = `{rank, kind, title, detail, pill: {role, text}, patient?, action?}`. Ranks: 1 danger (open SAFETY alerts for this viewer), 2 blocked (a step that waits on this viewer: unsaved count, unacknowledged orders when AI is paused, the role's own `now_next` action when `mine`), 3 late (overdue tasks, oldest first), 4 due now, 5 review (AI items in their undo window, staff only), 6 nothing (`title: "Nothing needs you."`, `detail: "Next: {next owner action}"` from `view.now_next`).
- `pickNowAcross(views, viewer, nowMs)` for the nurse queue: same ranks, then oldest; replaces `queueRows` RANK order.
- NowCard (`section.now-card aria-label="Now"`): eyebrow `"Now · for you"` (or `"Now · {owner}"`), `.t-heading` title, detail line, StatusPill, the action's controls as the only `primary` button(s) — reuse the existing blocks from `cardActions`/NurseActions/DoctorActions so every button keeps its exact accessible name; then "Next after this" (two rows) and "{rest} more" fold. Keep the existing backend next texts visible (beats expect "Nurse completes the admission.", "The visit is closed. No further steps.").
- NextUp (patient, Today + My care top): `section aria-label="What happens next"`, exactly one of: "You need to: {you_next}", "{who} will {what}{ by HH:MM}", "You don't need to do anything now." No "late", no task words.

- [ ] **Step 1: Failing tests** `now.test.js`: danger beats late beats due; review only for staff; patient never gets review/late; nurse across two patients sorts BP-below-limit first; nothing-case text.
- [ ] **Step 2–4:** FAIL → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: one Now per screen, picked by a fixed rule".

### Task 10: Chart layout and slim stage rail (spec §5.1, §5.11)

**Files:** Modify `Chart.jsx:71-89`, `JourneyBar.jsx`, `journey.js:10-20`, `derive.js:20` (STATE_LABEL unchanged), `RecordEvidence.jsx`, `History.jsx`, `DoctorActions.jsx` (QUIET actions), `ActionBar.jsx`, `care.css` journey rules, `styles.test.js` journey asserts, `moments.test.js:104-113`.

**Interfaces:**
- Chart order: StateHeader (patient band + rail) → NowCard → AlertBanner → AskInbox → AI admin (Task 11) → MedicinesFromHome → `Fold label="Orders and evidence"` wrapping RecordEvidence (closed by default) → `Fold label="History"` (closed). Region names unchanged ("Record and evidence", "History").
- JourneyBar: `ol.journey` ~40 px, six segments; current shows STATE_LABEL detail; after theatre the Theatre segment reads "Ward · back from theatre" on the Ward segment instead of a tick ahead of current; skipped shows "Skipped" (no strikethrough). Keeps `li.current|done|later|skipped`.
- Doctor QUIET actions (Dictate orders, Reference photo, Wound photo, Dictate discharge) render as secondary buttons with icons inside NowCard's action area; names and `aria-expanded` unchanged.
- Demo steps that need folded content (`H.click("Inspect")` on `.ai-moment` "sections drafted", Record rows) first open the Fold: add helper `H.unfold(label)` in `helpers.mjs`.

- [ ] **Step 1–4:** tests for chart order (src), Fold closed by default, rail labels → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: chart reads band, Now, attention, AI admin, then the folded record".

### Task 11: AI admin block folds after Undo (spec §5.5, constraint 2)

**Files:** Modify `AiHandling.jsx`, `handling.js`, `AiFeed.jsx`, `ProposalCard.jsx`, `handling.test.js`, `care.css` ops rules.

**Interfaces:**
- `handlingState(ops, nowMs) -> {open: rows with live undo, done: rows without, paused: rows, proposals}`; `foldTitle(done) = "AI did {n} admin task(s) · Review"`.
- Section label `"AI admin for this patient · {n}"`; while any row has live Undo: all rows open, each `<AiMark/> {text} · {HH:MM}` + Undo (secondary, `"Undo · {m} min"`) then Why (quiet), same size; when none live: one Fold row with `foldTitle`, opening shows rows with Why only.
- Paused: section shows "Waiting for a person" rows from `pausedRows` with the human action text (e.g. "Acknowledge order") — the nurse block's existing "Acknowledge" button stays the actionable control.
- Keep `aria-label="AI is handling"` region name? Rename to `"AI admin"` and update `walk`/steps if referenced (map says only AiHandling tests); keep `.ai-handling` class (styles.test asserts it).
- Beat strings "Acknowledged Dr. A. Rao's orders" must stay visible in kumar-admit/kumar-admission/iyer-orders (they are inside the undo window there — verify; if a beat lands after the window, expect the fold text instead).

- [ ] **Step 1–4:** handling tests: fold only when no live undo; paused never hides live Undo (Review Focus 4) → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: AI admin is a quiet label that folds once Undo has closed".

### Task 12: Plain source words; AI page split (spec §5.7)

**Files:** Create `frontend/src/care/source.js` (+ test); modify `AiMoment.jsx`, `moments.js:22-44` (chipFor/heardChip/draftChip → staff source words), `evidence.js:33`, `Dictate.jsx:102`, `InspectVoice.jsx:16`, `TaskProof.jsx:53`, `VideoCheck.jsx:39`, `AiDashboard.jsx`, `ModelCards.jsx`, `moments.test.js:36-45`, `ai.test.js:40-41`, `beats.mjs` HEARD/HEARD_ONLY and kumar-review, `beats.test.mjs:74-99`.

**Interfaces:**
- `sourceWords(moment) -> string | null`: sam/visual → "Read by camera"; spark photo read → "Read from photo"; voice → "Drafted from voice" (orders, discharge) or "Recorded by voice" (task/answer); rules only → `null`; dose strip → "Checked against the order". Rendered as `<AiMark/> {words}` in `span.source` (staff only). `chipFor` remains only for Inspector Model tab and ModelCards (rename `modelChip`).
- Demo strings: HEARD becomes "Drafted from voice"; kumar-review expects "Recorded by voice" instead of "by voice · Muse Voice · prepared"; the "ai" beat keeps model names (AI page).
- AiDashboard: two `h2` sections "What the AI did today" (ActivityList, AiFeed) then "How it works" (pipelines, ModelCards). `ai.test.js` order assertion updated to ActivityList → AiFeed → pipelines → ModelCards; ModelCard `aria-label={model.name}` unchanged.

- [ ] **Step 1–4:** source tests; scan test: render-free src scan that no care/*.jsx except Inspector.jsx, ModelCards.jsx, AiDashboard.jsx imports `modelChip` → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: rows say how a reading was made; model names live in the Inspector and on the AI page".

### Task 13: Inspector — Why first, plain history (spec §5.8)

**Files:** Modify `inspect.js:9,33`, `Inspector.jsx`, `InspectAgent.jsx`, `inspect.test.js`, `moments.test.js:57`, `beats.mjs` kumar-tray expect, `steps.mjs` (Inspector `Close` unchanged).

**Interfaces:**
- `TABS = [["why","Why"],["evidence","Evidence"],["history","History"],["model","Model"]]`; patient gets why + evidence. Open from a Why button → "why"; from Details → "why" too (it now answers "what it found").
- Why tab: four labelled lines "What it did", "Because", "How it chose", "Made by". For agent moments "How it chose" comes from the work item's rule (`plan.py` pick text: "the nurse on shift with the fewest open tasks"; add `how` to the work item payload in `backend/app/ops/plan.py` if absent, with a test); "Made by" = "A fixed rule, not a model" or the model names. For visual/voice/text kinds the existing Found view is the Why body.
- History tab: `historyLine(w)` = `"{HH:MM} · {who} {plain}"` with who = "AI" for AI_BY; header note "AI = AI admin acting for Ward 4" when any AI line; lines are not links unless they navigate (keep `Link` with `className="history-line"` styled as text). Quiet `button` "Copy event IDs" copies `w.type:w.event_id` lines (catch clipboard errors; show "Copied"/"Could not copy").
- Inspector header holds Undo (`"Undo · {m} min"`) for agent moments in their window, on every tab.
- kumar-tray expects "Why" tab content instead of "What the AI found".

- [ ] **Step 1–4:** inspect tests (no line contains `task.assigned`, `work.done` or the AI_BY string twice) → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: Inspector opens on Why and reads as a plain audit trail".

### Task 14: Buttons, links and photo inputs (spec §5.9)

**Files:** Create `frontend/src/care/PhotoInput.jsx` (+ src test); replace native inputs at `TheatreChecklist.jsx:32`, `VideoCheck.jsx:25`, `DoctorActions.jsx:36`, `StripPhoto.jsx:24`, `TaskProof.jsx:59`, `AskCards.jsx:58` (not the old `screens/*`); modify `DoctorActions.jsx:79-80` (Admit primary, Close visit secondary), `styles.css` button rules.

**Interfaces:**
- `<PhotoInput label="Take photo" accept="image/*" capture multiple={false} onFiles={fn} />` → a `label.photo-input` styled as a secondary button with IconCamera and the text, wrapping a visually hidden `input[type=file]` (so `H.file(region, …)` still finds `input[type=file]` in the region); below it `span.small` "or upload a file". Video variants pass `label="Add video or photos"`. Keep each existing region/label name used by steps (map item 15).
- Button rule classes: `.primary` (one per view), `button` secondary default, `.quiet` for show-more, `.danger` destructive; links only navigate. The Admit button's text stays exactly "Admit" (steps click it by exact name) and becomes `primary`; "Close visit" becomes secondary. The ward name appears in the card heading ("Admit A. Das to Ward 4, or close the visit"), not in the button.

- [ ] **Step 1–4:** src test: no care/*.jsx (outside PhotoInput) contains `type="file"` except Dictate's hidden audio input; PhotoInput input has class `visually-hidden` → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: one rule for buttons and links; photo inputs become Take photo".

### Task 15: Phone rows and the Show menu (spec §5.10)

**Files:** Modify `AiMoment.jsx`, `RecordEvidence.jsx`, `ProductHeader.jsx` (phone), `care.css` (≤640px), `moments.test.js:61-63,104-113`, `steps.mjs:120` ("Inspect" → "Details").

**Interfaces:**
- AiMoment row = one `button.moment-row` (min-height 56px) when inspectable, else a `div`; two lines: line 1 finding text; line 2 StatusPill + time + source words. Desktop shows a trailing quiet "Details ›" text inside the button; accessible name starts with the finding text and ends "Details". `data-moment` and `.ai-moment` class kept.
- Filters: `select` labelled "Show" with the seven FILTERS options; `aria-pressed` buttons removed (update moments.test.js assertion).
- Phone header: mark, alerts bell (44 px), initials (44 px); doctor availability chip moves into NowCard detail for staff.

- [ ] **Step 1–4:** tests → implement → suites + build + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: phone rows tap whole, two lines; filters in one menu".

### Task 16: Smaller items (spec §5.11)

**Files:** `NurseActions.jsx:55-60` (NurseTasks before HandoverCard), copy in `AiMoment`/AlertCard ("Details", "Save response" — verify done), `moment_text.py`/`ai_moments.py` drop "Rules" chip (done via `sourceWords` null — verify), demo data: `steps.mjs:137` note text "Day 3" → "Healing photo after surgery", and the doctor's dictated answer fixture text "The wound looks as expected for day 3." → "The wound looks as expected." (fixture + `beats.mjs` kumar-answers expect + any eval fixture that holds the answer text).

- [ ] **Step 1–4:** tests for nurse order (src) and the answer text → implement → suites + demo-check PASS.
- [ ] **Step 5: Commit** "Count Guard design: tasks before handover; demo wording matches the clock".

### Task 17: Final browser walk and constraint scan

**Files:** Create `frontend/scripts/demo/scan.mjs` (+ `scan.test.mjs`) — a pure function `scanText(text, role)` returning violations; run.mjs calls it per beat.

**Interfaces:** `scanText(innerText, role) -> string[]` flags: "Recorded" as a whole word in a pill context (`/\bRecorded\b/`), `/\bDay \d+ \d\d:\d\d\b/` (outside the dock: run.mjs passes `.app` innerText minus `[aria-label=Demo]`), `/\b[a-z]+_[a-z_]+\b/`, `task.assigned|work\.(done|opened)`, and for role patient: `/Muse |SAM 3|AI \(on behalf|Acknowledged by/`. run.mjs fails a beat on any violation.

- [ ] **Step 1:** scan tests (each rule positive + negative).
- [ ] **Step 2:** wire into run.mjs; `make demo-check` PASS.
- [ ] **Step 3:** Run the scratchpad walk script at W=1200 and W=390 (it lives at `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-hackathon-hackathon26/9c2f4abf-956d-48ef-93f1-f23a07ae1f69/scratchpad/walk-ops.mjs`; update its selectors for the new dock and AI admin region): 0 failed requests, 0 console errors, no HSCROLL at 390.
- [ ] **Step 4: Commit** "Count Guard design: the demo fails on any recorded-as-status, Day N, snake_case or patient-facing AI text".

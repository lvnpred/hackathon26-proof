# Count Guard v2 · P1 Patient States and Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each patient has one state; the screen shows that state's actions and a now/next line; typed
doctor orders reach the nurse's queue, become tasks, and are completed by tap; the three demo paths
(Kumar, Iyer, Das) complete by tapping alone.

**Architecture:** State, orders and tasks are new append-only ledger events in the existing episode store
(`app/morning/store.py`), read by two new pure modules (`journey/states.py`, `journey/tasks.py`) and
served by a new router (`journey/flow_api.py`). The journey `view()` gains `state`, `now_next`, `allowed`,
`order_list`, `tasks` (v1's `orders` key stays the `ward.orders_set` payload). Completing a task also writes the v1 fact event (`dose.given`, `obs.recorded`) and
signing an order also writes a merged `ward.orders_set`, so v1 nudges keep working unchanged. The
frontend chart drops the stage bar for a state header + state panel + history.

**Tech Stack:** FastAPI + pydantic v2, SQLite ledger, pytest; React 18 + react-router + Vite, Node built-in
test runner.

**Spec:** `docs/superpowers/specs/2026-10-29-count-guard-v2-patient-states-design.md` (P1 section, States
table, Data table, "Time and seeds", D4, D5, D14).

## Global Constraints

- Work on branch `count-guard-v2`. Commit after each task with
  `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Never push. No `Co-Authored-By` trailer.
- Keep every file under 500 lines. `backend/app/journey/api.py` (464 lines) gets only small edits.
- Validate input at system boundaries: every new route body is a pydantic model on the existing `Strict`
  base (`extra="forbid"`) with length and range bounds.
- No advice wording in any server or UI string except quoted doctor text:
  regex `\b(give|take|stop|increase|reduce|start|administer|consider)\b` (case-insensitive) must not match.
  Button labels use "Begin", "Mark done", "Record", not "Start".
- Synthetic data only. Names: `Dr. A. Rao (synthetic)`, `Nurse Meena (synthetic)` (ward),
  `Nurse Asha (synthetic)` (theatre).
- One ward clock: every action is stamped with the client's `at_ms`; a tap never moves the clock.
- No model calls in P1. Tests never call a model.
- Backend tests: `cd count-guard && make test` (pytest -q). Frontend tests:
  `cd count-guard/frontend && node --test 'src/care/*.test.js'`. Build: `npm run build`.
- v1 tests keep passing, or are rewritten in the task that changes the behaviour they pin.

## Review Focus

1. A transition the States table does not allow (e.g. `clinic` → `theatre`, or any move out of `home`) → 409 with a plain reason, ledger unchanged. Test in Task 1.
2. Theatre → ward with an open count and an empty reason → 409; with a reason → allowed and the reason is in the state event. Test in Task 1.
3. Acknowledging an order twice, or completing a `tick` task twice for a non-recurring item → 409, no duplicate `task.created`/`dose.given`. Test in Task 2.
4. Switching role on an open chart changes the actions and the lens shown, even after a lens chip was clicked. Test in Task 5 (pure helper) and checked in Task 8.
5. A stale roster in sessionStorage after the backend restarted (404 on a patient) reseeds instead of showing an empty ward — v1 behaviour (`care/ward.js` `fetchWard`) must survive the rewrite. Checked in Task 8.

---

### Task 1: Patient states and transitions (backend)

**Files:**
- Create: `count-guard/backend/app/journey/states.py`
- Create: `count-guard/backend/app/journey/flow_api.py`
- Modify: `count-guard/backend/app/journey/api.py` (`view()` merges `flow_view`), `count-guard/backend/app/main.py` (register `flow_router`)
- Test: `count-guard/backend/tests/test_flow_states.py`

**Interfaces:**
- Produces (`states.py`):
  - `STATES = ("clinic", "clinic_done", "admitting", "ward", "theatre", "discharging", "home")`
  - `PROCEDURES = {"hernia-repair": "Open inguinal hernia repair"}` (P3 adds tray data per key)
  - `current_state(events: list[dict]) -> str` — `to` of the latest `patient.state` event; `"clinic"` when none.
  - `count_open(events) -> bool` — latest `count.closing` not replaced (no later event with `supersedes_id` = its id) has `returned` < `quantity` of the latest `count.pack_opened`. Same rule `nudges.count_and_patient` uses; reuse, do not fork, if it can be imported cleanly.
  - `check_move(events, to: str, body: dict) -> str | None` — `None` if allowed, else the plain reason for a 409.
  - `allowed_moves(events) -> list[dict]` — `[{"to": str, "label": str, "role": "doctor"|"nurse", "needs": list[str]}]` for the current state.
  - `now_next(events) -> dict` — `{"now": str, "next": str}`, plain English, e.g. now `"Dr. A. Rao (synthetic) admitted the patient at Day 0 09:40."` next `"Nurse completes the admission."`. Times via `stories.clock(ts_ms)`.
  - `flow_view(events) -> dict` — `{"state", "now_next", "allowed", "procedure"}` (Task 2 adds `order_list`, `tasks`).
- Produces (`flow_api.py`): `flow_router = APIRouter(prefix="/journey/episodes/{episode_id}")`; `POST /state` body `StateIn(At)`: `to` (Literal of STATES), `by` (1–80), `reason` (0–300, default ""), `procedure` (optional key of PROCEDURES), `checklist` (dict[str,bool], ≤10 keys). Returns `view()`. Reuse `_act`, `_require`, `_store`, `At`, `Strict`, `view` from `api.py`.
- Produces: `POST /surgery` body `SurgeryIn(At)`: `step` Literal["began","ended"], `by`. Writes `surgery.began` / `surgery.ended`; only in `theatre`; `ended` needs a prior `began`.

Transition table (from → to: who, needs):

| From | To | Label | Role | Needs (else 409) |
|---|---|---|---|---|
| clinic | admitting | Admit | doctor | non-empty `reason` |
| clinic | clinic_done | Close visit | doctor | — |
| admitting | ward | Complete admission | nurse | `checklist` with all four true: `band`, `allergies`, `baseline_obs`, `consent` |
| ward | theatre | Send to theatre | doctor | `procedure` in PROCEDURES |
| theatre | ward | Back to ward | nurse | `surgery.ended` recorded; if `count_open` then non-empty `reason` (D14) |
| ward | discharging | — (only via Task 2's `/discharge/sign`) | doctor | a `discharge.signed` event |
| discharging | home | Complete discharge | nurse | `checklist` all true: `card_given`, `medicines_handed`, `reminders_set` |

The `patient.state` payload is `{"from", "to", "by", "reason", "procedure"?, "checklist"?}`. `stories.plain` gets a line for `patient.state`, `surgery.began`, `surgery.ended`.

- [ ] **Step 1: Write failing tests** in `test_flow_states.py` using the existing `client` fixture style of `tests/test_care_demo.py` (create an episode via `POST /morning/episodes`, then post to `/journey/episodes/{id}/state`):
  - `test_new_episode_is_in_clinic`: `GET` view → `state == "clinic"`, `allowed` targets `{"admitting", "clinic_done"}`.
  - `test_admit_needs_reason`: `to=admitting, reason=""` → 409; with `reason="Hernia repair"` → 200, `state == "admitting"`, `now_next["next"]` contains `"admission"`.
  - `test_disallowed_move_is_409_and_writes_nothing`: from clinic `to=theatre` → 409; event count unchanged.
  - `test_admission_checklist_must_be_complete`: three of four keys true → 409; all four → `ward`.
  - `test_theatre_needs_procedure_and_surgery_end`: `ward → theatre` without procedure → 409; with `hernia-repair` → `theatre`; `theatre → ward` before `surgery.ended` → 409.
  - `test_open_count_needs_reason`: in theatre, count opened 20, closing returned 19, surgery began+ended; `to=ward, reason=""` → 409 whose detail mentions the count; `reason="X-ray ordered"` → 200 and the state event's reason is `"X-ray ordered"`.
  - `test_home_is_final`: drive to `home` (discharging via direct store append of `discharge.signed` + `patient.state` is acceptable in this test) → any move → 409.
  - `test_no_advice_words_in_now_next`: for every state reached above, `now_next` text does not match the advice regex.
- [ ] **Step 2: Run** `cd count-guard && .venv/bin/pytest backend/tests/test_flow_states.py -q` → FAIL (404 / import error).
- [ ] **Step 3: Implement** `states.py`, `flow_api.py`, the `view()` merge (`**flow_view(events)`), router registration, `plain()` lines.
- [ ] **Step 4: Run** the file → PASS; then `make test` → all pass.
- [ ] **Step 5: Commit** `git add` the four files + test; message `Count Guard v2: patient states and guarded transitions`.

---

### Task 2: Orders, tasks and discharge (backend)

**Files:**
- Create: `count-guard/backend/app/journey/tasks.py`
- Modify: `count-guard/backend/app/journey/flow_api.py`, `count-guard/backend/app/journey/states.py` (`flow_view` adds `order_list`, `tasks`), `count-guard/backend/app/journey/stories.py` (`plain` lines)
- Test: `count-guard/backend/tests/test_flow_tasks.py`

**Interfaces:**
- Consumes: Task 1 `current_state`, `flow_view`, `flow_router`.
- Order item (pydantic `OrderItem(Strict)`): `kind` Literal["dose","obs","procedure","check","other"]; `text` 1–200; `name` 0–80; `amount` 0–40; `every_h` float|None (0 < x ≤ 72); `mode` Literal["tick","start_end"] default "tick"; `proof` Literal["none","photo","video"] default "none"; `limits` = v1 `Limits` (obs only).
- Routes on `flow_router`:
  - `POST /orders/sign` body `SignIn(At)`: `items` (1–20 OrderItem), `by`. Allowed in `clinic`, `admitting`, `ward`; else 409. Writes `order.signed {items, by}` and, when any item is `dose` or `obs`, a `ward.orders_set` merging the previous one: doses unioned by `key_of(name)` (later wins), `obs_every_h` = the newest obs item's `every_h`, `limits` merged key-wise (later wins), `by`.
  - `POST /orders/{order_id}/ack` body `AckIn(At)`: `by`. 404 if not this episode's `order.signed`; 409 if already acknowledged. Writes `order.acknowledged {order_id, by}` then one `task.created` per item: `{order_id, index, title, kind, mode, proof, every_h, due_ms, name, amount}`; `due_ms` = ack time (`at_ms`) for every item (first occurrence due now).
  - `POST /tasks/{task_id}/begin` body `BeginIn(At)`: `by`. Only `start_end` tasks, only when not running. Writes `task.began`.
  - `POST /tasks/{task_id}/done` body `DoneIn(At)`: `by`, `via` Literal["tap"] (P2 adds "voice"), `note` 0–300, `values` optional `{sbp,dbp,hr,spo2,temp}` with v1 `ObsIn` bounds. `start_end` needs a running `task.began`. A non-recurring task that is done → 409. `obs` kind needs `values` (422 otherwise). Writes `task.done`, then the fact: `dose` → `dose.given {name, amount, by}`; `obs` → `obs.recorded {**values, by}`.
  - `POST /discharge/sign` body `DischargeIn(At)`: `summary` 1–2000, `template` key of `CARE_TEMPLATES` (default `"hernia-repair"`), `by`. Only in `ward`. Writes `discharge.signed {summary, by}`, `discharge.card` (via `seed.card_payload`), then `patient.state` ward → discharging.
- Produces (`tasks.py`), pure functions over events:
  - `orders_list(events) -> list[dict]` — `{"id", "by", "items", "at_ms", "acknowledged_by": str|None}`.
  - `task_list(events) -> list[dict]` — `{"id", "order_id", "title", "kind", "mode", "proof", "every_h", "status": "open"|"running"|"done", "due_ms": int|None, "done": [{"at_ms","by","via","note"}], "began_ms": int|None}`. Recurring: after each `task.done`, `status` returns to `"open"` with `due_ms = last_done + every_h*3_600_000`. Non-recurring done → `"done"`, `due_ms None`. Overdue is computed by the client from `due_ms` and the ward clock.

- [ ] **Step 1: Write failing tests** in `test_flow_tasks.py`:
  - `test_sign_writes_order_and_merged_ward_orders`: sign paracetamol 1 g every 6 h (dose) + BP every 1 h with `sbp_min 90` (obs) → view `order_list[0].acknowledged_by is None`; v1 `orders` (ward.orders_set payload) has the dose and `obs_every_h == 1`, `limits.sbp_min == 90`. Sign a second order with a new dose → the first dose is still in `ward.orders_set`.
  - `test_sign_refused_outside_care_states`: in `clinic_done` → 409.
  - `test_ack_creates_one_task_per_item_once`: ack → 2 tasks, `status "open"`, `due_ms == ack at_ms`; second ack → 409; tasks still 2.
  - `test_tick_dose_writes_dose_given_and_recurs`: done on the dose task at t → a `dose.given` event exists; task `status "open"`, `due_ms == t + 6h`.
  - `test_obs_task_needs_values_and_feeds_limit_nudge`: done without values → 422; with `sbp 82` → `obs.recorded` written and an open nudge of kind `obs_past_limit` appears in the view.
  - `test_start_end_task`: item `kind procedure, mode start_end, text "Saline 1 L over 2 h"`: done before begin → 409; begin → `running`; begin again → 409; done → `done`, `began_ms` set.
  - `test_non_recurring_done_twice_is_409`.
  - `test_discharge_sign_moves_to_discharging`: in `ward` → `state "discharging"`, `card` present, `now_next.next` mentions discharge; in `clinic` → 409.
- [ ] **Step 2: Run** the file → FAIL.
- [ ] **Step 3: Implement** `tasks.py`, the routes, `flow_view` additions, `plain()` lines for `order.signed`, `order.acknowledged`, `task.created`, `task.began`, `task.done`, `discharge.signed`.
- [ ] **Step 4: Run** the file → PASS; `make test` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2: orders become nurse tasks; discharge signing`.

---

### Task 3: v2 seed and the three-path story test (backend)

**Files:**
- Modify: `count-guard/backend/app/journey/seed.py`
- Modify: `count-guard/backend/tests/test_care_demo.py` (seed tests), replace `count-guard/backend/tests/test_care_story.py` with the v2 story
- Test: those two files

**Interfaces:**
- Consumes: Tasks 1–2 routes and `tasks.py` helpers.
- Produces: `seed_ward(store, raise_nudges)` keeps its signature and return shape (`[{id, bed, name}]`, bed order 4, 7, 9). New starting state:
  - Bed 4 Kumar: nothing recorded (state `clinic`).
  - Bed 7 Iyer: at `ts_ms 0`: `patient.state` (from `None` → `ward`, reason `"Admitted the day before (seed)"`, by DOCTOR); `order.signed` with one obs item (`text "BP and pulse every 1 h"`, `every_h 1`, `limits {"sbp_min": 90}`), the merged `ward.orders_set`; `order.acknowledged` by NURSE; its `task.created`; one `obs.recorded` (sbp 124, dbp 78, hr 80, spo2 98, temp 36.9) and the matching `task.done`. Build these through the same helper functions Task 2's routes use (factor them in `tasks.py` if needed), not hand-written payloads.
  - Bed 9 Das: nothing recorded (state `clinic`).
  - Add `NURSE_THEATRE = "Nurse Asha (synthetic)"`. Module docstring updated.
- [ ] **Step 1: Rewrite tests.** In `test_care_demo.py`, replace the v1 seed assertions with: three patients, states `clinic`, `ward`, `clinic`; Iyer has one open recurring obs task due at `0 + 1h`; Das has no `card`. Replace `test_care_story.py` with `test_three_paths_by_tap` driving the HTTP API with explicit `at_ms` on the shared clock (`H = 3_600_000`):
  - **Das**: rx demo import at 0 → `POST /state to clinic_done` at 10 min → state `clinic_done`.
  - **Kumar**: rx demo import; admit (reason "Hernia repair") at 40 min; nurse completes admission at 1 h; doctor signs paracetamol 1 g every 6 h + BP every 1 h (sbp_min 90) at 1 h 10; nurse acks at 1 h 15; send to theatre (`hernia-repair`) at 2 h; surgery began 2 h 05, count opened 20, closing 19 at 3 h 30, corrected closing 20 (supersedes) at 3 h 35, surgery ended 3 h 40; back to ward with empty reason → 200 (count closed); nurse ticks paracetamol at 4 h; doctor signs discharge at 30 h; nurse completes discharge at 31 h → `home`.
  - **Iyer**: nurse completes the obs task with sbp 82 at 1 h → open `obs_past_limit` nudge; doctor signs `procedure` start_end "Saline 1 L over 2 h" + obs every 0.25 h at 1 h 05; ack; begin 1 h 10; done 3 h 10; discharge at 26 h; complete at 27 h → `home`.
  - Assert final states, that every `now_next` seen matches no advice word, and Kumar's timeline contains the struck 19 (`replaced_by` in `/audit` rows, as v1 asserted).
- [ ] **Step 2: Run** both files → FAIL against the v1 seed.
- [ ] **Step 3: Implement** the seed.
- [ ] **Step 4: Run** both files → PASS; `make test` → all pass (fix any other v1 test that pinned the old seed, in this task).
- [ ] **Step 5: Commit** `Count Guard v2: seed three patients at their starting states; three-path story test`.

---

### Task 4: Frontend logic — clock, queue, tasks (pure JS)

**Files:**
- Modify: `count-guard/frontend/src/care/clock.js`, `count-guard/frontend/src/care/derive.js`
- Modify: `count-guard/frontend/src/care/clock.test.js`, `count-guard/frontend/src/care/derive.test.js`

**Interfaces:**
- Consumes: the view fields from Tasks 1–2: `state`, `now_next`, `allowed`, `order_list`, `tasks`, `nudges`.
- Produces (`clock.js`): keep `H`, `M`, `label(ms)`. Remove `STAGES`, `stageOf`, `jumpTargets`, `plusHour`. Add `skipTargets(nowMs, patients) -> [{id, label, atMs}]`: `"+15 min"`, `"+1 h"`, and `"Next due"` = the smallest `due_ms > nowMs` across all open tasks of all patients (omitted when none).
- Produces (`derive.js`):
  - `STATE_LABEL = {clinic: "In clinic", clinic_done: "Clinic visit closed", admitting: "Being admitted", ward: "On the ward", theatre: "In theatre", discharging: "Being discharged", home: "Home"}`.
  - `taskDue(task, nowMs) -> "running"|"overdue"|"due"|"later"|"done"`: overdue when `due_ms + 30 min < nowMs` (v1 GRACE), due when `due_ms <= nowMs`.
  - `queueRows(patients, role, nowMs)` keeps its name and row shape (`key, kind, says, waited, lineId, episodeId, bed, name`) plus `state`. Rows:
    - doctor: patients in `clinic` ("See in clinic"); open `obs_past_limit` nudges (doctor sees them too, spec "Time and seeds"); patients in `ward` with no `order.signed` ("No orders signed").
    - nurse: unacknowledged orders ("New orders from {by}"); tasks `overdue` or `due` ("{title} · due"); `running` tasks; `admitting` ("Complete admission"); `discharging` ("Complete discharge"); v1 nurse nudges.
    - patient: none (patients use Today / My care).
  - `waitingPills` derives from the same rows (`who` = the role's display name).
- [ ] **Step 1: Write failing tests**: `skipTargets` returns "Next due" at the earliest future `due_ms`; `taskDue` boundaries (exactly `due_ms` → due; `due_ms + 30 min + 1` → overdue; running; done); `queueRows` for a nurse with one unacked order and one overdue task → two rows, overdue first; doctor sees an `obs_past_limit` nudge; nobody's rows contain an advice word.
- [ ] **Step 2: Run** `node --test 'src/care/*.test.js'` → FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** → PASS.
- [ ] **Step 5: Commit** `Count Guard v2: queue and skip-ahead from patient states and tasks`.

---

### Task 5: Chart shell — state header, history, role switch fix (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/StateHeader.jsx`, `count-guard/frontend/src/care/lens.js`, `count-guard/frontend/src/care/lens.test.js`
- Modify: `count-guard/frontend/src/care/Chart.jsx`, `count-guard/frontend/src/care/CareShell.jsx` (skip-ahead bar), `count-guard/frontend/src/care/Patients.jsx` (state badge per row), `count-guard/frontend/src/care/Queue.jsx` (state badge), `count-guard/frontend/src/styles.css`

**Interfaces:**
- Consumes: Task 4 `STATE_LABEL`, `skipTargets`, `label`.
- Produces: `StateHeader({ patient, view })` — name, bed, state badge, `now_next.now` and `now_next.next` as two lines ("Now" / "Next").
- Produces: `lens.js` `lensFor(role, picked) -> string` where `picked` is `{role, lens}|null`: returns `picked.lens` only when `picked.role === role`, else `role`. Chart stores `picked` as `{role, lens}` so a role switch drops a stale lens (root cause of the "switch doesn't refresh" report: v1 `Chart.jsx` used `picked || ward.role`).
- Produces: `Chart` layout: `StateHeader`, then `<StatePanel state role view act busy episodeId />` (Tasks 6–7 fill it; this task renders a placeholder listing `view.allowed` for the role as buttons that post `/state` with only `to` and `by` — enough for moves with no `needs`), then "Orders and tasks" (read-only list from `view.tasks`, `taskDue` badge), then History (the v1 `Timeline` with lens chips). Remove `StageBar`, the `?stage=` param, and the four `*Panel` imports from `Chart.jsx`. Keep `?line=` deep-link scroll.
- `CareShell` `ClockBar` uses `skipTargets(ward.nowMs, ward.patients)`; keeps Reset.
- [ ] **Step 1: Write failing test** `lens.test.js`: `lensFor("doctor", {role: "nurse", lens: "everyone"}) === "doctor"`; `lensFor("nurse", {role: "nurse", lens: "everyone"}) === "everyone"`; `lensFor("patient", null) === "patient"`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** node tests → PASS and `npm run build` → success.
- [ ] **Step 5: Commit** `Count Guard v2: chart shows the patient's state, now and next; role switch refreshes the lens`.

---

### Task 6: Doctor actions per state (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/StatePanel.jsx` (switch on state × role; under 200 lines — split helpers into the files below), `count-guard/frontend/src/care/OrderForm.jsx`, `count-guard/frontend/src/care/DoctorActions.jsx`
- Modify: `count-guard/frontend/src/care/Chart.jsx` (use `StatePanel`)

**Interfaces:**
- Consumes: routes from Tasks 1–2; v1 `ClinicPanel` pieces for prescription import and strip check (`screens/ClinicPanel.jsx`); `ward.act(id, path, body)` (stamps `at_ms`).
- Produces: `OrderForm({ busy, onSign(items) })` — rows of item kind (dose / obs / procedure / check / other), text, name + amount (dose), every h, mode (one tick / begin and end), limits (obs: systolic BP min/max). Sends `POST /orders/sign`. Default rows empty; an "Add dose", "Add observation", "Add procedure" button each appends a prefilled row (paracetamol 1 g every 6 h; BP and pulse every 1 h with systolic min 90; "Saline 1 L over 2 h", begin and end).
- Doctor panel by state:
  - `clinic`: prescription import (v1), strip check (v1), **Admit** (reason text, required) and **Close visit**; after Admit, the OrderForm is offered for first orders.
  - `admitting`: OrderForm; text "Waiting for the nurse to complete admission."
  - `ward`: OrderForm; **Send to theatre** (procedure select from a `procedures` list the view exposes — add `procedures: {key: title}` to `flow_view` in this task if Task 1 did not); **Sign discharge** (summary textarea + template select) → `/discharge/sign`.
  - `theatre`: read-only now/next plus "Surgery began/ended" times.
  - `discharging`, `home`, `clinic_done`: read-only summary.
- Every button disabled while `busy`; every failed post shows the server's 409/422 detail via the existing `ward.error` alert.
- [ ] **Step 1:** Add a node test for any pure helper you extract (e.g. `orderRowsToItems(rows)` drops empty rows, converts `every_h` to a number, omits `limits` on non-obs items).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2: doctor actions per patient state`.

---

### Task 7: Nurse, theatre and patient panels (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/NurseActions.jsx`, `count-guard/frontend/src/care/Checklist.jsx`
- Modify: `count-guard/frontend/src/care/StatePanel.jsx`, `count-guard/frontend/src/care/TheatrePanel.jsx`, `count-guard/frontend/src/care/Today.jsx`, `count-guard/frontend/src/care/MyCare.jsx`

**Interfaces:**
- Consumes: Task 6 `StatePanel`; Task 4 `taskDue`; routes from Tasks 1–2.
- Produces: `Checklist({ items: [[key, label]], busy, onDone(checklist) })` — all boxes must be ticked before the button enables.
- Nurse panel by state:
  - any state with unacknowledged orders: each order's items and **Acknowledge**.
  - `admitting`: Checklist band / allergies / baseline obs / consent → `POST /state to ward`.
  - `ward`: task list sorted overdue, due, running, later; `tick` → **Mark done** (obs kind opens a small BP/HR/SpO2/temp form → `values`); `start_end` → **Begin** then **End**. v1 nudges with Answer (v1 `Nudge` from `screens/WardPanel.jsx`).
  - `theatre`: `TheatrePanel` (v1 counts, manual and camera) plus **Surgery began** / **Surgery ended** and **Back to ward**, which asks for a reason when the count is open (server enforces D14; UI shows the field when `view.allowed` lists `needs` containing `"reason"` or the count is open).
  - `discharging`: Checklist card given / medicines handed over / reminders set → `POST /state to home`.
- Patient (`Today`, `MyCare`): show the `StateHeader` for their own record; My care lists orders with each task's done entries (who, when) — "proof" in P1 is who and when; Today keeps v1 check-in and Need help, shown only in `home`.
- [ ] **Step 1:** Node test for any extracted pure helper (e.g. `sortTasks(tasks, nowMs)` order overdue → due → running → later → done).
- [ ] **Step 2–4:** FAIL → implement → node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2: nurse tasks, checklists, theatre exit and patient view by state`.

---

### Task 8: Browser walk of the three paths and fixes

**Files:**
- Create: `.superpowers/sdd/<this plan's workspace>/p1-walk.md` (git-ignored walk log: each step, pass/fail, the fix commit; not a repo doc)
- Modify: whatever the walk finds broken

**Interfaces:**
- Consumes: everything above, running via `make dev` (backend :8100, Vite :5173). If the ports are already in use by a running Count Guard (`lsof -iTCP:8100 -sTCP:LISTEN`), use it — `--reload` and Vite HMR pick up the changes.
- [ ] **Step 1:** Using the Playwright MCP browser tools, open `http://localhost:5173`, press Reset, and walk Das, Kumar and Iyer exactly as Task 3's story test does, switching roles in the header between steps. At each step record in the walk log: the role, the control clicked, what the header's Now/Next says, pass/fail.
- [ ] **Step 2:** Check Review Focus 4 (click "Everyone (audit)" as nurse, switch to doctor → doctor lens and doctor actions show) and 5 (restart nothing; instead set `sessionStorage['cg-ward-roster']` to a roster with an unknown id and reload → ward reseeds).
- [ ] **Step 3:** For each failure: fix, add a test where the fault is in pure logic, re-walk that step.
- [ ] **Step 4:** `make test`, node tests, `npm run build` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2: browser walk of the three paths; fixes`.

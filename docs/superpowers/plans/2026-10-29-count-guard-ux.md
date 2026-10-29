# Count Guard UX (one record, two views) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the eight-tab Count Guard frontend with a queue and a per-patient chart for staff, and Today and My care for the patient. Add a demo clock, a waiting strip and three seeded patients, without changing any nudge rule.

**Architecture:**
- **Backend:** three small additions to the journey API.
  - `at_ms` on answering a nudge.
  - A count route on the journey clock.
  - A demo seed route.
- **Frontend:** a new `src/care/` folder.
  - Two pure modules (`clock.js`, `derive.js`), tested with Node's built-in test runner.
  - One hook (`useWard`) holding the roster, the views and the demo time.
  - Screens that reuse the panels extracted from today's Doctor, Nurse and Patient screens.

**Tech Stack:** FastAPI + pytest (backend), React 19 + react-router 7 + Vite 6 (frontend), `node --test` (Node 24, no new dependency).

**Spec:** `docs/superpowers/specs/2026-10-29-count-guard-ux-design.md`. Read it first. Decisions U1–U8 and calls C1–C5 are referenced below by number.

## Global Constraints

- No nudge rule, nudge wording or ledger behaviour changes (U7). `app/journey/nudges.py` is not edited.
- Every screen shows the banner "Research demo. Not for clinical use." (`BANNER` in `frontend/src/App.jsx:17`).
- No screen text may match the instruction words `give|take|stop|increase|reduce|start|administer|consider` as advice. This applies to labels, pills and placeholders (07 acceptance checks).
- Synthetic data only. Seeded names carry "(synthetic)".
- Every file stays under 500 lines.
- The demo clock bar renders only when `import.meta.env.VITE_DEMO !== "0"`. A non-demo build sets `VITE_DEMO=0`.
- **Do not run `git commit` or `git push`.** The owner's CLAUDE.md forbids it without an explicit request. Each task ends with a checkpoint: run the tests and list the changed files.
- Backend tests: `cd count-guard && make test`. All existing tests (97 at last run) must still pass.
- Frontend tests: `cd count-guard/frontend && node --test src/care/`. Build check: `cd count-guard/frontend && npm run build`.

## Stage times (episode clock; `ts_ms 0` = Day 0 09:00)

Taken from `backend/app/journey/play.py`, so the live demo and `/play` agree:

| Clock button | `at_ms` | Shows |
|---|---|---|
| Clinic | `0` | Day 0 09:00 |
| Strips (evening) | `10 * H` | Day 0 19:00 |
| Admission | `22 * H` | Day 1 07:00 |
| Theatre | `24 * H` | Day 1 09:00 |
| Ward | `26 * H` | Day 1 11:00 |
| Ward 18:30 check | `33 * H + 30 * M` | Day 1 18:30 |
| Home | `48 * H` | Day 2 09:00 |

`H = 3_600_000`, `M = 60_000`. "+1 h" adds `H`.

## Review Focus

1. **Answering a nudge before the clock reaches it.** An answer must never be stamped earlier than the nudge it answers. `seen` uses `max(at_ms, nudge ts)`. Test in Task 1.
2. **Pressing a stage button earlier than the current time.** The button is disabled, never sent. Test in Task 4 (`jumpTargets`).
3. **Reloading the browser mid-demo.** The roster and the demo time come back from `sessionStorage`. If a stored episode id now returns 404 (fresh database), reseed. Covered in Task 6 by the 404 path.
4. **Two nudges with the same text for two patients.** Queue rows are keyed by nudge id, not by text, and each row names its bed. Test in Task 5.
5. **A camera count filed to the wrong patient.** Close files to the chart that opened the camera, not to the session's default patient. Test step in Task 10.

---

### Task 1: `at_ms` on answering a nudge (C5)

**Files:**
- Modify: `count-guard/backend/app/journey/api.py:88-90` (`SeenIn`), `:327-334` (`nudge_seen`)
- Test: `count-guard/backend/tests/test_care_demo.py` (new; copy the `_client` helper from `tests/test_journey.py:28`)

**Interfaces:**
- Produces: `POST /journey/episodes/{id}/handover/{handover_id}/accept` also accepts `at_ms`. `AcceptIn` extends `At`, and the event is stamped `max(at_ms, handover ts)`. Every journey POST body then accepts `at_ms`, so the Task 6 hook can add it to every call.
- Produces: `POST /journey/episodes/{id}/nudges/{nudge_id}/seen` accepts `{"by", "note", "at_ms"?}`. The `nudge.seen` event is stamped `max(at_ms, nudge["ts_ms"])` when `at_ms` is given. Without `at_ms`, it keeps today's behaviour.

- [ ] **Step 1: Write the failing tests**

```python
def test_seen_takes_demo_time(tmp_path):
    client, eid = _episode_with_orders(tmp_path)          # orders set at 0, obs every 1 h
    view = client.post(f"/journey/episodes/{eid}/tick", json={"at_ms": 2 * H}).json()
    nudge = next(n for n in view["nudges"] if n["kind"] == "obs_overdue")
    client.post(f"/journey/episodes/{eid}/nudges/{nudge['id']}/seen", json={"by": "Nurse Meena", "at_ms": 3 * H})
    seen = [r for r in client.get(f"/journey/episodes/{eid}/audit").json()["rows"] if r["type"] == "nudge.seen"]
    assert seen[-1]["when"] == "Day 0 12:00"

def test_seen_never_before_the_nudge(tmp_path):
    ...same setup, answer with at_ms=0...
    assert seen[-1]["when"] == nudge["when"]   # stamped at the nudge's own time, not Day 0 09:00
```

`_episode_with_orders(tmp_path)` is a helper in the test file. It creates an episode (`POST /morning/episodes`), posts `/orders` with `ORDERS` from `test_journey.py:18` at `at_ms 0`, and posts one `/obs` at `at_ms 0`. It returns `(client, episode_id)`.

Check the audit row keys against `audit_rows` in `app/journey/stories.py` before asserting. Use whatever field there holds the clock text.

Also add `test_accept_takes_demo_time`, written in the same shape as the two tests above.

- [ ] **Step 2:** Run `cd count-guard && .venv/bin/pytest -q backend/tests/test_care_demo.py`. Expected: FAIL. `extra="forbid"` rejects `at_ms`.
- [ ] **Step 3:** Make `SeenIn` extend `At`. In `nudge_seen`, pass `max(body.at_ms, nudge["ts_ms"]) if body.at_ms is not None else None` to `_act`.
- [ ] **Step 4:** Run the same command. Expected: PASS. Then run `make test`. Expected: all pass.
- [ ] **Step 5: Checkpoint.** List the changed files. Do not commit.

### Task 2: Count on the journey clock (U8)

`/morning/.../count/replay` stamps events from its own frame times, starting at 0, and `count/manual` stamps "last event + 1 s". Neither lands at Theatre time. This route writes the same payloads `play.py:70-84` writes, at the demo time.

**Files:**
- Modify: `count-guard/backend/app/journey/api.py` (new models `CountIn`, new route)
- Test: `count-guard/backend/tests/test_care_demo.py`

**Interfaces:**
- Produces: `POST /journey/episodes/{id}/count` with body `CountIn(At)`:
  - `step: Literal["opened", "closing"]`
  - `quantity: int = Field(ge=1, le=200)`, used when `step == "opened"`
  - `returned: int = Field(ge=0, le=200)`, used when `step == "closing"`
  - `detail: str = ""` (max 200)
  - `by: str` (1–80)
  - `supersedes_id: str | None = None`
- It writes either:
  - `count.pack_opened` `{"item_type": "swab", "quantity", "source": "typed", "by"}`, or
  - `count.closing` `{"opened", "returned", "unaccounted": opened - returned, "detail", "by"}`. `opened` is the latest `count.pack_opened` quantity. If none exists, return 409 with "Record the pack opened first."
- `supersedes_id` must name a `count.closing` event of this episode, or the route returns 404. It returns `view(...)`. It goes through the same `append` + `raise_nudges` path as `_act`, but passes `supersedes_id` to `store.append`.

- [ ] **Step 1: Write the failing tests:**
  - `test_count_short_raises_nurse_nudge`: opened 20, closing returned 19 at `24*H+50*M`. Expect exactly one open nudge with `kind == "count_open"`, `to == "nurse"`, and `says == "Closing count: 19 of 20 back, 1 unaccounted."`.
  - `test_count_correction_strikes_through`: the closing above, then a closing of 20 with `supersedes_id` = the first closing id and detail "Swab found in the drape fold.". The audit rows show the first closing as replaced, using the same field `test_journey.py` uses for supersede. The answered nudge leaves `view["nudges"]` after `seen`.
  - `test_count_closing_needs_opened`: closing without opened returns 409.
  - `test_count_rejects_foreign_supersede`: `supersedes_id` of another episode's event returns 404.
- [ ] **Step 2:** Run the tests. Expected: FAIL (404 route).
- [ ] **Step 3:** Implement the route as specified.
- [ ] **Step 4:** Run the tests. Expected: PASS. Run `make test`. Expected: all pass.
- [ ] **Step 5: Checkpoint.**

### Task 3: Demo seed (C3)

**Files:**
- Create: `count-guard/backend/app/journey/seed.py`
- Create the route in: `count-guard/backend/app/journey/api.py` as a second router `demo_router = APIRouter(prefix="/journey/demo")`, registered in `count-guard/backend/app/main.py:47`
- Modify: `count-guard/frontend/vite.config.js:17-21`. The proxy bypass must also pass `/journey/demo`.
- Test: `count-guard/backend/tests/test_care_demo.py`

**Interfaces:**
- Produces:
  - `seed_ward(store, raise_nudges) -> list[dict]` returns `[{"id", "bed", "name"}]` in bed order.
  - `POST /journey/demo/seed` returns `{"patients": [...]}`. Each call creates three new episodes; old ones stay.
- The three patients (labels exactly):

| Bed | Label | Events written at seed |
|---|---|---|
| 4 | `R. Kumar, 58 M (synthetic)` | none (the video builds his story live) |
| 7 | `S. Iyer, 64 F (synthetic)` | `ward.orders_set` at 0 with `obs_every_h: 1`, limits `sbp_min 90`, by `Dr. A. Rao (synthetic)`; `obs.recorded` 124/78/80/98/36.9 at 0 |
| 9 | `A. Das, 47 M (synthetic)` | `rx.ordered` from `DEMO_DOCUMENT` at 0; `discharge.card` from template `hernia-repair` at 0, by `Dr. A. Rao (synthetic)` |

- **Deviation from the spec, recorded here:** the spec puts Iyer at "Ward Day 2 with an open `obs_overdue`". On one shared clock, Iyer's overdue round is instead raised by the real rule the first time the clock passes Day 0 10:00. Her events are not dated in the future. Das has no open nudge, as the spec says.
- Build the payloads with the helpers `play.py` already uses (`key_of`, `from_document`, `CARE_TEMPLATES`). Do not copy them.

- [ ] **Step 1: Write the failing tests:**
  - `test_seed_three_patients`: the response lists beds `["4", "7", "9"]` with the labels above, and each id `GET`s 200.
  - `test_seed_iyer_overdue_by_rule`: a tick at `2*H` on Iyer raises one `obs_overdue` addressed to nurse. No open nudge exists before the tick.
  - `test_seed_das_quiet`: Das has `card` set and `nudges == []`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `seed.py` and the route. Add `"/journey/demo"` to the vite bypass check.
- [ ] **Step 4:** Run. Expected: PASS. Run `make test`. Expected: all pass.
- [ ] **Step 5: Checkpoint.**

### Task 4: Demo clock module

**Files:**
- Create: `count-guard/frontend/src/care/clock.js`
- Test: `count-guard/frontend/src/care/clock.test.js`

**Interfaces:**
- Produces:
  - `H`, `M`.
  - `STAGES: {id, label, atMs}[]` (the stage-time table above, in order).
  - `label(ms) -> "Day 1 18:30"`, the same format as backend `clock()` in `app/journey/stories.py:65`.
  - `stageOf(ms) -> "clinic" | "theatre" | "ward" | "home"`: home from `48*H`, ward from `26*H`, theatre from `24*H`, else clinic.
  - `jumpTargets(nowMs) -> {id, label, atMs, enabled}[]`: `enabled` is `atMs > nowMs`.
  - `plusHour(ms)`.

- [ ] **Step 1: Write the failing tests (`node:test` + `node:assert/strict`):**
  - `label(0) === "Day 0 09:00"`, `label(33*H+30*M) === "Day 1 18:30"`, `label(48*H) === "Day 2 09:00"`.
  - `stageOf(24*H) === "theatre"`, `stageOf(26*H - 1) === "theatre"`, `stageOf(48*H) === "home"`.
  - `jumpTargets(26*H)`: Clinic, Strips and Theatre are disabled, Ward 18:30 and Home are enabled. Ward itself (`26*H`, equal to now) is disabled.
- [ ] **Step 2:** Run `cd count-guard/frontend && node --test src/care/`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Checkpoint.**

### Task 5: Queue, to-dos and waiting strip (C1)

**Files:**
- Create: `count-guard/frontend/src/care/derive.js`
- Test: `count-guard/frontend/src/care/derive.test.js`

**Interfaces:**
- Consumes: `label`, `H`, `M` from Task 4. `patients` is `{id, bed, name, view}[]`, where `view` is the journey view from `GET /journey/episodes/{id}` (`app/journey/api.py:151-181`; nudges carry `id, kind, to, says, at_ms, when`).
- Produces:
  - `queueRows(patients, role, nowMs) -> Row[]`, where `Row = {key, episodeId, bed, name, kind: "nudge"|"todo", says, waited, lineId, action}`. `lineId` is the nudge id for a nudge, or null.
    - Nurse and patient rows are the open nudges with `to === role`.
    - Doctor rows are to-dos only.
    - Rows sort by longest waited first. `waited` is text such as `"2 h 20 min"` or `"5 min"`.
  - `todos(patient) -> Row[]`, in this order:
    - `"Ward orders not set"` (doctor): when `view.rx` is set and `view.orders` is null.
    - `"Discharge card not signed"` (doctor): when `view.orders` is set and `view.card` is null.
    - `"Handover to {to_nurse} not accepted"` (nurse): when `view.handover` is set and `accepted_by` is null.
  - `waitingPills(patients, nowMs) -> {key, who, what, waited, late, episodeId, lineId}[]`.
    - It covers every open nudge and every to-do across all patients.
    - `who` is the role name for a nudge ("Nurse", "Patient"), or the to-do's owner ("Dr. A. Rao" for doctor to-dos, the `to_nurse` value for a handover).
    - `late` is waited ≥ 1 h.

- [ ] **Step 1: Write the failing tests, with fixture views as plain objects:**
  - Two patients each with an `obs_overdue` nudge of identical `says` give two nurse rows with different `key`s, each with its own `bed`.
  - A nurse nudge at `28*H` with `now 30*H+20*M` gives `waited === "2 h 20 min"` and `late === true`.
  - The doctor role with `rx` set and `orders` null gives one row, `"Ward orders not set"`, of kind `todo` and no `lineId`.
  - The patient role sees only `to === "patient"` nudges.
  - None of the produced strings matches `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Checkpoint.**

### Task 6: `useWard` hook: roster, views and demo time

**Files:**
- Create: `count-guard/frontend/src/care/ward.js`

**Interfaces:**
- Consumes: `call`, `postJourney` from `frontend/src/journey.js`. `postJourney` is exported today; also export `call`. It also consumes `STAGES` and `plusHour` from Task 4.
- Produces: `useWard() -> {patients, nowMs, role, setRole, busy, error, act, upload, jump, reset, find}`:
  - `upload(episodeId, path, file)` wraps `uploadJourney` and swaps in the returned view. It sends no `at_ms`.
  - `act(episodeId, path, body)` posts with `{...body, at_ms: nowMs}` and swaps in that patient's returned view.
  - `jump(ms)` sets `nowMs` (it refuses `ms <= nowMs`), then posts `/tick` with `at_ms: ms` to every patient.
  - `reset()` calls `POST /journey/demo/seed` and sets `nowMs = 0`.
  - `find(episodeId)` returns the matching patient.
- `sessionStorage` keys: `cg-ward-roster` (the seed response) and `cg-ward-now`. On load, if any stored id `GET`s 404, it calls `reset()`. Share one in-flight load, as `episode.js:20-24` does, so StrictMode does not seed twice.
- Role is kept in `sessionStorage` key `cg-role`. The default is `"nurse"`.

- [ ] **Step 1:** Implement. The pure logic is already tested in Tasks 4–5. This hook is checked by running the app in Task 12.
- [ ] **Step 2:** Run `npm run build`. Expected: success.
- [ ] **Step 3: Checkpoint.**

### Task 7: Extract panels from today's screens

The chart's stage panels and the patient's Today screen reuse today's forms. Move each into a component that takes `{view, busy, act}` and owns no fetching, so both the old route and the new chart can mount it.

**Files:**
- Create: `count-guard/frontend/src/screens/WardPanel.jsx` from `Nurse.jsx`: the dose form, observation form, `Nudge`, and the `NurseHandover` mount.
- Create: `count-guard/frontend/src/screens/ClinicPanel.jsx` from `Doctor.jsx`: rx import and demo rx, `RxTable`, `DoctorOrders`, card signing.
- Create: `count-guard/frontend/src/screens/TodayPanel.jsx` from `Patient.jsx`: `Medicines`, the strips form and photo, reminders, `CheckIn`, Need help, `MyCard`.
- Modify: `Nurse.jsx`, `Doctor.jsx`, `Patient.jsx` to become thin wrappers: `useJourney()` plus the panel.

**Interfaces:**
- Produces: `WardPanel`, `ClinicPanel` and `TodayPanel` (default exports), each with props `{view, busy, act}`. `TodayPanel` also takes `upload(path, file) -> Promise<view|null>` for the strip photo. `act(path, body)` has the same signature as `useJourney().act`. The new screens pass `(path, body) => ward.act(id, path, body)`.
- `Nudge` is exported from `WardPanel.jsx` as a named export (the chart renders it inline).

- [ ] **Step 1:** Move the code without changing behaviour.
- [ ] **Step 2:** Run `npm run build`. Expected: success. Open `/nurse`, `/doctor` and `/patient` in `npm run dev`. Each behaves as before; the `/journey` "Play" still fills them.
- [ ] **Step 3: Checkpoint.**

### Task 8: Care shell, routes and navigation (U5, two tabs)

**Files:**
- Create: `count-guard/frontend/src/care/CareShell.jsx`, which holds the app bar, tabs, role switcher, waiting strip and demo clock bar.
- Modify: `count-guard/frontend/src/App.jsx:160-173` (routes).
- Modify: `count-guard/frontend/src/styles.css` (strip, clock bar and highlight classes, in Lightday tokens).

**Interfaces:**
- Consumes: `useWard` (Task 6), `waitingPills` (Task 5), `jumpTargets`, `label` (Task 4), `Banner` (`App.jsx:19`).
- Produces: `<CareShell ward={ward}>{children}</CareShell>`. This task adds only `/` and `/patients`. Tasks 9, 10 and 11 each register their own route in `App.jsx` when the screen exists. The table lists the final routes:

| Route | Screen |
|---|---|
| `/` | redirect to `/queue`, or to `/today` when role is patient |
| `/queue` | `Queue` (Task 9) |
| `/patients` | list of `ward.patients`: bed, name, stage (`stageOf(nowMs)` for Kumar; the latest stage with events for others). Each opens `/chart/:id` |
| `/chart/:episodeId` | `Chart` (Task 10) |
| `/today`, `/my-care` | patient screens (Task 11), shown for Kumar |

- Tabs: "My queue" and "Patients" for staff. For the patient role: "Today" and "My care".
- Role switcher: Doctor, Nurse, Patient. Switching to Patient navigates to `/today`.
- Waiting strip: one pill per `waitingPills` entry, `"{who} → {what} · {waited}"`. A late pill uses the sun tone. A click opens `/chart/{episodeId}?line={lineId}`, or `/chart/{episodeId}` when there is no line.
- The demo clock bar (only when `VITE_DEMO !== "0"`) has:
  - The current `label(nowMs)`.
  - One button per `jumpTargets` entry. Disabled buttons are not sent.
  - "+1 h" and "Reset".
- The old routes stay mounted but leave the nav. A small "Guide" and "Older screens" link in the footer reaches `/guide` and a list of the old routes.

- [ ] **Step 1:** Implement.
- [ ] **Step 2:** Run `npm run build`. Expected: success. Run `node --test src/care/`. Expected: pass.
- [ ] **Step 3: Checkpoint.**

### Task 9: Queue screen (U2, U4)

**Files:**
- Create: `count-guard/frontend/src/care/Queue.jsx`

**Interfaces:**
- Consumes: `queueRows` (Task 5), `ward.act`, and `Nudge` (Task 7) for the demo quick action.
- The table columns are bed, patient, what, waited and "Open →".
- "Open →" goes to `/chart/{episodeId}?line={lineId}`.
- When `VITE_DEMO !== "0"`, a nudge row also has an "Answer" toggle that expands the `Nudge` answer form inline (U4).
- Below the table are "My patients" (one line each) and, for the nurse, the handover entry linking to the chart's Ward stage.
- The empty state reads "Nothing needs you now."

- [ ] **Step 1:** Implement. Run `npm run build`. Expected: success.
- [ ] **Step 2: Checkpoint.**

### Task 10: Chart with stages, lenses, deep link and the Theatre count (U1, U2, U8)

**Files:**
- Create: `count-guard/frontend/src/care/Chart.jsx`, covering the header, stage bar, lens chips, timeline and inline nudges.
- Create: `count-guard/frontend/src/care/TheatrePanel.jsx`, covering the count form and the camera button.
- Modify: `count-guard/frontend/src/screens/Close.jsx:47-58`, so it files to the chart's patient.

**Interfaces:**
- Consumes: `ward.find`, `ward.act`, `ClinicPanel`, `WardPanel`, `TodayPanel` (read-only use is not needed), `Nudge`, `stageOf`, `getAudit` (`journey.js`), and `POST /count` (Task 2).
- Stage bar: Clinic, Theatre, Ward, Home. A stage is done, now or later from `stageOf(nowMs)`. Key facts:
  - Theatre shows `"count {returned}/{opened}"` from the latest non-superseded `count.closing` in the timeline.
  - Home shows `"card signed"`.
- A click opens that stage's panel above the timeline:
  - Clinic → `ClinicPanel`
  - Theatre → `TheatrePanel`
  - Ward → `WardPanel`
  - Home → the card summary, check-ins and help lines
- Lens chips: Nurse, Doctor, Patient, Everyone (audit).
  - The role lenses filter timeline lines by type prefix:
    - doctor: `rx.`, `ward.orders`, `discharge.card`, `druglog.`
    - nurse: `count.`, `dose.`, `obs.`, `handover.`, `nudge.`
    - patient: `brownbag.`, `reminders.`, `checkin.`, `help.`
  - Nudges addressed to the current role always show.
  - "Everyone (audit)" renders `getAudit` rows, with replaced lines struck through.
- Deep link: `?line={nudgeId}` scrolls that nudge's line into view (`scrollIntoView({block: "center"})`) and adds the highlight class. A missing id shows the chart from the top without an error.
- `TheatrePanel`:
  - "Pack opened" takes a number and defaults to 20.
  - "Closing count" takes returned and detail, then posts `/count`.
  - When an open `count_open` nudge exists, "Correct the count" posts a closing with `supersedes_id` set to that closing.
  - "Count by camera" stores `sessionStorage["cg-chart-episode"] = episodeId`, then navigates to `/count`.
- `Close.jsx` files to `sessionStorage["cg-chart-episode"]` when it is set, falling back to today's `patient.episode.id`. After filing, it shows a link "Back to the chart" to `/chart/{id}`.

- [ ] **Step 1:** Implement `Chart.jsx` and `TheatrePanel.jsx`.
- [ ] **Step 2:** Make the `Close.jsx` change.
- [ ] **Step 3: Manual test of Review Focus 5:**
  - Open Iyer's chart, press "Count by camera", run the demo scenario case and close.
  - Confirm the count lands on Iyer, not on the session's default patient.
  - Then open Kumar's chart and confirm it has no camera count.
- [ ] **Step 4:** Run `npm run build`. Expected: success.
- [ ] **Step 5: Checkpoint.**

### Task 11: Patient app: Today and My care (U3)

**Files:**
- Create: `count-guard/frontend/src/care/Today.jsx`, which wraps `TodayPanel` for bed 4 with `ward.act`.
- Create: `count-guard/frontend/src/care/MyCare.jsx`, which shows the stage bar and the timeline read-only, using the patient lens and plain lines. It has no action buttons.

- [ ] **Step 1:** Implement both. My care has no form, no button except navigation, and no `act` import.
- [ ] **Step 2:** Run `npm run build`. Expected: success.
- [ ] **Step 3: Checkpoint.**

### Task 12: The video run-through (U6)

**Files:**
- Create: `count-guard/backend/tests/test_care_story.py`. It plays the story below through HTTP only, using the routes the new screens call, with explicit `at_ms`.

- [ ] **Step 1:** Write `test_care_story` from the checklist below. Use `POST /journey/demo/seed`, then Kumar's episode. It asserts each queue-visible nudge: its `kind`, its `to`, and its leaving `view["nudges"]` after `seen`. It also asserts the audit rows show the 19 closing as replaced. Run it. Expected: PASS. If it fails, fix the earlier code, not the test.
- [ ] **Step 2:** The owner walks the same table in the browser (`make dev`). This is listed in the final report, not run by an agent. Checklist:
  - **Clinic:** import the prescription. Jump to Strips. As the patient on Today, enter "amlodipine 10 mg". The patient queue shows the strip nudge. Jump to Admission: as the doctor, set orders (paracetamol 1 g IV every 6 h) with BP limit 90.
  - **Theatre:** pack opened 20, closing 19. "Closing count: 19 of 20 back, 1 unaccounted." appears in the nurse queue and the strip. Correct to 20, answer the count nudge. The audit lens strikes the 19 through.
  - **Ward:** on arrival (11:00) the nurse logs paracetamol. Log obs 86/54 at 16:10 (+1 h steps). Queue → "Open →" lands on the BP 86 line, highlighted. Answer it. The row leaves the queue and the strip. Jump to 18:30: paracetamol overdue appears. Log it. Draft the handover. The strip shows "Nurse Kavya → accept handover".
  - **Home:** as the doctor, sign the card. Jump to Home. As the patient, check in with "Fever above 38 °C" and press Need help with "The dressing is wet". Both appear in the nurse queue. The audit lens shows the whole journey.
- [ ] **Step 3:** Run `make test` and `node --test src/care/`. Expected: all pass. Run `npm run build`. Expected: success.
- [ ] **Step 4: Checkpoint.** List every changed and new file for the owner's review. Do not commit.

# Count Guard v2 Clarity Pass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A first-time viewer can tell, on every care screen, whose screen it is, what matters now and what to press, with the 31-beat demo still green.

**Architecture:** Wording moves to where it is decided. The backend's `stories.py` gets one more wording function, for the patient, and the timeline view carries both texts. The frontend gets small pure helpers with node tests: `alerts.js` (new), `actions.js` (new), and additions to `tasklist.js`, `derive.js`, `video.js` and `clock.js`. Thin components render them. The beat table, the step functions and the video-script doc change in the same task as the screen text they check.

**Tech Stack:** FastAPI + pytest (backend `count-guard/backend/app/journey`), React 18 + Vite, `node:test` (care helpers in `count-guard/frontend/src/care`), Playwright demo runner (`count-guard/frontend/scripts/demo`).

**Spec:** `docs/superpowers/specs/2026-10-30-count-guard-v2-clarity-design.md` (11 changes, C1 to C11). Read it with this plan.

## Global Constraints

- `make demo-check` stays green with all 31 beats (run as `cd count-guard && make demo-check MODEL_API_KEY=`).
- Backend tests (345), care node tests (91) and demo tests (36) stay green. New behaviour gets new tests.
- `docs/demo/count-guard-v2-video-script.md` matches the screen. Its doc test checks every beat's `say`, every `expect` string and every id. Update its "Clicks:" and "On screen:" lines whenever `beats.mjs` changes.
- The no-advice word scan passes: no new copy may contain give, take, stop, increase, reduce, start, administer or consider as whole words. Buttons keep "Begin".
- Files stay under 500 lines. Near the limit: `backend/app/journey/api.py` (467), `frontend/src/styles.css` (429). Task 1 keeps `api.py` flat by moving timeline building into `stories.py`. If `styles.css` passes 480, move the care-only rules (`.wait-strip` to `.clock-bar`, plus this plan's new rules) into `frontend/src/care/care.css` and import it from `CareShell.jsx`.
- No new model calls, states or data. No backend model changes. The old `/journey` and `/steps` screens are out of scope.
- Commit on branch `count-guard-v2-clarity` only, with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Add no `Co-Authored-By` trailer. Never push.
- Test commands (run from `count-guard/`):
  - backend: `.venv/bin/python -m pytest backend/tests -q` (`pytest.ini` sets `pythonpath = backend`)
  - care: `cd frontend && node --test 'src/care/*.test.js'`
  - demo: `cd frontend && node --test 'scripts/demo/*.test.mjs'`
  - build: `cd frontend && npm run build`

## Review Focus

1. **Two open safety alerts on one patient** (a BP past its limit and an open count). The banner shows both forms, and NOW names the newest one. Test: `alertNow picks the newest safety nudge` (Task 2).
2. **A chart for a patient with no alerts while others have some.** The strip must be empty on that chart, not show other patients' alerts. Test: `stripPills on a chart keeps that patient's pills only` (Task 2).
3. **The doctor opens a chart with an alert addressed to the nurse.** The doctor sees it read-only with "Waiting for the nurse's answer". The form appears only when the doctor arrived by that alert's deep link. Test: `bannerAlerts gives the form to the nurse, to the addressee and to the deep link` (Task 2).
4. **The patient comes back from theatre with a dose overdue.** The due nudge is held while in theatre and raised on the first action or tick after the return. Test: `test_due_nudges_pause_in_theatre_and_resume` (Task 3).
5. **An observation set with some values present and some missing.** Present values stay, including a temperature, and missing ones are left out. Test: `test_obs_line_leaves_out_missing_values` (Task 1).

## Decisions this plan takes where the spec leaves a choice or conflicts with the code

- **C7 order, owner to confirm:** the steps are numbered ① Tray check → ② Surgery began → ③ Swab count → ④ Surgery ended → Back to ward. The spec puts Surgery began first, but the server refuses a tray check once surgery began (`backend/app/journey/video_api.py:56`), and backend changes are out of scope. The beats already run tray before Surgery began.
- **C2 scope:**
  - "Safety alert" means the `obs_past_limit` and `count_open` nudges, plus the tray flag. The tray flag is shown read-only because it has no answer.
  - Every other open nudge's form also moves into the banner, in normal style. That way no form shows twice: the timeline and the nurse's ward card both lost theirs.
  - NOW reads `Waiting for the nurse's answer: …` for safety nudges only, so routine due nudges do not hide what happened.
- **C2 demo text:** with Iyer's BP alert open, NOW no longer reads "began/finished Saline …". The `iyer-setup` and `iyer-end` expects move to the task line (`… running`, `… done`).
- **C3 panels:** they are closed by default and opened by their bar button, since "panels not chosen stay closed" rules out open-by-default. A panel with an open dictation draft opens by itself. The chosen panels reset on a state move. The demo gains one `H.open` click per hidden control.
- **C5 extra statuses:** a running task reads "Running", a one-off done task reads "Done HH:MM", and a task in theatre reads "Paused (in theatre)". The spec does not name these.
- **C6 checks wording:** an unchecked clip reads "A video was kept; it was not checked.", and a photo check says "photos" in place of "a video".
- **C8 pause:** due nudges are held while in theatre. Due times are not shifted, so a task that fell due during theatre shows as overdue on return. The clock bar's "Next due" button is unchanged.
- **C9 placement:** the frontend clock steps 2 min after each successful `act` or `upload`. No backend change is needed and every action keeps its explicit `at_ms`.
- **C1 "Today":** the strip is hidden for the patient role, as it is today. The name prefix applies on every staff screen except a chart.

---

### Task 1: Timeline wording: observation line, plurals, patient lens (C10 text, C6 timeline)

**Files:**
- Modify: `count-guard/backend/app/journey/stories.py:81-172` (`plain`), add `count_of`, `patient_line`, `timeline_items`
- Modify: `count-guard/backend/app/journey/api.py:194-197` (the `"timeline"` key of `view`)
- Modify: `count-guard/frontend/src/care/Timeline.jsx:37` (patient lens text)
- Test: `count-guard/backend/tests/test_clarity_text.py` (create)

**Interfaces:**
- Produces: `count_of(n: int, word: str) -> str` gives "1 order" and "2 orders".
- Produces: `patient_line(event: dict, tasks: dict[str, dict]) -> str`. It returns the patient's wording, or `plain(event)` when it has none. `tasks` maps a `task.created` id to its payload.
- Produces: `timeline_items(events: list[dict]) -> list[dict]`. Each item is `{id, when, type, plain, patient}`. `api.view` returns these as `"timeline"`.
- Produces (view): every timeline item now has a `patient` string. Task 2 and Task 5 read timeline items, but neither needs the new key.

- [ ] **Step 1: Write the failing tests** in `backend/tests/test_clarity_text.py`

```python
from app.journey.stories import count_of, patient_line, plain, timeline_items

def ev(kind, eid="e1", ts=0, **p):
    return {"id": eid, "event_type": kind, "ts_ms": ts, "payload": p}

def test_obs_line_leaves_out_missing_values():
    assert plain(ev("obs.recorded", by="N", sbp=82, dbp=54, hr=112, spo2=None, temp=None)) == "N logged BP 82/54, HR 112."
    assert plain(ev("obs.recorded", by="N", sbp=112, dbp=70, hr=84, spo2=None, temp=36.9)) == "N logged BP 112/70, HR 84, T 36.9."

def test_order_counts_are_singular_and_plural():
    assert count_of(1, "order") == "1 order" and count_of(2, "order") == "2 orders"
    assert plain(ev("order.signed", by="D", items=[{}])) == "D signed 1 order."
    assert plain(ev("order.drafted", by="D", items=[{}])) == "D dictated 1 order (draft, not signed)."

TASKS = {"t1": {"title": "Paracetamol 1 g every 6 h", "name": "Paracetamol", "kind": "dose"},
         "t2": {"title": "BP and pulse every 1 h", "name": "", "kind": "obs"},
         "t3": {"title": "Saline 1 litre over 2 hours", "name": "", "kind": "procedure"}}

def test_patient_wording():
    s = lambda frm, to: ev("patient.state", by="D", to=to, **{"from": frm})
    assert patient_line(s("clinic", "admitting"), {}) == "You were admitted."
    assert patient_line(s(None, "ward"), {}) == "You were admitted."
    assert patient_line(s("ward", "theatre"), {}) == "You went to theatre."
    assert patient_line(s("theatre", "ward"), {}) == "You are back on the ward."
    assert patient_line(s("discharging", "home"), {}) == "You went home."
    assert patient_line(ev("surgery.ended", by="N"), {}) == "Your operation finished."
    assert patient_line(ev("order.signed", by="D", items=[{}, {}]), {}) == "The doctor signed 2 orders."
    done = lambda tid: ev("task.done", by="Nurse Meena (synthetic)", task_id=tid)
    assert patient_line(done("t1"), TASKS) == "Nurse Meena gave paracetamol."
    assert patient_line(done("t2"), TASKS) == "Nurse Meena checked your observations."
    assert patient_line(done("t3"), TASKS) == "Nurse Meena finished: Saline 1 litre over 2 hours."
    other = ev("help.requested", says="Pain")
    assert patient_line(other, {}) == plain(other)

def test_timeline_items_carry_both_texts():
    events = [ev("task.created", "t1", **{**TASKS["t1"], "order_id": "o1"}),
              ev("task.done", "d1", 120_000, by="Nurse Meena (synthetic)", task_id="t1", via="tap")]
    item = timeline_items(events)[1]
    assert item == {"id": "d1", "when": "Day 0 09:02", "type": "task.done",
                    "plain": "Nurse Meena (synthetic) finished a task.", "patient": "Nurse Meena gave paracetamol."}
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd count-guard && .venv/bin/python -m pytest backend/tests/test_clarity_text.py -q`
Expected: FAIL with an ImportError for `count_of`.

- [ ] **Step 3: Implement the wording in `stories.py`**

Make `plain` for `obs.recorded` join only the non-None parts: "BP s/d" (when both are present), "HR h", "SpO2 x", "T t". Make `order.signed` and `order.drafted` use `count_of(len(items), "order")`. Add `patient_line` with the patient-state map below. The person's name is `short_name(p["by"])` from `app.journey.ask`. Every other event type falls back to `plain`.

| `to` (and `from`) | Patient wording |
|---|---|
| `admitting`, or `from` is None | You were admitted. |
| `ward` from `admitting` | You are on the ward. |
| `ward` from `theatre` | You are back on the ward. |
| `theatre` | You went to theatre. |
| `clinic_done` | Your clinic visit was closed. |
| `discharging` | Your discharge was signed. |
| `home` | You went home. |

Also add: `surgery.began` reads "Your operation began.", and `discharge.signed` reads "The doctor signed your discharge.".

`timeline_items` builds the `tasks` map from the `task.created` events. Then it maps each event to the item shape in the Interfaces block.

- [ ] **Step 4: Use it in `api.view`.** Replace the inline timeline list with `"timeline": timeline_items(events)`. Import `timeline_items` beside `plain`, and drop `plain` from the import if nothing else in `api.py` uses it.

- [ ] **Step 5: Use it in the patient lens.** In `Timeline.jsx:37`, render `lens === "patient" ? item.patient || item.plain : item.plain`. The nurse and doctor lenses keep `plain`.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd count-guard && .venv/bin/python -m pytest backend/tests -q && cd frontend && node --test 'src/care/*.test.js' && npm run build`
Expected: all pass. `test_p2_dictation.py:275` ("dictated 2 orders") still passes. No beat text changes: `iyer-recheck` expects "logged BP 112/70, HR 84", which is a prefix of the new line.

- [ ] **Step 7: Commit**

```bash
git add count-guard/backend/app/journey/stories.py count-guard/backend/app/journey/api.py count-guard/frontend/src/care/Timeline.jsx count-guard/backend/tests/test_clarity_text.py
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: obs line without missing values, 1 order/2 orders, patient wording on the timeline"
```

---

### Task 2: Alerts name their patient and sit at the top of the chart (C1, C2)

**Files:**
- Create: `count-guard/frontend/src/care/alerts.js`, `count-guard/frontend/src/care/alerts.test.js`, `count-guard/frontend/src/care/AlertBanner.jsx`
- Modify: `count-guard/frontend/src/care/derive.js:170-179` (add `name` to each pill)
- Modify: `count-guard/frontend/src/care/CareShell.jsx:42-61` (`Strip`)
- Modify: `count-guard/frontend/src/care/StateHeader.jsx` (an `alert` prop overrides NOW)
- Modify: `count-guard/frontend/src/care/Chart.jsx:64-72, 123-132` (banner under the header; Timeline props)
- Modify: `count-guard/frontend/src/care/Timeline.jsx` (no answer forms; drop `busy`, `act`, `readOnly`)
- Modify: `count-guard/frontend/src/care/MyCare.jsx:55` (drop `readOnly`)
- Modify: `count-guard/frontend/src/care/NurseActions.jsx:2,91` (drop the nudge list and its import)
- Modify: `count-guard/frontend/src/care/TheatrePanel.jsx:81` (drop the "Open: …" line; the banner carries it)
- Modify: `count-guard/frontend/src/care/DoctorActions.jsx:152,156` (drop the tray-flag note; the banner carries it)
- Modify: `count-guard/frontend/src/styles.css` (`.alert-banner`, `.alert-safety`)
- Modify: `count-guard/frontend/scripts/demo/beats.mjs:220,228`, `count-guard/frontend/scripts/demo/beats.test.mjs:79-80`, `docs/demo/count-guard-v2-video-script.md` (the `iyer-setup` and `iyer-end` On screen lines)

**Interfaces:**
- Consumes: `waitingPills(patients, nowMs)` from `derive.js`. This task adds `name` to its output.
- Produces in `alerts.js`:
  - `SAFETY = ["obs_past_limit", "count_open"]`
  - `surname(name: string) -> string` gives "Kumar" for "R. Kumar, 58 M (synthetic)".
  - `stripPills(pills, episodeId: string | undefined) -> pills`, each pill with an added `text`. On a chart it keeps that patient's pills only and the text is `${who} → ${what}`. Off a chart the text is `${surname} · ${who} → ${what}`.
  - `alertNow(view) -> string | null` gives `Waiting for ${WHO[to]}'s answer: ${says}` for the newest open nudge whose kind is in `SAFETY`. `WHO = { nurse: "the nurse", doctor: "the doctor", patient: "the patient" }`.
  - `bannerAlerts(view, role, line) -> [{ nudge, safety: boolean, canAnswer: boolean }]` covers every open nudge, with safety nudges first. `canAnswer` is `role === "nurse" || nudge.to === role || nudge.id === line`. That is the rule the timeline used before.
- Produces: `<AlertBanner view role line busy act />`. It renders nothing when there are no alerts and no tray flag. Each answerable alert reuses `Nudge` from `screens/WardPanel` (class `card sunk`, which `steps.mjs:174` relies on). Each item carries `data-line={nudge.id}`, so the deep-link scroll in `Chart.jsx:44-48` lands on the banner first. The tray flag (`trayFlag(view)` from `video.js`) shows as one read-only line.
- Produces: `StateHeader({ patient, view, alert })`. When `alert` is truthy, NOW shows it. Only `Chart` passes `alert`; the patient pages keep the server's NOW.

- [ ] **Step 1: Write the failing tests** in `alerts.test.js`. Also add `assert.equal(waitingPills(patients, now)[0].name, "Patient e1")` to `derive.test.js` "waited text and late flag".

```js
import { SAFETY, alertNow, bannerAlerts, stripPills, surname } from "./alerts.js";
const n = (id, kind, to, at_ms, says = `says ${id}`) => ({ id, kind, to, at_ms, says, when: "Day 0 10:00" });
const pill = (episodeId, name, who, what) => ({ key: `${episodeId}:${what}`, episodeId, name, who, what });

test("surname", () => assert.equal(surname("R. Kumar, 58 M (synthetic)"), "Kumar"));
test("stripPills off a chart names each patient", () => {
  const out = stripPills([pill("e9", "A. Das, 47 M (synthetic)", "Patient", "This strip reads …")], undefined);
  assert.equal(out[0].text, "Das · Patient → This strip reads …");
});
test("stripPills on a chart keeps that patient's pills only", () => {
  const pills = [pill("e9", "A. Das", "Patient", "x"), pill("e4", "R. Kumar", "Nurse", "y")];
  assert.deepEqual(stripPills(pills, "e4").map((p) => p.text), ["Nurse → y"]);
  assert.deepEqual(stripPills(pills, "e7"), []);
});
test("alertNow picks the newest safety nudge", () => {
  const view = { nudges: [n("a", "obs_past_limit", "nurse", 1, "BP low."), n("b", "count_open", "nurse", 2, "Count open."), n("c", "obs_overdue", "nurse", 3)] };
  assert.equal(alertNow(view), "Waiting for the nurse's answer: Count open.");
  assert.equal(alertNow({ nudges: [n("c", "obs_overdue", "nurse", 3)] }), null);
});
test("bannerAlerts gives the form to the nurse, to the addressee and to the deep link", () => {
  const view = { nudges: [n("o", "obs_overdue", "nurse", 1), n("a", "obs_past_limit", "nurse", 2)] };
  assert.deepEqual(bannerAlerts(view, "nurse", null).map((x) => [x.nudge.id, x.safety, x.canAnswer]), [["a", true, true], ["o", false, true]]);
  assert.deepEqual(bannerAlerts(view, "doctor", null).map((x) => x.canAnswer), [false, false]);
  assert.deepEqual(bannerAlerts(view, "doctor", "a").map((x) => x.canAnswer), [true, false]);
});
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd count-guard/frontend && node --test 'src/care/*.test.js'`
Expected: FAIL with a missing-module error for `./alerts.js`, and on the new `name` assertion.

- [ ] **Step 3: Implement `alerts.js`, then the `name` field in `waitingPills`.**

- [ ] **Step 4: Wire the screens.**
  1. In `Strip`, read the chart id with `useMatch("/chart/:episodeId")?.params.episodeId`. Render `stripPills(...)` and print `pill.text` plus the waited suffix.
  2. In `Chart`, render `<StateHeader … alert={alertNow(view)} />`, then `<AlertBanner view role line busy act />`, then `StatePanel`.
  3. Make `Timeline` show every open nudge as a plain line. Keep the existing filter rule: a nudge for the current role, or the deep-linked one, shows in any lens.
  4. Remove the duplicate answer surfaces in `NurseActions`, `TheatrePanel` and `DoctorActions` listed under Files.
  5. Add CSS: `.alert-banner` uses the existing `--record` and `--record-soft` tokens with a 2px border. `.alert-safety` uses the red border on each safety item.

- [ ] **Step 5: Update the beats that read NOW while Iyer's BP alert is open.** From `iyer-bp` to `iyer-recheck`, NOW reads "Waiting for the nurse's answer: Systolic BP 82 …". The NOW lines "began …" and "finished …" are therefore no longer on screen. The chart's task line `<span>{title}</span> <span className="pill">{status}</span>` carries the same fact.
  - In `beats.mjs`, change `iyer-setup` expect `` `began ${SALINE}` `` to `` `${SALINE} running` ``.
  - In `beats.mjs`, change `iyer-end` expect `` `finished ${SALINE}` `` to `` `${SALINE} done` ``.
  - In `beats.test.mjs:79-80`, change the two ruling assertions to match.
  - In the doc, change the `iyer-setup` and `iyer-end` "On screen:" lines to the same strings. Keep the `say` lines unchanged.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd count-guard/frontend && node --test 'src/care/*.test.js' && node --test 'scripts/demo/*.test.mjs' && npm run build`
Expected: all pass. `iyer-recheck`'s `absent` ("→ Systolic BP 82 is below the limit of 90") still works. On Iyer's own chart the pill has no name prefix, and the alert is answered by then.

- [ ] **Step 7: Commit**

```bash
git add count-guard/frontend/src/care/{alerts.js,alerts.test.js,AlertBanner.jsx,derive.js,derive.test.js,CareShell.jsx,StateHeader.jsx,Chart.jsx,Timeline.jsx,MyCare.jsx,NurseActions.jsx,TheatrePanel.jsx,DoctorActions.jsx} count-guard/frontend/src/styles.css count-guard/frontend/scripts/demo/beats.mjs count-guard/frontend/scripts/demo/beats.test.mjs docs/demo/count-guard-v2-video-script.md
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: alerts name their patient; open alerts on top of the chart, answered once"
```

---

### Task 3: One task list, patient task wording, ward tasks pause in theatre (C4, C5, C8)

**Files:**
- Create: `count-guard/frontend/src/care/OrderTasks.jsx` (the staff "Orders and tasks" card, moved out of `Chart.jsx:74-108`)
- Modify: `count-guard/frontend/src/care/derive.js:32-39` (`taskDue` gains `state`; add `dueLabel`)
- Modify: `count-guard/frontend/src/care/tasklist.js` (add `orderLines`, `patientTaskStatus`; add `paused` to `ORDER`)
- Modify: `count-guard/frontend/src/care/clock.js` (add `hhmm`)
- Modify: `count-guard/frontend/src/care/Chart.jsx`, `count-guard/frontend/src/care/MyCare.jsx:24-50`
- Modify: `count-guard/backend/app/journey/nudges.py:88-147` (due checks held while in theatre)
- Test: `count-guard/frontend/src/care/tasklist.test.js`, `count-guard/frontend/src/care/derive.test.js`, `count-guard/frontend/src/care/clock.test.js`, `count-guard/backend/tests/test_clarity_pause.py` (create)

**Interfaces:**
- Produces: `taskDue(task, nowMs, state?)`. It returns `"paused"` when `state === "theatre"` and the task is open. Closed, done and running keep their words.
- Produces: `dueLabel(due) -> string`. It maps `"paused"` to `"paused (in theatre)"`; every other value prints as itself.
- Produces: `hhmm(ms) -> "HH:MM"`, which is `label(ms).slice(-5)`.
- Produces: `orderLines(order, tasks) -> [{ key: string, text: string, task: object | null }]`. There is one line per order item. Each item is matched to a task of the same `order_id` whose `title === item.text`, and each task is used once. A task left unmatched is appended.
- Produces: `patientTaskStatus(task, state) -> string`. It never returns "To do".
- Keeps: the staff task line markup `<span>{task.title}</span> <span className="pill …">{dueLabel(due)}</span>`. Task 2's beats `` `${SALINE} running` `` and `` `${SALINE} done` `` read it.

- [ ] **Step 1: Write the failing tests** (use the existing `t()` helper and `NOW = 10 * 60 * M` in `tasklist.test.js`)

```js
// tasklist.test.js
test("orderLines shows each item once and an item with no task without one", () => {
  const order = { id: "o1", items: [{ text: "Paracetamol 1 g every 6 h" }, { text: "Check wound" }] };
  const tasks = [{ id: "t1", order_id: "o1", title: "Paracetamol 1 g every 6 h" }, { id: "t9", order_id: "o2", title: "Check wound" }];
  assert.deepEqual(orderLines(order, tasks).map((l) => [l.text, l.task?.id ?? null]), [["Paracetamol 1 g every 6 h", "t1"], ["Check wound", null]]);
});
test("patientTaskStatus", () => {
  const at = (h, m = 0) => (h - 9) * 60 * M + m * M; // Day 0 clock
  const dose = { kind: "dose", every_h: 6, status: "open", due_ms: at(16), done: [{ at_ms: at(10) }] };
  assert.equal(patientTaskStatus(dose, "ward"), "Given 10:00 · next due 16:00");
  assert.equal(patientTaskStatus({ ...dose, kind: "obs", due_ms: at(11) }, "ward"), "Done 10:00 · next due 11:00");
  assert.equal(patientTaskStatus({ kind: "obs", every_h: 1, status: "open", due_ms: at(10), done: [] }, "ward"), "Due 10:00");
  assert.equal(patientTaskStatus({ ...dose, status: "closed", due_ms: null }, "home"), "Finished");
  assert.equal(patientTaskStatus({ kind: "check", every_h: null, status: "done", due_ms: null, done: [{ at_ms: at(10, 5) }] }, "ward"), "Done 10:05");
  assert.equal(patientTaskStatus({ ...dose, status: "running" }, "ward"), "Running");
  assert.equal(patientTaskStatus(dose, "theatre"), "Paused (in theatre)");
});
// derive.test.js
test("ward tasks pause in theatre", () => {
  const task = { status: "open", due_ms: 0 };
  assert.equal(taskDue(task, 2 * H, "theatre"), "paused");
  assert.equal(taskDue(task, 2 * H, "ward"), "overdue");
  assert.equal(taskDue({ status: "done" }, 2 * H, "theatre"), "done");
  assert.equal(dueLabel("paused"), "paused (in theatre)");
  assert.equal(dueLabel("due"), "due");
});
// clock.test.js
test("hhmm", () => assert.equal(hhmm(H + 5 * M), "10:05"));
```

```python
# backend/tests/test_clarity_pause.py
from tests.test_flow_states import _move, _new, _surgery, _to_ward
from tests.test_flow_tasks import DOSE, H, _ack, _sign

def _kinds(view):
    return {n["kind"] for n in view["nudges"]}

def test_due_nudges_pause_in_theatre_and_resume(tmp_path):
    client, eid = _new(tmp_path)
    _to_ward(client, eid)
    order = _sign(client, eid, [DOSE]).json()["order_list"][0]
    _ack(client, eid, order["id"])
    assert _move(client, eid, "theatre", procedure="hernia-repair").status_code == 200
    tick = lambda at: client.post(f"/journey/episodes/{eid}/tick", json={"at_ms": at}).json()
    assert "dose_overdue" not in _kinds(tick(7 * H))
    _surgery(client, eid, "began"); _surgery(client, eid, "ended")
    assert _move(client, eid, "ward", by="Nurse Asha (synthetic)", reason="", checklist={}, at_ms=7 * H + 1000).status_code == 200
    assert "dose_overdue" in _kinds(tick(7 * H + 2000))
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd count-guard && .venv/bin/python -m pytest backend/tests/test_clarity_pause.py -q; cd frontend && node --test 'src/care/*.test.js'`
Expected: the backend test fails at the first `dose_overdue` assert. The node tests fail with missing exports.

- [ ] **Step 3: Implement the backend pause.** In `nudges.py`, add `_in_theatre(events) -> bool`, which is true when the latest `patient.state` event's `to` is `"theatre"`. Write it locally: `states.py` imports `nudges.py`, so importing `current_state` back would be circular. Skip the `dose_overdue` block in `doses_vs_orders` while it is true. Skip the `obs_overdue` block in `obs_vs_limits` while it is true. Limit checks, early doses and unordered doses still run. Due times are not shifted: after the return, the normal rule applies.

- [ ] **Step 4: Implement the frontend helpers.**
  - Add `taskDue`'s `state` parameter and `dueLabel` in `derive.js`.
  - Add `paused: 3` to `ORDER` in `tasklist.js`.
  - Add `orderLines` and `patientTaskStatus` in `tasklist.js`. `patientTaskStatus` checks in this order: closed → "Finished"; theatre and open → "Paused (in theatre)"; running → "Running"; done → `Done ${hhmm(last)}`; repeating and done before → `${kind === "dose" ? "Given" : "Done"} ${hhmm(last)} · next due ${hhmm(due)}`; otherwise `Due ${hhmm(due)}`, or "" when there is no due time.
  - Keep `TASK_STATUS_LABEL` and `taskStatusLabel`; their existing tests still cover them.

- [ ] **Step 5: Render.**
  - `OrderTasks({ orders, tasks, photos, nowMs, state })` keeps the order header from `Chart.jsx:79-82`. It renders `orderLines`: a task line with `dueLabel(taskDue(task, nowMs, state))`, the video label and the last "Done by …" proof (unchanged from `Chart.jsx:90-101`), or the bare item text when there is no task. Delete the duplicate item list at `Chart.jsx:83-85`.
  - `MyCare` uses `orderLines` the same way. The pill shows `patientTaskStatus(task, view.state)`, and is left out when that is "". The "Done by … at …, by voice" lines stay, because `kumar-mycare` expects ", by voice" and "Photo matches the task".

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd count-guard && .venv/bin/python -m pytest backend/tests -q && cd frontend && node --test 'src/care/*.test.js' && node --test 'scripts/demo/*.test.mjs' && npm run build`
Expected: all pass. No beat strings change.

- [ ] **Step 7: Commit**

```bash
git add count-guard/frontend/src/care/{OrderTasks.jsx,derive.js,derive.test.js,tasklist.js,tasklist.test.js,clock.js,clock.test.js,Chart.jsx,MyCare.jsx} count-guard/backend/app/journey/nudges.py count-guard/backend/tests/test_clarity_pause.py
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: one line per task, patient task wording, ward tasks paused in theatre"
```

---

### Task 4: The doctor's action bar (C3)

**Files:**
- Create: `count-guard/frontend/src/care/actions.js`, `count-guard/frontend/src/care/actions.test.js`, `count-guard/frontend/src/care/ActionBar.jsx`
- Modify: `count-guard/frontend/src/care/DoctorActions.jsx` (about 211 lines now, about 245 after; `ReferencePhoto` becomes a labelled card)
- Modify: `count-guard/frontend/src/care/StatePanel.jsx:8` (`key={state}` on `DoctorActions`, so the chosen panels reset on a state move)
- Modify: `count-guard/frontend/src/styles.css` (`.action-bar`)
- Modify: `count-guard/frontend/scripts/demo/helpers.mjs` (add `open`), `count-guard/frontend/scripts/demo/steps.mjs` (`kumar-orders`, `kumar-discharge`, `iyer-orders`, `iyer-discharge`), `count-guard/frontend/scripts/demo/beats.mjs` (the same four beats' `clicks`), `docs/demo/count-guard-v2-video-script.md` (their "Clicks:" lines)

**Interfaces:**
- Produces in `actions.js`:
  - `ACTIONS = { clinic: [["orders", "Dictate orders"], ["photo", "Reference photo"]], ward: [["orders", "Dictate orders"], ["photo", "Wound photo"], ["discharge", "Dictate discharge"]] }`
  - `actionsFor(state) -> [id, label][]` returns `[]` for theatre, admitting and every other state.
  - `toggled(set: Set, id) -> Set` returns a new set.
  - `panelOpen(chosen: Set, id, view) -> boolean` is `chosen.has(id)`, or true when an open draft exists for that panel (`orders` with `view.drafts.order`, `discharge` with `view.drafts.discharge`). A dictated draft is never hidden.
- Produces: `<ActionBar actions isOpen onToggle />`. It is a `role="group"` with `aria-label="Doctor actions"`. Each button carries `aria-expanded`.
- Produces (demo): `H.open(name)` clicks the named button only when its `aria-expanded` is not `"true"`.

- [ ] **Step 1: Write the failing tests** in `actions.test.js`

```js
test("actionsFor", () => {
  assert.deepEqual(actionsFor("clinic").map(([, l]) => l), ["Dictate orders", "Reference photo"]);
  assert.deepEqual(actionsFor("ward").map(([, l]) => l), ["Dictate orders", "Wound photo", "Dictate discharge"]);
  assert.deepEqual(actionsFor("theatre"), []);
});
test("panels stay closed until chosen; a draft opens its panel", () => {
  const none = new Set();
  assert.equal(panelOpen(none, "orders", { drafts: {} }), false);
  assert.equal(panelOpen(toggled(none, "photo"), "photo", {}), true);
  assert.equal(panelOpen(toggled(toggled(none, "photo"), "photo"), "photo", {}), false);
  assert.equal(panelOpen(none, "orders", { drafts: { order: { id: "d1" } } }), true);
  assert.equal(panelOpen(none, "discharge", { drafts: { discharge: { id: "d2" } } }), true);
  assert.equal(none.size, 0);
});
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd count-guard/frontend && node --test src/care/actions.test.js`
Expected: FAIL with a missing-module error.

- [ ] **Step 3: Implement `actions.js` and `ActionBar.jsx`.**

- [ ] **Step 4: Rework `DoctorActions`.**
  - Keep one `chosen` state at the top of `DoctorActions`. Render `<ActionBar>` first.
  - Render the chosen panels directly under the bar.
  - Clinic panels: "orders" holds `OrdersDictation`; "photo" holds the photo card titled "Reference photo".
  - Ward panels: "orders" holds `OrdersDictation`; "photo" holds the photo card titled "Wound photo"; "discharge" holds `Dictate discharge` plus the Discharge card (Summary, Template, Sign discharge).
  - These stay always visible: Prescription, Check strips and Visit (Admit / Close visit) in clinic, and the Theatre card (Send to theatre) in ward. Admitting and theatre keep today's content.
  - The photo card is `<section className="card" aria-label={title}>` with `<p className="label">{title}</p>` and the existing labelled input "Add reference photo". Keep that label: `kumar-discharge` uploads through it.

- [ ] **Step 5: Update the demo.** Add `open: async (name) => { … }` to `helpers.mjs`. Add one `H.open(...)` per step, before the control it reveals:

| Beat | Inserted step (step and `clicks` text) | Before |
|---|---|---|
| `kumar-orders` | `H.open("Dictate orders")` / `'Button "Dictate orders"'` | the file into "Dictate orders" |
| `kumar-discharge` | `H.open("Wound photo")` / `'Button "Wound photo"'` | "Add reference photo" |
| `kumar-discharge` | `H.open("Dictate discharge")` / `'Button "Dictate discharge"'` | the file into "Dictate discharge" |
| `iyer-orders` | `H.open("Dictate orders")` / `'Button "Dictate orders"'` | the file into "Dictate orders" |
| `iyer-discharge` | `H.open("Dictate discharge")` / `'Button "Dictate discharge"'` | Field "Summary" |

Then renumber those four beats' "Clicks:" lines in the doc. No `expect` or `say` changes.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `cd count-guard/frontend && node --test 'src/care/*.test.js' && node --test 'scripts/demo/*.test.mjs' && npm run build`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add count-guard/frontend/src/care/{actions.js,actions.test.js,ActionBar.jsx,DoctorActions.jsx,StatePanel.jsx} count-guard/frontend/src/styles.css count-guard/frontend/scripts/demo/{helpers.mjs,steps.mjs,beats.mjs} docs/demo/count-guard-v2-video-script.md
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: doctor action bar; panels open in place; photo control in a labelled card"
```

---

### Task 5: Checks in patient words; theatre steps numbered and shown once (C6 checks, C7)

**Files:**
- Modify: `count-guard/frontend/src/care/video.js` (add `shownChecks`, `patientCheckLine`)
- Modify: `count-guard/frontend/src/care/VideoChecks.jsx` (props `hideTray`, `patient`)
- Modify: `count-guard/frontend/src/care/VideoCheck.jsx:6,18` (optional `step` prop, shown before the title; `aria-label` stays `title`)
- Modify: `count-guard/frontend/src/care/NurseActions.jsx:96-137` (`Theatre` reordered and numbered)
- Modify: `count-guard/frontend/src/care/TheatrePanel.jsx:50` (optional `step` prop on the "Swab count" label)
- Modify: `count-guard/frontend/src/care/Chart.jsx` (`<VideoChecks view hideTray={view.state === "theatre" && ward.role === "nurse"} />`), `count-guard/frontend/src/care/MyCare.jsx` (`<VideoChecks view patient />`; the task's video line uses `patientCheckLine`)
- Test: `count-guard/frontend/src/care/video.test.js`

**Interfaces:**
- Produces: `shownChecks(checks, { hideTray = false, patient = false }) -> checks`. It drops `check === "tray"` when either flag is set.
- Produces: `patientCheckLine(check) -> string`. The source word is "a video", or "photos" when `check.media === "photos"`:
  - `ok`: `Checked from ${source}: everything planned was seen.`
  - `mismatch`: `Checked from ${source}: something planned was not seen; the nurse was told.`
  - any other value: `${Source} was kept; it was not checked.`

- [ ] **Step 1: Write the failing tests** in `video.test.js`

```js
test("shownChecks hides tray checks from the patient and from the nurse's theatre screen", () => {
  const checks = [{ id: "a", check: "tray" }, { id: "b", check: "setup" }];
  assert.deepEqual(shownChecks(checks, {}).map((c) => c.id), ["a", "b"]);
  assert.deepEqual(shownChecks(checks, { patient: true }).map((c) => c.id), ["b"]);
  assert.deepEqual(shownChecks(checks, { hideTray: true }).map((c) => c.id), ["b"]);
});
test("patientCheckLine", () => {
  assert.equal(patientCheckLine({ check: "setup", match: "ok" }), "Checked from a video: everything planned was seen.");
  assert.equal(patientCheckLine({ check: "setup", match: "mismatch" }), "Checked from a video: something planned was not seen; the nurse was told.");
  assert.equal(patientCheckLine({ check: "setup", match: "ok", media: "photos" }), "Checked from photos: everything planned was seen.");
  assert.equal(patientCheckLine({ check: "setup", match: null }), "A video was kept; it was not checked.");
});
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `cd count-guard/frontend && node --test src/care/video.test.js`
Expected: FAIL because `shownChecks` is not exported.

- [ ] **Step 3: Implement both helpers and the `VideoChecks` props.** With `patient`, each check prints `patientCheckLine(c)` in place of the staff label, by-line and source. The section label is "Checks from a video". Frames stay. When `shownChecks` returns nothing, render nothing.

- [ ] **Step 4: Number the nurse's theatre screen.** Use this card order. The labels show the number; button names, field labels and `aria-label`s do not change, because the steps find controls by them:
  1. `VideoCheck` with step "①" and title "Tray check". The upload stays hidden once surgery began.
  2. A card labelled "② Surgery began" holding the "Surgery began" button and the began time.
  3. `TheatrePanel` with step "③" and the "Swab count" card.
  4. A card labelled "④ Surgery ended" holding the "Surgery ended" button, then "Back to ward" (or the surgeon's count note).

  The doctor's theatre card is unchanged.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `cd count-guard/frontend && node --test 'src/care/*.test.js' && node --test 'scripts/demo/*.test.mjs' && npm run build`
Expected: all pass. `kumar-tray` still finds `region "Tray check"`, and its expects ("Flagged: …", "needle holder", "2 (missing)", "Prepared demo result") still come from the ① card.

- [ ] **Step 6: Commit**

```bash
git add count-guard/frontend/src/care/{video.js,video.test.js,VideoChecks.jsx,VideoCheck.jsx,NurseActions.jsx,TheatrePanel.jsx,Chart.jsx,MyCare.jsx}
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: checks in patient words, tray hidden from the patient; theatre steps numbered, tray result once"
```

---

### Task 6: Clock steps per action; queue alignment; fixed role switch (C9, C10 table, C11)

**Files:**
- Modify: `count-guard/frontend/src/care/clock.js` (add `STEP_MS`, `afterAction`), `count-guard/frontend/src/care/clock.test.js`
- Modify: `count-guard/frontend/src/care/ward.js:133-146` (`run` moves the clock after a recorded action)
- Modify: `count-guard/frontend/src/care/Queue.jsx:59,18` (Patient column class `left`)
- Modify: `count-guard/frontend/src/care/CareShell.jsx:113-122` (header controls)
- Modify: `count-guard/frontend/src/styles.css` (`th.left, td.left`, `.header-controls`, `.picker-slot`)

**Interfaces:**
- Produces: `STEP_MS = 2 * M` and `afterAction(nowMs) -> nowMs + STEP_MS`.
- Behaviour: `act` and `upload` stamp the action at the current `nowMs`. On success, the clock moves to `afterAction(nowMs)`, and the new value is saved under `cg-ward-now`. `ask` (a proposal, not a record) and `jump` do not step. Stepping posts no `/tick`: the next action raises nudges at its own `at_ms`.

- [ ] **Step 1: Write the failing test**

```js
test("each recorded action moves the clock 2 minutes", () => {
  assert.equal(STEP_MS, 2 * M);
  assert.equal(afterAction(0), 2 * M);
  assert.equal(label(afterAction(afterAction(0))), "Day 0 09:04");
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd count-guard/frontend && node --test src/care/clock.test.js`
Expected: FAIL because `STEP_MS` is undefined.

- [ ] **Step 3: Implement.**
  - In `run`, after `swap(id, next)`, call `setNowMs((ms) => { const n = afterAction(ms); write(NOW, String(n)); return n; })`.
  - In `Queue`, put `className="left"` on the Patient `<th>` and `<td>`.
  - In `CareShell`, wrap the controls in `<div className="header-controls">`. It holds `<div className="picker-slot">` (the patient `<select>` for the patient role, empty otherwise), then the unchanged `role-switch`.
  - CSS: `.header-controls { display: flex; align-items: center; gap: 12px; margin-left: auto; flex-wrap: nowrap; }` and `.picker-slot { width: 240px; display: flex; justify-content: flex-end; }` with `select { max-width: 100%; }`. Inside the existing 640px media block, let `.header-controls` wrap and give `.picker-slot` width auto.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `cd count-guard/frontend && node --test 'src/care/*.test.js' && npm run build`
Expected: all pass.

- [ ] **Step 5: Check the layout.** Run `cd count-guard && make demo-check MODEL_API_KEY=`. In `demo-shots/`, open `01-intro.png` (doctor), `05-das-ask.png` (patient) and `09-kumar-admission.png` (nurse). The role switch has the same right edge and top in all three.

The run may fail on clock drift (see Task 7). That does not block this commit if the unit tests and build pass. Record the failing beat for Task 7.

- [ ] **Step 6: Commit**

```bash
git add count-guard/frontend/src/care/{clock.js,clock.test.js,ward.js,Queue.jsx,CareShell.jsx} count-guard/frontend/src/styles.css
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: each action moves the demo clock 2 min; queue Patient column left; role switch fixed"
```

---

### Task 7: Full demo check and drift fixes

**Files:**
- Modify (only as the run requires): `count-guard/frontend/scripts/demo/beats.mjs`, `count-guard/frontend/scripts/demo/steps.mjs`, `count-guard/frontend/scripts/demo/beats.test.mjs`, `docs/demo/count-guard-v2-video-script.md`

**Interfaces:**
- Consumes: everything above. No new names.

Known risk from C9: about 40 recorded actions now add about 80 minutes before the Iyer path. Iyer's seeded hourly round was due at Day 0 10:00. Her `obs_overdue` nudge (non-safety) will now be open at `iyer-bp`, and her task line will read overdue. Neither is in any `expect`. `kumar-free-soon` stays safe: the hernia template is 31 minutes (`backend/app/journey/sample_data/hernia-repair.json:4`), and the check jumps 1 h.

- [ ] **Step 1: Run every suite**

Run: `cd count-guard && .venv/bin/python -m pytest backend/tests -q && cd frontend && node --test 'src/care/*.test.js' && node --test 'scripts/demo/*.test.mjs' && npm run build`
Expected: all pass. Backend has at least 345 + 5 tests and care at least 91 + 13.

- [ ] **Step 2: Run the demo check**

Run: `cd count-guard && make demo-check MODEL_API_KEY=`
Expected: `DEMO CHECK PASSED: 31 beats; …`

- [ ] **Step 3: On a failure, fix the text, not the app.**
  1. Read the `DEMO CHECK FAILED at beat NN <id>` line and `demo-shots/NN-<id>-FAIL.png`.
  2. If the screen is right and the beat's string is stale, change that `expect` or `before` string in `beats.mjs`.
  3. Change the same string on the doc's "On screen:" line.
  4. If the string is pinned there, change it in `beats.test.mjs` too.
  5. If a control moved, fix the step in `steps.mjs` and the beat's `clicks`, plus the doc's "Clicks:" line.
  6. Keep every `say` line unless its wording is now false on screen. In that case, change it in both `beats.mjs` and the doc.
  7. Repeat with `CG_DEMO_UNTIL=<next beat id>`, then the full run, until it passes.

  A failure that shows a real bug goes back to the owning task's files, with a test.

- [ ] **Step 4: Check the screens by eye.** Look at these screenshots in `demo-shots/`:
  - `02-das-rx.png`: the strip has no other patient's alerts.
  - `14-kumar-count.png`: the red banner sits under the header, and NOW reads "Waiting for the nurse's answer: …".
  - `16-kumar-mycare.png`: the status reads "Given …" with no "To do".
  - `13-kumar-tray.png`: the cards are numbered ①–④, with one tray result.
  - `23-iyer-bp.png`: NOW names the nurse's answer.

  Check the word scan: `cd count-guard/frontend && node --test scripts/demo/doc.test.mjs` passes "narration passes the no-advice regex".

- [ ] **Step 5: Commit**

```bash
git add count-guard/frontend/scripts/demo docs/demo/count-guard-v2-video-script.md
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard v2 clarity: demo check green with the clarity pass; beat and script text follow the screen"
```

If nothing changed, skip the commit and record "demo check green, no drift" in the hand-off.

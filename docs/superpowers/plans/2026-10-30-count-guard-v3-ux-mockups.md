# Count Guard v3 UX Mockups (M1–M7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task stands alone: read its Files, Interfaces and Rulings before you start.

**Goal:** Build the seven mockups M1–M7 of the v3 UX review. Every chart gets one "do this now" card, demo-only controls move into one dock, and each fact appears once. The 31-beat demo check stays green after every task.

**Architecture:** The backend adds four read-only fields to the episode view: `visited`, `now_next.next_role`, and `count`. The frontend puts every decision in pure, tested helpers (`journey.js`, `names.js`, `today.js`, `patients.js`, `dock.js`, plus additions to `tasklist.js`, `drafts.js`, `theatre.js`, `askText.js`). JSX components only render what those helpers return. `ward.js` strips "(synthetic)" from every name and sentence in one place, using `displayView()`.

**Tech Stack:** FastAPI + pytest (backend). React 18 + Vite + react-router (frontend). `node --test` for care and demo tests. A playwright-core demo runner.

**Spec (binding):** `docs/superpowers/specs/2026-10-30-count-guard-v3-ux-mockups-design.md`

All paths are relative to `count-guard/` unless they start with `docs/`. The demo document is `docs/demo/count-guard-v2-video-script.md` at the repo root. Its per-beat block has a `Clicks:` line (numbered, mirrors `clicks`) and an `On screen:` line (backticked, mirrors `expect`). `frontend/scripts/demo/doc.test.mjs` checks that the document matches.

## Global Constraints

Copied verbatim from the spec:

- `make demo-check MODEL_API_KEY=` stays green: 31 beats, 58/58/58 s. Selectors, beats, steps and `docs/demo/count-guard-v2-video-script.md` change together.
- Backend, care and demo node tests stay green. Every behaviour change gets a test.
- The no-advice regex applies to all new copy. Files stay under 500 lines.
- Never call live models in tests. Never touch ports 8100/5173.
- Keep accessible names the demo relies on, or update the demo to match.

House rules for this plan:
- The no-advice regex is `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i` (`frontend/scripts/demo/beats.mjs:3`, `backend/tests/test_flow_states.py:9`).
- Test baselines on `count-guard-v3` at `34f385e`: backend 380, care 143, demo 36. Each task states its expected new counts as "at least".
- Commit with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Add no Co-Authored-By line. Never push.

Commands (run from `count-guard/`; the venv is `count-guard/.venv`, see `Makefile:1`):
- Backend: `.venv/bin/python -m pytest backend/tests -q`
- Care: `cd frontend && node --test src/care/*.test.js`
- Demo unit tests: `cd frontend && node --test scripts/demo/*.test.mjs`
- Build: `cd frontend && npm run build`
- Full demo: `make demo-check MODEL_API_KEY=`. It starts its own servers on 8200/5273. Use `CG_DEMO_UNTIL=<beat id>` to stop before a beat while you debug.

How the demo checks text: `waitText` reads `document.querySelector(".app").innerText` (`frontend/scripts/demo/helpers.mjs:6`). Text inside a closed `<details>` or a `display:none` node is **not** in `innerText`. So any expected string must stay visible after a fold is added. Each task below names the strings it moves.

## Rulings on spec ambiguities

These rulings bind all tasks.

| # | Question | Ruling |
|---|---|---|
| R1 | "Start check-in" (M6) and "Give early" (M2) fail the no-advice regex (`start`, `give`). | Use "Open check-in" and "Given early". "Given" does not match `\bgive\b`. |
| R2 | A patient who never went to theatre is discharging or home. Is Theatre "done"? | No. The status is `"skipped"`: muted, with no ✓. |
| R3 | Who owns NEXT? | The backend returns `now_next.next_role`. It always names the subject of the NEXT sentence (`"doctor"`, `"nurse"` or `null`). The frontend never parses the sentence. |
| R4 | NEXT with no owner (clinic_done, home with nothing open) | The eyebrow is "Next", with no "for …". The card has no buttons and no waiting line. |
| R5 | "Last: <NOW sentence>" while a safety alert is open | Last always shows the server's NOW sentence (`now`, or `you_now` on patient pages). The alert stays in `AlertBanner` only. |
| R6 | The state badge ("On the ward") duplicates the journey bar, but 7 beats expect those words. | The badge goes. The current journey step shows `STATE_LABEL[state]` as a small second line (`detail`). |
| R7 | The history fold has "last 3 events". | The last 3 lines **after** the lens filter. A `?line=` deep link to a hidden line opens the fold. |
| R8 | "4 min late" versus the 30-min overdue grace (`derive.js:36`) | Lateness counts from the due time. An overdue row reads at least "31 min late"; "due now" covers the grace window. From 60 min it reads "1 h 4 min late". |
| R9 | The per-row 🎙 flow | The row mic opens a `Dictate` inside the row, with verb "Use this". The text goes to `/dictate/task`. The confirm panel ("Confirm task") then opens **for that row's task**, with no radio choice. `via` comes from `answerHow` (voice only while the box still holds what was heard). |
| R10 | Done tasks leave the list (two groups only). Where do "by voice" and the photo match show for the nurse? | Each row shows its last completion as one muted line: "Last done HH:MM by <name>, by voice · Photo matches the task". |
| R11 | Theatre "current = first not-done step" would hide "Correct the count" once a closing count exists. | A done step that needs attention has status `"open"`: a count with missing > 0. It stays expanded and does not block the next step. |
| R12 | Done steps take one line, but the tray flag detail is needed by the surgeon (and by beat `kumar-tray`). | A **flagged** tray step keeps its result table under its one line. The swab-count note ("Correction recorded.") moves up to the checklist, so it survives the step collapsing. |
| R13 | No tray planned | The tray step is done, with the line "No tray planned". |
| R14 | M5 for the nurse | The nurse keeps "My queue" and "Patients" unchanged. Only the doctor gets the single "My patients" tab. For the doctor, `/queue` and `/patients` render the same list; for the nurse they stay as they are. |
| R15 | M5 doctor chip | The product bar keeps `DoctorChip` for every role (beats `kumar-theatre`, `kumar-free-soon` and `close` read it). The "Available ▾" menu on My patients is the control. |
| R16 | M6 "Ask Dr. Rao" fold content | It is read-only: the doctor's answered questions, plus a link "Ask a question →" to `/ask`. No second ask form. |
| R17 | M6 "Check my strips" | It becomes a fourth fold. An empty "My medicines" moves to the end of the folds. |
| R18 | M6 "day N" | The demo-clock day (`Day 0` = the day the stay starts). Day 0 reads "You are home", with no day. |
| R19 | M6 next item when the server says "No further steps." | `Next: <card.review, first letter lower-cased>`. Otherwise `Next: <you_next, first letter lower-cased>`. |
| R20 | M7 scope of "(synthetic)" removal | `displayView()` strips it from every string in each patient object in `ward.js`, including names, `by` fields and server sentences. The audit table (Everyone lens, fetched separately) keeps the raw record. |
| R21 | M7 alerts pill | The strip is collapsed by default. The pill `N alerts` (`aria-expanded`) toggles it, and is hidden at 0. |
| R22 | M4 order | Open items come first, oldest first. Then answered items, oldest first. |
| R23 | M4 "Day N" on the healing photo | The demo-clock day of the photo (`label(at_ms)` → "Day 0"). |
| R24 | M1 doctor in theatre | The theatre checklist renders **under** the card for the doctor, with the surgeon's buttons (the card's owner is the nurse). For the nurse it renders **inside** the card. |
| R25 | M1 clinic tools | The Prescription and Check strips cards stay as cards below the quiet row. They are clinic tools, not NEXT actions. |

## Review Focus

| # | Input or failure mode | Pinned by |
|---|---|---|
| 1 | A patient who went to theatre and returned to the ward: Theatre must read done, not later. A second theatre stay must not show the first stay's swab count. | Task 1 `test_visited_keeps_theatre_after_return` and `test_count_is_per_theatre_stay`; Task 2 `journeySteps` "returned from theatre" test |
| 2 | `clinic_done`: Clinic current with "Visit closed", `next_role` null, no buttons, eyebrow "Next". | Task 1 `test_next_role_follows_the_next_sentence`; Task 2 "closed visit" and "no owner" tests |
| 3 | Empty lists: no tasks, an empty prescription, an empty inbox. Groups are empty and render their empty line. "My medicines" is never first. | Task 4 `taskGroups([])`; Task 6 `inboxItems` empty; Task 8 `todayFolds` empty schedule |
| 4 | 390 px wide: the dock folds to one line, the help bar fits, and nothing scrolls sideways. | Task 9 `dockSummary` test and `styles.test.js` dock rule; Task 10 sweep at 390 px |
| 5 | A role with no next action: the nurse on a ward where NEXT is the doctor's, and the doctor while discharging. The card shows "Waiting for the …" and **no** buttons. | Task 2 `nextCard` "someone else's step" test; Task 3 demo `kumar-admit` (the doctor sees the nurse's step) |

---

### Task 1: Backend view fields: visited, next_role, count (M1, M3 data)

**Files:**
- Modify: `backend/app/journey/states.py` (add after `current_state` at `:73`; `_next_step` `:253-273`; `now_next` `:276-285`; `flow_view` `:288-310`)
- Test: `backend/tests/test_flow_states.py` (append)

**Interfaces:**
- Produces `journey_path(events) -> list[str]`. It is `["clinic"]` plus `payload["to"]` of every `patient.state` event, in order. The seeded Iyer gives `["clinic", "ward"]`.
- Produces `next_role(events, state) -> str | None`. It uses the same branches as `_next_step`:
  - Base values are `{"clinic": "doctor", "clinic_done": None, "admitting": "nurse", "ward": "doctor", "theatre": "nurse", "discharging": "nurse", "home": None}`.
  - Unacknowledged orders in `ward` or `admitting` give `"nurse"`.
  - The theatre tray branch gives `"nurse"`.
  - In `PHOTO_STATES`, an open review or question gives `"doctor"`.
- Produces `theatre_count(events) -> dict`. It returns `{"opened": int|None, "opened_by": str|None, "opened_at_ms": int|None, "returned": int|None, "missing": int|None}`. It reads the latest `count.pack_opened` (`quantity`) and the latest `count.closing` (`returned`, `unaccounted`). It uses `visible_events(events)`, so a correction replaces the closing it supersedes. It only reads events after the last `patient.state`, the same rule as `surgery_status` (`:85-92`).
- `now_next()` adds `"next_role"`. `flow_view()` adds `"visited": journey_path(events)` and `"count": theatre_count(events)`.

- [ ] **Step 1: Capture the before shots.** Run `make demo-check MODEL_API_KEY=`. Copy `count-guard/demo-shots/` to `$TMPDIR/cg-v3-before-shots/` (not committed). Task 10 compares against these.

- [ ] **Step 2: Write the failing tests** (reuse `_new`, `_move`, `_view`, `_to_ward`, `_to_theatre`, `_surgery` in the file):

```python
def test_visited_keeps_theatre_after_return(tmp_path):
    client, eid = _new(tmp_path)
    assert _view(client, eid)["visited"] == ["clinic"]
    _to_theatre(client, eid)
    _surgery(client, eid, "began"); _surgery(client, eid, "ended")
    assert _move(client, eid, "ward", checklist={}).status_code == 200
    assert _view(client, eid)["visited"] == ["clinic", "admitting", "ward", "theatre", "ward"]

def test_next_role_follows_the_next_sentence(tmp_path):
    client, eid = _new(tmp_path)
    assert _view(client, eid)["now_next"]["next_role"] == "doctor"
    _move(client, eid, "admitting", reason="Hernia repair")
    assert _view(client, eid)["now_next"]["next_role"] == "nurse"
    _move(client, eid, "ward", checklist=ADMIT_CHECKS)
    assert _view(client, eid)["now_next"]["next_role"] == "doctor"
    das = client.post("/morning/episodes", json={"label": "Synthetic demo, A. Das"}).json()["id"]
    _move(client, das, "clinic_done")
    assert _view(client, das)["now_next"]["next_role"] is None

def test_count_is_per_theatre_stay(tmp_path):
    client, eid = _new(tmp_path)
    _to_theatre(client, eid)
    base, by = f"/journey/episodes/{eid}", {"by": "Nurse Asha (synthetic)", "at_ms": 0}
    assert _view(client, eid)["count"] == {"opened": None, "opened_by": None, "opened_at_ms": None, "returned": None, "missing": None}
    client.post(f"{base}/count", json={"step": "opened", "quantity": 20, **by})
    closing = client.post(f"{base}/count", json={"step": "closing", "returned": 19, **by}).json()
    count = _view(client, eid)["count"]
    assert (count["opened"], count["returned"], count["missing"], count["opened_by"]) == (20, 19, 1, "Nurse Asha (synthetic)")
    fix_id = [t for t in closing["timeline"] if t["type"] == "count.closing"][-1]["id"]
    client.post(f"{base}/count", json={"step": "closing", "returned": 20, "supersedes_id": fix_id, **by})
    assert _view(client, eid)["count"]["missing"] == 0
    _surgery(client, eid, "began"); _surgery(client, eid, "ended")
    _move(client, eid, "ward", checklist={})
    assert _view(client, eid)["count"]["opened"] is None
```

A home patient with an open review gives `next_role == "doctor"`. Put that in a fourth test, `test_next_role_is_doctor_for_an_open_photo`. Set it up the way `test_care_story.py` posts `/ask/review`.

- [ ] **Step 3: Run `.venv/bin/python -m pytest backend/tests/test_flow_states.py -q`.** Expected: FAIL (`KeyError: 'visited'`).

- [ ] **Step 4: Implement** the three functions and the view fields. `next_role` sits beside `_next_step` and repeats its conditions in the same order, so the two cannot drift. Add a one-line comment that says so.

- [ ] **Step 5: Run the full backend suite and `make demo-check MODEL_API_KEY=`.** Expected: backend ≥ 384 pass. The demo stays green, because no UI changed.

- [ ] **Step 6: Commit** (`backend/app/journey/states.py backend/tests/test_flow_states.py`). Message: "Count Guard: the view says where the patient has been, who owns the next step, and this stay's swab count".

---

### Task 2: Pure helpers for the journey bar, the next card, history and names (M1, M7 helper)

**Files:**
- Create: `frontend/src/care/journey.js`, `frontend/src/care/journey.test.js`, `frontend/src/care/names.js`, `frontend/src/care/names.test.js`
- Modify: `frontend/src/care/Timeline.jsx:1-17` (move the filter out to `lensLines`)

**Interfaces:**
- Consumes: `view.state`, `view.visited`, `view.now_next.{now,next,you_now,you_next,next_role}`, `view.order_list`, `STATE_LABEL` (`derive.js:20`), `LENSES` (`Timeline.jsx:2`).
- Produces (`names.js`):
  - `displayName(label: string | null) -> string`. It removes every `" (synthetic)"` and trims. `null` gives `""`.
  - `shortName(label) -> string`. It is `displayName(label).split(",")[0].trim()`, so `"R. Kumar, 58 M (synthetic)"` gives `"R. Kumar"`.
  - `displayView(value) -> value`. It returns a deep copy with `displayName` applied to every string, and arrays and objects mapped. Numbers, booleans and `null` pass through unchanged.
- Produces (`journey.js`):
  - `JOURNEY = [{key:"clinic",label:"Clinic",states:["clinic","clinic_done"]}, {key:"admitted",label:"Admitted",states:["admitting"]}, {key:"ward",label:"Ward",states:["ward"]}, {key:"theatre",label:"Theatre",states:["theatre"]}, {key:"discharge",label:"Discharge",states:["discharging"]}, {key:"home",label:"Home",states:["home"]}]`
  - `journeySteps(state, visited = []) -> [{ key, label, status, detail }]`. `status` is one of `"done" | "current" | "later" | "skipped"`.
    - The current step is the one whose `states` include `state`. Its `detail` is `STATE_LABEL[state]`. With `clinic_done`, its label is `"Visit closed"`.
    - A step before the current one is `"done"`, except Theatre: it is `"skipped"` when `visited` lacks `"theatre"` (R2).
    - A step after the current one is `"done"` when `visited` holds any of its states, else `"later"`. Other steps have `detail` `""`.
  - `cardActions(state, role, view) -> string[]`:
    - doctor: `clinic` → `["admit"]`; `ward` → `["theatre", "discharge"]`.
    - nurse: `admitting` → `["ack", "admission"]` when there are fresh orders, else `["admission"]`; `ward` → `["ack"]`; `theatre` → `["theatre"]`; `discharging` → `["discharge"]`.
    - Anything else gives `[]`.
  - `quietActions(state, role) -> [id, label][]`. The doctor gets: `clinic` → `[["orders","Dictate orders"],["photo","Reference photo"]]`; `ward` → `[["orders","Dictate orders"],["photo","Wound photo"]]`; `admitting` → `[["orders","Dictate orders"]]`. Everything else is `[]`. This replaces `ACTIONS`/`actionsFor` in `actions.js`; keep `toggled` and `panelOpen`.
  - `nextCard(view, role, { you = false } = {}) -> { owner, mine, eyebrow, text, waiting, last, actions }`.
    - `owner = view.now_next.next_role ?? null` and `mine = owner !== null && owner === role`.
    - `eyebrow`: `"Next · for you"` when `mine`; `` `Next · for the ${owner}` `` when there is an owner; `"Next"` otherwise (R4).
    - `text = (you ? you_next || next : next) || "Nothing queued"`.
    - `waiting = !owner || mine ? "" : `Waiting for the ${owner}.``
    - `last = `Last: ${(you ? you_now : now) || "Nothing recorded"}`` (R5).
    - `actions = mine && !you ? cardActions(view.state, role, view) : []`.
  - `lensLines(lines, nudges, lens, role, line) -> lines`. This is the filter now inside `Timeline.jsx:9-15`, moved unchanged.
  - `foldLines(lines, open, keep = 3) -> { lines, more }`. When open, it returns all lines and `more: 0`. Otherwise it returns the last `keep` lines and `more = lines.length - keep` (never below 0).
  - `foldOpensFor(lines, line) -> boolean`. True when `line` is set and is not among the last 3 ids (R7).

- [ ] **Step 1: Write the failing tests** (`journey.test.js` and `names.test.js`):

```js
const S = (steps) => steps.map((s) => s.status);
test("returned from theatre: Theatre is done while on the ward", () => {
  assert.deepEqual(S(journeySteps("ward", ["clinic", "admitting", "ward", "theatre", "ward"])), ["done", "done", "current", "done", "later", "later"]);
  assert.deepEqual(S(journeySteps("ward", ["clinic", "admitting", "ward"])), ["done", "done", "current", "later", "later", "later"]);
});
test("closed visit: Clinic is current and reads Visit closed", () => {
  const steps = journeySteps("clinic_done", ["clinic", "clinic_done"]);
  assert.deepEqual(steps[0], { key: "clinic", label: "Visit closed", status: "current", detail: "Clinic visit closed" });
  assert.deepEqual(S(steps).slice(1), ["later", "later", "later", "later", "later"]);
});
test("home without theatre: Theatre is skipped, not done", () => {
  assert.deepEqual(S(journeySteps("home", ["clinic", "admitting", "ward", "discharging", "home"])), ["done", "done", "done", "skipped", "done", "current"]);
});
const view = (state, next_role, extra = {}) => ({ state, order_list: [], now_next: { now: "N.", next: "X.", you_now: "YN.", you_next: "YX.", next_role }, ...extra });
test("my step: eyebrow for you, actions from the state", () => {
  const c = nextCard(view("ward", "doctor"), "doctor");
  assert.equal(c.eyebrow, "Next · for you");
  assert.deepEqual(c.actions, ["theatre", "discharge"]);
  assert.equal(c.waiting, "");
  assert.equal(c.last, "Last: N.");
});
test("someone else's step: no buttons, says who is waiting", () => {
  const c = nextCard(view("ward", "doctor"), "nurse");
  assert.equal(c.eyebrow, "Next · for the doctor");
  assert.deepEqual(c.actions, []);
  assert.equal(c.waiting, "Waiting for the doctor.");
});
test("no owner: plain eyebrow, nothing waiting", () => {
  const c = nextCard(view("clinic_done", null), "doctor");
  assert.equal(c.eyebrow, "Next");
  assert.deepEqual([c.actions, c.waiting], [[], ""]);
});
test("patient pages use you wording and never actions", () => {
  const c = nextCard(view("ward", "doctor"), "patient", { you: true });
  assert.deepEqual([c.text, c.last, c.actions], ["YX.", "Last: YN.", []]);
});
test("nurse acknowledges fresh orders first", () => {
  const fresh = { order_list: [{ acknowledged_by: null }] };
  assert.deepEqual(cardActions("admitting", "nurse", fresh), ["ack", "admission"]);
  assert.deepEqual(cardActions("admitting", "nurse", { order_list: [] }), ["admission"]);
});
test("history folds to the last 3 lines; a deep link opens it", () => {
  const lines = ["a", "b", "c", "d", "e"].map((id) => ({ id }));
  assert.deepEqual(foldLines(lines, false), { lines: lines.slice(2), more: 2 });
  assert.deepEqual(foldLines(lines, true), { lines, more: 0 });
  assert.equal(foldOpensFor(lines, "a"), true);
  assert.equal(foldOpensFor(lines, "e"), false);
  assert.equal(foldOpensFor(lines, null), false);
});
test("new copy has no advice words", () => {
  for (const s of ["Next · for you", "Next · for the nurse", "Waiting for the doctor.", "Visit closed", "Show full history (5)"]) assert.doesNotMatch(s, ADVICE);
});
// names.test.js
test("displayName and shortName strip the synthetic tag", () => {
  assert.equal(displayName("R. Kumar, 58 M (synthetic)"), "R. Kumar, 58 M");
  assert.equal(displayName("Nurse Acknowledges orders from Dr. A. Rao (synthetic)."), "Nurse Acknowledges orders from Dr. A. Rao.");
  assert.equal(displayName(null), "");
  assert.equal(shortName("R. Kumar, 58 M (synthetic)"), "R. Kumar");
});
test("displayView maps every string and keeps the rest", () => {
  const v = { by: "Dr. A. Rao (synthetic)", n: 3, ok: true, none: null, rows: [{ by: "Nurse Asha (synthetic)" }] };
  assert.deepEqual(displayView(v), { by: "Dr. A. Rao", n: 3, ok: true, none: null, rows: [{ by: "Nurse Asha" }] });
  assert.equal(v.by, "Dr. A. Rao (synthetic)");
});
```

- [ ] **Step 2: Run `cd frontend && node --test src/care/journey.test.js src/care/names.test.js`.** Expected: FAIL (module not found).

- [ ] **Step 3: Implement both modules.** `Timeline.jsx` imports `lensLines` from `journey.js`, and keeps exporting `LENSES` for `journey.js` to import. Move `LENSES` into `journey.js` and re-export it from `Timeline.jsx`, so `Chart.jsx:17` keeps working. `actions.js` drops `ACTIONS`/`actionsFor`. Update `actions.test.js`: delete its `actionsFor` test. `quietActions` is covered above, so add `assert.deepEqual(quietActions("ward", "nurse"), [])` to `journey.test.js`. `DoctorActions.jsx:5,218` switches to `quietActions(state, "doctor")` and keeps the ward discharge toggle in its own bar until Task 3. **Until Task 3 lands, keep "Dictate discharge" in the ward bar:** call `[...quietActions(state, "doctor"), ...(state === "ward" ? [["discharge", "Dictate discharge"]] : [])]`, so the demo is unchanged.

- [ ] **Step 4: Run the care tests, the build and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 155 pass, the build is clean, the demo is green, and no beat changes.

- [ ] **Step 5: Commit** (`frontend/src/care`). Message: "Count Guard: pure helpers for the journey bar, the next card, the history fold and display names".

---

### Task 3: Journey bar, next-action card, quiet row and history fold (M1 UI)

**Files:**
- Create: `frontend/src/care/JourneyBar.jsx`, `frontend/src/care/NextCard.jsx`, `frontend/src/care/History.jsx`
- Modify: `frontend/src/care/StateHeader.jsx` (rewrite), `frontend/src/care/StatePanel.jsx`, `frontend/src/care/Chart.jsx:62-106`, `frontend/src/care/DoctorActions.jsx:57-92,94-152,207-240`, `frontend/src/care/NurseActions.jsx:25-40,142-169`, `frontend/src/care/ActionBar.jsx`, `frontend/src/care/care.css`
- Demo: `frontend/scripts/demo/helpers.mjs:44-47` (`open`)

**Interfaces:**
- Consumes: `journeySteps`, `nextCard`, `quietActions`, `foldLines`, `foldOpensFor`, `lensLines` (Task 2). `view.visited`, `view.now_next.next_role` (Task 1).
- Produces:
  - `<JourneyBar state visited />` renders `<ol className="journey" aria-label="Journey">`. Each `<li className={status}>` holds the label, and for the current step `aria-current="step"` plus `<small>{detail}</small>`. Done steps carry a `✓` in an `aria-hidden` span.
  - `<StateHeader patient view you? />` renders the bed label, `<h1>{patient.name}</h1>`, `<JourneyBar>`, and — only when `you` — `<NextCard card={nextCard(view, "patient", { you: true })} />`. Staff charts render the card in `StatePanel` instead.
  - `<NextCard card>{children}</NextCard>` renders `<section className="card next-card" aria-label="Next step">`. Inside: the eyebrow (`.label`), `<p className="next-text">{text}</p>` (large type), the children only when `card.mine`, `<p className="note">{waiting}</p>` when set, and `<p className="small muted">{last}</p>`.
  - `StatePanel` computes `card = nextCard(view, role)` and passes it to `DoctorActions`/`NurseActions` as `card`. Each of those renders, in order: `<NextCard card>{primary for card.actions}</NextCard>`, then the quiet row, then the open panels and the rest.
  - The `ActionBar` stays as `role="group" aria-label="Doctor actions"`, with class `action-bar quiet-row`. Its buttons get `className="quiet"`.
  - `<History view role line rows rowsError replaced />` owns `open` (a `useState` initialised from `foldOpensFor`; not stored, R7) and `picked`. Collapsed, it shows the role's lens, the last 3 lines and a button `Show full history (${n})`, where `n` is the lens line count. Open, it shows the segmented `role="group" aria-label="Lens"` (the chips now at `Chart.jsx:85-90`), the full timeline or audit table, and a "Show less" button.

Primary action blocks (moved, not rewritten):

| Key | Role | Component content | Source today |
|---|---|---|---|
| `admit` | doctor | The Visit block: Reason for admission, Admit, Close visit | `DoctorActions.jsx:78-89` |
| `theatre` | doctor | The Procedure select, `TrayPreview`, Send to theatre | `DoctorActions.jsx:138-149` |
| `discharge` | doctor | A toggle button `Dictate discharge` (`aria-expanded`). When open: the `Dictate` plus the Discharge form | `DoctorActions.jsx:111-136` |
| `ack` | nurse | Per fresh order: `<p className="label">New orders from {order.by}</p>`, the items, and Acknowledge | `NurseActions.jsx:25-40` |
| `admission` | nurse | The admission `Checklist` | `NurseActions.jsx:151-156` |
| `theatre` | nurse | The nurse's theatre steps (Task 5 turns them into the checklist) | `NurseActions.jsx:98-140` |
| `discharge` | nurse | The discharge `Checklist` | `NurseActions.jsx:159-164` |

The nurse's ward tasks (`Ward`, `NurseActions.jsx:79-96`) render after the card. The doctor's theatre `Theatre` block (`DoctorActions.jsx:154-201`) renders after the card (R24). The `Clinic` cards Prescription and Check strips render after the quiet row (R25). The doctor's fallback `doctorWaiting` line at `DoctorActions.jsx:239` stays below the card until Task 6.

Chart order: StateHeader, AlertBanner (+ nudge Fault), StatePanel (card, quiet row, panels; + its Fault), AskInbox, Photos, VideoChecks, OrderTasks, History.

- [ ] **Step 1: Write the failing test** in `styles.test.js`:

```js
test("care.css styles the journey bar, the next card and the quiet row", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /\.journey li\.current/);
  assert.match(css, /\.journey li\.later, \.journey li\.skipped \{[^}]*color:\s*var\(--ink-muted\)/);
  assert.match(css, /\.next-text \{[^}]*font-size/);
  assert.match(css, /\.quiet-row/);
});
```

- [ ] **Step 2: Run `node --test src/care/styles.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement the components and the CSS.**
  - The journey bar is one horizontal row of six steps. It wraps to two rows of three at ≤ 640 px.
  - The current step uses `var(--sun-soft)` with a `var(--sun)` border. Done steps use `--ink`, and later or skipped steps use `--ink-muted`.
  - `.next-text` is `font-size: 1.25rem; font-weight: 700`.
  - Delete the `.now-next` rules and `.state-head .state-badge`.

- [ ] **Step 4: Update the demo helper.** `open(name)` finds `page.getByRole("button", { name, exact: true }).first()` page-wide, because "Dictate discharge" now sits in the card. Keep the "leave it open if `aria-expanded` is true" rule. Beat clicks still say `Button "Dictate discharge"`, so no beat or document line changes.

- [ ] **Step 5: Run the care tests, the build and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 156, the build is clean, the demo is green. Strings that move but stay visible:
  - `das-close` "The visit is closed. No further steps." (card text) and "Clinic visit closed" (journey detail).
  - `kumar-admit` NEXT sentence (card text, eyebrow "Next · for the nurse").
  - `kumar-admission` "New orders from Dr. A. Rao" (the `ack` label) and "acknowledged the orders at" (the Last line).
  - "On the ward", "In theatre", "Being admitted", "Being discharged" and "Home" (journey detail).

  If a beat fails because its string now sits in the collapsed history, do not change the fold. Find the string's visible owner in the card or the journey bar, and fix it there.

- [ ] **Step 6: Commit** (`frontend/src/care frontend/scripts/demo/helpers.mjs`). Message: "Count Guard: a journey bar and one next-step card on every chart, with history folded".

---

### Task 4: Nurse: one task list with voice on each row (M2)

**Files:**
- Create: `frontend/src/care/NurseTasks.jsx`
- Modify:
  - `frontend/src/care/tasklist.js` (add `taskStatusText`, `taskGroups`, `rowMark`, `orderFoldTitle`)
  - `frontend/src/care/drafts.js` (add `lastDoneLine`, `rowSession`)
  - `frontend/src/care/derive.js:8` (export `waitedText`)
  - `frontend/src/care/TaskProof.jsx` (rewrite into the confirm panel)
  - `frontend/src/care/NurseActions.jsx:42-96` (`TaskRow`/`Ward` move to `NurseTasks.jsx`)
  - `frontend/src/care/ObsForm.jsx` (a `label` prop)
  - `frontend/src/care/OrderTasks.jsx` (a `role` prop; the nurse fold)
  - `frontend/src/care/Chart.jsx` (pass `role` to `OrderTasks`)
  - `frontend/src/care/care.css`
- Test: `frontend/src/care/tasklist.test.js`, `frontend/src/care/drafts.test.js`
- Demo: `frontend/scripts/demo/helpers.mjs`, `steps.mjs`, `beats.mjs`, `beats.test.mjs:74-80`, the demo document

**Interfaces:**
- Consumes: `taskDue`, `sortTasks`, `hhmm`, `proofOf`, `MATCH_LABEL`, `answerHow`, `displayName` (Task 2), `waitedText` (now exported).
- Produces:
  - `taskStatusText(task, nowMs, state) -> string`:

    | `taskDue` result | Text |
    |---|---|
    | overdue | `` `${waitedText(nowMs - task.due_ms)} late` `` (R8) |
    | due | `"due now"` |
    | running | `"running"` |
    | paused | `"paused while in theatre"` |
    | later | `` `next at ${hhmm(due_ms)}` ``, or `"no set time"` when `due_ms == null` |
    | done | `"done"` |
    | closed | `"closed"` |
  - `taskGroups(tasks, nowMs, state) -> { now: Row[], later: Row[] }`. A `Row` is `{ task, due, status }`. `now` holds overdue, due and running rows. `later` holds later and paused rows. Done and closed tasks are left out. The order follows `sortTasks`.
  - `rowMark(task, due) -> { label, primary }`. An obs task gives `{ "Save readings", true }`. A later dose gives `{ "Given early", false }` (R1). Any other later task gives `{ "Mark done early", false }`. Everything else gives `{ "Mark done", true }`.
  - `orderFoldTitle(order) -> string`. It is `` `Signed orders · ${displayName(order.by)} ${hhmm(order.at_ms)} · ${order.acknowledged_by ? "acknowledged" : "not acknowledged yet"}` ``.
  - `lastDoneLine(task, photos) -> { text, match, flagged } | null`. It takes the last `task.done` entry `d`, and uses `proof = proofOf(d, photos)`:
    - `text` is `` `Last done ${hhmm(d.at_ms)} by ${displayName(d.by)}, ${proof.voice ? "by voice" : proof.typed ? "typed" : "by tap"}` ``.
    - `match` is `d.match ? MATCH_LABEL[d.match] || MATCH_LABEL.none : null`.
    - `flagged` is `proof.flagged`.
    - With no done entries it returns `null`.
  - `rowSession(proposal, task) -> { proposal: { candidates: [task], values }, via, transcript, source, heardBy }`. `values` is `proposal.values || {}` for an obs task, else `{}`. `via` is `proposal.heard_by === "typed" ? "text" : "voice"` (as at `TaskProof.jsx:48`).
  - `<NurseTasks view nowMs state by busy act upload ask />` renders `<section className="card" aria-label="Tasks">` with headings `Due now` and `Later today`. Each group shows its empty line ("Nothing due now." / "Nothing later today.").
    - Each row is `<li className="task-row">`. The first line is `<span>{task.title}</span> <span className="pill …">{status}</span>`, which keeps the innerText "Saline … running".
    - Under it sits the `lastDoneLine` (text, then `· <pill>{match}</pill>`). Then the existing controls, using `rowMark` for the button label.
    - The obs `ObsForm` gets `label="Save readings"`.
    - The mic button is `aria-label={`Say it: ${task.title}`}`, shows 🎙, and is hidden when the status is paused.
    - When the mic is open, the row renders `<Dictate label={`Say it: ${task.title}`} verb="Use this" …>`. Its `onSend` calls `ask("/dictate/task", undefined, { text, by, heard_by })`, then opens the confirm panel with `rowSession(proposal, task)`.
  - `<TaskProof view task session by busy act upload onClear />` renders `<section className="card" aria-label="Confirm task">`. It shows the transcript line, the Heard by line, `ObsForm` for obs, the Add photo input, the match line, and Confirm and Cancel. The radio group and the global "Complete a task by voice" box are gone. "Add photo proof" opens it with `{ via: "tap", transcript: "", proposal: { candidates: [task], values: {} } }`. Only one confirm panel is open at a time, owned by `NurseTasks`.
  - `OrderTasks` with `role === "nurse"` renders one `<details className="card order-fold">` per order, collapsed, `<summary>{orderFoldTitle(order)}</summary>`, holding the existing lines. With `role === "doctor"` it keeps the card. Its pills read `taskStatusText(task, nowMs, state)` instead of `dueLabel(due)`.
  - `NurseTasks` renders in `ward` and in `theatre` (after the checklist). In theatre every row is paused, with no controls.

- [ ] **Step 1: Write the failing tests:**

```js
// tasklist.test.js
const t = (o) => ({ id: "t", title: "BP", kind: "obs", status: "open", due_ms: 60 * M, ...o });
test("taskStatusText words", () => {
  assert.equal(taskStatusText(t({}), 60 * M + 34 * M, "ward"), "34 min late");
  assert.equal(taskStatusText(t({}), 60 * M + 94 * M, "ward"), "1 h 34 min late");
  assert.equal(taskStatusText(t({}), 60 * M + 5 * M, "ward"), "due now");
  assert.equal(taskStatusText(t({ due_ms: 6 * H + 10 * M }), 0, "ward"), "next at 15:10");
  assert.equal(taskStatusText(t({ due_ms: null }), 0, "ward"), "no set time");
  assert.equal(taskStatusText(t({}), 0, "theatre"), "paused while in theatre");
  assert.equal(taskStatusText(t({ status: "running" }), 0, "ward"), "running");
});
test("taskGroups splits due now from later and drops done", () => {
  const g = taskGroups([t({ id: "a" }), t({ id: "b", due_ms: 9 * H }), t({ id: "c", status: "done" }), t({ id: "d", status: "running" })], 61 * M, "ward");
  assert.deepEqual(g.now.map((r) => r.task.id), ["a", "d"]);
  assert.deepEqual(g.later.map((r) => r.task.id), ["b"]);
  assert.deepEqual(taskGroups([], 0, "ward"), { now: [], later: [] });
  assert.deepEqual(taskGroups([t({})], 0, "theatre").later.map((r) => r.status), ["paused while in theatre"]);
});
test("rowMark labels", () => {
  assert.deepEqual(rowMark(t({}), "due"), { label: "Save readings", primary: true });
  assert.deepEqual(rowMark(t({ kind: "dose" }), "later"), { label: "Given early", primary: false });
  assert.deepEqual(rowMark(t({ kind: "task" }), "later"), { label: "Mark done early", primary: false });
  assert.deepEqual(rowMark(t({ kind: "dose" }), "overdue"), { label: "Mark done", primary: true });
});
test("orderFoldTitle", () => {
  assert.equal(orderFoldTitle({ by: "Dr. A. Rao (synthetic)", at_ms: 2 * M, acknowledged_by: "Nurse Meena" }), "Signed orders · Dr. A. Rao 09:02 · acknowledged");
  assert.equal(orderFoldTitle({ by: "D", at_ms: 0, acknowledged_by: null }), "Signed orders · D 09:00 · not acknowledged yet");
});
test("M2 copy has no advice words", () => {
  for (const s of ["Given early", "Save readings", "due now", "paused while in theatre", "Due now", "Later today", "Signed orders"]) assert.doesNotMatch(s, ADVICE);
});
// drafts.test.js
test("lastDoneLine names time, who and how, with the photo match", () => {
  const task = { done: [{ at_ms: 96 * M, by: "Nurse Meena (synthetic)", via: "voice", transcript: "x", match: "ok", proof_id: "p1" }] };
  const line = lastDoneLine(task, [{ id: "p1", check: { match: "ok" } }]);
  assert.equal(line.text, "Last done 10:36 by Nurse Meena, by voice");
  assert.equal(line.match, MATCH_LABEL.ok);
  assert.equal(lastDoneLine({ done: [] }, []), null);
});
test("rowSession pins the row's task and keeps obs values only", () => {
  const obs = { id: "o", kind: "obs" };
  const s = rowSession({ heard_by: "prepared", transcript: "BP", source: "rules", values: { sbp: 82 }, candidates: [{ id: "x" }] }, obs);
  assert.deepEqual(s.proposal, { candidates: [obs], values: { sbp: 82 } });
  assert.equal(s.via, "voice");
  const typed = rowSession({ heard_by: "typed", values: { sbp: 1 } }, { id: "d", kind: "dose" });
  assert.deepEqual(typed.proposal.values, {});
  assert.equal(typed.via, "text");
});
```

- [ ] **Step 2: Run `node --test src/care/tasklist.test.js src/care/drafts.test.js`.** Expected: FAIL (not exported).

- [ ] **Step 3: Implement the helpers, `NurseTasks`, the confirm panel and the order fold.** `NurseActions.jsx` keeps the checklists and the theatre block. Check that `wc -l` is under 500 for each file you touch.

- [ ] **Step 4: Update the demo in the same task.**
  - `helpers.mjs` adds three helpers:
    - `say(rowText)`: `page.locator("li.task-row").filter({ hasText: rowText }).getByRole("button", { name: /^Say it: / }).click()`.
    - `sayFile(rowText, rel)`: sets the files on the row's `input[type=file][accept="audio/*"]`.
    - `sayText(rowText, text)`: fills the row's `getByLabel("What was said")`.
  - `steps.mjs` drops `VOICE` and changes four steps:
    - `kumar-paracetamol`: `say("Paracetamol")`, `sayFile("Paracetamol", wav)`, click "Use this", the before check, `H.file("Confirm task", png)`, click "Confirm".
    - `iyer-bp`: `say("BP and pulse")`, `sayFile`, "Use this", the before check, "Confirm".
    - `iyer-recheck`: `say("BP and pulse")`, `sayText("BP and pulse", "BP 112 over 70, pulse 84, bed 7.")`, "Use this", "Confirm", then the flag answer as today (no radio).
    - `iyer-end`: unchanged clicks.
  - `beats.mjs`:
    - `kumar-paracetamol.clicks` becomes `['Button "Say it: Paracetamol…" on the Paracetamol row', 'File eval/p2/kumar-paracetamol.wav into that row', 'Button "Use this"', 'File eval/p2/strip-paracetamol.png into "Confirm task"', 'Button "Confirm"']`.
    - `iyer-bp.clicks` follows the same pattern for the "BP and pulse" row.
    - `iyer-recheck.clicks` becomes `['Role Nurse', 'Button "Say it: BP and pulse every 1 h"', 'Textarea "What was said" in that row <- BP 112 over 70, pulse 84, bed 7.', 'Button "Use this"', 'Button "Confirm"', 'Field "What you did or saw" in the below-the-limit flag <- Reading checked again at the bedside', 'Button "Answer" in that flag']`.
    - `iyer-end.expect` becomes `[`finished ${SALINE} at`]`. The nurse's orders are folded, so "Saline … done" is no longer visible; the Last line reads "Last: Nurse Meena finished Saline … at 13:…" (R5).
    - Other expectations are unchanged. "by voice" and "Photo matches the task" now come from the row's last-done line (R10). "Saline … running" comes from the Due now row.
  - `beats.test.mjs:79-80` changes to `assert.ok(by["iyer-end"].expect.includes(`finished ${title} at`))`.
  - The demo document: rewrite the `Clicks:` lines of the four beats and the `On screen:` line of `iyer-end` to match, word for word.

- [ ] **Step 5: Run the care, demo-unit and build checks, then `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 163, demo 36, the build is clean, and the demo is green at 58/58/58.

- [ ] **Step 6: Commit** (`frontend/src/care frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: the nurse has one task list, due now and later today, with voice on each row".

---

### Task 5: Theatre checklist (M3)

**Files:**
- Create: `frontend/src/care/TheatreChecklist.jsx`
- Modify:
  - `frontend/src/care/theatre.js` (extend `theatreSteps`; add `checklistState`, `swabFigures`, `packLine`)
  - `frontend/src/care/TheatrePanel.jsx` (rewrite the body: three numbers; `onNote`; no `step` prop)
  - `frontend/src/care/VideoCheck.jsx:20-23` (a drop-zone class on the tray label)
  - `frontend/src/care/NurseActions.jsx` (the theatre block → `<TheatreChecklist role="nurse">`)
  - `frontend/src/care/DoctorActions.jsx` (`Theatre` → `<TheatreChecklist role="doctor">` plus the existing reason and Back to ward)
  - `frontend/src/care/care.css`
- Test: `frontend/src/care/theatre.test.js`

**Interfaces:**
- Consumes: `view.count` (Task 1), `view.tray`, `view.timeline`, `view.allowed`, `checkLabel`, `hhmm`, `label`, `displayName`.
- Produces:
  - `theatreSteps(view)`: each item gains `key` (`"tray" | "began" | "count" | "ended"`), `at` (`"HH:MM"` or `""`) and `open` (boolean). Existing `title`/`done`/`says` stay, so the existing tests still pass.
    - `tray.at` is `hhmm(tray.at_ms)`.
    - `began.at` and `ended.at` are `line.when.slice(-5)`.
    - `count.at` is the closing line's `when.slice(-5)`.
    - `count.open` is `(view.count?.missing ?? 0) > 0`.
    - With `!view.tray?.planned`, the tray step reads `{ done: true, says: "No tray planned" }` (R13).
  - `checklistState(steps) -> steps with status and wait`:
    - `status` is `"open"` for a done step with `open`. Other done steps are `"done"`. The first not-done step is `"current"`. The rest are `"later"`.
    - `wait` is set on later steps only: `{ began: "after the tray check", count: "after surgery began", ended: "after the count" }[key]`, else `""`.
  - `swabFigures(count) -> { opened, back, missing, tone }`. Missing values read `"–"`. `tone` is `"red"` when missing > 0, `"green"` when missing is 0, and `""` when unknown.
  - `packLine(count) -> string`. It is `` `Pack opened ${hhmm(count.opened_at_ms)} by ${displayName(count.opened_by)}` ``, or `""` when nothing is opened.
  - `<TheatreChecklist role view episodeId busy act upload replaced />` renders `<section className="card" aria-label="Theatre steps">` with an `<ol className="checklist">`:
    - A done step is one line: `✓ {title} · {at} · {says}`.
    - An expanded step ("current" or "open") holds the step's controls:
      - **tray** (nurse): `VideoCheck` with title "Tray check" and the drop zone "Upload tray video or photos".
      - **began**: "Surgery began".
      - **count** (nurse): `TheatrePanel`.
      - **ended**: "Surgery ended".
      - The doctor sees the same steps. On tray and count the doctor gets read-only lines; on began and ended the doctor gets their own buttons, posting `by: DOCTOR`.
    - A later step is muted: `{title} · {wait}`.
    - A done tray step with `tray.latest.match` flagged also renders `<VideoCheck … hideUpload>`, so its result table stays (R12).
    - The checklist owns `note` (TheatrePanel calls `onNote`) and renders it as `<p className="note" role="status">` under the list.
    - For the nurse, a "Back to ward" button sits under the list. It is disabled until `ended.done`, and shows the muted text "after step 4" next to it while disabled. Keep the surgeon branch text from `NurseActions.jsx:121-123`.
  - `TheatrePanel` shows three big numbers: `opened`, `back`, `missing`, with class `tone-{tone}`.
    - "Record pack opened" and its quantity input show only while `count.opened == null`.
    - After that, it shows `packLine(count)` and a quiet button `change`, which brings back the quantity input and "Record pack opened".
    - Then come "Closing count (returned)", Detail, "Record closing count", "Correct the count" (as today) and "Count by camera".

- [ ] **Step 1: Write the failing tests** (append to `theatre.test.js`):

```js
const base = { tray: { planned: [{}], latest: null }, timeline: [IN_THEATRE], count: { opened: null, returned: null, missing: null } };
test("first not-done step is current; later steps say why they wait", () => {
  const s = checklistState(theatreSteps(base));
  assert.deepEqual(s.map((x) => x.status), ["current", "later", "later", "later"]);
  assert.deepEqual(s.map((x) => x.wait), ["", "after the tray check", "after surgery began", "after the count"]);
});
test("an open count stays expanded and does not block surgery ended", () => {
  const view = { ...base, tray: { planned: [{}], latest: { check: "tray", match: "ok", at_ms: 22 * M } },
    timeline: [IN_THEATRE, line("surgery.began", "Day 0 09:24"), line("count.closing", "Day 0 09:30", "Closing count: 14 of 15 back, 1 unaccounted.")],
    count: { opened: 15, returned: 14, missing: 1, opened_by: "Nurse Asha (synthetic)", opened_at_ms: 22 * M } };
  const s = checklistState(theatreSteps(view));
  assert.deepEqual(s.map((x) => x.status), ["done", "done", "open", "current"]);
  assert.equal(s[0].at, "09:22");
});
test("no tray planned reads done", () => {
  assert.deepEqual(theatreSteps({ ...base, tray: { planned: null } })[0], { key: "tray", title: "Tray check", done: true, says: "No tray planned", at: "", open: false });
});
test("swab figures and the pack line", () => {
  assert.deepEqual(swabFigures({ opened: 15, returned: 14, missing: 1 }), { opened: 15, back: 14, missing: 1, tone: "red" });
  assert.equal(swabFigures({ opened: 15, returned: 15, missing: 0 }).tone, "green");
  assert.deepEqual(swabFigures({ opened: null, returned: null, missing: null }), { opened: "–", back: "–", missing: "–", tone: "" });
  assert.equal(packLine({ opened: 15, opened_by: "Nurse Asha (synthetic)", opened_at_ms: 22 * M }), "Pack opened 09:22 by Nurse Asha");
  assert.equal(packLine({ opened: null }), "");
});
test("checklist copy has no advice words", () => {
  for (const s of ["after the tray check", "after surgery began", "after the count", "after step 4", "Upload tray video or photos", "No tray planned"]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run `node --test src/care/theatre.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement.** Add the CSS: `.checklist` rows, `.drop-zone` (a dashed `--line-control` border, min-height 88 px, centred text), `.swab-figures` (three columns, numbers at 2rem), `.tone-red { color: var(--record) }`, `.tone-green { color: var(--ready-text, var(--ink)) }`. First confirm which token names exist in `styles.css`.

- [ ] **Step 4: Run the care tests, the build and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 168, the demo is green, and no beat or document line changes:
  - `kumar-tray` uses region "Tray check", and its flagged table stays visible.
  - `kumar-count` "Surgery began", "Record pack opened", the closing fields, "Correct the count" and "Correction recorded." all stay; the note is lifted to the checklist.
  - `kumar-back` "Surgery ended" and "Back to ward" stay.

  If `kumar-count` fails on "Record pack opened" because the step is not yet current, check that the tray step is done after `kumar-tray` (its check exists).

- [ ] **Step 5: Commit** (`frontend/src/care`). Message: "Count Guard: the theatre steps are one checklist, with the swab count as three numbers".

---

### Task 6: Doctor inbox: one card per item (M4)

**Files:**
- Modify:
  - `frontend/src/care/askText.js` (add `inboxItems`, `inboxHeader`, `photoDay`, `sendVerb`; delete `doctorWaiting`)
  - `frontend/src/care/AskInbox.jsx` (rewrite into per-item cards)
  - `frontend/src/care/Dictate.jsx` (a `placeholder` prop)
  - `frontend/src/care/DoctorActions.jsx:239` (delete the fallback line; the card covers it)
  - `frontend/src/care/Chart.jsx` (pass `name` and `nowMs` to AskInbox)
- Test: `frontend/src/care/askText.test.js` (replace the `doctorWaiting` tests)
- Demo: `steps.mjs` (`kumar-review`), `beats.mjs` (`kumar-review.clicks`), the demo document

**Interfaces:**
- Consumes: `view.ask.questions`, `view.ask.reviews`, `waitedText` (Task 4), `shortName` (Task 2), `label`.
- Produces:
  - `inboxItems(view, role, nowMs) -> [{ kind: "question" | "review", id, atMs, open, waited }]`. It covers questions with `to === "doctor"` and reviews. The doctor sees all items; other roles see answered items only. Open items come first, then answered, each by `at_ms` ascending (R22). `waited` is `waitedText(nowMs - at_ms)` for open items, else `""`.
  - `inboxHeader(name, items) -> string`. It is `` `From ${shortName(name)} · ${n} waiting` `` when `n = items.filter(open).length > 0`, else `` `From ${shortName(name)}` ``.
  - `photoDay(atMs) -> string`. It is `label(atMs)` without the time, so `"Day 0"` (R23).
  - `sendVerb(name) -> string`. It is `` `Send to ${shortName(name)}` ``.
  - `<AskInbox view role name nowMs busy act ask fault episodeId />` renders `<section aria-label="Ask inbox">` with `<p className="label">{inboxHeader}</p>` and one `<article className="card inbox-card" data-line={id}>` per item. Each card shows a `waited` pill when open.
    - Question card: `<p className="quote">“{text}”</p>`. Open, for the doctor: the existing `<section aria-label={`Your answer to ${q.by} at ${label(q.at_ms)}`}>` around `<Dictate bare label="Your answer" field="Your answer (check it before sending)" placeholder="Type or say your answer" verb={sendVerb(name)} …>`. Answered: the `Answered` line.
    - Review card: two figures side by side. One is the healing photo, captioned `photoDay(r.at_ms)`. The other is the newest reference photo, captioned "After surgery". Then the three `DECISIONS` buttons, and a quiet button "+ add a note" that reveals the "Note (optional)" input.
  - The "Waiting for your answer above." line no longer exists anywhere.

- [ ] **Step 1: Write the failing tests:**

```js
const v = { ask: {
  questions: [{ id: "q2", to: "doctor", at_ms: 20 * M, answer: null }, { id: "q1", to: "doctor", at_ms: 10 * M, answer: null }, { id: "b", to: "bot", at_ms: 0, answer: null }, { id: "q0", to: "doctor", at_ms: 0, answer: { text: "ok" } }],
  reviews: [{ id: "r1", at_ms: 15 * M, answer: null }] } };
test("inboxItems: open oldest first, then answered; others see answered only", () => {
  assert.deepEqual(inboxItems(v, "doctor", 30 * M).map((i) => i.id), ["q1", "r1", "q2", "q0"]);
  assert.equal(inboxItems(v, "doctor", 30 * M)[0].waited, "20 min");
  assert.deepEqual(inboxItems(v, "nurse", 30 * M).map((i) => i.id), ["q0"]);
  assert.deepEqual(inboxItems({}, "doctor", 0), []);
});
test("header, verb and photo day", () => {
  const items = inboxItems(v, "doctor", 30 * M);
  assert.equal(inboxHeader("R. Kumar, 58 M (synthetic)", items), "From R. Kumar · 3 waiting");
  assert.equal(inboxHeader("R. Kumar, 58 M", []), "From R. Kumar");
  assert.equal(sendVerb("R. Kumar, 58 M (synthetic)"), "Send to R. Kumar");
  assert.equal(photoDay(3 * 24 * H + 5 * M), "Day 3");
});
test("inbox copy has no advice words", () => {
  for (const s of ["Type or say your answer", "+ add a note", "After surgery", "From R. Kumar · 2 waiting"]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run `node --test src/care/askText.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement.** `Dictate` passes `placeholder` to its textarea. Delete `doctorWaiting` and its import. When nothing applies, `DoctorActions` returns only the card, which already says "Waiting for the nurse." or shows the plain "Next".

- [ ] **Step 4: Update the demo.**
  - `steps.mjs` `kumar-review`: `H.click("Send to R. Kumar")` replaces `H.click("Send answer")`.
  - `beats.mjs` `kumar-review.clicks[4]` becomes `'Button "Send to R. Kumar"'`.
  - Expectations are unchanged. "Reference" is still shown by the Photos card ("Reference · Dr. A. Rao"), and "Healing photo" by the review card's label `Healing photo`. Render that label inside each review card as `<p className="label">Healing photo</p>`.
  - The demo document: update the `kumar-review` `Clicks:` line.

- [ ] **Step 5: Run the care, demo-unit and build checks, and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 171, the demo is green.

- [ ] **Step 6: Commit.** Message: "Count Guard: the doctor's inbox is one card per question or photo, oldest first".

---

### Task 7: Doctor home: one patient list (M5)

**Files:**
- Create: `frontend/src/care/patients.js`, `frontend/src/care/patients.test.js`, `frontend/src/care/MyPatients.jsx`
- Modify:
  - `frontend/src/care/derive.js` (export `rowsFor`)
  - `frontend/src/care/Queue.jsx:57-66,98-112` (drop the doctor status group and the duplicate "My patients" list)
  - `frontend/src/care/CareShell.jsx:22,44,121-125` (doctor tabs, home, `pick`)
  - `frontend/src/App.jsx:177-178` (routes)
  - `frontend/src/care/care.css`
- Demo: `helpers.mjs` (`chart`), `steps.mjs` (`kumar-review`, `iyer-orders`, `close`), `beats.mjs`, the demo document

**Interfaces:**
- Consumes: `rowsFor(patient, "doctor", nowMs)` (rows keep `key`, `nudgeKind`, `waited`, `waitedMs`), `nudgeLabel` (`askText.js:81`), `STATE_LABEL`, `hhmm`, `displayName`, `STATUS_CHOICES`.
- Produces (`patients.js`):
  - `reasonText(rows) -> string`. It maps each row by the segment after `episodeId:` in `row.key`:
    - `question` → "Question"
    - `review` → "Healing photo"
    - `clinic` → "See in clinic"
    - `no-orders` → "No orders signed"
    - `nudge` → `nudgeLabel(row.nudgeKind)`

    It de-duplicates in order, then joins with `" + "`. Every part after the first gets a lower-case first letter.
  - `nextForOthers(patient, nowMs) -> string`. It takes the earliest open task with `due_ms != null` and gives `` `Nurse ${({ obs: "obs", dose: "dose" })[task.kind] || "task"} due ${hhmm(task.due_ms)}` ``. With no such task it gives `displayName(view.now_next.next)`.
  - `patientGroups(patients, nowMs) -> { waiting: Row[], quiet: Row[] }`. A `Row` is `{ episodeId, bed, name, state, reason, waited, next }`.
    - `waiting` holds patients with at least one doctor row, sorted by the longest `waitedMs` (rows with no time last).
    - `quiet` holds the rest, by bed.
    - `state` is `STATE_LABEL[view.state]`. `reason`/`waited` are filled for waiting rows; `next` is filled for quiet rows.
  - `statusWord(status) -> string`: `{ available: "Available", busy: "Busy", in_theatre: "In theatre" }[status?.status] || "Status"`.
- Produces (UI):
  - `<MyPatients />` renders `PageLead` (kicker "Ward", title "My patients", body "Who is waiting on you first.").
  - Top right is `<details className="status-menu"><summary>{statusWord(ward.doctorStatus)} ▾</summary>`, holding the `STATUS_CHOICES` buttons inside `role="group" aria-label="My status"` and the `STATUS` Fault.
  - Two headings: `Waiting on you · {n}` and `Nothing for you now · {n}`. Each group is a `ul.patient-list` of `<a className="waiting">` or `<a className="quiet">` links to `/chart/:id`, so the whole row opens the chart.
  - A waiting row shows Bed, name, reason, the state pill and the waited pill. A quiet row shows Bed, name, the state pill and `next`.
  - Exports `QueueRoute` and `PatientsRoute`. Each renders `MyPatients` for the doctor; otherwise `Queue` and `Patients` respectively (R14). `App.jsx` uses them for `/queue` and `/patients`.
  - `STAFF_TABS` becomes role-aware: doctor `[["/patients", "My patients"]]`, nurse unchanged. `CareHome` sends the doctor to `/patients`.

- [ ] **Step 1: Write the failing tests** (`patients.test.js`; build patients with `view: { state, order_list: [], tasks: [], nudges: [], ask: {…}, now_next: { next: "…" } }`):

```js
test("reasonText joins distinct reasons", () => {
  assert.equal(reasonText([{ key: "e4:question:q1" }, { key: "e4:question:q2" }, { key: "e4:review:r1" }]), "Question + healing photo");
  assert.equal(reasonText([{ key: "e7:nudge:n1", nudgeKind: "obs_past_limit" }]), "Observation past its limit");
});
test("patientGroups splits waiting from quiet", () => {
  const kumar = P("e4", "4", "home", { ask: { questions: [{ id: "q", to: "doctor", at_ms: 0, answer: null }], reviews: [{ id: "r", at_ms: 10 * M, answer: null }] } });
  const iyer = P("e7", "7", "ward", { order_list: [{}], tasks: [{ status: "open", kind: "obs", due_ms: H }] });
  const g = patientGroups([iyer, kumar], 30 * M);
  assert.deepEqual(g.waiting.map((r) => [r.bed, r.reason, r.waited, r.state]), [["4", "Question + healing photo", "30 min", "Home"]]);
  assert.deepEqual(g.quiet.map((r) => [r.bed, r.next]), [["7", "Nurse obs due 10:00"]]);
});
test("a quiet patient with no task reads the NEXT sentence", () => {
  const das = P("e9", "9", "clinic_done", { now_next: { next: "The visit is closed. No further steps." } });
  assert.equal(nextForOthers(das, 0), "The visit is closed. No further steps.");
});
test("statusWord", () => {
  assert.equal(statusWord({ status: "available" }), "Available");
  assert.equal(statusWord(null), "Status");
});
test("M5 copy has no advice words", () => {
  for (const s of ["Waiting on you · 1", "Nothing for you now · 2", "Who is waiting on you first.", "Nurse obs due 10:00"]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run `node --test src/care/patients.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement.** Add the CSS: `.patient-list a.waiting { border-left: 4px solid var(--sun) }`, `.patient-list a.quiet { color: var(--ink-muted) }`, `.status-menu` (top right, its summary styled as a pill).

- [ ] **Step 4: Update the demo.**
  - `helpers.chart` clicks `nav.getByRole("link", { name: /^(My )?patients$/i })`. That is "Patients" for the nurse and "My patients" for the doctor. Keep the `.patient-list a` filter.
  - `steps.mjs`:
    - `kumar-review`: `H.tab("My patients")`, then `H.page.locator(".patient-list a.waiting").filter({ hasText: KUMAR }).click()`, then `await H.page.locator("h1", { hasText: KUMAR }).waitFor()`.
    - `iyer-orders`: `H.tab("My patients")`.
    - `close`: `H.tab("My patients")`.
  - `beats.mjs` clicks:
    - `kumar-review`: `'Tab "My patients"'`, `'Row "R. Kumar" under "Waiting on you"'`.
    - `iyer-orders`: `'Tab "My patients" (row reads "Observation past its limit")'`.
    - `close`: `'Tab "My patients"'`, and `say` becomes "Back on My patients, Dr. Rao shows as available and every step above has a record." (it passes the regex).
  - The nurse beat `kumar-admission` keeps `Tab "My queue"`.
  - The demo document: the three `Clicks:` lines, plus the `close` narration line (`> …`), which `doc.test.mjs` checks.

- [ ] **Step 5: Run the care, demo-unit and build checks, and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 176, the demo is green (`close` still sees "Dr. A. Rao: Available" in the product bar, R15). By hand, open `/queue` as the doctor and check that it shows My patients.

- [ ] **Step 6: Commit.** Message: "Count Guard: the doctor's home is one patient list, waiting on you first".

---

### Task 8: Patient phone home: Today (M6)

**Files:**
- Create: `frontend/src/care/today.js`, `frontend/src/care/today.test.js`
- Modify:
  - `frontend/src/care/Today.jsx` (rewrite)
  - `frontend/src/screens/TodayPanel.jsx` (export `Medicines` and a `Strips` block; the default export goes, because Today composes the parts)
  - `frontend/src/screens/PatientCard.jsx:5-50` (split `MyCard` into `MyCard` (card only) and `NeedHelp` (input, "Need help" button, status, Fault `/help`))
  - `frontend/src/care/CareShell.jsx` (export `DoctorChip`)
  - `frontend/src/care/care.css`

**Interfaces:**
- Consumes: `view.state`, `view.now_next.you_now`/`you_next`, `view.card.review`, `view.schedule`, `doctorQuestions` (`askText.js:16`), `shortName`, `displayName`, `label`.
- Produces (`today.js`):
  - `greeting(name) -> string`. It is `` `Hi, ${shortName(name)}` ``.
  - `whereWords(state, nowMs) -> string`:

    | State | Words |
    |---|---|
    | home | `` `You are home · day ${d}` `` for d ≥ 1, else `"You are home"` (R18). `d` is the demo day, `Math.floor(nowMs / DAY)`. |
    | clinic | "You are in clinic" |
    | clinic_done | "Your clinic visit is closed" |
    | admitting | "You are being admitted" |
    | ward | "You are on the ward" |
    | theatre | "You are in theatre" |
    | discharging | "You are getting ready to go home" |
  - `nextWords(view) -> string`, per R19. Both branches go through `displayName` and lower-case the first letter.
  - `todayFolds(view) -> [{ key, title }]`. The order is `card` "My discharge card", `medicines` "My medicines", `strips` "Check my strips", `ask` `` `Ask Dr. Rao (${n} answered)` ``. With an empty `view.schedule`, `medicines` moves to the end (R17).
- Produces (UI), in this order:
  1. A greeting row: `<h1>{greeting(name)}</h1>` and `<DoctorChip>`. No PageLead and no eyebrow name.
  2. `<section className="card" aria-label="Your status">`: `<p className="next-text">{whereWords}</p>`, `<p>{you_now}</p>`, `<p className="small">{nextWords}</p>`.
  3. The "For you now" nudge card (as today).
  4. Home only: a button "Open check-in" (R1, primary). It reveals the existing `CheckIn`.
  5. Home only: one `<details className="card fold">` per `todayFolds` entry. Inside: card → `MyCard`; medicines → `Medicines` plus the reminders button, link and Fault (`TodayPanel.jsx:99-104`); strips → the strips block; ask → the answered `doctorQuestions` (text, answer, `answerByLine`) and `<Link to="/ask">Ask a question →</Link>` (R16).
  6. Home only: a pinned `<div className="help-bar" role="region" aria-label="Need help">`, holding "Feeling worse?" and a button "Need help now". The button toggles a sheet holding `NeedHelp`.

  When not home, the page shows 1–3 plus "Check-ins and Need help open once you are home."

- [ ] **Step 1: Write the failing tests:**

```js
const home = (extra = {}) => ({ state: "home", schedule: [{}], card: { review: "Wound check in the surgical clinic on day 7 (synthetic)" }, ask: { questions: [] },
  now_next: { you_now: "Dr. A. Rao completed your discharge at 10:50.", you_next: "You are home. No further steps." }, ...extra });
test("greeting and where", () => {
  assert.equal(greeting("R. Kumar, 58 M (synthetic)"), "Hi, R. Kumar");
  assert.equal(whereWords("home", 3 * 24 * H + 5 * M), "You are home · day 3");
  assert.equal(whereWords("home", 5 * M), "You are home");
  assert.equal(whereWords("theatre", 0), "You are in theatre");
});
test("next item: the review when nothing else is next", () => {
  assert.equal(nextWords(home()), "Next: wound check in the surgical clinic on day 7");
  assert.equal(nextWords(home({ now_next: { you_next: "The doctor reviews your healing photo." } })), "Next: the doctor reviews your healing photo.");
});
test("folds: an empty My medicines never comes first, and the answered count shows", () => {
  assert.deepEqual(todayFolds(home()).map((f) => f.key), ["card", "medicines", "strips", "ask"]);
  const empty = home({ schedule: [], ask: { questions: [{ to: "doctor", answer: { text: "ok" } }, { to: "doctor", answer: null }] } });
  assert.deepEqual(todayFolds(empty).map((f) => f.key), ["card", "strips", "ask", "medicines"]);
  assert.equal(todayFolds(empty).find((f) => f.key === "ask").title, "Ask Dr. Rao (1 answered)");
});
test("M6 copy has no advice words", () => {
  for (const s of ["Open check-in", "Feeling worse?", "Need help now", "You are getting ready to go home", "Ask a question →"]) assert.doesNotMatch(s, ADVICE);
});
```

- [ ] **Step 2: Run `node --test src/care/today.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement.** Add the CSS:
  - `.help-bar { position: fixed; left: 0; right: 0; bottom: 0; display: flex; justify-content: space-between; align-items: center; gap: 12px; padding: 12px 16px; background: var(--surface); border-top: 1px solid var(--line); }`
  - `.page:has(.help-bar) { padding-bottom: 96px; }`

  Check at 390 px that nothing scrolls sideways (Task 10 measures it).

- [ ] **Step 4: Run the care tests, the build and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 180, the demo is green. `kumar-chip` reads the chip in the greeting row and the product bar; no beat changes.

- [ ] **Step 5: Commit** (`frontend/src/care frontend/src/screens`). Message: "Count Guard: the patient's Today leads with a greeting, a status card and one check-in button".

---

### Task 9: Demo dock and display names (M7)

**Files:**
- Create: `frontend/src/care/dock.js`, `frontend/src/care/dock.test.js`, `frontend/src/care/DemoDock.jsx`
- Delete: `frontend/src/care/fold.js`, `frontend/src/care/fold.test.js`
- Modify:
  - `frontend/src/care/ward.js:89,135,188,200` (wrap every `setPatients` input in `shown()`)
  - `frontend/src/care/CareShell.jsx` (the header, nav-bar, Strip toggle, ClockBar and ModelsChip move; `pick` unchanged)
  - `frontend/src/care/care.css:30-44` (drop `.demo-toggle`, `.fold-wrap`, `.demo-fold`; add the dock)
  - `frontend/src/care/styles.test.js`
- Demo: `beats.mjs` (`intro`, `kumar-admit`, `iyer-orders`), the demo document

**Interfaces:**
- Consumes: `displayName`, `displayView` (Task 2), `label`, `skipTargets`, `stripPills`, `waitingPills`, `BANNER`/`Banner` (`App.jsx:24`).
- Produces:
  - `ward.js`: `const shown = (p) => ({ ...p, name: displayName(p.name), view: displayView(p.view) })`. It is applied to the roster at load and reset, and to every returned view, at the four `setPatients` sites (R20). Data the frontend posts (the `DOCTOR` and `NURSE` constants) keeps "(synthetic)", so the backend record is unchanged.
  - `dock.js`:
    - `dockSummary(role, nowMs) -> string`, e.g. `` `DEMO · ${ROLE_NAME[role]} · ${hhmm(nowMs)}` `` → "DEMO · Nurse · 09:12".
    - `modelsText(live: boolean | null) -> string`: `true` → "Synthetic data · models: live"; `false` → "Synthetic data · models: offline (prepared)"; `null` → "Synthetic data".
    - `alertsLabel(n) -> string`: 0 → `""`; 1 → `"1 alert"`; otherwise `` `${n} alerts` ``.
  - `<DemoDock ward />` renders `<section className="demo-dock" aria-label="Demo">`:
    - A summary button `className="dock-summary"` with text `{dockSummary} ▾` and `aria-expanded`. It is visible only at ≤ 640 px.
    - `<div className="dock-body">` holds:
      - the role switch `role="group" aria-label="Role"`;
      - the patient select `aria-label="Patient"` (patient role only, as today);
      - the clock group `className="clock-bar" role="group" aria-label="Demo clock"`, with the time, the skip buttons, Reset and the CLOCK Fault;
      - `<span>{modelsText(live)}</span>` (the `ModelsChip` fetch moves here);
      - `<Banner />`.
    - At ≤ 640 px, `.demo-dock:not(.open) .dock-body { display: none; }`.
  - The product bar (`header.app-bar`) holds the brand, the role's `nav` (`aria-label="Main"`), an alerts pill (`<button className="pill wait" aria-expanded>` with `alertsLabel(mine + others)`, hidden at 0), and `DoctorChip`. `Strip` renders only while that pill is expanded (R21). The `DEMO` env check still hides the clock; the dock always shows the banner.
  - Every role shows "Research demo. Not for clinical use." in the dock.

- [ ] **Step 1: Write the failing tests:**

```js
// dock.test.js
test("dockSummary folds the dock to one line", () => {
  assert.equal(dockSummary("nurse", 12 * M), "DEMO · Nurse · 09:12");
  assert.equal(dockSummary("doctor", 0), "DEMO · Doctor · 09:00");
});
test("modelsText and alertsLabel", () => {
  assert.equal(modelsText(false), "Synthetic data · models: offline (prepared)");
  assert.equal(modelsText(true), "Synthetic data · models: live");
  assert.equal(modelsText(null), "Synthetic data");
  assert.deepEqual([0, 1, 2].map(alertsLabel), ["", "1 alert", "2 alerts"]);
});
test("dock copy has no advice words", () => {
  for (const s of [dockSummary("patient", 0), modelsText(false), alertsLabel(2)]) assert.doesNotMatch(s, ADVICE);
});
// styles.test.js
test("the dock folds to one line at phone width and the clock keeps its disabled style", () => {
  const css = fs.readFileSync(new URL("./care.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 640px\)[\s\S]*\.demo-dock:not\(\.open\) \.dock-body \{[^}]*display:\s*none/);
  assert.match(css, /\.demo-dock \{[^}]*background/);
  assert.doesNotMatch(css, /\.demo-toggle/);
});
```

- [ ] **Step 2: Run `node --test src/care/dock.test.js src/care/styles.test.js`.** Expected: FAIL.

- [ ] **Step 3: Implement.**
  - The dock is dark: `background: var(--ink); color: var(--surface)`. Its buttons are outlined in `--surface`.
  - The existing `.clock-bar button:disabled` rule stays, because `styles.test.js:14` checks it.
  - Delete `fold.js` and its test. They are only used by `CareShell.jsx`.

- [ ] **Step 4: Update the demo.**
  - `intro.expect` becomes `["Synthetic data · models: offline (prepared)", "Research demo. Not for clinical use."]`, and `intro.keyed` becomes "No model call. The dock reads models: live, not offline, when a key is set."
  - `kumar-admit.expect[1]` becomes "Nurse acknowledges the new orders from Dr. A. Rao, then completes the admission."
  - `iyer-orders.expect[1]` becomes "Nurse acknowledges the new orders from Dr. A. Rao."
  - The demo document: the `On screen:` lines of those three beats, and the `intro` keyed row.
  - The helpers do not change. `role`, `pick` and `clock` use the same accessible names, and the run is at 1200 px wide, so the dock is open.
  - Scan the other expectations for "(synthetic)":

    ```bash
    grep -n "synthetic)" frontend/scripts/demo/beats.mjs
    ```

    Expected: no match.

- [ ] **Step 5: Run the care, demo-unit and build checks, and `make demo-check MODEL_API_KEY=`.** Expected: care ≥ 183 (−1 for the deleted `fold.test.js`), demo 36, the demo is green at 58/58/58.

- [ ] **Step 6: Commit** (`frontend/src frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: one demo dock holds every demo control, and names drop the synthetic tag".

---

### Task 10: Verification sweep and before/after review

**Files:**
- Modify: only what a failure below points at, in the owning task's files.
- Scratch (not committed): `/private/tmp/claude-502/-Users-narenlingala-Documents-workspace-hackathon-hackathon26/9c2f4abf-956d-48ef-93f1-f23a07ae1f69/scratchpad/sweep.mjs`

- [ ] **Step 1: Run every suite.** Backend, care and demo pass with counts at or above 384 / 183 / 36. `npm run build` is clean. `wc -l frontend/src/care/*.jsx frontend/src/care/*.js frontend/src/care/care.css frontend/src/screens/*.jsx backend/app/journey/states.py` shows every file under 500.

- [ ] **Step 2: Run `make demo-check MODEL_API_KEY=`.** Expected: "31 beats", 58/58/58 s. Compare `demo-shots/` with `$TMPDIR/cg-v3-before-shots/` by eye, beat by beat. List each changed screen in the commit body.

- [ ] **Step 3: Update `sweep.mjs` for the new chrome.**
  - Its `role()` opens the dock summary (`.dock-summary`) when visible, in place of the "Demo controls" button.
  - Its doctor queue step uses the "My patients" tab.
  - Add a pass at a `390 × 844` viewport that visits `/today`, `/patients`, `/queue` and one chart for each role. On each page it asserts `document.documentElement.scrollWidth <= 390`.

- [ ] **Step 4: Start the servers with `make dev CG_API_PORT=8200 CG_WEB_PORT=5273 MODEL_API_KEY=`, and run `node <scratchpad>/sweep.mjs`.** Never use 8100/5173. Check that each of these holds:
  - Every role in every state (clinic, clinic_done, admitting, ward, theatre, discharging, home) shows the journey bar with the right statuses. Kumar after theatre shows Theatre ✓ on the ward.
  - The card shows buttons only to its owner.
  - The nurse in theatre sees the checklist inside the card. The surgeon sees it under the card with "Surgery began" and "Surgery ended".
  - The doctor's `/queue` shows My patients.
  - The patient's Today folds, "Open check-in" and the pinned "Need help now" all work at 390 px.
  - No screen shows "(synthetic)", except the Everyone (audit) table.
  - There are no console errors and no failed requests other than deliberate 409s, and each 409 shows inside its card.

- [ ] **Step 5: Stop the servers.** Fix any failure in the owning task's files. After a fix, run Steps 1–2 again.

- [ ] **Step 6: Commit any fixes.** Message: "Count Guard v3 mockups: verification fixes". Skip the commit when nothing changed. List the changed files.

---

## Self-review against the spec

**Coverage of M1–M7:**

| Spec bullet | Task |
|---|---|
| M1 journey bar, its six steps and the state mapping | 2 (`JOURNEY`, `journeySteps`), 3 (`JourneyBar`) |
| M1 done / current / later; Theatre done after a return; clinic_done "Visit closed" | 1 (`visited`), 2 (tests) |
| M1 next card replacing NOW/NEXT; large NEXT; eyebrow "for you" / "for the …" | 2 (`nextCard`), 3 (`NextCard`, StateHeader rewrite) |
| M1 primary actions in the card per role (doctor ward: procedure + Send to theatre + Dictate discharge; nurse admitting checklist; mapped from `allowed_moves` and the components) | 2 (`cardActions`), 3 (action table) |
| M1 "Last: <NOW>"; no buttons and who is waiting when not mine | 2, 3 (R5) |
| M1 secondary actions as a quiet row | 2 (`quietActions`), 3 |
| M1 history fold: last 3, "Show full history (N)", segmented role filter inside, not stored | 2 (`foldLines`, `foldOpensFor`), 3 (`History`) |
| M2 one list, Due now / Later today | 4 (`taskGroups`) |
| M2 "N min late", "due now", "next at HH:MM" with no Day 0, "paused while in theatre" | 4 (`taskStatusText`, R8) |
| M2 🎙 per row → Dictate for that task; via voice; global card removed | 4 (`rowSession`, `NurseTasks`, `TaskProof` rewrite, R9) |
| M2 obs inline fields and primary "Save readings" | 4 (`rowMark`, `ObsForm label`) |
| M2 later dose "Give early" (outline) | 4 ("Given early", R1) |
| M2 signed orders fold for the nurse; the doctor keeps the card with next times | 4 (`orderFoldTitle`, `OrderTasks role`) |
| M3 one vertical checklist; one-line done steps with ✓ and time; current expanded; later muted with why | 5 (`checklistState`, `TheatreChecklist`) |
| M3 tray drop zone "Upload tray video or photos" | 5 (`VideoCheck` drop zone) |
| M3 opened / back / missing, red/green; "Record pack opened" until opened; "Pack opened 09:22 by Nurse Asha · change"; closing input and "Count by camera" | 1 (`count`), 5 (`swabFigures`, `packLine`, `TheatrePanel`) |
| M3 "Back to ward" disabled with "after step 4" | 5 |
| M3 the surgeon sees the same checklist with their buttons | 5 (R24) |
| M4 one card per item, oldest first, with waiting time | 6 (`inboxItems`, R22) |
| M4 quoted question, `Dictate` placeholder "Type or say your answer", "Send to R. Kumar" | 6 (`sendVerb`, `placeholder`) |
| M4 photo and reference side by side, "Day N" / "After surgery", three buttons, "+ add a note" | 6 (`photoDay`, R23) |
| M4 header "From R. Kumar · 2 waiting"; banner removed | 6 (`inboxHeader`; `doctorWaiting` deleted) |
| M5 My patients with two groups, amber edge, reason, state, waiting pill; muted rows with the next item for others | 7 (`patientGroups`, `reasonText`, `nextForOthers`) |
| M5 whole row opens the chart; "Available ▾" menu; `/patients` stays, `/queue` alias | 7 (R14, R15) |
| M6 greeting with chip; status card; one check-in button; folds with "N answered"; pinned "Feeling worse?" bar; name once; empty medicines never first | 8 (`today.js`, R16–R19, R1) |
| M7 dark dock with role, picker, clock (+15 min, +1 h, Next due, Reset) and synthetic/models text; one line at ≤ 640 px | 9 (`DemoDock`, `dockSummary`, `modelsText`) |
| M7 product bar: brand, nav, alerts pill, doctor status | 9 (`alertsLabel`, R21) |
| M7 "(synthetic)" stripped by `displayName()`; the backend keeps it; research notice in the dock on every screen | 2 (`names.js`), 9 (`ward.js shown`, R20) |
| Done when: demo green, sweep with no errors at 390 px, before/after shots reviewed | 1 Step 1, 10 |

**Name consistency across tasks.** These names are each defined once and used with the same spelling everywhere:
- `next_role`, `visited` and `count` come from Task 1 and are used in Tasks 2, 3 and 5.
- `displayName`, `shortName` and `displayView` come from Task 2 and are used in Tasks 4, 5, 6, 7, 8 and 9.
- `waitedText` is exported in Task 4 and used in Tasks 6 and 7.
- `nextCard`, `cardActions`, `quietActions`, `foldLines` and `lensLines` come from Task 2 and are used in Task 3.
- `DoctorChip` is exported in Task 8 and used again in Task 9.
- `rowsFor` is exported in Task 7.

**Demo safety per task.** Each task that changes a selector or a visible string updates `beats.mjs`, `steps.mjs`, `helpers.mjs` and the demo document in the same commit:

| Task | Demo change |
|---|---|
| 3 | `open` |
| 4 | 4 beats, plus `beats.test.mjs` |
| 6 | `kumar-review` |
| 7 | `chart`, 3 beats |
| 9 | 3 beats |
| 1, 2, 5, 8 | No beat lines change; each still runs `make demo-check` |

The filmed seconds are unchanged, so 58/58/58 holds.

# Count Guard v2 UX Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the five wrong behaviours (A1–A5) and ship the nine refinements (B1–B9) of the v2 UX review, with the 31-beat demo check still green.

**Architecture:** Errors become scoped faults `{episodeId, scope, message}` in `useWard`, shown by a `Fault` component next to the action that raised them. `Dictate` becomes one voice-first text box: audio goes to `/ask/hear`, fills the box, and the verb button sends text plus the hearer. The backend gains dose-order matching for the medicine photo, a patient-voiced NOW line (`you_now`) and `heard_by` on typed dictation. Care-only CSS moves to `src/care/care.css`.

**Tech Stack:** FastAPI + pytest (backend), React 18 + Vite + react-router (frontend), `node --test` for care and demo tests, playwright-core demo runner.

**Spec:** `docs/superpowers/specs/2026-10-30-count-guard-v2-ux-refine-design.md`

All paths below are relative to `count-guard/` unless they start with `docs/`. The demo document is `docs/demo/count-guard-v2-video-script.md` at the repo root.

## Global Constraints

- `make demo-check MODEL_API_KEY=` stays green: 31 beats, doctor/nurse/patient 58/58/58 s. Beats (`frontend/scripts/demo/beats.mjs`), steps (`steps.mjs`) and the demo document change together, in the same task.
- Backend, care and demo node tests stay green. Every behaviour change gets a test. Baselines: backend 357, care 120, demo 36.
- New copy passes the no-advice regex `/\b(give|take|stop|increase|reduce|start|administer|consider)\b/i`.
- Files stay under 500 lines. `frontend/src/styles.css` is 443 lines; care-only rules move to `frontend/src/care/care.css` in Task 4.
- Never call a live model in tests or checks. Never touch ports 8100/5173 (use 8200/5273).
- Commit with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`, no Co-Authored-By line. Never push.

Commands (run from `count-guard/`):
- Backend: `.venv/bin/python -m pytest backend/tests -q`
- Care: `cd frontend && node --test 'src/care/*.test.js'`
- Demo: `cd frontend && node --test 'scripts/demo/*.test.mjs'`
- Build: `cd frontend && npm run build`
- Full: `make demo-check MODEL_API_KEY=`

## Review Focus

1. A recording is sent with a forged `heard_by` field: the server ignores it and records the transcriber's own source (Task 4 test).
2. A signed dose order with no `every_h`: the medicine row reads "as ordered", never "every None h" (Task 3 test).
3. The same medicine is on both the prescription and a dose order: the prescription row wins, so the doctor's schedule is restated (Task 3 test).
4. The current role has no pills of its own but other roles do: the strip still shows the collapsed "+N for nurse" pill (Task 7 test).
5. A click on the "Answer" button or the "Open →" link inside a queue row does exactly that and does not also fire the row's navigation (Task 5 test).

---

### Task 1: Errors stay where they happen (A1)

**Files:**
- Create: `frontend/src/care/faults.js`, `frontend/src/care/faults.test.js`, `frontend/src/care/Fault.jsx`
- Modify: `frontend/src/care/ward.js:73-208`, `frontend/src/care/CareShell.jsx:65-77,95-143`, `frontend/src/care/Chart.jsx:50,62-76`, `frontend/src/care/AskInbox.jsx:94-106`, `frontend/src/care/Ask.jsx:9-34`, `frontend/src/care/AskCards.jsx` (each card), `frontend/src/care/Today.jsx`, `frontend/src/care/MyCare.jsx:18`, `frontend/src/care/Queue.jsx:25-51`

**Interfaces:**
- Produces (`faults.js`):
  - `makeFault(episodeId: string | null, scope: string, message: string) -> { episodeId, scope, message }`
  - `faultText(fault, episodeId: string | null, { only?: string[] | null, except?: string[] } = {}) -> string`. Returns the message only when `fault.episodeId === episodeId` and `fault.scope` starts with one of `only` (any scope when `only` is null) and with none of `except`. Otherwise `""`.
  - `INBOX_SCOPES = ["/questions/", "/reviews/"]`, `NUDGE_SCOPES = ["/nudges/"]`, `CLOCK = "clock"`, `STATUS = "status"`.
- Produces (`useWard()` return): drops `error`; adds `fault`, `loadError: string`, `clearFault()`. `act(id, path, body, scope = path)`, `upload(id, path, file, fields, scope = path)`, `ask(id, path, file, fields, scope = path)`. `jump`/`reset` fail with scope `CLOCK` and `episodeId: null`. `setDoctorStatus` fails with scope `STATUS` and `episodeId: null`.
- Produces: `<Fault fault episodeId only? except? />` renders `<p className="error small" role="alert">` or nothing.

- [ ] **Step 1: Capture the before shots.** Run `make demo-check MODEL_API_KEY=`, then copy `count-guard/demo-shots/` to `$TMPDIR/cg-before-shots/` (not committed). Task 8 compares against these.

- [ ] **Step 2: Write the failing tests** in `faults.test.js`:

```js
const f = makeFault("e9", "/ask/medicines", "No prescription");
test("a fault shows only on its own episode", () => {
  assert.equal(faultText(f, "e4"), "");
  assert.equal(faultText(f, "e9"), "No prescription");
  assert.equal(faultText(null, "e9"), "");
});
test("only and except pick the action", () => {
  assert.equal(faultText(f, "e9", { only: ["/ask/review"] }), "");
  assert.equal(faultText(f, "e9", { only: ["/ask/medicines"] }), "No prescription");
  const q = makeFault("e4", "/questions/q1/answer", "x");
  assert.equal(faultText(q, "e4", { except: INBOX_SCOPES }), "");
  assert.equal(faultText(q, "e4", { only: INBOX_SCOPES }), "x");
});
test("ward-wide faults have no episode", () => {
  assert.equal(faultText(makeFault(null, CLOCK, "m"), null, { only: [CLOCK] }), "m");
  assert.equal(faultText(makeFault(null, CLOCK, "m"), "e4"), "");
});
```

- [ ] **Step 3: Run `cd frontend && node --test src/care/faults.test.js`.** Expected: FAIL, module not found.

- [ ] **Step 4: Implement `faults.js` and `Fault.jsx`.**

- [ ] **Step 5: Rewire `ward.js`.** Replace `error` with `fault`. `run(id, send, scope)` sets `makeFault(id, scope, exc.message)`. The `loadWard()` catch sets `loadError`. A partial `jump` failure sets `makeFault(null, CLOCK, "The time moved, but …")` with the current wording.

- [ ] **Step 6: Place the faults and clear them.**
  - `CareShell`: delete the global `ward.error` line (`:141`). Add `useEffect(() => ward.clearFault(), [location.pathname, ward.role, ward.patientBed])`. `ClockBar` renders `<Fault only={[CLOCK]} episodeId={null}>`.
  - `Chart`: `<Fault except={[...INBOX_SCOPES, ...NUDGE_SCOPES]}>` directly under `StatePanel`. A second `<Fault only={NUDGE_SCOPES}>` sits directly under `AlertBanner`.
  - `AskInbox`: `only={INBOX_SCOPES}` inside its card. Its `/ask/hear` call passes the scope `` `/questions/${q.id}/answer` ``, so a hearing error lands in the inbox.
  - `Ask.jsx`: passes `fault` and `episodeId` in `props`. Each card renders `only={[path]}` inside its own `<section>`: `/ask/bot`, `/ask/doctor`, `/ask/review`, `/ask/medicines`.
  - `Today`: a `Fault` under `TodayPanel`.
  - `Queue`: an open nudge row renders `only={NUDGE_SCOPES}` for `row.episodeId`. The "My status" group renders `only={[STATUS]}` with `episodeId={null}`.
  - The `ward.error ||` loading fallbacks in Chart, Ask, Today and MyCare read `ward.loadError`.

- [ ] **Step 7: Run the care tests, then `npm run build`, then `make demo-check MODEL_API_KEY=`.** Expected: care 123 pass, build clean, demo check green. No beat text changes in this task.

- [ ] **Step 8: Commit.**

```bash
git add frontend/src/care
git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit -m "Count Guard: an error shows on its own patient, next to the action that raised it"
```

---

### Task 2: Clinic orders, open items first, plurals (A2, A3, A4)

**Files:**
- Modify: `frontend/src/care/tasklist.js` (add after `orderLines`), `frontend/src/care/OrderTasks.jsx:16-17`, `frontend/src/care/MyCare.jsx:29`, `frontend/src/care/askText.js`, `frontend/src/care/DoctorActions.jsx:236`, `frontend/src/care/Chart.jsx:64-76`, `backend/app/journey/stories.py:88,90`
- Test: `frontend/src/care/tasklist.test.js`, `frontend/src/care/askText.test.js`, `backend/tests/test_clarity_text.py`

**Interfaces:**
- Produces: `orderStatus(order, state: string) -> string` in `tasklist.js`.
- Produces: `doctorOpenItems(view) -> number` in `askText.js`. It counts unanswered questions with `to === "doctor"`, unanswered reviews, and nudges with `to === "doctor"`.

- [ ] **Step 1: Write the failing tests.**

```js
// tasklist.test.js
test("orderStatus says what happens to a clinic order", () => {
  const o = { acknowledged_by: null };
  assert.equal(orderStatus(o, "clinic"), "Starts when the patient is admitted");
  assert.equal(orderStatus(o, "clinic_done"), "Not started: the visit was closed.");
  assert.equal(orderStatus(o, "ward"), "Waiting for the nurse");
  assert.equal(orderStatus({ acknowledged_by: "Nurse Meena" }, "clinic_done"), "Acknowledged by Nurse Meena");
});
// askText.test.js
test("doctorOpenItems counts what waits on the doctor", () => {
  const view = { ask: { questions: [{ to: "doctor", answer: null }, { to: "bot", answer: null }, { to: "doctor", answer: {} }],
    reviews: [{ answer: null }] }, nudges: [{ to: "doctor" }, { to: "nurse" }] };
  assert.equal(doctorOpenItems(view), 3);
  assert.equal(doctorOpenItems({}), 0);
});
```

```python
# test_clarity_text.py
def test_ward_orders_and_rx_counts_are_singular():
    assert plain(ev("ward.orders_set", by="D", doses=[{}], obs_every_h=4)) == "Ward orders from D: 1 dose, observations every 4 h."
    assert plain(ev("rx.ordered", by="D", rows=[{}], source="demo")) == "Prescription from D: 1 medicine (demo)."
```

- [ ] **Step 2: Run the three test files.** Expected: FAIL (`orderStatus` and `doctorOpenItems` not exported; "1 doses").

- [ ] **Step 3: Implement.**
  - `OrderTasks` line 17 becomes `Signed by {by} at {time} · {orderStatus(order, state)}`.
  - `MyCare` line 29 becomes `Ordered by {by} · {orderStatus(order, view.state)}`.
  - `stories.py` uses `count_of(len(...), "dose")` and `count_of(len(...), "medicine")`.
  - `DoctorActions`: the fallback branch returns the "Nothing to do from this state…" line only when `doctorOpenItems(view) === 0`. Otherwise it returns `null`.
  - `Chart` order becomes: StateHeader, AlertBanner, AskInbox, StatePanel (+ its Fault), Photos, VideoChecks, OrderTasks, History. Safety alerts stay above the inbox because they drive NOW.

- [ ] **Step 4: Run the backend and care suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: all green, backend 358, care 125. No beat or document lines change: no expected string uses "Waiting for the nurse" or "doses", and `kumar-review` checks text, not order.

- [ ] **Step 5: Commit** (`frontend/src/care backend/app/journey/stories.py backend/tests/test_clarity_text.py`). Message: "Count Guard: clinic orders say what will happen, open items come first, plurals fixed".

---

### Task 3: The medicine photo matches signed dose orders (A5)

**Files:**
- Modify: `backend/app/journey/medicines.py`, `backend/app/journey/ask_api.py:29,156-174`
- Test: `backend/tests/test_p4_medicines.py`

**Interfaces:**
- Consumes: `orders_list(events)` from `app.journey.tasks`. Each order has `by` and `items` (`kind`, `name`, `amount`, `every_h`, `text`). The A1 card fault from Task 1 shows the 409 detail inside the Medicines photo card.
- Produces (`medicines.py`):
  - `dose_rows(orders: list[dict]) -> list[dict]`. One row per dose item that has a name: `{"key": key_of(name), "medicine": f"{name} {amount}".strip(), "strength": amount, "schedule": f"every {every_h:g} h" if every_h else "as ordered", "by": order["by"]}`.
  - `match_medicines(strips, rx: dict | None, doses: list[dict] = ()) -> dict`. A prescription row wins over a dose row with the same key.
  - `record_holds(orders: list[dict]) -> str`.
- Produces (`ask_api.py`): `NO_MEDICINES` replaces `NO_RX`. A 409 is returned only when there is no `rx.ordered` and `dose_rows` is empty.

Exact copy:
- Matched by dose order: `f"On your signed orders from {by}: {medicine}, {schedule}."`
- Dose order, strength differs (flag `strength_differs`, same rule as the prescription): `f"The strip reads {read}. Your signed orders say {medicine}."`
- Not matched: `f"{read} is not on {where}. Ask Dr. Rao about it."` `where` is `your prescription from {rx_by}`, `your signed orders`, or `your prescription from {rx_by} or your signed orders`.
- Summary: `f"{on} of {n} medicines in the photo are on {noun}."` `noun` is `your prescription`, `your signed orders`, or `your prescription or signed orders`. With no doses, `WHY_KUMAR` and the Iyer text are unchanged.
- `NO_MEDICINES = "There is no prescription or signed dose order on your record yet, so the medicines cannot be matched."`
- `record_holds`: `"Your record holds no orders yet."` or `"Your record holds signed orders for: " + "; ".join(item texts) + "."`
- 409 detail: `f"{NO_MEDICINES} {record_holds(orders)}"`

- [ ] **Step 1: Write the failing tests.**

```python
DOSE = [{"by": "Dr. A. Rao (synthetic)", "items": [{"kind": "dose", "name": "Paracetamol", "amount": "1 g", "every_h": 6, "text": "Paracetamol 1 g every 6 h"}]}]

def test_dose_order_matches_without_a_prescription():
    got = match_medicines(_strips(("Paracetamol", "1 g")), None, dose_rows(DOSE))
    row = got["rows"][0]
    assert row["prescribed"] and row["medicine"] == "Paracetamol 1 g" and row["schedule"] == "every 6 h"
    assert row["why"] == "On your signed orders from Dr. A. Rao (synthetic): Paracetamol 1 g, every 6 h."
    assert got["why"] == "1 of 1 medicines in the photo are on your signed orders."

def test_dose_order_without_interval_reads_as_ordered():
    rows = dose_rows([{"by": "D", "items": [{"kind": "dose", "name": "Ondansetron", "amount": "4 mg", "every_h": None, "text": "Ondansetron 4 mg"}]}])
    assert rows[0]["schedule"] == "as ordered"

def test_prescription_wins_over_a_dose_order():
    got = match_medicines(_strips(("Paracetamol", "650 mg")), _rx(), dose_rows(DOSE))
    assert got["rows"][0]["schedule"] == "as needed; As needed for pain; Max 3 times daily"

def test_no_record_names_what_the_record_holds(tmp_path):
    # das, clinic_done, no rx, no orders
    refused = _post(client, das)
    assert refused.status_code == 409
    assert refused.json()["detail"] == f"{NO_MEDICINES} Your record holds no orders yet."
```

Also: point `test_route_refusals` at `NO_MEDICINES + " Your record holds no orders yet."`. Add one route test: an episode with a signed dose order and no rx, moved to `home`, gets `200` and `match == "ok"`. Use the `test_route_offline_kumar_and_iyer` set-up, with the prepared strip read for that file name.

- [ ] **Step 2: Run `.venv/bin/python -m pytest backend/tests/test_p4_medicines.py -q`.** Expected: FAIL (`dose_rows` not defined).

- [ ] **Step 3: Implement `dose_rows`, `record_holds` and the widened `match_medicines`, then the route change.** Keep `medicine_strings_have_no_advice` green.

- [ ] **Step 4: Run the full backend suite and `make demo-check MODEL_API_KEY=`.** Expected: green. `iyer-meds` still reads "Pantoprazole 40 mg:" because Iyer has no dose orders. In a manual check, the Das 409 detail shows inside the "Medicines photo" card and nowhere else.

- [ ] **Step 5: Commit** (`backend/app/journey/medicines.py backend/app/journey/ask_api.py backend/tests/test_p4_medicines.py`). Message: "Count Guard: the medicine photo matches signed dose orders and says what the record holds".

---

### Task 4: One voice-first input everywhere (B1, B2)

**Files:**
- Modify: `frontend/src/care/Dictate.jsx` (rewrite), `frontend/src/care/DoctorActions.jsx:30,50-57,115`, `frontend/src/care/AskInbox.jsx:22-57`, `frontend/src/care/TaskProof.jsx:39-51`, `backend/app/journey/media_api.py:35-42,78-133`, `backend/app/journey/ask_api.py:90-101` (docstring only)
- Create: `frontend/src/care/care.css`, imported once from `CareShell.jsx`. Move `styles.css` lines 396-409 (Care shell block) and 411-443 (Chart block) into it.
- Test: `backend/tests/test_p2_dictation.py`
- Demo: `frontend/scripts/demo/beats.mjs`, `frontend/scripts/demo/steps.mjs`, `docs/demo/count-guard-v2-video-script.md`

**Interfaces:**
- Consumes: `ward.ask(id, path, file, fields, scope)` (Task 1). `answerHow(heardText, currentText, heardBy) -> { via, heard_by }` (`askText.js`, unchanged).
- Produces:
  - `Dictate({ label, field = "What was said", verb, busy, maxLength = 2000, onHear, onSend })`.
  - `onHear(file: File) -> Promise<{ text: string, heard_by: string } | null>`.
  - `onSend({ text: string, heard: { text: string, by: string } | null }) -> Promise<truthy | falsy>`. A truthy result clears the box and `heard`.
  - Section `aria-label={label}`. Textarea label `field`. Mic button `aria-label` is "Record", or "Finish recording" while recording. "Upload audio" is a `<label>` that wraps a visually hidden `input[type=file][accept="audio/*"]`. A "Heard by: {sourceLabel(heard.by)}" line shows while `heard` is set. The primary verb button is disabled while `busy`, while recording, or while the box is empty.
- Produces (backend): `_heard(settings, file, text, heard_by: str = "")`. Typed text gives `source = heard_by or "typed"`. `heard_by` is ignored when a file is sent. `/dictate/orders`, `/dictate/discharge` and `/dictate/task` accept `heard_by: str = Form("", max_length=40)`.

Callers:

| Caller | label | field | verb | onHear → onSend |
|---|---|---|---|---|
| Orders (DoctorActions) | Dictate orders | What was said | Draft orders | `ask("/ask/hear", f, {by: DOCTOR}, "/dictate/orders")` → `upload("/dictate/orders", undefined, {text, by, heard_by})` |
| Discharge (DoctorActions) | Dictate discharge | What was said | Draft discharge | same, path `/dictate/discharge` |
| Answer (AskInbox, B2) | Your answer | Your answer (check it before sending) | Send answer | `ask("/ask/hear", f, {by: DOCTOR}, answerPath)` → `act(answerPath, {text, by, ...answerHow(...)})`. `maxLength={1000}`. The second textarea and the separate "Heard by" line go. |
| Task (TaskProof) | Complete a task by voice | What was said | Use this | `ask("/ask/hear", f, {by}, "/dictate/task")` → `ask("/dictate/task", undefined, {text, by, heard_by})`. `session.via` comes from `answerHow`. |

In every row, `heard_by` comes from `answerHow(heard?.text, text, heard?.by).heard_by`. Dictate is keyed per episode already, through `StatePanel key` and `AskInbox key`, so a box never carries text to another patient.

- [ ] **Step 1: Write the failing backend tests** in `test_p2_dictation.py`:

```python
def test_typed_text_keeps_the_hearer_it_was_heard_by(tmp_path):
    # POST dictate/orders data={by, text: ORDERS_TEXT, heard_by: "prepared"}
    assert view["drafts"]["order"]["heard_by"] == "prepared"

def test_hearer_is_ignored_with_a_recording(tmp_path):
    # POST dictate/orders with the kumar-orders.wav file and heard_by="forged"
    assert view["drafts"]["order"]["heard_by"] == "prepared"
```

The existing `heard_by == "typed"` test (`:94`) stays as the no-hearer case.

- [ ] **Step 2: Run `.venv/bin/python -m pytest backend/tests/test_p2_dictation.py -q`.** Expected: FAIL (`heard_by` is `"typed"`).

- [ ] **Step 3: Implement the backend `heard_by` field.** Change the `/ask/hear` docstring to "What was said, as text to check. Any role. Writes nothing."

- [ ] **Step 4: Rewrite `Dictate` and its four callers as in the table.** Add `.dictate-box` (relative; textarea `padding-right: 56px`), `.dictate-mic` (40 px round, absolute top 8 px right 8 px), `.dictate-upload` (small link style) and `.visually-hidden` to `care.css`. Confirm `wc -l` for `styles.css` and `care.css` are both under 480.

- [ ] **Step 5: Update the demo for the new names and the extra verb click.**
  - `steps.mjs`:
    - `kumar-orders`: add `H.click("Draft orders")` after the file.
    - `kumar-paracetamol`: add `H.click("Use this")` after the wav, before `before(...)`.
    - `kumar-discharge`: add `H.click("Draft discharge")` after the wav, before `before(...)`.
    - `kumar-review`: `H.file("Your answer", "eval/p2/rao-answer.wav")`.
    - `iyer-orders`: add `H.click("Draft orders")` before "Sign orders".
    - `iyer-recheck`: `H.fill("What was said", "BP 112 over 70, pulse 84, bed 7.", VOICE)` then `H.click("Use this")`.
  - `beats.mjs` clicks get the same changes as strings:
    - `'Button "Draft orders"'` (kumar-orders, iyer-orders)
    - `'Button "Use this"'` (kumar-paracetamol, iyer-recheck)
    - `'Button "Draft discharge"'` (kumar-discharge)
    - `into "Your answer"` (kumar-review)
    - `'Textarea "What was said" in "Complete a task by voice" <- …'` (iyer-recheck)
  - `keyed` of kumar-orders, kumar-discharge and iyer-orders: "Live speech can be replaced by typing in the box."
  - Document lines that change: 82, 147, 161, 182, 206, 227 (Clicks lines, same strings), 268 ("Live speech can use the mic button, the WAV files, or typing in the box."), 274, 277, 280 (keyed). Expected strings are unchanged: `HEARD` still shows in the Dictate "Heard by" line, and in the draft once `heard_by` is passed.

- [ ] **Step 6: Run the backend, care and demo suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: all green, 31 beats, 58/58/58.

- [ ] **Step 7: Commit** (`frontend/src backend/app/journey/media_api.py backend/app/journey/ask_api.py backend/tests/test_p2_dictation.py frontend/scripts/demo ../docs/demo/count-guard-v2-video-script.md`). Message: "Count Guard: one voice-first input; the doctor answers in one box".

---

### Task 5: Buttons, rows and names read right (B3, B6, B8, B9)

**Files:**
- Create: `frontend/src/care/rows.js`, `frontend/src/care/rows.test.js`, `frontend/src/care/styles.test.js`
- Modify: `frontend/src/care/tasklist.js`, `frontend/src/care/NurseActions.jsx:70-72`, `frontend/src/styles.css:241` (`button:disabled`), `frontend/src/care/care.css` (`.clock-bar button:disabled`, `.row-link`, `.open-cue`), `frontend/src/care/Queue.jsx:16-24,88-95`, `frontend/src/care/Patients.jsx:22-26`, `frontend/src/care/AskCards.jsx:34,67,129`
- Test: `frontend/src/care/tasklist.test.js`
- Demo: `beats.mjs` (das-ask, kumar-ask, iyer-meds clicks), `steps.mjs` (same three), document lines 65, 175, 248

**Interfaces:**
- Produces: `markDone(due: string) -> { label: string, primary: boolean }` in `tasklist.js`.
- Produces: `opensRow(target: { closest(sel: string): unknown }) -> boolean` in `rows.js`. It is false when `target.closest("a, button, input, textarea, select, label")` is truthy.

- [ ] **Step 1: Write the failing tests.**

```js
test("markDone: due work is primary, later work is early", () => {
  assert.deepEqual(markDone("overdue"), { label: "Mark done", primary: true });
  assert.deepEqual(markDone("due"), { label: "Mark done", primary: true });
  assert.deepEqual(markDone("later"), { label: "Mark done early", primary: false });
});
test("opensRow ignores clicks on the row's own controls", () => {
  assert.equal(opensRow({ closest: () => null }), true);
  assert.equal(opensRow({ closest: (s) => (s.includes("button") ? {} : null) }), false);
});
test("disabled buttons are outlined, never filled", () => {
  const css = fs.readFileSync(new URL("../styles.css", import.meta.url), "utf8");
  assert.match(css, /button:disabled[^{]*\{[^}]*background:\s*transparent/);
  assert.match(css, /button\.primary:disabled/);
});
```

- [ ] **Step 2: Run the three care test files.** Expected: FAIL.

- [ ] **Step 3: Implement.**
  - B3: `TaskRow` uses `markDone(due)` for the label and the `primary` class.
  - B6: `button:disabled, button.primary:disabled, .button.primary:disabled { background: transparent; border-color: var(--line); color: var(--ink-muted); opacity: 1; cursor: not-allowed; }` with no hover fill. Set `.clock-bar button:disabled` to match.
  - B8, queue: the queue `<tr>` gets `className="row-link"` and `tabIndex={0}`. `onClick={(e) => opensRow(e.target) && navigate(to)}`. `onKeyDown`: Enter with `e.target === e.currentTarget` navigates. "Open →" stays.
  - B8, lists: the My patients and Patients `<Link>` rows add `<span className="open-cue">Open →</span>`.
  - B9: `aria-label` "Ask the record" becomes "Ask your record", "Ask the doctor" becomes "Ask Dr. Rao", "Medicine photo" becomes "Medicines photo". The button texts stay the same.

- [ ] **Step 4: Update the demo.**
  - `steps.mjs`: das-ask fill scope "Ask your record". kumar-ask fill scope "Ask Dr. Rao". iyer-meds `H.file("Medicines photo", …)`.
  - `beats.mjs` clicks: `'Textarea in "Ask your record" <- …'`, `'Textarea in "Ask Dr. Rao" <- …'`, `'File input in "Medicines photo" <- …'`.
  - Document lines 65, 175 and 248 get the same strings.
  - `kumar-review`'s `getByRole("link", { name: /Open/ })` still resolves, so it is unchanged.

- [ ] **Step 5: Run the care and demo suites, the build and `make demo-check MODEL_API_KEY=`.** Expected: green.

- [ ] **Step 6: Commit.** Message: "Count Guard: due work looks primary, disabled looks disabled, rows open, names match headings".

---

### Task 6: The patient reads "you" (B4)

**Files:**
- Modify: `backend/app/journey/states.py:165-221`, `frontend/src/care/StateHeader.jsx`, `frontend/src/care/Today.jsx:15`, `frontend/src/care/MyCare.jsx:23`, `frontend/src/care/Ask.jsx:20`
- Test: `backend/tests/test_flow_states.py`

**Interfaces:**
- Produces: `_latest_happening(events, you: bool = False) -> str | None`. `now_next(events)` returns `{"now", "next", "you_now"}`. `next` is shared by both lenses.
- Produces: `StateHeader({ patient, view, alert, you = false })`. With `you`, NOW reads `view.now_next.you_now`.

Exact copy for `you=True` (`{n}` = `short_name(p["by"])`, `{t}` = `clock(ts)`):

| Event | Patient line |
|---|---|
| seeded `patient.state` | `You were admitted to the ward the day before.` |
| `patient.state` | `{n} {YOU_DID[to]} at {t}.` with `YOU_DID = {"admitting": "admitted you", "clinic_done": "closed your visit", "ward": "moved you to the ward", "theatre": "sent you to theatre", "discharging": "signed your discharge", "home": "completed your discharge"}` |
| `order.signed` | `{n} signed new orders for you at {t}.` |
| `order.acknowledged` | `{n} acknowledged your orders at {t}.` |
| `task.done`, dose kind | `{n} gave {name} {amount} at {t}.` (from the `task.created` payload; the title is the fallback) |
| `task.began` / other `task.done` | `{n} began {title} at {t}.` / `{n} finished {title} at {t}.` |
| `question.asked` to doctor | `You sent a question to the doctor at {t}.` |
| `question.answered` by doctor | `{n} answered your question at {t}.` |
| `review.requested` | `You sent a healing photo at {t}.` |
| `review.answered` | `{n} reviewed your healing photo at {t}: {label}.` |
| nothing | `You are in clinic.` |

- [ ] **Step 1: Write the failing tests.**

```python
def test_patient_now_speaks_to_you(tmp_path):
    # home episode; patient posts ask/review at a known ms
    assert view["now_next"]["you_now"] == f"You sent a healing photo at {clock(ts)}."
    assert view["now_next"]["now"].startswith("R. Kumar sent a healing photo")

def test_patient_now_names_the_nurse_who_gave_a_dose(tmp_path):
    # ward episode; dose task (Paracetamol, 1 g) done by "Nurse Meena (synthetic)"
    assert view["now_next"]["you_now"].startswith("Nurse Meena gave Paracetamol 1 g at ")
    assert view["now_next"]["now"].startswith("Nurse Meena (synthetic) finished ")
```

Extend `test_no_advice_words_in_now_next` to scan `you_now` too.

- [ ] **Step 2: Run `.venv/bin/python -m pytest backend/tests/test_flow_states.py -q`.** Expected: FAIL (`KeyError: 'you_now'`).

- [ ] **Step 3: Implement `you` in `_latest_happening` and `now_next`.** Then pass `you` from the three patient pages.

- [ ] **Step 4: Run the backend suite, the build and `make demo-check MODEL_API_KEY=`.** Expected: green. No patient beat expects a NOW string: `kumar-ask` checks NEXT ("The doctor reviews the healing photo."), which is unchanged.

- [ ] **Step 5: Commit.** Message: "Count Guard: the patient's NOW line speaks to the patient".

---

### Task 7: Compact demo chrome on a phone; own alerts first (B5, B7)

**Files:**
- Create: `frontend/src/care/fold.js`, `frontend/src/care/fold.test.js`
- Modify: `frontend/src/care/CareShell.jsx` (header, nav-bar, `Strip`, `ClockBar`), `frontend/src/care/alerts.js:10-16`, `frontend/src/care/derive.js:178-189` (add `role: r.role` to each pill), `frontend/src/care/care.css`
- Test: `frontend/src/care/alerts.test.js` (update the four `stripPills` tests to `.mine`, and give the `pill` helper a `role` argument)

**Interfaces:**
- Produces: `stripPills(pills, episodeId, role) -> { mine: Pill[], others: { role: string, text: string, pills: Pill[] }[] }`. Chart filtering and text are unchanged. `others` has one group per other role, in the order nurse, doctor, patient, with `text` = `+${n} for ${role}`.
- Produces: `foldsOnPhone(control: "picker" | "role" | "models" | "doctor" | "banner" | "clock", role: string) -> boolean`. True for every control except `"doctor"` when `role === "patient"`.

- [ ] **Step 1: Write the failing tests.**

```js
test("stripPills puts the role's own pills first and folds the rest", () => {
  const pills = [pill("e4", "R. Kumar", "Nurse", "a", "nurse"), pill("e7", "S. Iyer", "Dr. A. Rao", "b", "doctor"), pill("e7", "S. Iyer", "Nurse", "c", "nurse")];
  const out = stripPills(pills, undefined, "doctor");
  assert.deepEqual(out.mine.map((p) => p.what), ["b"]);
  assert.deepEqual(out.others.map((g) => g.text), ["+2 for nurse"]);
});
test("stripPills with no own pills still shows the folded ones", () => {
  const out = stripPills([pill("e4", "R. Kumar", "Nurse", "a", "nurse")], undefined, "doctor");
  assert.equal(out.mine.length, 0);
  assert.equal(out.others[0].text, "+1 for nurse");
});
test("foldsOnPhone keeps the doctor chip out for the patient", () => {
  assert.equal(foldsOnPhone("doctor", "patient"), false);
  assert.equal(foldsOnPhone("doctor", "nurse"), true);
  for (const c of ["picker", "role", "models", "banner", "clock"]) assert.equal(foldsOnPhone(c, "patient"), true);
});
```

- [ ] **Step 2: Run the alerts and fold tests.** Expected: FAIL.

- [ ] **Step 3: Implement.**
  - B7: `Strip` renders `mine`. Each `others` group renders a `<button className="pill wait" aria-expanded>` with its `text`. Tapping it shows that group's pills inline.
  - B5: `CareShell` keeps its DOM order. Every control where `foldsOnPhone` is true gets the class `demo-fold`. A `<button className="demo-toggle" aria-expanded>Demo controls</button>` sits in the header. It sets `demo-open` on `.app`.
  - B5 CSS: `.demo-toggle { display: none }`. In `@media (max-width: 640px)`: `.demo-toggle { display: inline-flex; min-height: 36px }` and `.app:not(.demo-open) .demo-fold { display: none }`. Desktop is unchanged because the toggle is hidden and nothing is folded above 640 px.

- [ ] **Step 4: Run the care suite, the build and `make demo-check MODEL_API_KEY=`.** The run is at 1200 px, so the chrome is unfolded. Expected: green. If an expected string came only from another role's strip pill, `waitText` fails. Fix it in this task by expanding the group in the step (`H.click("+1 for nurse")`), and add the same click to the beat and document line.

- [ ] **Step 5: Commit.** Message: "Count Guard: demo controls fold on a phone; each role sees its own alerts first".

---

### Task 8: Full verification and the off-script walk

**Files:**
- Modify: only what a failure below points at, in the owning file.

- [ ] **Step 1: Run every suite.** Backend, care and demo all pass, with counts at or above 357/120/36 plus this branch's new tests. `npm run build` is clean. `wc -l frontend/src/styles.css frontend/src/care/*.css frontend/src/care/*.jsx` shows every file under 500.

- [ ] **Step 2: Run `make demo-check MODEL_API_KEY=`.** Expected: "31 beats", 58/58/58 s. Diff `demo-shots/` against `$TMPDIR/cg-before-shots/` by eye, beat by beat.

- [ ] **Step 3: Start the servers.** Run `make dev CG_API_PORT=8200 CG_WEB_PORT=5273 MODEL_API_KEY=`. Never use 8100/5173.

- [ ] **Step 4: Walk off script with playwright.** Watch console errors and failed requests. Each item must hold:
  - Every role in every state: clinic, clinic_done, admitting, ward, theatre, discharging, home.
  - Photo instead of video for a set-up check.
  - Clinic orders read "Starts when the patient is admitted", then "Not started: the visit was closed." after Close visit.
  - Surgeon theatre buttons: Surgery began and Surgery ended.
  - Patient: ask, healing photo, and medicines photo with and without a record. The Das reason shows inside the card and is gone after a role change.
  - Phone width 390 px: the Demo controls fold and the doctor chip stays for the patient.
  - Expected: zero console errors and zero failed requests other than deliberate 409s, which show inside their card.

- [ ] **Step 5: Stop the servers.** Fix any failure in the owning task's files. Re-run Steps 1–2 after a fix.

- [ ] **Step 6: Commit any fixes.** Message: "Count Guard v2 UX refinement: verification fixes". Skip the commit when nothing changed. List the changed files.

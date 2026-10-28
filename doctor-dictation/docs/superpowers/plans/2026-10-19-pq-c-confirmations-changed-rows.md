# PQ-c: a spoken correction clears only the changed rows' confirmations — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After a spoken correction, the doctor's "Confirmed by you" stays on every medicine row the correction did not
change, and is cleared only on the rows it changed, added or renamed.

**Architecture:** The server already decides, row by row, which rows a correction touched: it restores the prior
verification state of every other row (`preserve_untouched_rx_status`, `doctor_dictation/core/correction.py:364-413`).
We expose that same decision as `changed_rows: list[int]` on the `/api/v1/correct` response. The page keys
confirmations on a stable row id (`frontend/app.js:38`, `:859`), but `renderRx` mints new ids on every render
(`frontend/app.js:894-902`). So the page maps each returned row back to its prior row by **name + occurrence**, the
same pairing the server uses, and re-renders unchanged rows under their old row id. A confirmation then follows the
medicine, not the index. When the page cannot trust the answer, it clears all confirmations, as today.

**Tech Stack:** Python 3 / FastAPI (server), vanilla JS (page), pytest + node (`tests/test_frontend_*.py` style:
pure rules run under node, wiring checked as comment-stripped text).

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` section 4, fix idea 1. Shared
contract: `docs/superpowers/plans/2026-10-19-pq-00-index.md` ("Correction response (plan c)").

**Owner answers 2026-10-19:** Q8 OK and Q9 OK (the plan stands as written). Q10 no prior-index field: the response
carries only `changed_rows`; the page pairs returned rows to prior rows by name + occurrence (design decision 2). No
task changes.

## Global Constraints

- Response field name and type are fixed by the index: `changed_rows: list[int]`, indexes into the returned `structured.rx`.
- Files stay under 500 lines. `frontend/app.js` (1251 lines) is already over: new logic goes into the pure module
  `frontend/rxstate.js` (175 lines); `app.js` gets only the wiring (about 6 changed lines).
- Tests run with `.venv/bin/python -m pytest -q -x tests/<file>`; the autouse `DB_PATH` fixture (`tests/conftest.py:29-34`) keeps the dev DB safe.
- Bump the `?v=` pins of every changed static file by one from the value the preflight finds (at 9bf466e:
  `rxstate.js?v=7` at `frontend/index.html:258`, `app.js?v=36` at `frontend/index.html:265`).
- No commit without the owner's word: the "Commit" steps mean "ask the owner, then commit".
- **Not in this plan** (not approved): fix idea 2 (store `confirmed_by` / `confirmed_at` on the row, survive save and
  reopen) and fix idea 3 (row fingerprint of name, strength, form, dose). Also not here: sending confirmations in the
  `/api/v1/correct` request, and recording confirmations in the stored prescription (spec section 4 table, rows 2-4).

## Design decisions

**1. What counts as "changed" (server).** A returned row is changed when the server did **not** restore its prior
state, i.e. exactly the `continue` branch at `correction.py:389`:

- its name key is named by the patch (`_patch_rx_names`, `correction.py:329-338`) or renamed by a spoken
  `replace` (`touched` from `apply_ops`, `core/ops.py:154-155`), or
- it has no prior row of the same name key left (a new medicine appended by `_merge_rx`, `correction.py:227-228`,
  or a row whose name validation changed).

This reuses one pairing function for both `preserve_untouched_rx_status` and `changed_rx_rows`, so the two can
never disagree.

**2. How confirmations follow rows (page).** Indexes shift when a correction removes a row (`core/ops.py:130`) or
appends one. Example:

```
before (sent)       rowid  confirmed      correction: "remove Pantoprazole, add Cetirizine"
0 Pantoprazole      r1     yes            after (returned)     changed_rows = [2]
1 Dolo 650          r2     yes     --->   0 Dolo 650     carry r2  -> still confirmed
2 Zyloric           r3     no             1 Zyloric      carry r3
                                          2 Cetirizine   null (new id, not confirmed)
```

The page pairs each returned row with the next unused prior row of the same name key (`trim().toLowerCase()`, the
JS twin of `_norm_name`, `correction.py:82-84`), in page order. Like the server (`correction.py:388`), a changed
row still **uses up** its prior slot, so a later same-name row keeps its own. Changed rows get `null` (a fresh id).
Confirmations survive only on carried ids that are still in `state.confirmed` when the response arrives.

**3. Fallback: clear all.** The page clears every confirmation (today's behaviour) when `changed_rows` is missing,
not an array, or holds anything other than a whole number in `0 .. rx.length-1`. The server sends every index as
changed when either `rx` is not a list (it cannot pair).

**4. Known limit.** A carried row keeps "Confirmed by you" but loses the finer "you chose the strength" detail
(`r.how`, `frontend/rxview.js:30-31`), because the row element is rebuilt. Accepted: the save gate only reads the
confirmed set.

## File structure

| File | Change | Responsibility |
|---|---|---|
| `doctor_dictation/core/correction.py` | Modify `:364-413`, add ~20 lines | Shared prior-row pairing; `changed_rx_rows` |
| `doctor_dictation/api/format.py` | Modify `:13-21`, `:216-228` | Return `changed_rows` |
| `frontend/rxstate.js` | Add `carryRowids`, export at `:174` | Pure page rule: which prior row id each returned row keeps |
| `frontend/app.js` | Modify `:560-575`, `:855-859`, `:894-902`, `:907-921` | Wiring only |
| `frontend/index.html` | Modify `:258`, `:265` | Pin bumps |
| `tests/test_correction_changed_rows.py` | Create | Server unit + endpoint tests |
| `tests/test_frontend_carry_confirmed.py` | Create | Node tests for `carryRowids`; app.js wiring as text; pins |

## Review Focus

1. **The model echoes an untouched row in its patch** (LLM returns `{"rx":[{"name":"Dolo 650"}]}` unasked): that row
   is "named", so its confirmation clears. Expected and safe (conservative). Pinned in Task 1 (`test_echoed_row_counts_as_changed`).
2. **Two rows with the same name, the correction names that name:** both are changed (the key is named), both
   confirmations clear. Pinned in Task 1 (`test_a_named_duplicate_marks_every_row_of_that_name`).
3. **A response without `changed_rows`** (an old server behind a fresh page, a proxy error body): clear all. Pinned in
   Task 3 (`test_bad_changed_rows_fall_back_to_clear_all`).
4. **A row removed above a confirmed row:** the confirmation follows the medicine to its new index. Pinned in Task 2
   (endpoint) and Task 3 (page rule).
5. **An untouched row comes back with different clinical text** (validation rewrote its strength or dose): the carried
   confirmation would then vouch for text the doctor never saw. Pinned in Task 2
   (`test_untouched_row_clinical_fields_come_back_identical`); if it ever fails, that row must be reported as changed.

---

### Task 1: `changed_rx_rows` in `core/correction.py`

**Files:**
- Modify: `doctor_dictation/core/correction.py:364-413`
- Test: `tests/test_correction_changed_rows.py` (create)

**Interfaces:**
- Consumes: `_norm_name` (`correction.py:82`), `_patch_rx_names` (`:329`).
- Produces:
  - `_paired_prior(current: dict, structured: dict) -> list[dict | None]` — one entry per `structured["rx"]` item: the
    prior row paired by name key + occurrence (deque per key, popped for every output row of that key), `None` when
    none is left or the item is not a dict.
  - `changed_rx_rows(current: dict, patch: dict, structured: dict, extra_named=()) -> list[int]` — sorted indexes of
    `structured["rx"]` whose key is in `_patch_rx_names(patch) | {_norm_name(n) for n in extra_named}` or whose paired
    prior is `None`; non-dict items count as changed. When `current["rx"]` or `structured["rx"]` is not a list:
    every index of `structured["rx"]` (or `[]` when that is not a list). Pure: never mutates its inputs.

- [ ] **Step 0: Preflight.** Re-read `doctor_dictation/core/correction.py:329-413` and `doctor_dictation/api/format.py:180-228`
  (plans a and b run first and may have moved lines). Note the current line count of `correction.py`; it must stay < 500.

- [ ] **Step 1: Write the failing tests** in `tests/test_correction_changed_rows.py` (reuse the `_prior` / `_fresh`
  shapes of `tests/test_same_name_rows.py:16-22`).

```python
from doctor_dictation.core.correction import changed_rx_rows

def _rx(*names): return {"rx": [{"name": n, "dose": "1-0-0"} for n in names]}

def test_nothing_named_nothing_changed():
    assert changed_rx_rows(_rx("Dolo 650", "Zyloric"), {}, _rx("Dolo 650", "Zyloric")) == []

def test_named_row_is_changed():
    assert changed_rx_rows(_rx("Dolo 650", "Zyloric"), {"rx": [{"name": "zyloric "}]}, _rx("Dolo 650", "Zyloric")) == [1]

def test_appended_new_medicine_is_changed():
    assert changed_rx_rows(_rx("Dolo 650"), {"rx": [{"name": "Cetirizine"}]}, _rx("Dolo 650", "Cetirizine")) == [1]

def test_removed_row_shifts_indexes_and_nothing_else_changes():
    # current is the PRE-ops form, as format.py passes it; Pantoprazole was removed by apply_ops
    assert changed_rx_rows(_rx("Pantoprazole", "Dolo 650", "Zyloric"), {}, _rx("Dolo 650", "Zyloric")) == []

def test_renamed_row_is_changed_via_extra_named():
    assert changed_rx_rows(_rx("Cephixime", "Dolo 650"), {}, _rx("Cefixime", "Dolo 650"), extra_named={"cefixime"}) == [0]

def test_a_named_duplicate_marks_every_row_of_that_name():
    assert changed_rx_rows(_rx("Amlodipine", "Dolo 650", "Amlodipine"), {"rx": [{"name": "Amlodipine"}]},
                           _rx("Amlodipine", "Dolo 650", "Amlodipine")) == [0, 2]

def test_echoed_row_counts_as_changed():
    assert changed_rx_rows(_rx("Dolo 650"), {"rx": [{"name": "Dolo 650"}]}, _rx("Dolo 650")) == [0]

def test_a_name_validation_changed_has_no_prior_and_is_changed():
    assert changed_rx_rows(_rx("dolo"), {}, _rx("Dolo 650")) == [0]

def test_cannot_pair_means_every_row_changed():
    assert changed_rx_rows({"rx": "garbage"}, {}, _rx("A1", "B1")) == [0, 1]
    assert changed_rx_rows({}, {}, {"rx": None}) == []
    assert changed_rx_rows(_rx("A1"), {}, {"rx": ["x", {"name": "A1"}]}) == [0]

def test_inputs_are_not_mutated():
    cur, out = _rx("A1"), _rx("A1")
    snap = (repr(cur), repr(out))
    changed_rx_rows(cur, {"rx": [{"name": "A1"}]}, out)
    assert (repr(cur), repr(out)) == snap
```

- [ ] **Step 2: Run to verify they fail.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_correction_changed_rows.py`
  Expected: FAIL, `ImportError: cannot import name 'changed_rx_rows'`.

- [ ] **Step 3: Implement.** Extract the pairing loop of `preserve_untouched_rx_status` (`correction.py:377-388`)
  into `_paired_prior`, make `preserve_untouched_rx_status` iterate `zip(out_rows, _paired_prior(current, structured))`
  with unchanged behaviour, and add `changed_rx_rows` next to it, with a docstring that says it is the exact set
  `preserve_untouched_rx_status` does not restore.

- [ ] **Step 4: Run the new tests and the pairing regression suites.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_correction_changed_rows.py tests/test_same_name_rows.py tests/test_correction.py tests/test_correction_ops.py`
  Expected: all PASS.

- [ ] **Step 5: Commit** (ask the owner first): `git add doctor_dictation/core/correction.py tests/test_correction_changed_rows.py`,
  message `Correction: changed_rx_rows shares the prior-row pairing with preserve_untouched_rx_status`.

---

### Task 2: `/api/v1/correct` returns `changed_rows`

**Files:**
- Modify: `doctor_dictation/api/format.py:13-21` (import), `:221-228` (compute, return)
- Test: `tests/test_correction_changed_rows.py` (append)

**Interfaces:**
- Consumes: `changed_rx_rows` (Task 1).
- Produces: response key `"changed_rows": list[int]` on every 200 response of `POST /api/v1/correct`, computed as
  `changed_rx_rows(current, patch2, structured, extra_named=touched)` right after the
  `preserve_untouched_rx_status(...)` call at `format.py:221`. The 403 path (`format.py:198-201`) is unchanged.

- [ ] **Step 1: Write the failing endpoint tests.** Copy `_client` and `_stub_llm` from `tests/test_correction.py:83-118`
  (`tests/` has no `__init__.py`, so they cannot be imported).

```python
CUR = [{"form": "Tab.", "name": "Pantoprazole", "strength": "40 mg", "dose": "1-0-0", "instructions": "", "status": "verified", "lexicon_match": "Pantoprazole"},
       {"form": "Tab.", "name": "Paracetamol", "strength": "650 mg", "dose": "SOS", "instructions": "", "status": "verified", "lexicon_match": "Paracetamol"},
       {"form": "Tab.", "name": "Tamsulosin", "strength": "0.4 mg", "dose": "0-0-1", "instructions": "", "status": "verified", "lexicon_match": "Tamsulosin"}]

def test_offline_empty_correction_changes_no_row(monkeypatch):
    j = _client(monkeypatch).post("/api/v1/correct", json={"transcript": "", "current_form": {"rx": CUR}}).json()
    assert j["changed_rows"] == []

def test_dose_change_reports_only_that_row(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]})
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "paracetamol twice daily", "current_form": {"rx": CUR}}).json()
    assert [r["name"] for r in j["structured"]["rx"]] == ["Pantoprazole", "Paracetamol", "Tamsulosin"]
    assert j["changed_rows"] == [1]

def test_remove_above_and_append_shift_indexes(monkeypatch):
    _stub_llm(monkeypatch, {"remove": {"rx": ["Pantoprazole"]}, "rx": [{"name": "Cetirizine", "strength": "10 mg", "dose": "0-0-1"}]})
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "remove pantoprazole add cetirizine", "current_form": {"rx": CUR}}).json()
    assert [r["name"] for r in j["structured"]["rx"]] == ["Paracetamol", "Tamsulosin", "Cetirizine"]
    assert j["changed_rows"] == [2]

def test_spoken_rename_reports_the_renamed_row(monkeypatch):
    _stub_llm(monkeypatch, {"replace": {"rx": [{"from": "Tamsulosin", "to": "Silodosin"}]}})
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "not tamsulosin, silodosin", "current_form": {"rx": CUR}}).json()
    assert j["structured"]["rx"][2]["name"] == "Silodosin" and j["changed_rows"] == [2]

def test_untouched_row_clinical_fields_come_back_identical(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Paracetamol", "dose": "1-0-1"}]})
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "paracetamol twice daily", "current_form": {"rx": CUR}}).json()
    keys = ("form", "name", "strength", "dose", "instructions", "status")
    for i in (0, 2):
        assert {k: j["structured"]["rx"][i].get(k, "") for k in keys} == {k: CUR[i][k] for k in keys}

def test_missing_current_form_gives_empty_changed_rows(monkeypatch):
    j = _client(monkeypatch).post("/api/v1/correct", json={"transcript": ""}).json()
    assert j["structured"]["rx"] == [] and j["changed_rows"] == []
```

  If a stubbed name is not in the shipped lexicon and a test needs a verified row, swap it for one the existing
  tests already use (`tests/test_correction.py:136-200`); keep the assertions.

- [ ] **Step 2: Run to verify they fail.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_correction_changed_rows.py`
  Expected: FAIL with `KeyError: 'changed_rows'`.

- [ ] **Step 3: Implement** the import and the response key in `doctor_dictation/api/format.py`; extend the
  `correct` docstring (`format.py:188-198`) with one sentence: `changed_rows` lists the returned rx rows whose
  prior state was not restored; the page keeps confirmations on the others.

- [ ] **Step 4: Run.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_correction_changed_rows.py tests/test_correction.py tests/test_same_name_rows.py tests/test_api_app.py`
  Expected: all PASS.

- [ ] **Step 5: Commit** (ask first): `git add doctor_dictation/api/format.py tests/test_correction_changed_rows.py`,
  message `/api/v1/correct returns changed_rows`.

---

### Task 3: `RxState.carryRowids` (pure page rule)

**Files:**
- Modify: `frontend/rxstate.js` (new function before `stripMarker`; export at `:174`)
- Test: `tests/test_frontend_carry_confirmed.py` (create; copy the `_node` helper of `tests/test_frontend_rxrow.py:20-26`)

**Interfaces:**
- Produces: `RxState.carryRowids(priorRowids, priorRows, nextRows, changed) -> Array<string | null>`
  - `priorRowids[i]` is the row id of `priorRows[i]` (the `indexToRowid` and `structured.rx` that `serializeForm`
    returns, `frontend/app.js:646-662`); `nextRows` is the response `structured.rx`; `changed` is `j.changed_rows`.
  - Returns one entry per `nextRows` item (`[]` when `nextRows` is not an array).
  - All `null` when `changed` is not an array, or any entry is not an integer (`Number.isInteger`) in `0 .. nextRows.length-1`.
  - Otherwise: per name key (`String(name ?? "").trim().toLowerCase()`, strings only, else `""`), a queue of prior
    indexes in page order. Each next row pops its key's queue (even when changed). It gets `priorRowids[popped]` only
    when its index is not in `changed`, the pop succeeded, and that id is a non-empty string; else `null`.
    Non-object rows get `null` and pop nothing. An id is never returned twice.

- [ ] **Step 1: Write the failing node tests.**

```python
R = lambda *names: json.dumps([{"name": n} for n in names])
def carry(ids, prior, nxt, changed): return _node(f"RxState.carryRowids({json.dumps(ids)},{prior},{nxt},{changed})")

def test_nothing_changed_keeps_every_id():
    assert carry(["1", "2"], R("Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric"), "[]") == ["1", "2"]

def test_a_changed_row_gets_a_fresh_id():
    assert carry(["1", "2"], R("Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric"), "[1]") == ["1", None]

def test_confirmation_follows_the_medicine_when_a_row_above_is_removed():
    assert carry(["1", "2", "3"], R("Pantoprazole", "Dolo 650", "Zyloric"), R("Dolo 650", "Zyloric", "Cetirizine"), "[2]") == ["2", "3", None]

def test_reordered_rows_pair_by_name():
    assert carry(["1", "2"], R("A1", "B1"), R("B1", "A1"), "[]") == ["2", "1"]

def test_same_name_rows_pair_by_occurrence_and_a_changed_one_uses_its_slot():
    assert carry(["1", "2"], R("Amlodipine", "Amlodipine"), R("Amlodipine", "Amlodipine"), "[0]") == [None, "2"]

def test_name_case_and_outer_space_do_not_matter():
    assert carry(["7"], R("dolo 650"), R(" Dolo 650 "), "[]") == ["7"]

def test_a_new_name_not_reported_as_changed_still_gets_no_id():
    assert carry(["1"], R("A1"), R("A1", "Z9"), "[]") == ["1", None]

def test_bad_changed_rows_fall_back_to_clear_all():
    for bad in ("undefined", "null", '"1"', "[1.5]", "[-1]", "[2]", "[true]", '["0"]', "{}"):
        assert carry(["1", "2"], R("A1", "B1"), R("A1", "B1"), bad) == [None, None], bad

def test_garbage_rows_and_ids_are_safe():
    assert carry(["1"], R("A1"), "null", "[]") == []
    assert carry(["1"], "null", R("A1"), "[]") == [None]
    assert carry([None, 5], R("A1", "B1"), R("A1", "B1"), "[]") == [None, None]
    assert carry(["1", "2"], R("A1", "B1"), json.dumps(["x", {"name": "B1"}]), "[]") == [None, "2"]

def test_no_id_is_ever_returned_twice():
    got = carry(["1", "2", "3"], R("A1", "A1", "A1"), R("A1", "A1", "A1", "A1"), "[]")
    ids = [g for g in got if g]
    assert ids == ["1", "2", "3"] and len(set(ids)) == len(ids)
```

- [ ] **Step 2: Run to verify they fail.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_frontend_carry_confirmed.py`
  Expected: FAIL (node error: `RxState.carryRowids is not a function`).

- [ ] **Step 3: Implement** `carryRowids` in `frontend/rxstate.js` with a header comment: "which prior row id each
  row of a correction keeps: name + occurrence, the server's pairing (core/correction.py `_paired_prior`); changed
  rows and an untrusted `changed_rows` get none". Add it to the `root.RxState` export. File stays < 500 lines.

- [ ] **Step 4: Run.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_frontend_carry_confirmed.py tests/test_frontend_rxrow.py tests/test_frontend_rxspell.py`
  Expected: all PASS.

- [ ] **Step 5: Commit** (ask first): `git add frontend/rxstate.js tests/test_frontend_carry_confirmed.py`,
  message `RxState.carryRowids: a correction's rows keep their prior row id unless changed`.

---

### Task 4: wire it into the page, bump pins

**Files:**
- Modify: `frontend/app.js:560-575` (`applyCorrection`), `:855-859` (`rxRow`, no change needed: it already takes `rowid`),
  `:894-902` (`renderRx`), `:907-921` (`renderSheet`)
- Modify: `frontend/index.html:258` (`rxstate.js?v=` +1), `:265` (`app.js?v=` +1)
- Test: `tests/test_frontend_carry_confirmed.py` (append)

**Interfaces:**
- Consumes: `RxState.carryRowids` (Task 3); `changed_rows` (Task 2); `serializeForm()` (`app.js:646-662`).
- Produces: `renderSheet(s, rowids)` and `renderRx(rows, rowids)` — optional `rowids: Array<string|null>`; row `i`
  is built with `rxRow(r, i, rowids && rowids[i])` (`null`/`undefined` mints a fresh id as today, `app.js:859`). Every
  other caller keeps passing one argument.

`applyCorrection` after the change, in order:
1. `const before = serializeForm(), current = before.structured;` replaces `const current = readForm();` (`app.js:561`).
2. After `state.structured = j.structured || current;`: compute
   `const carry = RxState.carryRowids(before.indexToRowid, current.rx, (state.structured || {}).rx, j.changed_rows);`
3. Replace `state.confirmed.clear();` (`app.js:572`) with: keep only ids that are both in `carry` and in
   `state.confirmed` **now** (read after the response), drop the rest. Mutate the existing Set (RxView holds
   `() => state.confirmed`, `app.js:1240`). Update the comment at `app.js:570` to "A correction re-grounds the rows
   it changed; confirmations stay on the rest (changed_rows)".
4. `renderSheet(state.structured, carry);` replaces `renderSheet(state.structured);` (`app.js:575`). Confirmations
   are set **before** the render, as `rxview.js:43` and `:161` require.

The other three `state.confirmed.clear()` calls (open `:311`, format `:540`, new patient `:1203`) stay.

- [ ] **Step 0: Preflight.** Re-read `frontend/app.js:555-600`, `:890-925`, and `frontend/index.html:255-266`; plans a
  and b may have moved lines or bumped pins. Record the current pins.

- [ ] **Step 1: Write the failing wiring tests** (use the comment-stripping `_code` / `_slice` helpers of
  `tests/test_frontend_steps.py:18-27`).

```python
def test_apply_correction_keeps_unchanged_confirmations():
    body = _slice(_code("app.js"), "async function applyCorrection", "function retryLast")
    assert "serializeForm()" in body and "readForm()" not in body
    assert "RxState.carryRowids(" in body and "j.changed_rows" in body and "indexToRowid" in body
    assert "state.confirmed.clear()" not in body
    assert body.index("RxState.carryRowids(") < body.index("renderSheet(state.structured, carry)")

def test_render_passes_kept_row_ids_to_rxrow():
    src = _code("app.js")
    assert re.search(r"function renderRx\(rows, rowids\)", src) and re.search(r"function renderSheet\(s, rowids\)", src)
    assert "rxRow(r, i, rowids && rowids[i])" in _slice(src, "function renderRx", "function renderCheck")
    assert "renderRx(s.rx, rowids)" in _slice(src, "function renderSheet", "const stepCounts")

def test_other_paths_still_clear_all_confirmations():
    src = _code("app.js")
    for start, end in (("async function formatTranscript", "async function applyCorrection"), ("async function openDocument", "\n}\n")):
        assert "state.confirmed.clear()" in _slice(src, start, end)

def test_pins_are_bumped():
    html = _read("index.html")
    assert int(re.search(r"rxstate\.js\?v=(\d+)", html).group(1)) >= 8
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 37
```

  Raise the pin floors to (preflight value + 1) if plans a/b already bumped them.

- [ ] **Step 2: Run to verify they fail.**
  Run: `.venv/bin/python -m pytest -q -x tests/test_frontend_carry_confirmed.py`
  Expected: FAIL on `test_apply_correction_keeps_unchanged_confirmations`.

- [ ] **Step 3: Implement** the four `app.js` edits above and the two pin bumps. Net growth of `app.js`: at most 4 lines.

- [ ] **Step 4: Run the frontend and correction suites.**
  Run: `.venv/bin/python -m pytest -q tests/test_frontend_carry_confirmed.py tests/test_frontend_rxrow.py tests/test_frontend_rxspell.py tests/test_frontend_dates.py tests/test_frontend_steps.py tests/test_frontend_spell_modal_dom.py tests/test_correction_changed_rows.py`
  Then the whole suite: `.venv/bin/python -m pytest -q`
  Expected: all PASS.

- [ ] **Step 5: Manual browser check** (the owner or executor, with `DB_PATH` set to a temp file; not run by the
  plan writer). With an LLM key configured:
  1. Dictate three medicines with at least two needing confirmation. Confirm both.
  2. Dictate a correction that changes the dose of one confirmed row. Expect: that row asks again; the other stays "Confirmed by you".
  3. Dictate "remove <the first medicine>". Expect: the remaining confirmed row is still "Confirmed by you" at its new number.
  4. Save. Expect: no 409 for the carried row (its index is in `confirmed_rows`, `app.js:656-660`).

- [ ] **Step 6: Commit** (ask first): `git add frontend/app.js frontend/index.html tests/test_frontend_carry_confirmed.py`,
  message `Page: a spoken correction clears only the changed rows' confirmations`.

---

## Self-review notes

- Spec coverage: section 4 row 1 ("Spoken correction wipes all rows") is fixed by Tasks 1-4; row 5 (hand edit
  clears that row, `app.js:956`) is untouched and stays correct. Rows 2-4 and fix ideas 2-3 are listed as not in this plan.
- Contract: `changed_rows: list[int]`, indexes into the returned `rx`, as the index file states. No new response
  fields beyond it.
- Names used across tasks: `_paired_prior`, `changed_rx_rows`, `changed_rows`, `RxState.carryRowids`,
  `renderSheet(s, rowids)`, `renderRx(rows, rowids)`.

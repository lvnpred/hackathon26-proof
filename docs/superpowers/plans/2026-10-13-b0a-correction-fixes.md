# B0a: Correction Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop spoken corrections from creating blank-named medicine rows, and give the correction prompt the same schema rules as the format prompt.

**Architecture:** A new pure function `resolve_blank_names` in `backend/correction.py` rewrites nameless patch rows before the existing merge; `main.py` calls it and returns a `warnings` field. No restructuring (that is plan B1).

**Tech Stack:** Python 3.12 (venv at `.venv`), FastAPI, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-10-13-platform-foundation-design.md` (§2 problem 1, §4 rows "Blank-name rows" and "Correction prompt"). This is plan 1 of 6: **B0a** (this), **B0b** (event loop, upload cap, UI warnings, live check; written next, `docs/superpowers/plans/2026-10-13-b0b-event-loop-upload-cap-ui.md`), then B1 restructure, accuracy (§5), B2 template and PDF (§7A), D0 deploy (§8). Later plans are written after B0 lands because B1 moves the files these tasks edit.

**Baseline before starting:** 122 tests pass. **After this plan:** 135.

## Global Constraints

- "Every fix: write the failing test, watch it fail, then fix. No bundled refactoring."
- "No file over 500 lines." `backend/main.py` is already 1,058 lines (B1 splits it): add only what each task shows.
- `backend/correction.py` is "pure and deterministic: no network, no time, no randomness, stdlib only".
- Run tests with `.venv/bin/python -m pytest tests/ -q`.
- **Do not run `git commit` or `git push`** (user rule; the repo also has no commits yet). Leave every change in the working tree and list changed files at the end. This overrides the usual "commit" step.
- Tests must never call OpenAI. Endpoint tests clear the keys or stub `httpx.AsyncClient` using the existing helpers `_client` and `_stub_llm` in `tests/test_correction.py` (a developer's real `.env` key is loaded by `load_dotenv()`).

## Review Focus

1. A form with **one** medicine where the doctor changes an already-filled field without naming it (nameless `dose` patch): expect no change and a warning, never a silent overwrite. Test in Task 1.
2. Two medicines both missing the stated field and a nameless patch: expect no change and a warning, never a guess. Tasks 1 and 3.
3. A patch row with **no `name` key at all**, or `name: None`, behaves like a blank name. Task 1.
4. Non-string values in a patch row (`strength: 5`, `None`) must not crash. Task 1.

---

### Task 1: `resolve_blank_names` and the nameless-row guard

**Files:**
- Modify: `backend/correction.py` (docstring lines 16-21; add helpers after `_norm_name` at line 40; `_merge_rx` branch at lines 76-81)
- Test: `tests/test_correction.py` (import line 11; append tests at end)

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `resolve_blank_names(current: dict, patch: dict) -> tuple[dict, list[str]]`. Returns a copy of `patch` whose `rx` list has every nameless row either rewritten to carry the one medicine it can mean (only that medicine's empty fields) or dropped, plus warning strings. `merge_form` additionally never appends a nameless row.

- [ ] **Step 1: Write the failing tests**

Change line 11 of `tests/test_correction.py` to:

```python
from backend.correction import extract_correction, merge_form, resolve_blank_names
```

Append at the end of the file:

```python
# ---- B0 Task 1: nameless patch rows must never become ghost medicines ----

_ASCORIL = {"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "1-0-1",
            "timing": "", "duration": "", "instructions": ""}


def test_resolve_fills_the_one_incomplete_medicine():
    cur = {"rx": [dict(_ASCORIL)]}
    patch = {"rx": [{"name": "", "strength": "5 ml", "duration": "7 days"}]}
    out, warnings = resolve_blank_names(cur, patch)
    assert out["rx"] == [{"name": "Ascoril", "strength": "5 ml", "duration": "7 days"}]
    assert warnings == []


def test_resolve_ambiguous_blank_name_row_is_dropped_with_warning():  # Review Focus #2
    cur = {"rx": [dict(_ASCORIL), dict(_ASCORIL, name="Zincovit")]}
    out, warnings = resolve_blank_names(cur, {"rx": [{"name": "", "duration": "7 days"}]})
    assert out["rx"] == []
    assert len(warnings) == 1
    assert "Could not tell which medicine" in warnings[0]
    assert "duration: 7 days" in warnings[0]


def test_resolve_never_overwrites_a_filled_field():  # Review Focus #1
    cur = {"rx": [dict(_ASCORIL, dose="1-1-1")]}
    out, warnings = resolve_blank_names(cur, {"rx": [{"name": "", "dose": "1-0-1"}]})
    assert out["rx"] == []
    assert len(warnings) == 1


def test_resolve_row_without_content_is_dropped_silently():
    out, warnings = resolve_blank_names({"rx": [dict(_ASCORIL)]},
                                        {"rx": [{"name": "", "strength": "  "}]})
    assert out["rx"] == []
    assert warnings == []


def test_resolve_passes_named_rows_through_untouched():
    named = {"name": "Paracetamol", "dose": "1-0-1"}
    out, warnings = resolve_blank_names({"rx": [dict(_ASCORIL)]},
                                        {"rx": [named, {"name": "", "strength": "5 ml"}]})
    assert out["rx"] == [named, {"name": "Ascoril", "strength": "5 ml"}]
    assert warnings == []


def test_resolve_row_without_name_key_and_non_string_values():  # Review Focus #3, #4
    cur = {"rx": [dict(_ASCORIL)]}
    out, _ = resolve_blank_names(cur, {"rx": [{"strength": 5, "duration": None}]})
    assert out["rx"] == [{"name": "Ascoril", "strength": "5"}]
    out, _ = resolve_blank_names(cur, {"rx": [{"name": None, "strength": "5 ml"}]})
    assert out["rx"] == [{"name": "Ascoril", "strength": "5 ml"}]


def test_resolve_never_mutates_its_inputs():
    cur = {"rx": [dict(_ASCORIL)]}
    patch = {"rx": [{"name": "", "strength": "5 ml"}], "review": "1 week"}
    before_cur, before_patch = json.dumps(cur), json.dumps(patch)
    resolve_blank_names(cur, patch)
    assert json.dumps(cur) == before_cur and json.dumps(patch) == before_patch


def test_merge_form_never_appends_a_nameless_row():
    cur = {"rx": [dict(_ASCORIL)]}
    out = merge_form(cur, {"rx": [{"name": "", "strength": "5 ml"}]})
    assert out["rx"] == cur["rx"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_correction.py -q`
Expected: collection error `ImportError: cannot import name 'resolve_blank_names'`.

- [ ] **Step 3: Implement**

In `backend/correction.py`, add this block directly after `_norm_name` (after line 39):

```python
def _text(value) -> str:
    """Stripped string form of any value (None -> "")."""
    return str(value if value is not None else "").strip()


def resolve_blank_names(current: dict, patch: dict):
    """Give every nameless patch rx row the medicine it can only mean, or drop it.

    The model sometimes returns `{"name": "", "strength": "5 ml"}` for "strength
    is 5 ml for the Ascoril"; merging that by name would append a ghost row.
    A nameless row is applied to the ONE current (named) row that is missing a
    field the row states, filling only that row's empty fields. With zero or
    several candidates it is dropped and a warning says what was ignored.
    Returns `(patch_copy, warnings)`; never mutates its inputs.
    """
    pat = dict(patch) if isinstance(patch, dict) else {}
    rows = pat.get("rx")
    if not isinstance(rows, list):
        return pat, []
    cur_rows = current.get("rx") if isinstance(current, dict) else None
    named = [r for r in cur_rows if isinstance(r, dict) and _norm_name(r.get("name"))] \
        if isinstance(cur_rows, list) else []
    kept, warnings = [], []
    for row in rows:
        if not isinstance(row, dict) or _norm_name(row.get("name")):
            kept.append(row)
            continue
        stated = {f: _text(v) for f, v in row.items() if f != "name" and _text(v)}
        if not stated:
            continue  # nothing to apply
        candidates = [r for r in named if any(not _text(r.get(f)) for f in stated)]
        if len(candidates) == 1:
            target = candidates[0]
            fill = {f: v for f, v in stated.items() if not _text(target.get(f))}
            kept.append({"name": target["name"], **fill})
            continue
        said = ", ".join(f"{f}: {v}" for f, v in stated.items())
        warnings.append(
            "Could not tell which medicine this correction was for, so it was "
            f"not applied ({said}). Name the medicine and try again.")
    pat["rx"] = kept
    return pat, warnings


```

In `_merge_rx`, replace

```python
        else:
            out.append(dict(row))  # new medicine -> append
```

with

```python
        elif key:
            out.append(dict(row))  # new medicine -> append
        # a nameless row is never appended (resolve_blank_names handles those first)
```

In the module docstring, change "A new name is appended;" to "A new name is appended (a nameless row never is);".

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_correction.py -q`
Expected: all pass (17 existing + 8 new).

- [ ] **Step 5: Leave uncommitted.** Note `backend/correction.py` and `tests/test_correction.py` as changed.

---

### Task 2: Correction prompt carries the schema rules

**Files:**
- Modify: `backend/correction.py:28-34` (`CORRECTION_INSTRUCTION`)
- Test: `tests/test_correction.py` (append)

**Interfaces:**
- Consumes: nothing.
- Produces: the same constant name `CORRECTION_INSTRUCTION` with more text; it must still contain `byte-identical` (an existing test asserts it).

- [ ] **Step 1: Write the failing test** (append to `tests/test_correction.py`)

```python
# ---- B0 Task 2: the correction prompt has the same rules as the format prompt ----

def test_correction_prompt_carries_schema_and_rules():
    from backend.correction import CORRECTION_INSTRUCTION as P
    assert "byte-identical" in P                # existing behaviour kept
    assert 'MUST include "name"' in P           # every rx row names its medicine
    for needle in ('"1-0-0"', '"1-0-1"', '"1-1-1"', '"0-0-1"', '"SOS"',
                   '"After food"', '"Before food"', '"At bedtime"', '"45 / M"'):
        assert needle in P, needle
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_correction.py::test_correction_prompt_carries_schema_and_rules -q`
Expected: FAIL (`assert 'MUST include "name"' in P`).

- [ ] **Step 3: Implement** — replace the whole `CORRECTION_INSTRUCTION = (...)` block in `backend/correction.py` with:

```python
CORRECTION_INSTRUCTION = (
    "You are applying a spoken correction to an existing prescription form. "
    "Change ONLY what this correction states; leave every other field "
    "byte-identical. Return ONLY a JSON object containing the fields that "
    "change, using the same schema as the form. If the correction changes "
    "nothing, return {}.\n"
    "RULES:\n"
    '1. Every rx row you return MUST include "name": the medicine the correction '
    "is about, copied from the current form with its exact spelling. If the doctor "
    "refers to a medicine, find it in the current form and use that name. "
    "Never return an rx row without a name.\n"
    '2. Allowed dose codes ONLY: "1-0-0", "1-0-1", "1-1-1", "0-0-1", "SOS". '
    "Map: once daily/OD -> 1-0-0; twice daily/BD -> 1-0-1; thrice daily/TDS -> 1-1-1; "
    "at bedtime/HS -> 0-0-1; as needed/for pain -> SOS.\n"
    '3. Allowed timing ONLY: "After food", "Before food", "At bedtime", or "".\n'
    '4. ageSex format is "<age> / <M|F>", for example "45 / M".\n'
    '5. Duration format: "<N> days/weeks/months" with digits; two weeks -> 14 days.\n'
    "6. Never invent strengths, durations or drugs. Return only fields the doctor stated."
)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_correction.py -q`
Expected: all pass (the existing `byte-identical` assertion in the endpoint test still holds).

- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Wire `resolve_blank_names` into `/api/v1/correct`

**Files:**
- Modify: `backend/main.py` (both `correction` import blocks, lines 58-70; `correct()` at lines 761-772)
- Test: `tests/test_correction.py` (append)

**Interfaces:**
- Consumes: `resolve_blank_names(current, patch) -> (patch, warnings)` from Task 1.
- Produces: the `/api/v1/correct` response gains `"warnings": list[str]` (always present, `[]` when none).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_correction.py`)

```python
# ---- B0 Task 3: /api/v1/correct applies resolve_blank_names ----

def _ascoril_form(**extra_rows):
    rows = [{"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "1-0-1",
             "timing": "", "duration": "", "instructions": ""}]
    for name in extra_rows.get("more", []):
        rows.append(dict(rows[0], name=name))
    return {"rx": rows}


def test_correct_endpoint_blank_name_row_fills_the_one_incomplete_medicine(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "strength": "5 ml", "duration": "7 days"}]})
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "strength is 5 ml for the Ascoril and the duration is 7 days",
        "current_form": _ascoril_form()}).json()
    rows = j["structured"]["rx"]
    assert [r["name"] for r in rows] == ["Ascoril"]  # no ghost row
    assert rows[0]["strength"] == "5 ml" and rows[0]["duration"] == "7 days"
    assert rows[0]["dose"] == "1-0-1"
    assert j["warnings"] == []


def test_correct_endpoint_ambiguous_blank_name_row_changes_nothing_and_warns(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "duration": "7 days"}]})
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "duration is 7 days",
        "current_form": _ascoril_form(more=["Zincovit"])}).json()
    rows = j["structured"]["rx"]
    assert [r["name"] for r in rows] == ["Ascoril", "Zincovit"]
    assert all(r["duration"] == "" for r in rows)
    assert len(j["warnings"]) == 1 and "Could not tell which medicine" in j["warnings"][0]


def test_correct_endpoint_blank_name_fill_regrounds_the_filled_row(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "", "strength": "650 mg"}]})
    cur = {"rx": [{"form": "Tab.", "name": "Paracetamol", "strength": "", "dose": "1-1-1",
                   "timing": "After food", "duration": "5 days", "instructions": "",
                   "status": "unverified-strength", "lexicon_match": "Paracetamol"}]}
    from fastapi.testclient import TestClient
    j = TestClient(M.app).post("/api/v1/correct", json={
        "transcript": "strength is 650 mg for the Paracetamol",
        "current_form": cur}).json()
    row = j["structured"]["rx"][0]
    assert row["strength"] == "650 mg"
    assert row["status"] == "verified"  # the stale "unverified-strength" was not restored


def test_correct_endpoint_always_returns_a_warnings_list(monkeypatch):
    client = _client(monkeypatch)  # keys cleared -> rules path
    j = client.post("/api/v1/correct", json={"transcript": "", "current_form": {}}).json()
    assert j["warnings"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_correction.py -q -k "blank_name_row or always_returns"`
Expected: FAIL (ghost row present / `KeyError: 'warnings'`).

- [ ] **Step 3: Implement**

In `backend/main.py` there are two identical two-line fragments (the `try` and `except ImportError` import blocks):

```python
        preserve_untouched_rx_status,
        strip_grounding_markers,
```

Replace **both** with (use replace-all on this exact fragment):

```python
        preserve_untouched_rx_status,
        resolve_blank_names,
        strip_grounding_markers,
```

In `correct()`, replace

```python
    structured, _warnings = validate_structured(
        strip_grounding_markers(merge_form(current, patch)), normalized)
    preserve_untouched_rx_status(current, patch, structured)
    grounding = {"rounds": 0, "open_issues": open_issues(structured),
                 "llm_calls": llm_calls}
    return {"structured": structured, "grounding": grounding, "engine": engine}
```

with

```python
    patch, merge_warnings = resolve_blank_names(current, patch)
    structured, _warnings = validate_structured(
        strip_grounding_markers(merge_form(current, patch)), normalized)
    preserve_untouched_rx_status(current, patch, structured)
    grounding = {"rounds": 0, "open_issues": open_issues(structured),
                 "llm_calls": llm_calls}
    return {"structured": structured, "grounding": grounding, "engine": engine,
            "warnings": merge_warnings}
```

- [ ] **Step 4: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/ -q`
Expected: all pass (122 + 8 + 1 + 4 = 135).

- [ ] **Step 5: Leave uncommitted.**

---

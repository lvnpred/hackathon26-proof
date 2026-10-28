# Row Check Endpoint Implementation Plan (I1-d)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `POST /api/v1/rx/check-row` re-checks ONE row, so the Spell it popover changes only that row, and a shared `core/rowcheck.py` `ground_one` (contract 4.3) that `validate_structured` also uses, so the two paths cannot drift.

**Architecture:** Today `validate_structured` coerces and grounds each row inline (`core/determinism.py:425-471`). That per-row block moves, unchanged in behaviour, into `rowcheck.ground_with_notes(item, raw, normalized, age_sex, index) -> (row, notes)`. `ground_one` is that function minus the notes; `validate_structured` and the route both call it, so identical input gives an identical row dict and identical warnings. The route (`api/rx.py`) normalizes the transcript as `/api/format` does, grounds the row in a worker thread and adds suggestions: up to 3 from `suggest_candidates` plus `lasa.twins` of the row's lexicon match, de-duplicated. No database, no AI, so there is no clinic data to scope (I1-h revisits).

**Tech Stack:** FastAPI, pydantic, `asyncio.to_thread`, pytest TestClient. Stdlib only in `core/`.

**Spec:** "Iteration 1" section 3 (Spell it) of `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md`; contracts 4.1-4.4 in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (section 4 wins).

**Assumptions about earlier plans:** I1-b, I1-a and I1-c are applied (`determinism.py` is 457 lines; its row block holds I1-b's `generic`, I1-a's `lasa_row` and I1-c's `ground_extra`, in that merged form: dose before look-alike, results kept in `extra` and `lextra`). `core/lasa.py` must exist (`twins`, contract 4.3). Task 1's `ground_with_notes` below is already written in that merged form. Re-find each anchor with `grep -n`; line numbers drift.

## Global Constraints

- Test command `.venv/bin/python -m pytest tests/ -q`, offline (no network, no LLM). Never commit or push; "leave uncommitted" means that.
- No file over 500 lines; `core/` pure (`tests/test_core_purity.py`). This plan removes about 46 lines from `determinism.py` (457 to 408).
- Existing endpoints keep their status codes and JSON shapes; existing tests change only where a route table lists the new route.
- Errors use the repo's shape `{"error": "..."}` (as `api/format.py:84`, `api/session.py:42`).
- Baseline: run the suite first and note the count; expect baseline + **23** at the end.

## Review Focus

- A name typed by the doctor is never trusted: unknown stays `unknown-medicine`, a known name nobody said stays `unverified-name` (tests: `test_ground_one_has_every_field...`, `test_an_empty_transcript...`).
- A row sent back from the page already carries `[unverified: confirm with doctor]`: it must not stack a second marker (`test_an_unknown_drug_is_flagged_once...`).
- Huge or malformed bodies cost no CPU: field and transcript caps, and non-string fields, are a 400 before any lookup (`test_bad_or_oversized_input...`). The proxy also caps JSON bodies at 1 MiB (`Caddyfile:22`).
- No session means no answer, and the temporary-password gate still applies (`test_it_is_closed_without_a_session...`).
- The route never builds an LLM (`test_no_llm_is_ever_built`).

## File Structure

Create `doctor_dictation/core/rowcheck.py`, `doctor_dictation/api/rx.py`, `tests/test_rowcheck.py`, `tests/test_rx_check_row.py`. Modify `core/determinism.py` (the `dosing` import, the row block), `api/app.py` (`:18`, `:79`), `tests/test_api_app.py` (`:28`), `tests/test_isolation_routes.py` (after `:180`).

### Task 1: `core/rowcheck.py`

**Interfaces:** Consumes `determinism` names (lazy import: `determinism` will import this module; `lasa` for the same reason), `dosing.ground_extra`, `lasa.twins`, `suggest_candidates`. Produces `ground_with_notes(item, raw_transcript, normalized_transcript, age_sex="", index=0) -> (dict | None, list[str])`, `ground_one(row, raw_transcript, normalized_transcript, age_sex="") -> dict` (raises `ValueError` for a row with neither name nor strength), `suggestions(row) -> list[str]`, `SUGGESTION_LIMIT = 5`.

- [ ] **Step 1: Write the failing tests** `tests/test_rowcheck.py` (the fourth test, the parity test, arrives in Task 2; write the first three now):
```python
"""core/rowcheck.py: one row grounded the same way /api/format grounds it. Offline, pure."""
import pytest

from doctor_dictation.core import lasa, rowcheck
from doctor_dictation.core.determinism import normalize_transcript, validate_structured
from dosing_fixtures import use_fixture

RAW = "patient on tablet prednisone 10 mg twice daily after meals for 5 days, paracetamol 650 mg thrice daily"
NORM = normalize_transcript(RAW)
ROW = {"form": "Tab.", "name": "Prednisone", "strength": "10 mg", "dose": "1-0-1", "timing": "", "duration": "5 days"}
FIELDS = {"form", "name", "strength", "dose", "timing", "duration", "instructions", "status", "lexicon_match",
          "strength_options", "usual_strength", "dose_note", "heard", "lookalike", "generic"}


def test_ground_one_has_every_field_and_never_trusts_a_name_nobody_said():
    got = rowcheck.ground_one(ROW, RAW, NORM)
    assert FIELDS <= set(got) and (got["status"], got["lexicon_match"]) == ("lookalike-check", "Prednisone")   # curated pair (I1-a)
    for transcript in ("", "tablet metformin 500 mg"):
        typed = rowcheck.ground_one(ROW, transcript, transcript)
        assert (typed["status"], typed["lexicon_match"]) == ("unverified-name", "Prednisone")
    assert rowcheck.ground_one({"name": "Zzqxwv"}, "", "")["status"] == "unknown-medicine"


def test_suggestions_put_candidates_first_then_twins_without_duplicates(monkeypatch):
    monkeypatch.setattr(lasa, "twins", lambda c: ["Prednisolone", "Predni-twin"] if c == "Prednisone" else [])
    got = rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})
    assert got == ["Prednisone", "Prednisolone", "Predni-twin"]
    assert rowcheck.suggestions({"name": "Zzqxwv", "lexicon_match": ""}) == []
    monkeypatch.setattr(lasa, "twins", lambda c: [f"Twin{i}" for i in range(9)])
    assert len(rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})) == rowcheck.SUGGESTION_LIMIT


def test_ground_one_refuses_a_row_with_nothing_in_it():
    for row in ({}, {"name": " ", "strength": ""}):
        with pytest.raises(ValueError):
            rowcheck.ground_one(row, RAW, NORM)
    assert rowcheck.ground_with_notes({}, RAW, NORM, index=3) == (None, ["rx[3]: dropped empty row"])
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_rowcheck.py -q`. Expected: `ImportError: cannot import name 'rowcheck' from 'doctor_dictation.core'`.
- [ ] **Step 3: Write `doctor_dictation/core/rowcheck.py`.** The body of `ground_with_notes` is the current per-row block of `validate_structured` plus I1-c's hook line; only `i` became `index`, `warnings.append` became `notes.append`, `continue` became `return`, and determinism's names are reached through `D`. With an empty transcript `_ground_row` finds the name "not clearly dictated", so a known name is `unverified-name`: nobody said it, and the server cannot know the doctor typed it on purpose. That confirmation lives in the page (its confirmed set, contract 4.5), never here.
```python
"""Grounding of ONE prescription row: the single code path behind /api/format, /api/v1/correct and
/api/v1/rx/check-row, so the page and the Spell it popover can never disagree. Pure; no AI, no network."""
from . import dosing
from .candidates import suggest_candidates
from .lasa import lasa_row

SUGGESTION_LIMIT = 5


def ground_with_notes(item: dict, raw_transcript: str, normalized_transcript: str, age_sex: str = "", index: int = 0):
    """(row, notes): the coerced, grounded row, or None for an empty one (no name and no strength).

    ``notes`` are the warning strings validate_structured reports for this row, already prefixed ``rx[index]``.
    """
    from . import determinism as D   # lazy: determinism imports this module
    notes = []
    form = str(item.get("form") or "Tab.")
    if form not in D.ALLOWED_FORMS:
        form = "Tab."
    name = str(item.get("name") or "").strip().strip(".")
    strength = str(item.get("strength") or "").strip()
    dose = str(item.get("dose") or "").strip()
    if dose not in D.ALLOWED_DOSES:
        fixed = D.normalize_dose(dose.lower()) if dose else ""
        if fixed:
            dose = fixed
        else:
            notes.append(f"rx[{index}] {name or '?'}: unknown dose '{dose}' -> '1-0-0'")
            dose = "1-0-0"
    timing = str(item.get("timing") or "").strip()
    if timing not in D.ALLOWED_TIMINGS:
        fixed = D.normalize_timing(timing.lower())
        if fixed:
            timing = fixed
        elif ("food" in timing.lower() or "bedtime" in timing.lower()
              or "as needed" in timing.lower()):
            pass  # legacy combined strings from seeded example
        else:
            timing = ""
    duration = D.normalize_duration(str(item.get("duration") or "").lower()) or str(item.get("duration") or "")
    instructions = str(item.get("instructions") or "")
    if not name and not strength:
        return None, [f"rx[{index}]: dropped empty row"]
    # Agent-loop grounding: status + lexicon match on every row.
    status, match, issue = D._ground_row(name, strength, (normalized_transcript or "").lower())
    status, extra = dosing.ground_extra(status, match, form, strength, dose, age_sex)
    status, lextra = lasa_row(status, match, name, raw_transcript)      # after dose-check: contract 4.2
    if status in (D.RX_VERIFIED, dosing.DOSE_CHECK):
        pass
    elif status == D.RX_UNKNOWN_MEDICINE:
        notes.append(f"rx[{index}] '{name}': not in medicine list -> flagged {status}")
        instructions = (instructions + " [unverified: confirm with doctor]").strip()
    elif status == D.RX_UNVERIFIED_STRENGTH:
        notes.append(f"rx[{index}] '{name}': {issue} -> flagged {status}")
        instructions = (instructions + " [unverified strength: confirm with doctor]").strip()
    elif status == D.RX_UNVERIFIED_NAME:
        notes.append(f"rx[{index}] {issue} -> flagged unverified")
        instructions = (instructions + " [unverified: confirm with doctor]").strip()
    return {
        "form": form, "name": name, "strength": strength,
        "dose": dose, "timing": timing, "duration": duration,
        "instructions": instructions, "status": status,
        "lexicon_match": match, "generic": D._generic_of(name, match), **extra, **lextra,
    }, notes


def ground_one(row: dict, raw_transcript: str, normalized_transcript: str, age_sex: str = "") -> dict:
    """The grounded row for ``row`` (contract 4.3). Raises ValueError when it has neither a name nor a strength."""
    out, _ = ground_with_notes(row, raw_transcript, normalized_transcript, age_sex)
    if out is None:
        raise ValueError("row has neither a name nor a strength")
    return out


def suggestions(row: dict) -> list:
    """Sound-alike names for the typed name, then the look-alike twins of its lexicon match: de-duplicated
    case-insensitively, first occurrence wins, at most SUGGESTION_LIMIT."""
    from . import lasa   # lazy, like determinism above: lasa may import determinism, which imports this module
    twins = lasa.twins(row["lexicon_match"]) if row.get("lexicon_match") else []
    seen, out = set(), []
    for name in suggest_candidates(row.get("name", "")) + list(twins):
        if name.casefold() not in seen:
            seen.add(name.casefold())
            out.append(name)
    return out[:SUGGESTION_LIMIT]
```
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/test_rowcheck.py -q`. Expected: `3 passed`. Leave uncommitted.

### Task 2: `validate_structured` uses `ground_with_notes`

**Files:** Modify `core/determinism.py`; append the parity test to `tests/test_rowcheck.py`.

- [ ] **Step 1: Append the parity test** (the imports it needs are already in the file header). It spies on `ground_with_notes` so it fails until `validate_structured` goes through it:
```python
def test_ground_one_and_validate_structured_give_identical_rows(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)                                         # so one row is a dose-check
    seen, real = [], rowcheck.ground_with_notes
    monkeypatch.setattr(rowcheck, "ground_with_notes", lambda *a, **k: seen.append(a) or real(*a, **k))
    rows = [ROW, {**ROW, "dose": "twice a week", "timing": "after meals", "duration": "for 5 days"},
            {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}, {"name": "Zzqxwv"},
            {"name": "Metformin", "strength": "500 mg"}, {"name": "Amlodipine", "strength": "7 mg"},
            {"form": "Syringe", "name": "Prednisone.", "strength": " 10 mg ", "instructions": "with milk"}]
    for row in rows:
        seen.clear()
        validated, warnings = validate_structured({"ageSex": "45 / M", "rx": [row]}, NORM, raw_transcript=RAW)
        assert len(seen) == 1, "validate_structured must ground each row through rowcheck"
        assert rowcheck.ground_one(row, RAW, NORM, "45 / M") == validated["rx"][0], row
        assert rowcheck.ground_with_notes(row, RAW, NORM, "45 / M")[1] == warnings, row
    assert rowcheck.ground_one(rows[2], RAW, NORM, "45 / M")["status"] == "dose-check"
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_rowcheck.py -q`. Expected: `1 failed`: `AssertionError: validate_structured must ground each row through rowcheck` (or `TypeError ... 'raw_transcript'` if I1-a has not added that keyword; Step 3 adds it).
- [ ] **Step 3: Edit `core/determinism.py`.** (a) `from . import dosing` becomes `from . import rowcheck` (nothing else in the file uses `dosing`; check with `grep -n "dosing" doctor_dictation/core/determinism.py`; the `lasa_row` import stays: `ground_rx` still calls it). (b) the signature is already this after I1-c; check it:
```python
def validate_structured(data: dict, transcript: str, raw_transcript: str = "", age_sex: str = ""):
```
(c) Delete from `    tl = (transcript or "").lower()` (the line just before `for i, item in enumerate(rx[:RX_ROW_LIMIT]):`) through the closing `        })` of `out["rx"].append({`, and put this in its place; `return out, warnings` stays:
```python
    for i, item in enumerate(rx[:RX_ROW_LIMIT]):
        if not isinstance(item, dict):
            warnings.append(f"rx[{i}]: dropped non-object")
            continue
        row, notes = rowcheck.ground_with_notes(item, raw_transcript, transcript, age_sex or out["ageSex"], i)
        warnings += notes
        if row is not None:
            out["rx"].append(row)
```
(d) **Carry-across:** done already: Task 1's code carries I1-b's `generic`, I1-a's `lasa_row` (with the `elif status == RX_UNVERIFIED_NAME` branch and `{issue}` warning) and I1-c's hook. Run `grep -n "heard\|lookalike\|generic\|source" doctor_dictation/core/determinism.py` before deleting: any remaining hit inside the block that Task 1 does not carry (I1-h2's `row_extras` is added later, in `rowcheck`) must be moved too. `FIELDS` in the test already lists them.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest tests/ -q`. Expected: no failures, baseline + 4 passed (every existing `validate_structured` test is the guard). `wc -l doctor_dictation/core/determinism.py` prints 408. Leave uncommitted.

### Task 3: The route, its registration and the route tests

**Interfaces:** Produces `POST /api/v1/rx/check-row`, request `{"row": {...}, "transcript": "", "age_sex": ""}`, response `{"row": {...}, "suggestions": [...]}`, 400 `{"error": str}` for a missing or non-object `row`, a row with neither name nor strength, a non-text field, or an over-long field.

- [ ] **Step 1: Write the failing tests** `tests/test_rx_check_row.py` (Task 4 appends the last test and its fixture; the imports it needs are already here):
```python
"""POST /api/v1/rx/check-row and core/rowcheck.py: one row re-checked, identical to /api/format. Offline."""
import pytest
from fastapi.testclient import TestClient

import doctor_dictation.main as M
from doctor_dictation import accounts as A
from doctor_dictation import clinics
from doctor_dictation.api import rx as rx_api
from doctor_dictation.api.app import create_app
from doctor_dictation.core import lasa
from dosing_fixtures import use_fixture

URL, H = "/api/v1/rx/check-row", {"X-DD-Client": "1"}
RAW = "patient on tablet prednisone 10 mg twice daily after meals for 5 days, paracetamol 650 mg thrice daily"
ROW = {"form": "Tab.", "name": "Prednisone", "strength": "10 mg", "dose": "1-0-1", "timing": "", "duration": "5 days"}


def _post(body, client=None):
    return (client or TestClient(M.app)).post(URL, json=body)


def test_a_known_row_is_grounded_with_every_field_and_suggestions():
    r = _post({"row": ROW, "transcript": RAW, "age_sex": "46 / F"})
    got = r.json()
    assert r.status_code == 200 and "dose_note" in got["row"]
    assert (got["row"]["status"], got["row"]["lexicon_match"]) == ("lookalike-check", "Prednisone")   # curated pair (I1-a)
    assert got["suggestions"][0] == "Prednisone" and "Prednisolone" in got["suggestions"]


def test_age_reaches_the_dose_check(monkeypatch, tmp_path):
    use_fixture(monkeypatch, tmp_path)
    row = {"name": "Paracetamol", "strength": "650 mg", "dose": "1-1-1"}
    status = lambda age: _post({"row": row, "transcript": RAW, "age_sex": age}).json()["row"]["status"]   # noqa: E731
    assert (status("45 / M"), status("9 / F"), status("")) == ("dose-check", "verified", "verified")


def test_an_unknown_drug_is_flagged_once_and_gets_sound_alikes():
    row = {"name": "Cephixime", "strength": "200 mg", "instructions": "[unverified: confirm with doctor]"}
    got = _post({"row": row, "transcript": "cephixime 200 mg twice daily"}).json()
    assert got["row"]["status"] == "unknown-medicine"
    assert got["row"]["instructions"].count("[unverified: confirm with doctor]") == 1      # no stacked marker
    assert "Cefixime" in got["suggestions"]


def test_twins_follow_the_candidates_without_duplicates(monkeypatch):
    monkeypatch.setattr(lasa, "twins", lambda c: ["Prednisolone", "Predni-twin"] if c == "Prednisone" else [])
    got = _post({"row": ROW, "transcript": RAW}).json()["suggestions"]
    assert got == ["Prednisone", "Prednisolone", "Predni-twin"] and len(got) == len({n.lower() for n in got})
    assert _post({"row": ROW, "transcript": RAW}).json()["suggestions"] == got            # stable order


def test_an_empty_transcript_leaves_a_known_name_unverified_and_never_trusted():
    for transcript in ("", "   "):
        got = _post({"row": ROW, "transcript": transcript}).json()["row"]
        assert (got["status"], got["lexicon_match"]) == ("unverified-name", "Prednisone")
    assert _post({"row": {"name": "Zzqxwv"}}).json()["row"]["status"] == "unknown-medicine"


@pytest.mark.parametrize("body", [
    {}, {"row": None}, {"row": [ROW]}, {"row": "Prednisone"}, {"row": {}}, {"row": {"name": "  "}},
    {"row": {"name": 5}}, {"row": {**ROW, "name": "x" * 101}}, {"row": {**ROW, "instructions": "x" * 601}},
    {"row": ROW, "transcript": "x" * 20001}, {"row": ROW, "transcript": ["a"]}, {"row": ROW, "age_sex": "9" * 41},
])
def test_bad_or_oversized_input_is_a_400_with_the_json_error_shape(body):
    r = _post(body)
    assert r.status_code == 400 and list(r.json()) == ["error"] and r.json()["error"]


def test_no_llm_is_ever_built(monkeypatch):
    def boom(*_a, **_k):
        raise AssertionError("check-row must not build an LLM")
    monkeypatch.setattr("doctor_dictation.providers.llm.factory.make_llm", boom)
    monkeypatch.setattr("doctor_dictation.api.format.make_llm", boom)
    assert not hasattr(rx_api, "make_llm") and _post({"row": ROW, "transcript": RAW}).status_code == 200
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_rx_check_row.py -q`. Expected: collection error `ImportError: cannot import name 'rx' from 'doctor_dictation.api'`.
- [ ] **Step 3: Write `doctor_dictation/api/rx.py`.** Validation is by hand so every failure is the same 400 shape (a body that is not a JSON object at all still gets FastAPI's 422, like every other route). Both CPU-heavy steps (normalization, the difflib lookups) run in worker threads, as `api/format.py:65-77` does.
```python
"""POST /api/v1/rx/check-row: re-check ONE prescription row (the Spell it popover). Stateless: no database, no AI."""
import asyncio
from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.core.correction import strip_grounding_markers
from doctor_dictation.core.determinism import normalize_transcript
from doctor_dictation.core.rowcheck import ground_one, suggestions

router = APIRouter()
# Longest accepted text per field. The lookup is a difflib pass, so a huge string must not reach it.
ROW_LIMITS = {"form": 20, "name": 100, "strength": 60, "dose": 40, "timing": 60, "duration": 60, "instructions": 600}
MAX_TRANSCRIPT, MAX_AGE_SEX = 20000, 40


class CheckRowRequest(BaseModel):
    row: Any = None            # validated by hand below so every failure is the same 400 {"error": ...}
    transcript: Any = ""
    age_sex: Any = ""


def _problem(req: CheckRowRequest):
    if not isinstance(req.row, dict):
        return "row must be an object"
    for field, limit in ROW_LIMITS.items():
        value = req.row.get(field, "")
        if value is not None and not isinstance(value, str):
            return f"row.{field} must be text"
        if value and len(value) > limit:
            return f"row.{field} is longer than {limit} characters"
    if not (req.row.get("name") or "").strip() and not (req.row.get("strength") or "").strip():
        return "row needs a name or a strength"
    for label, value, limit in (("transcript", req.transcript, MAX_TRANSCRIPT), ("age_sex", req.age_sex, MAX_AGE_SEX)):
        if not isinstance(value, str) or len(value) > limit:
            return f"{label} must be text of at most {limit} characters"
    return None


def _ground(row: dict, raw: str, normalized: str, age_sex: str) -> dict:
    grounded = ground_one(row, raw, normalized, age_sex)
    return {"row": grounded, "suggestions": suggestions(grounded)}


@router.post("/api/v1/rx/check-row")
async def check_row(req: CheckRowRequest):
    """Ground one row exactly as /api/format does. A typed name is never trusted: it must still be in the transcript.

    With an empty transcript a known name comes back ``unverified-name`` (nobody said it); the doctor's own typing is
    confirmed in the page (its confirmed set), never by the server.
    """
    problem = _problem(req)
    if problem:
        return JSONResponse(status_code=400, content={"error": problem})
    raw = req.transcript.strip()
    normalized = await asyncio.to_thread(normalize_transcript, raw) if raw else ""   # same step as /api/format
    row = strip_grounding_markers({"rx": [req.row]})["rx"][0]            # a row sent back from the page keeps no stale marker
    return await asyncio.to_thread(_ground, row, raw, normalized, req.age_sex.strip())
```
- [ ] **Step 4: Register the router** exactly like its siblings. `api/app.py:18` and `:79` become:
```python
from doctor_dictation.api import auth, health, persistence, profile, rx, stt
    for module in (auth, health, stt, format_api, profile, persistence, users_api, rx):
```
- [ ] **Step 5: List the route in the two route-table tests.** `tests/test_api_app.py`: add `    ("POST", "/api/v1/rx/check-row"),` as a new line before `:28` (`("GET", "/api/v1/users"), ...`). `tests/test_isolation_routes.py`: add after `:180` (`"POST /api/format": ...`):
```python
    "POST /api/v1/rx/check-row": "stateless: grounds one row against the global lexicon, reads no clinic data (I1-h revisits)",
```
- [ ] **Step 6: Run** `.venv/bin/python -m pytest tests/test_rx_check_row.py tests/test_api_app.py tests/test_isolation_routes.py tests/test_closed_by_default.py -q`. Expected: all pass (`test_closed_by_default` walks the route table, so it covers the new route with no edit). Leave uncommitted.

### Task 4: Protection test and full suite

**Why no per-route code:** `SessionMiddleware` (`api/session.py:36-62`) gates every non-public path before routing: no cookie is 401 (JSON for `/api/*`), a missing `X-DD-Client` header on POST is 403, and a temporary password is 403 `must_change_password`. `api/profile.py` has no per-route auth either. The route reads no clinic data, so nothing needs `current_scope()`.

- [ ] **Step 1: Append the protection test** to `tests/test_rx_check_row.py` (modelled on `tests/test_auth_routes.py:17-34`):
```python
@pytest.fixture()
def clinic(multi):
    clinics.provision_clinic("rao", "Rao Clinic")
    A.create_user("rao", "dr.rao", display_name="Dr. Rao", password="temp-password-1")
    with TestClient(create_app(), follow_redirects=False) as c:
        yield c


def test_it_is_closed_without_a_session_and_open_after_login(clinic):
    body = {"row": ROW, "transcript": RAW}
    assert clinic.post(URL, json=body, headers=H).status_code == 401           # no cookie
    assert clinic.post(URL, json=body).status_code == 403                      # no X-DD-Client header
    login = {"username": "dr.rao", "password": "temp-password-1"}
    assert clinic.post("/api/v1/auth/login", json=login, headers=H).status_code == 200
    gated = clinic.post(URL, json=body, headers=H)                             # temporary password still gates it
    assert (gated.status_code, gated.json()["code"]) == (403, "must_change_password")
    change = {"current_password": "temp-password-1", "new_password": "brand-new-pass-1"}
    assert clinic.post("/api/v1/auth/change-password", json=change, headers=H).status_code == 200
    ok = clinic.post(URL, json=body, headers=H)
    assert ok.status_code == 200 and ok.json()["row"]["status"] == "lookalike-check"
```
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_rx_check_row.py -q`. Expected: `19 passed`.
- [ ] **Step 3: Run the full suite** `.venv/bin/python -m pytest tests/ -q`. Expected: baseline + 23 passed, 1 skipped. Check `wc -l` of every changed file stays under 500.
- [ ] **Step 4: Finish.** Leave uncommitted. Changed files: the eight in File Structure.

## Self-Review

Contract 4.3 `ground_one` and 4.4 route: Tasks 1 and 3; one code path for format and check-row (parity test): Task 2; protection: Task 4. `ground_with_notes` is defined in Task 1 with the signature Task 2 calls. Not changed: `api/format.py` (no new call sites), the frontend (I1-e), the dose vocabulary.

**Not done:** per-clinic formulary names (I1-h adds them inside `ground_with_notes`), voice spelling, a rate limit (the route is stateless and bounded; add one if the proxy shows abuse).

**Decision needed:** confirm that a blank row (neither name nor strength) is a 400 here while `validate_structured` silently drops it (`rx[i]: dropped empty row`).

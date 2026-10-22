# SH-H4: Patient Context for Correction Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** When the doctor records a spoken correction, the page sends the sheet's patient fields inside the `context` field (H3). This plan finds that patient: the OP number, else the exact name (casefolded, spaces collapsed) with matching age and sex. Rows with the same name, age and sex count as one person (owner decision 7). The result is exactly one person or none. It then lifts the medicines and tests from that person's last 3 visits with this doctor to tier 3, so they come first in the speech hints. No new table, no new UI step, no near-tie work (cut to backlog SH-B4 on 2026-10-21). Patient names never leave the server. Adds 13 tests. Runs AFTER H1 and H3.

**Goal:** A correction recording hints, before everything else, the medicines and tests this doctor gave this patient on the last 3 visits, and never sends the patient's name to a speech engine.

**Architecture:** A pure matcher `core/patientctx.py` (contract 5.6). Two SQL readers in `db/spoken.py` (`patient_candidates`, `patient_term_keys`). A thin `api/patientctx.py` that takes the doctor from the scope, fails soft, and returns the patient's term keys. `api/stt.py _doctor_terms(context)` lifts every `HintTerm` whose `key` is in those keys to `tier = max(tier, 3)`.

**Tech Stack:** Python 3.12, FastAPI, stdlib sqlite3, vanilla JS, pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-21-sh-00-index-and-contracts.md` (binding, as amended 2026-10-21): row 4; owner decisions 2 (option A: no "pick the patient first" step) and 7 (exact name, equal rows are one person); S1; S2; 5.1 (no H4 table); 5.2 (`HintTerm.key`); 5.3 (`patient_term_keys`, uncapped `doctor_hint_terms`); 5.6 (the patient rule); 7 (SH-B4). Conventions: section 2 of `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md`.

**Assumptions about earlier plans** (H1 and H3 were written in parallel; this plan relies only on index names, and the Preflight locates each one with `grep -n`):

| # | From | Contract item used |
|---|---|---|
| A1 | H1 | `core/spoken.py`: `key(text)`; `HintTerm(phrase, weight, tier=0, term_id=0, key="")` (frozen dataclass); `rank`; `terms_from_save(structured, known_patient_words) -> list[Term]` with `Term.key` (5.2) |
| A2 | H1 | `db/spoken.py` with `record_terms` and `doctor_hint_terms(conn, doctor_id, today)`, which returns EVERY live term with `key` set, uncapped (5.3). Table `spoken_terms`; `doctor_id` 0 in single-database mode (5.1) |
| A3 | H1 | `api/spoken.py learn_spoken_terms(conn, structured, document_id, user_id)` (5.5); `user_id` None records under doctor 0 |
| A4 | H1 | `api/stt.py _doctor_terms(context) -> list[HintTerm]`: sync, module level, called by `_prepare_audio` through `asyncio.to_thread`. `build_hints` takes the ranked phrases first and applies the budget (5.3) |
| A5 | H3 | `POST /api/transcribe` takes `context` (typed `Any` in the route), parses it (5.6) and passes the dict to `_doctor_terms(context)`. It keeps `context["patient"]` with each field a string capped at 200 characters |
| A6 | H3 | H3 lifts tier 2 inside `_doctor_terms` by `term_id` (`linked_term_ids`) |
| A7 | H3 | The page sends `context` only on correction recordings (`frontend/app.js` `transcribe`, `:486` on 8c9ce76), built from the diagnosis lines and the patient fields |

## Disagreements with the index (earlier points are resolved: `HintTerm.key` was added, near-tie moved to SH-B4, owner decision 7)

1. **`patient_term_keys` takes a group of ids.** Owner decision 7 makes one "person" several patient rows: without a dictated OP, every first save creates a new row (`api/persistence.py:280`). The first parameter of the 5.3 signature is therefore `patient_ids`: an int, as in 5.3, or a sequence of ids. The 3-visit window spans the whole group. Section 5.3 still names it `patient_id`.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`). `core/patientctx.py` imports only `re` and `.dosing`. No new table or migration (5.1).
- **S1:** tier 3 only re-orders terms the doctor already has. It never adds a phrase and never touches a row's `name`, `status` or `generic`. Spell it and Did you mean are untouched.
- **S2:** patient names, OP numbers and the `context` field never reach a speech engine. Log lines carry no name or OP, only the exception type.
- Fail soft: a database error in the patient lookup means "no patient" (logged). The transcription still answers with hints. The status codes and JSON body of `/api/transcribe` do not change.
- No Python file over 500 lines (`tests/test_file_sizes.py`). `frontend/app.js` is already 1279 lines (pre-existing); this plan adds at most 4 lines there. Tests are offline. `tests/conftest.py` gives every test a temp `DB_PATH` (`_private_single_mode_db`). Never write `from conftest import *`. Test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

| # | Input | Expected | Pinned in |
|---|---|---|---|
| 1 | Several rows with the same name, age and sex (a returning patient saved without an OP; also real same-name twins) | One person: every row's visits count (decision 7). For twins, the worst case is the other twin's terms first in the hints; the sheet does not change | Task 1 test 3, Task 3 test 2 |
| 2 | Same name, different people (ages 10 years apart), or names one letter apart ("Asha" / "Usha Verma") | Nobody, unless the dictated age tells the people apart. A one-letter difference never matches | Task 1 tests 2, 3 |
| 3 | Another doctor's patient (same clinic) or another clinic's patient, by name or by OP | Nothing | Task 4 |
| 4 | A stored age 2 or more years old | The name path finds nobody; the OP path still works | Task 1 tests 4, 5 |
| 5 | Database trouble during the lookup | Hints without tier 3. Never a failed transcription or an empty hint list | Task 3 test 3 |

## Decisions (and why)

1. **Name and person (owner decision 7).** The name must be equal after casefolding and collapsing spaces; there is no fuzzy match ("Asha Verma" vs "Usha Verma" would score 0.9). A person is the group of candidate rows with one identity `(normalised name, sex letter, age in years)`. The grouping is read-only and records are never merged. `match_patient` returns the group's ids, or `()`. A row with an unknown age is its own group but fits any dictated age, so rows ("40 / M", "") give two groups and nobody.
2. **Age** is read by `dosing.age_years` (`core/dosing.py:89`): "45 / M" gives 45, "6 months / F" gives 0, unclear text gives None. The app keeps one age reader. **Sex** is the letter after "/", else a standalone M, F, male or female.
3. **OP** comes first, matched exactly after trimming and case-sensitive, like `find_patients_by_op` (`db/__init__.py:158`). If the OP's rows form one identity, that person's whole group is the answer, including their rows without an OP. If several identities share the OP (`db/__init__.py:159-162`), the name rule runs among those rows only. If no row has it, the name rule runs over all candidates.
4. **Whose visits.** In multi-clinic mode only this doctor's encounters count, for the candidates (5.6) and for the documents (spoken_terms are per doctor, 5.1). In single-database mode (doctor 0) everything counts. A scope with no user gets no patient context.
5. **Same keys as H1.** `patient_term_keys` derives keys through `spoken.terms_from_save(form, frozenset())`, the function H1 records with, so the keys equal `HintTerm.key`.

## File Structure

| File | Change | Lines (budget) |
|---|---|---|
| `doctor_dictation/core/patientctx.py` | NEW: `match_patient`, `sex_letter`, `patient_of` | ~55 (≤ 70) |
| `doctor_dictation/db/spoken.py` (H1) | + `patient_candidates`, `patient_term_keys` | +~30 (file ≤ 500) |
| `doctor_dictation/api/patientctx.py` | NEW: `doctor_id`, `clean_patient`, `context_keys` | ~50 (≤ 70) |
| `doctor_dictation/api/stt.py` | lift to tier 3 in `_doctor_terms(context)` | +~3 |
| `frontend/app.js` | `patientContext()`, only if H3 does not send the patient (A7) | +≤ 4 |
| `tests/test_patientctx.py` | NEW, 6 tests | ~60 |
| `tests/test_patient_context.py` | NEW, 6 tests (Tasks 2 and 3) | ~150 |
| `tests/test_isolation_patient_context.py` | NEW, 1 test | ~45 |

---

### Preflight (before Task 1)

- [ ] **Step 1: Baseline.** Run: `.venv/bin/python -m pytest tests/ -q`. Note the count N (2824 passed, 1 skipped on 8c9ce76; higher after H1–H3).
- [ ] **Step 2: Locate A1–A7.** Record the line each command finds, or "missing", in the hand-over.

```bash
grep -n "^def key\|^class HintTerm\|term_id: int\|key: str\|^def rank\|^def terms_from_save" doctor_dictation/core/spoken.py  # A1
grep -n "^def record_terms\|^def doctor_hint_terms\|^def linked_term_ids" doctor_dictation/db/spoken.py                     # A2, A6
grep -n "^def learn_spoken_terms" doctor_dictation/api/spoken.py                                                             # A3
grep -n "_doctor_terms\|context\|tier\|replace(" doctor_dictation/api/stt.py                                                 # A4, A5, A6
grep -n "context\|patient" frontend/app.js | grep -i "context"                                                               # A7
```

- [ ] **Step 3: Decide.** If A1–A4 are missing, stop and report: H1 is not applied. If A5 drops `patient`, Task 3 Step 3 keeps it. If A7 lacks the patient, do Task 3 Step 4. Re-read `api/stt.py`: H1 and H3 have changed it.

---

### Task 1: The pure patient match

**Files:** Create `doctor_dictation/core/patientctx.py` and `tests/test_patientctx.py`.

**Interfaces:** Produces `AGE_SLACK = 1`, `sex_letter(age_sex) -> str`, `patient_of(structured) -> {"name", "age_sex", "op_no"}` (the sheet's fields, "" for anything not text) and `match_patient(op_no, name, age_sex, candidates) -> tuple[int, ...]` (the matched person's row ids in candidate order, `()` for nobody; `candidates`: mappings with `id, name, age_sex, op_no`, a `sqlite3.Row` works).

- [ ] **Step 1: Write the failing tests** in `tests/test_patientctx.py`:

```python
"""Plan SH-H4: find the patient a dictation names (contract 5.6, owner decision 7). Pure and offline."""
from doctor_dictation.core.patientctx import AGE_SLACK, match_patient, patient_of, sex_letter


def p(pid, name, age_sex="", op_no=None):
    return {"id": pid, "name": name, "age_sex": age_sex, "op_no": op_no}


def test_the_sex_letter_reads_every_way_the_sheet_writes_it():
    assert [sex_letter(s) for s in ("45 / M", "45 / F", "45Y/M", "45 / Male", "Female", "45 M", "6 months / F")] == \
        ["M", "F", "M", "M", "F", "M", "F"]
    assert [sex_letter(s) for s in ("", "45", None, 45)] == ["", "", "", ""] and AGE_SLACK == 1


def test_only_the_exact_name_matches_after_casefolding_and_collapsing_spaces():
    pool = [p(1, "Suresh Babu", "40 / M"), p(2, "Asha Verma", "34 / F")]
    assert match_patient("", "  suresh   BABU ", "40 / M", pool) == (1,)
    assert match_patient("", "Usha Verma", "34 / F", pool) == ()             # one letter off is someone else
    assert match_patient("", "Suresh Baabu", "40 / M", pool) == match_patient("", "Suresh", "40 / M", pool) == ()


def test_rows_with_the_same_name_age_and_sex_are_one_person_and_two_people_are_nobody():
    same = [p(1, "Ravi Kumar", "40 / M"), p(2, "ravi  kumar", "40 / M"), p(3, "Asha Verma", "34 / F")]
    assert match_patient("", "Ravi Kumar", "40 / M", same) == match_patient("", "Ravi Kumar", "", same) == (1, 2)
    apart = [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "50 / M")]
    assert match_patient("", "Ravi Kumar", "", apart) == match_patient("", "Ravi Kumar", "45 / M", apart) == ()
    assert match_patient("", "Ravi Kumar", "40 / M", apart) == (1,)          # the dictated age tells them apart
    assert match_patient("", "Ravi Kumar", "40 / M", [p(1, "Ravi Kumar", "40 / M"), p(2, "Ravi Kumar", "")]) == ()


def test_age_and_sex_rule_a_candidate_out_only_when_both_sides_give_them():
    ravi = [p(1, "Ravi Kumar", "40 / M")]
    assert match_patient("", "Ravi Kumar", "42 / M", ravi) == ()                # two years apart
    assert match_patient("", "Ravi Kumar", "39 / M", ravi) == (1,)
    assert match_patient("", "Ravi Kumar", "40 / F", ravi) == ()                # the other sex
    assert match_patient("", "Ravi Kumar", "", ravi) == match_patient("", "Ravi Kumar", "M", ravi) == (1,)
    assert match_patient("", "Ravi Kumar", "40 / M", [p(1, "Ravi Kumar", "")]) == (1,)     # stored without age_sex


def test_an_op_number_match_wins_and_a_shared_op_narrows_the_name_rule():
    pool = [p(1, "Ravi Kumar", "40 / M", "RAO-0007"), p(2, "Somebody Else", "", "RAO-0008"), p(3, "Ravi Kumar", "40 / M")]
    assert match_patient("RAO-0007", "Somebody Else", "", pool) == (1, 3)     # the OP wins; his other row comes too
    assert match_patient(" RAO-0007 ", "", "", pool) == (1, 3)                 # trimmed; no name needed
    assert match_patient("rao-0007", "", "", pool) == ()                       # exact: case counts
    assert match_patient("RAO-0099", "Ravi Kumar", "40 / M", pool) == (1, 3)   # an unknown OP: the name rule
    shared = [p(1, "Ravi Kumar", "40 / M", "OP 5"), p(2, "Asha Verma", "34 / F", "OP 5"), p(3, "Ravi Kumar", "70 / M", "OP 6")]
    assert match_patient("OP 5", "Ravi Kumar", "", shared) == (1,)             # among the OP's patients only
    assert match_patient("OP 5", "", "", shared) == ()


def test_blank_or_short_input_matches_nobody_and_patient_of_reads_the_sheet():
    assert match_patient("", "", "", [p(1, "", "")]) == () and match_patient("", "Al", "", [p(1, "Al", "")]) == ()
    assert match_patient("", "Ravi Kumar", "40 / M", []) == () and match_patient(None, None, None, None) == ()
    assert patient_of({"patientName": "Ravi Kumar", "ageSex": "40 / M", "opNo": "OP 5", "rx": []}) == \
        {"name": "Ravi Kumar", "age_sex": "40 / M", "op_no": "OP 5"}
    assert patient_of({"patientName": 7}) == patient_of(None) == {"name": "", "age_sex": "", "op_no": ""}
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_patientctx.py -q`. Expected: 6 errors (`ModuleNotFoundError: doctor_dictation.core.patientctx`).
- [ ] **Step 3: Create `core/patientctx.py`.** The rule order is subtle, so its core follows. These tests passed against it on a scratch copy (6 passed). Also add a docstring naming contract 5.6 and owner decision 7; `from .dosing import age_years`; `_text(v)` (`v` if a str, else ""); `_norm(v)` (`" ".join(_text(v).casefold().split())`); and `sex_letter`, the upper-cased first letter of `/\s*(male|female|m|f)\b`, else of `\b(male|female|m|f)\b` (case-insensitive), "" when neither matches.

```python
def _ident(c) -> tuple:                          # one person = one (name, sex, age); rows are never merged
    return (_norm(c["name"]), sex_letter(c["age_sex"]), age_years(_text(c["age_sex"])))

def _fits(want, age, sex, ident) -> bool:
    name, other_sex, other_age = ident
    if name != want or (sex and other_sex and sex != other_sex):
        return False
    return age is None or other_age is None or abs(age - other_age) <= AGE_SLACK

def match_patient(op_no, name, age_sex, candidates) -> tuple:
    pool = list(candidates or ())
    group = {}
    for c in pool:
        group.setdefault(_ident(c), []).append(c["id"])
    op = _text(op_no).strip()
    if op:
        same = [c for c in pool if _text(c["op_no"]).strip() == op]
        if len({_ident(c) for c in same}) == 1:
            return tuple(group[_ident(same[0])])     # the OP's person, with their rows that have no OP
        pool = same or pool                          # shared OP: the name rule among them; unknown OP: over all
    want = _norm(name)
    if sum(ch.isalpha() for ch in want) < 3:
        return ()
    age, sex = age_years(_text(age_sex)), sex_letter(age_sex)
    hits = {_ident(c) for c in pool if _fits(want, age, sex, _ident(c))}
    return tuple(group[hits.pop()]) if len(hits) == 1 else ()
```
- [ ] **Step 4: Run.** `.venv/bin/python -m pytest tests/test_patientctx.py tests/test_core_purity.py -q`. Expected: all pass.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: The SQL readers

**Files:** Modify `doctor_dictation/db/spoken.py` (H1). Create `tests/test_patient_context.py`.

**Interfaces:** Consumes A1 and A2. Produces `patient_candidates(conn, doctor_id: int) -> list[sqlite3.Row]` (columns `id, name, age_sex, op_no`, ordered by id) and `patient_term_keys(conn, patient_ids, doctor_id, visits=3) -> set[str]`. `patient_ids` is one id or a person's group from `match_patient`, and the window is the group's last `visits` documents (Disagreement 1). In both, `doctor_id` 0 means single-database mode, with no doctor filter.

- [ ] **Step 1: Write the failing tests.** Task 3 reuses this file's header and helpers.

```python
"""Plan SH-H4: the patient's earlier terms lift correction hints to tier 3. Offline, single-database mode."""
import json
import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import patientctx
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken
from doctor_dictation.core.patientctx import match_patient
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript
from doctor_dictation.scope import Scope, use_scope

K = spoken.key
T = ["2026-10-0%dT09:00:00Z" % d for d in range(1, 10)]
AUDIO = {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
SURESH = {"name": "Suresh Babu", "age_sex": "40 / M", "op_no": ""}


def fresh():
    conn = dbmod.get_conn()                    # the autouse temp DB_PATH (tests/conftest.py)
    dbmod.migrate(conn)
    return conn


def visit(conn, pid, when, meds=(), tests=(), doctor=None, finalized=True, learn=False):
    eid = dbmod.create_encounter(conn, pid, doctor_id=doctor, status="finalized")
    form = {"patientName": "", "ageSex": "", "opNo": "", "diagnosis": [],
            "rx": [{"form": "Tab.", "name": m, "strength": "", "status": "verified"} for m in meds],
            "investigations": [{"text": t, "canonical": "", "status": "", "source": "dictated"} for t in tests]}
    did = dbmod.save_document(conn, eid, f"sha-{pid}-{when}", form, finalized_at=when if finalized else None, created_at=when)
    if learn:
        learn_spoken_terms(conn, form, did, doctor)          # H1's save hook fills spoken_terms
    return did


def test_patient_term_keys_reads_the_last_three_finalized_visits_of_this_doctor():
    conn = fresh()
    a, b = dbmod.create_user(conn, "dr.a", "x"), dbmod.create_user(conn, "dr.b", "x")
    pid = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    visit(conn, pid, T[0], ["Amoxicillin"], doctor=a)                       # 4th of a's visits: outside the window
    visit(conn, pid, T[1], ["Montelukast"], ["Serum creatinine"], doctor=a)
    visit(conn, pid, T[2], ["Cetirizine"], doctor=a)
    visit(conn, pid, T[3], ["Doxycycline"], doctor=a, finalized=False)     # never finalized: never counts
    visit(conn, pid, T[4], ["Azithromycin"], doctor=b)                      # another doctor's visit
    visit(conn, pid, T[5], ["Pantoprazole", "Montelukast"], doctor=a)
    odd = dbmod.create_patient(conn, "Gopal Das", "62 / M", None)
    visit(conn, odd, T[6], ["Telmisartan"])
    dbmod.save_document(conn, dbmod.create_encounter(conn, odd, status="finalized"), "sha-bad", "not json",
                        finalized_at=T[7], created_at=T[7])
    assert sdb.patient_term_keys(conn, pid, a) == {K("Montelukast"), K("Serum creatinine"), K("Cetirizine"), K("Pantoprazole")}
    assert sdb.patient_term_keys(conn, pid, a, visits=1) == {K("Pantoprazole"), K("Montelukast")}
    assert sdb.patient_term_keys(conn, pid, b) == {K("Azithromycin")}
    assert sdb.patient_term_keys(conn, pid, 0) == {K("Azithromycin"), K("Pantoprazole"), K("Montelukast"), K("Cetirizine")}
    assert sdb.patient_term_keys(conn, odd, 0) == {K("Telmisartan")}        # a malformed document adds nothing
    assert sdb.patient_term_keys(conn, 999, 0) == sdb.patient_term_keys(conn, (), 0) == set()
    again = dbmod.create_patient(conn, "Suresh Babu", "40 / M", None)       # his row from a save without an OP
    visit(conn, again, T[8], ["Levocetirizine"], doctor=a)
    assert sdb.patient_term_keys(conn, (pid, again), a) == {K("Levocetirizine"), K("Pantoprazole"), K("Montelukast"), K("Cetirizine")}
    conn.close()


def test_candidates_are_this_doctors_patients_or_everyone_in_single_database_mode():
    conn = fresh()
    a, b = dbmod.create_user(conn, "dr.a", "x"), dbmod.create_user(conn, "dr.b", "x")
    mine = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    theirs = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 6")
    nobody = dbmod.create_patient(conn, "Gopal Das", "", None)               # no encounter yet
    for _ in range(2):
        dbmod.create_encounter(conn, mine, doctor_id=a)                      # two visits, one candidate
    dbmod.create_encounter(conn, theirs, doctor_id=b)
    assert [r["id"] for r in sdb.patient_candidates(conn, a)] == [mine]
    assert [r["id"] for r in sdb.patient_candidates(conn, 0)] == [mine, theirs, nobody]
    assert sdb.patient_candidates(conn, a)[0].keys() == ["id", "name", "age_sex", "op_no"]
    assert match_patient("", "Suresh Babu", "40 / M", sdb.patient_candidates(conn, a)) == (mine,)
    assert match_patient("OP 6", "", "", sdb.patient_candidates(conn, a)) == ()      # another doctor's OP
    assert match_patient("", "Suresh Babu", "40 / M", sdb.patient_candidates(conn, 0)) == (mine, theirs)   # one person
    conn.close()
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_patient_context.py -q`. Expected: a collection error, `ImportError: cannot import name 'patientctx' from 'doctor_dictation.api'`. Create `doctor_dictation/api/patientctx.py` holding only its docstring (Task 3 fills it). Run again. Expected: 2 FAIL with `AttributeError: ... 'patient_candidates'`.
- [ ] **Step 3: Add the two functions to `db/spoken.py`.** The SQL follows; on a scratch copy these queries passed both tests.

```sql
-- patient_candidates, doctor_id 0:
SELECT id, name, age_sex, op_no FROM patients ORDER BY id
-- patient_candidates, doctor_id > 0:
SELECT id, name, age_sex, op_no FROM patients WHERE id IN (SELECT patient_id FROM encounters WHERE doctor_id = ?) ORDER BY id
-- patient_term_keys: ids = (patient_ids,) for an int, else tuple(patient_ids); no ids: set() without a query;
--   " AND e.doctor_id = ?" only when doctor_id > 0; the LIMIT is max(0, int(visits))
SELECT d.structured_json FROM documents d JOIN encounters e ON e.id = d.encounter_id
 WHERE e.patient_id IN (?, ...) AND d.finalized_at IS NOT NULL [AND e.doctor_id = ?] ORDER BY d.created_at DESC, d.id DESC LIMIT ?
```

  `patient_term_keys` returns the union of `{t.key for t in spoken.terms_from_save(form, frozenset())}` over the rows whose JSON parses to a dict. It skips a row on `TypeError` or `ValueError` (Decision 5). Each docstring states the doctor-0 rule.
- [ ] **Step 4: Run.** `.venv/bin/python -m pytest tests/test_patient_context.py -q`. Expected: 2 passed. If H1's `terms_from_save` skips a row kind used here, change the fixture rows, never the window assertions.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: Tier 3 in the correction hints

**Files:** Fill `doctor_dictation/api/patientctx.py`. Modify `doctor_dictation/api/stt.py`. Modify H3's context parser and `frontend/app.js` only if A5 or A7 need it. Append to `tests/test_patient_context.py`.

**Interfaces:** Consumes Tasks 1 and 2, and A4–A6. Produces in `api/patientctx.py`: `doctor_id() -> int | None` (0 with no scope, `scope.user_id` when set, None for a scope without a user); `clean_patient(raw) -> dict | None` (string fields only, each capped at 200 characters (H3's cap), "" for non-strings; None when `raw` is not a dict or every field is blank); `context_keys(conn, doctor_id, context) -> set[str]`: `set()` when `doctor_id` is None or there is no clean patient; otherwise `ids = match_patient(...)` over `patient_candidates`, then `patient_term_keys(conn, ids, doctor_id)` when `ids` is not empty. It catches `sqlite3.Error`, logs only `type(exc).__name__`, and returns `set()`.

- [ ] **Step 1: Append the failing tests.**

```python
class Recorder:                                      # the speech provider: records the hints it was sent
    name, available = "recorder", staticmethod(lambda: True)

    def __init__(self):
        self.calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append(list(hints))
        return Transcript(text="tab montelukast", engine="recorder")


def tier3(context):
    return {t.key for t in api_stt._doctor_terms(context) if t.tier == 3}


def test_a_correction_recording_hints_this_patients_earlier_medicines_first(monkeypatch):
    conn = fresh()
    suresh, gopal = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5"), dbmod.create_patient(conn, "Gopal Das", "62 / M", "OP 6")
    for when in T[:3]:
        visit(conn, gopal, when, ["Pantoprazole"], learn=True)               # the doctor's most-used medicine
    visit(conn, suresh, T[3], ["Montelukast", "Cetirizine"], learn=True)
    conn.close()
    rec = Recorder()
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: rec)
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    ctx = {"diagnosis": [], "patient": {**SURESH, "name": "suresh  babu"}}
    with TestClient(create_app()) as client:
        plain = client.post("/api/transcribe", files=AUDIO)                  # a first dictation: no context
        hinted = client.post("/api/transcribe", files=AUDIO, data={"context": json.dumps(ctx)})
    assert plain.status_code == hinted.status_code == 200 and plain.json() == hinted.json()
    first, second = rec.calls
    assert first[0] == "Pantoprazole"
    assert set(second[:2]) == {"Montelukast", "Cetirizine"} and second[2] == "Pantoprazole"
    assert not [h for h in first + second if "suresh" in h.casefold() or "babu" in h.casefold()]    # S2


def test_tier_three_needs_exactly_one_person_named_in_the_context():
    conn = fresh()
    suresh = dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5")
    visit(conn, dbmod.create_patient(conn, "Gopal Das", "62 / M", "OP 6"), T[0], ["Pantoprazole"], learn=True)
    visit(conn, suresh, T[1], ["Montelukast", "Cetirizine"], learn=True)
    mine = {K("Montelukast"), K("Cetirizine")}
    assert tier3({"patient": SURESH}) == tier3({"patient": {**SURESH, "name": "", "op_no": "OP 5"}}) == mine
    assert tier3(None) == tier3({"diagnosis": []}) == tier3({"patient": "Suresh Babu"}) == set()
    assert tier3({"patient": {**SURESH, "age_sex": "43 / M"}}) == tier3({"patient": {**SURESH, "name": "Suresh Baabu"}}) == set()
    again = dbmod.create_patient(conn, "Suresh Babu", "40 / M", None)            # his row from a save without an OP
    visit(conn, again, T[2], ["Levocetirizine"], learn=True)
    both = mine | {K("Levocetirizine")}
    assert tier3({"patient": SURESH}) == tier3({"patient": {**SURESH, "name": "", "op_no": "OP 5"}}) == both   # one person
    dbmod.create_patient(conn, "Suresh Babu", "60 / M", None)                     # another man, twenty years older
    assert tier3({"patient": {**SURESH, "age_sex": ""}}) == set()                 # two people: nobody
    assert tier3({"patient": SURESH}) == both                                     # the dictated age tells them apart
    assert {t.key for t in api_stt._doctor_terms({"patient": SURESH})} >= mine | {K("Pantoprazole")}   # none lost
    conn.close()


def test_patient_context_fails_soft_and_takes_the_doctor_from_the_scope(monkeypatch):
    conn = fresh()
    visit(conn, dbmod.create_patient(conn, "Suresh Babu", "40 / M", "OP 5"), T[0], ["Montelukast"], learn=True)
    conn.close()

    def broken(conn, doctor_id):
        raise sqlite3.OperationalError("disk I/O error")
    monkeypatch.setattr(sdb, "patient_candidates", broken)
    terms = api_stt._doctor_terms({"patient": SURESH})
    assert terms and not [t for t in terms if t.tier == 3]                        # hints without the patient, never none
    assert patientctx.doctor_id() == 0
    with use_scope(Scope("rao", user_id=7)):
        assert patientctx.doctor_id() == 7
    with use_scope(Scope("rao", user_id=None)):
        assert patientctx.doctor_id() is None
    assert patientctx.clean_patient({"name": "x" * 300, "age_sex": 45, "op_no": "OP 5"}) == \
        {"name": "x" * 200, "age_sex": "", "op_no": "OP 5"}
    assert patientctx.clean_patient({"name": " ", "age_sex": "", "op_no": ""}) is None
    assert patientctx.clean_patient("Suresh Babu") is None


def test_the_page_puts_the_sheets_patient_in_the_correction_context():
    js = (Path(__file__).resolve().parents[1] / "frontend" / "app.js").read_text(encoding="utf-8")
    body = js.split("function patientContext()", 1)[1].split("\n}", 1)[0]
    assert all(f'$("{i}")' in body for i in ("pName", "pAge", "pOp"))
    assert "patient: patientContext()" in js
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_patient_context.py -q`. Expected: the 4 new tests FAIL. Tier 3 is empty, `patientctx.doctor_id` is missing, and `patientContext` is missing unless H3 added it.
- [ ] **Step 3: Fill `api/patientctx.py`** to the Interfaces above. In `api/stt.py _doctor_terms`, add these lines inside the same `with` block, after H3's tier-2 lift (A6) and before the terms are returned. `replace` is `dataclasses.replace`. `max` keeps any higher tier.

```python
        keys = patientctx.context_keys(conn, patientctx.doctor_id(), context)      # SH-H4: this patient's last 3 visits
        terms = [replace(t, tier=max(t.tier, 3)) if t.key in keys else t for t in terms]
```

  Rename `terms` to H3's variable. If A5 showed that H3's parser drops `patient`, keep `raw.get("patient")` in the parsed dict (one line). `clean_patient` checks it, and it is never logged.
- [ ] **Step 4: The page (A7).** If `transcribe` does not send the patient yet, add the function below next to H3's context builder, and set `patient: patientContext()` in the context object. If H3 wrote the three fields inline, move them into this function.

```js
function patientContext() {   // SH-H4: the sheet's patient, for the server only (never sent to a speech engine)
  return { name: text($("pName")), age_sex: text($("pAge")), op_no: text($("pOp")) };
}
```

- [ ] **Step 5: Run.** `.venv/bin/python -m pytest tests/test_patient_context.py tests/test_transcribe_acc2.py tests/test_file_sizes.py -q`, plus every H1 or H3 hint test file the Preflight found. Expected: all pass (`test_patient_context.py`: 6 passed).
- [ ] **Step 6: Leave uncommitted.**

---

### Task 4: Isolation (clinics and doctors)

**Files:** Create `tests/test_isolation_patient_context.py`.

**Interfaces:** Consumes the `world` fixture (`tests/isolation_fixtures.py:79`: clinic A has dr.rao and dr.mehta, clinic B has dr.iyer), the `op_no` in the save response (`api/persistence.py:354`), and Task 3.

- [ ] **Step 1: Write the test.**

```python
"""Plan SH-H4: a doctor never gets another clinic's or another doctor's patient terms. Offline; the two-clinic world."""
import json

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken
from isolation_fixtures import H, world  # noqa: F401

AUDIO = {"audio": ("a.webm", b"x" * 64, "audio/webm")}
K = spoken.key


def save_rx(client, patient, *medicines):
    rx = [{"form": "Tab.", "name": m, "status": "verified"} for m in medicines]
    body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": rx}, "confirmed_rows": []}
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["op_no"]


def test_patient_terms_stay_with_the_doctor_and_the_clinic_that_wrote_them(world, monkeypatch):
    override_settings(monkeypatch, stt_use_hints=True)          # the world already stubs the LLM and the speech chain
    for who in ("rao", "mehta", "iyer"):
        save_rx(getattr(world, who), "Gopal Das", "Montelukast", "Azithromycin")    # all three use both
    op_a = save_rx(world.mehta, "Suresh Babu", "Montelukast")                      # clinic A, Dr. Mehta's patient
    save_rx(world.iyer, "Suresh Babu", "Azithromycin")                             # clinic B: same name, another person
    seen, real = [], api_stt._doctor_terms
    monkeypatch.setattr(api_stt, "_doctor_terms", lambda context=None: seen.append(real(context)) or seen[-1])

    def tier3(who, **patient):
        ctx = {"diagnosis": [], "patient": {"name": "", "age_sex": "", "op_no": "", **patient}}
        r = getattr(world, who).post("/api/transcribe", files=AUDIO, data={"context": json.dumps(ctx)}, headers=H)
        assert r.status_code == 200, r.text
        return {t.key for t in seen[-1] if t.tier == 3}
    named = {"name": "Suresh Babu", "age_sex": "40 / M"}
    assert tier3("mehta", **named) == tier3("mehta", op_no=op_a) == {K("Montelukast")}
    assert tier3("iyer", **named) == {K("Azithromycin")}
    assert tier3("rao", **named) == tier3("rao", op_no=op_a) == set()      # same clinic, another doctor's patient
    assert tier3("iyer", op_no=op_a) == set()                              # another clinic's OP number
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_isolation_patient_context.py -q`. Expected: 1 passed. To see it guard, drop the `WHERE id IN (...)` filter from `patient_candidates` and run again. Expected: it fails at the `rao` line. Restore the filter.
- [ ] **Step 3: Leave uncommitted.**

---

### Task 5: Mutations, whole suite, sizes and hand-over

- [ ] **Step 1: Mutations.** Apply each mutation alone and run the named test file. Expected: at least one failure. Revert the mutation. Report each result as "killed by ...".

| # | Mutation | Must fail |
|---|---|---|
| M1–M3 | a fuzzy name compare (difflib >= 0.9); `AGE_SLACK = 2`; drop the sex check | `test_patientctx.py` tests 2, 4 (Usha; 42 vs 40; 40 / F) |
| M3b | `_ident` without the age (group by name and sex only) | test 3 (ten years apart) |
| M4–M5 | keep the whole `pool` for a shared OP; casefold the OP | test 5 (shared OP 5; `rao-0007`) |
| M6–M9 | drop `AND e.doctor_id = ?`; drop `finalized_at IS NOT NULL`; candidates ignore `doctor_id`; fixed `LIMIT 3` | Task 2 tests 1, 2; Task 4 |
| M10 | delete the lift line in `_doctor_terms` | Task 3 tests 1, 2; Task 4 |
| M11–M12 | `context_keys` stops catching `sqlite3.Error`; `doctor_id()` gives 0 for a scope without a user | Task 3 test 3 |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: N + 13 passed, the same skip count, no failure.
- [ ] **Step 3: Sizes.** Run: `wc -l doctor_dictation/core/patientctx.py doctor_dictation/api/patientctx.py doctor_dictation/db/spoken.py doctor_dictation/api/stt.py`. Expected: each file inside its File Structure budget and under 500 lines.
- [ ] **Step 4: Check by hand (single mode, temp database).** Run `DB_PATH=$(mktemp -d)/h4.db STT_USE_HINTS=1 .venv/bin/uvicorn doctor_dictation.main:app --port 8001`. Save two visits for one patient with an OP number, start a third dictation for that patient, and record a spoken correction. Expected: the hints the provider received list that patient's medicines first, with no patient name.
- [ ] **Step 5: Leave uncommitted.** List the changed files and the Preflight table (A1–A7 found or missing).

## Self-Review

- Coverage of index row 4: the 5.6 match rule with decision 7 (Task 1); `patient_term_keys` and the candidate rule (Task 2); the tier-3 lift by `HintTerm.key`, correction recordings only, S2 (Task 3); isolation (Task 4); no table (Global Constraints). Each Review Focus row has a test. `match_patient`, `patient_candidates`, `patient_term_keys`, `doctor_id`, `clean_patient` and `context_keys` keep one signature across tasks.
- **Owner answers (decision 7, 2026-10-21):** equal rows (same name, age and sex) are one person, read-only; the name must match exactly. Both are pinned in Task 1 tests 2 and 3 and Task 3 test 2.
- Deliberately out of scope: the near-tie context in format, correct or Spell it (SH-B4); the early-clip variant (SH-B1); a labelled "this patient's earlier medicines" group (SH-B2); merging duplicate patient rows; patient hints on a first dictation (it has no context).

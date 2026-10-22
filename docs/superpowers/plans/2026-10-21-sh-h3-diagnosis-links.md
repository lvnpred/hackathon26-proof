# SH-H3: Diagnosis Links Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** Each save teaches "for this diagnosis, this doctor used these medicines and tests" (`term_links`, counted once per document). A spoken correction now sends the sheet's diagnosis lines and patient fields as an optional `context` field on `POST /api/transcribe`. The server reads it, and the doctor's terms linked to that diagnosis in 2 or more saves go first in the speech hints (tier 2). The context never reaches a speech engine. A bad context is ignored with one log line. **The near-tie part is cut** (Disagreement 1) and proposed as backlog card SH-B4 (end of file). Adds 8 tests. Runs AFTER H1 (and H2 if built).

**Goal:** Learn diagnosis ↔ term links on save and use them, from a correction's `context`, to put the doctor's linked terms first in the speech hints.

**Architecture:** Pure rules go in `core/spoken.py` (diagnosis key, context parsing, tier raise). SQL goes in `db/spoken.py` (record and read links). The save hook stays H1's `learn_spoken_terms`, plus one H3 call. `api/stt.py` reads the form field, parses it, and passes it to `_doctor_terms(context)`. That function raises the tier of linked terms the doctor already has; it never adds a term. The page appends `context` in `transcribe(blob)` only when the recording is a correction.

**Tech Stack:** Python 3.12, FastAPI 0.143 / Starlette 1.7, stdlib sqlite3, vanilla JS, pytest, node (frontend tests skip without it). No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-21-sh-00-index-and-contracts.md` (binding): row 3, 5.1 (`013_term_links.sql`), 5.2 `diagnosis_key`, 5.3, 5.5, 5.6, S1–S5. Conventions: section 2 of `docs/superpowers/plans/2026-10-13-00-index-and-contracts.md`.

**Assumptions about earlier plans** (H1 is written in parallel; only index names are relied on; Task 0 re-finds each with `grep -n`):

- **A1 (5.2)** `core/spoken.py` has `key`, `Term`, frozen `HintTerm(phrase, weight, tier=0)`, `usual_strength`, `phrase`, `rank`, `terms_from_save`.
- **A2 (5.1)** `011_spoken_terms.sql` creates `spoken_terms`, `spoken_term_strengths` and `spoken_term_docs` as written. H2's `012` is not needed.
- **A3 (5.3)** `db/spoken.py` has `record_terms(conn, doctor_id, terms, document_id)`. `doctor_hint_terms(conn, doctor_id, today)` returns every active term of the doctor; each `phrase` is `phrase(spoken, usual_strength({strength: uses}))`.
- **A4 (5.5)** `api/spoken.py learn_spoken_terms(conn, structured, document_id, user_id)` runs after `remember_from_save` (today `api/persistence.py:344-348`). It builds the save's `list[Term]` and calls `record_terms`. `doctor_id` is `user_id or 0`.
- **A5 (5.3)** `api/stt.py _doctor_terms(context=None)` replaces `_doctor_top` (`:21-32`). `_prepare_audio` (`:35-45`) runs it in a thread and calls `build_hints(doctor_terms, limit)`. `doctor_id` is the scope's `user_id`, else 0.
- **A6** Two saves of a confirmed, verified `Dolo` / `650 mg` row give one term with the phrase `Dolo 650` (`_exact_lookup("Dolo") == "Paracetamol"`, checked: hint-eligible). **A7 (H2)** If tier 1 exists, `rank` puts tier 2 before it.

## Disagreements with the index

1. **Row 3 "near-tie use" is cut** (unsafe on `/api/format`, near-nil on `/api/v1/correct`; card SH-B4 at the end). (a) The `/api/format` cache key (`api/format.py:125-126`) is per clinic, has no doctor id and is built before the LLM returns the diagnosis. Yet the cached draft holds `did_you_mean`, computed through `formulary.tie_break` (`core/rowcheck.py:91` → `_best_alike` `:196` → `_sound_options` `:155`). Other doctors would get a diagnosis-ordered Did you mean that goes stale as links change. (b) `_DYM_CACHE` is keyed `(letters, layer, id(lex))` (`:239`). (c) A band reorder changes Did you mean only for clinic names that share a generic: a different-generic rival within `INLINE_GAP` 0.05 already suppresses it (`:207`). (d) Spell it is `POST /api/v1/rx/check-row` (`api/rx.py:55`), which receives no diagnosis.
   **Cache-key finding:** H3 sets no grounding context, so the key stays as it is. No later plan should set one on `/api/format`: a link set known only after the draft cannot be part of a key built before it.
2. **5.6 "oversize → never a 4xx"** holds from 4097 bytes to 5 MB. Above 5 MB the upload routes refuse the whole request (`400 Part exceeded maximum size of 5120KB`) before the route body runs: `api/forms.py FormLimitRoute` (added 2026-10-21 at the owner's request; Starlette's own default is 1 MB). The page never sends more than 4096 bytes. The probe also showed that `context: str | None = Form(None)` gives **422** for a file part, so the plan uses `context: Any = Form(None)` (200; the `UploadFile` is ignored).
3. **`HintTerm` has no term identity** (5.2), so ids from `linked_term_ids` (and H2's ids, H4's keys) cannot be mapped to it. H3 matches by phrase key: `db/spoken.term_phrase_keys` rebuilds each phrase with the contract's `phrase`/`usual_strength`, and the pure `spoken.with_tier` raises the tier. H2 and H4 can reuse both. Cleaner, but an index decision: `HintTerm.term_id: int = 0`.
4. **5.3 gives `record_links(...)` no signature.** H3 fixes it as `record_links(conn, doctor_id, diagnosis_keys, term_refs, document_id) -> int` and adds `term_phrase_keys`.
5. **5.6 sets no limit for the patient fields.** H3 uses 200 characters each, like a diagnosis line.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): the additions import only `json` and `dataclasses`. No Python file over 500 lines (`tests/test_file_sizes.py`). `frontend/app.js` is already 1,279 lines (JS is not covered by that test); H3 adds about 10 and does not split it.
- `POST /api/transcribe`: same status codes and the same 200 body, with or without `context`. The 413/400/500 checks run first, unchanged.
- S1: no row's `name`, `status` or `generic` changes, and Spell it and Did you mean are untouched. S2: the `context` field, diagnosis and patient text never reach a speech engine; tier 2 only reorders the doctor's own terms, and `build_hints` still applies H1's eligibility filter. S3: links use only `terms_from_save` terms; diagnosis keys stay in the clinic database and are never logged. S4: the link hook logs and continues. S5: one `term_link_docs` row per (link, document).
- Tests offline. Every DB test uses a temp `DB_PATH`. No `from conftest import *`. Command: `.venv/bin/python -m pytest tests/ -q`. No commits.

## Review Focus

| Input or failure | Expected | Pinned in |
|---|---|---|
| `context` as a file part, non-JSON, over 4096 bytes, 11 lines, a 201-character line, wrong types | 200, the same body, exactly one `transcribe: context ignored (<reason>)` line, no content in the log | Tests 1, 5 |
| The diagnosis written differently ("ACUTE  pharyngitis", "Acute pharyngitis.") | The same key, so the link applies | Tests 1, 3, 4 |
| The same document re-saved; a broken link hook | No count change (S5); the save still succeeds (S4) | Test 3 |
| A colleague in the same clinic; another clinic | No tier 2 from my links; no rows in the other clinic | Test 6 |
| H1 and H3 build the phrase differently (usual strength) | Tier 2 would silently miss; test 4 fails | Test 4 |
| Diagnosis or patient words in the hints | Never | Tests 4, 6 |

## Decisions

Tier 2 only reorders: a linked term the doctor's list lacks is not added, so S2 and the 500-character budget hold. A context that breaks any rule is ignored whole; unknown keys are ignored, so H4 can add keys. The context is parsed whenever it is sent (the log names the reason, never the content) and is used only when hints are on. A re-save counts the document once for each new pair. Diagnosis keys get no S3 filter: they stay in the clinic database, as the document does.

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/db/migrations/013_term_links.sql` | NEW, index 5.1 verbatim |
| `doctor_dictation/core/spoken.py` (H1) | `LINK_MIN`, `CONTEXT_*`, `diagnosis_key`, `diagnosis_keys`, `parse_context`, `with_tier` (+50) |
| `doctor_dictation/db/spoken.py` (H1) | `record_links`, `linked_term_ids`, `term_phrase_keys` (+45) |
| `doctor_dictation/api/spoken.py` (H1), `api/stt.py` | `_learn_links` + one call; `context` field, `_linked_tier` (+40) |
| `frontend/app.js`, `frontend/index.html` | `speechContext()`, one line in `transcribe`; `app.js?v=` +1 |
| NEW `tests/test_term_links.py`, `tests/test_isolation_term_links.py`, `tests/test_frontend_speech_context.py` | tests 1–5, 6, 7–8 |
| `tests/isolation_fixtures.py`, `tests/test_db.py`, `test_authorship_db.py`, `test_template_scope_db.py`, 4 `app.js?v=47` pins | setup lists and pins only |

### Task 0: Preflight

- [ ] **Step 1: Re-find every assumption.** Stop and report if a name is missing or has another shape. Do not invent it.

```bash
grep -n "^def key\|^class HintTerm\|^def usual_strength\|^def phrase\|^def rank\|^def terms_from_save" doctor_dictation/core/spoken.py
grep -n "^def record_terms\|^def doctor_hint_terms" doctor_dictation/db/spoken.py; grep -n "def learn_spoken_terms\|record_terms(\|^log" doctor_dictation/api/spoken.py
grep -n "_doctor_terms\|build_hints(\|def _prepare_audio" doctor_dictation/api/stt.py; grep -n "learn_spoken_terms" doctor_dictation/api/persistence.py
ls doctor_dictation/db/migrations/; grep -n "app.js?v=" frontend/index.html; grep -ln "app.js?v=[0-9]" tests/*.py
grep -n "_overlay.sql\|_spoken_terms.sql\|_mishearings.sql\|n == 1" tests/test_db.py tests/test_authorship_db.py tests/test_template_scope_db.py
```

- [ ] **Step 2: Baseline.** Run: `.venv/bin/python -m pytest tests/ -q`. Note the passed count N and the skip count. Expect N + 8 at the end.

### Task 1: Migration and the pure rules

**Files:** Create `doctor_dictation/db/migrations/013_term_links.sql`, `tests/test_term_links.py`. Modify `doctor_dictation/core/spoken.py`, `tests/test_db.py`, `tests/test_authorship_db.py`, `tests/test_template_scope_db.py`.

**Interfaces:** Produces `spoken.LINK_MIN = 2`, `CONTEXT_BYTES, CONTEXT_LINES, CONTEXT_CHARS = 4096, 10, 200`, `PATIENT_FIELDS = ("name", "age_sex", "op_no")`, `diagnosis_key(line) -> str`, `diagnosis_keys(lines) -> list[str]`, `parse_context(raw) -> tuple[dict | None, str]`, `with_tier(terms, phrase_keys, tier) -> list[HintTerm]`.

- [ ] **Step 1: Write the failing test** (`tests/test_term_links.py`; tests 2–5 are appended later).

```python
"""Plan SH-H3: diagnosis <-> term links learned on save; a correction's context lifts linked terms in the hints. Offline."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.config import override_settings
from doctor_dictation.core import spoken as S
from doctor_dictation.db import spoken as sdb
from doctor_dictation.providers.stt.base import Transcript

H = {"X-DD-Client": "1"}


def test_diagnosis_keys_and_the_context_rules():
    assert S.diagnosis_key(" Acute  Pharyngitis. ") == "acute pharyngitis" and S.diagnosis_key("T2DM & HTN") == "t2dm and htn"
    assert S.diagnosis_key("Hb") == "" and S.diagnosis_key("UTI") == "uti" and S.diagnosis_key("x" * 100) == "x" * 80
    lines = ["Fever", "fever!", 7, "", "Hb"] + [f"Disease {i}" for i in range(12)]
    assert S.diagnosis_keys(lines) == ["fever"] + [f"disease {i}" for i in range(9)]          # unique, at most 10
    ok = json.dumps({"diagnosis": [" Acute  pharyngitis ", ""], "patient": {"name": "Asha  Verma", "op_no": "OP 7"}, "later": 1})
    assert S.parse_context(ok) == ({"diagnosis": ["Acute pharyngitis"],
                                    "patient": {"name": "Asha Verma", "age_sex": "", "op_no": "OP 7"}}, "")
    assert S.parse_context(None) == S.parse_context("") == (None, "")
    bad = [(b"{}", "not text"), ("x" * 4097, "over 4096 bytes"), ("{", "not JSON"), ("[]", "not an object"),
           (json.dumps({"diagnosis": ["a"] * 11}), "bad diagnosis"), (json.dumps({"diagnosis": ["a" * 201]}), "bad diagnosis"),
           (json.dumps({"diagnosis": "fever"}), "bad diagnosis"), (json.dumps({"patient": {"name": 7}}), "bad patient"),
           (json.dumps({"patient": "Asha"}), "bad patient")]
    for raw, reason in bad:
        assert S.parse_context(raw) == (None, reason), raw
    wide = json.dumps({"diagnosis": ["अ" * 200] * 6}, ensure_ascii=False)     # characters per line; bytes for the whole field
    assert S.parse_context(wide)[0]["diagnosis"] == ["अ" * 200] * 6
    t = [S.HintTerm("Pan 40", 3.0), S.HintTerm("Dolo 650", 1.0, 1), S.HintTerm("CBC", 0.5, 3)]
    assert S.with_tier(t, {"dolo 650", "cbc"}, 2) == [t[0], S.HintTerm("Dolo 650", 1.0, 2), t[2]]   # never lowers a tier
    assert [h.phrase for h in S.rank(S.with_tier(t, {"dolo 650"}, 2))] == ["CBC", "Dolo 650", "Pan 40"]
```

- [ ] **Step 2: Run it.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q`. Expected: FAIL, `AttributeError: module 'doctor_dictation.core.spoken' has no attribute 'diagnosis_key'`.
- [ ] **Step 3: Write the migration** `013_term_links.sql`. Use the two `CREATE TABLE` statements of index 5.1 (`term_links`, `term_link_docs`) character for character. Put this comment above them: `-- 013: per doctor, how many saved documents paired a diagnosis line (spoken.diagnosis_key) with a medicine or investigation term. A link is used at count >= 2; term_link_docs counts each document once (plan SH-H3).`
- [ ] **Step 4: Add the rules to `core/spoken.py`.** Add `import json` and the constants. Write the functions after H1's code.
  - `diagnosis_key(line)`: `key(line)[:80]` (5.2, exactly), and `""` when it has fewer than 3 letters (`str.isalpha` count). A non-str gives `""`.
  - `diagnosis_keys(lines)`: unique non-empty keys of the str items, in order, at most `CONTEXT_LINES`. `lines` that is not a list or tuple gives `[]`.
  - `with_tier(terms, phrase_keys, tier)`: `dataclasses.replace(t, tier=max(t.tier, tier))` where `key(t.phrase) in phrase_keys`. Other terms stay as they are, in input order.
  - `parse_context(raw)`, checked in this order: `None` or `""` → `(None, "")`. Not a `str` (an `UploadFile`) → `"not text"`. UTF-8 length (`errors="replace"`) over `CONTEXT_BYTES` → `f"over {CONTEXT_BYTES} bytes"`. `json.loads` raises `ValueError`/`RecursionError` → `"not JSON"`. Not a dict → `"not an object"`. `diagnosis` (default `[]`) is not a list of at most `CONTEXT_LINES` strings of at most `CONTEXT_CHARS` → `"bad diagnosis"`. `patient` (default `{}`) is not a dict whose `PATIENT_FIELDS` (default `""`) are strings of at most `CONTEXT_CHARS` → `"bad patient"`. Otherwise return `({"diagnosis": lines with spaces collapsed and blanks dropped, "patient": the three fields with spaces collapsed}, "")`. Unknown keys are ignored.
- [ ] **Step 5: Update the migration pins** (setup lists only). In `tests/test_db.py` (`test_init_db_idempotent`), `tests/test_authorship_db.py` and `tests/test_template_scope_db.py`, append `"013_term_links.sql"` after the last listed migration. In `tests/test_db.py`, also raise `assert n == ...` by one.
- [ ] **Step 6: Run.** Run: `.venv/bin/python -m pytest tests/test_term_links.py tests/test_db.py tests/test_authorship_db.py tests/test_template_scope_db.py tests/test_core_purity.py -q`. Expected: all pass.
- [ ] **Step 7: Leave uncommitted.**

### Task 2: Link SQL

**Files:** Modify `doctor_dictation/db/spoken.py`. Append to `tests/test_term_links.py`.

**Interfaces:** Consumes the 5.1 tables and `spoken.key`, `phrase`, `usual_strength`, `LINK_MIN`. Produces `record_links(conn, doctor_id: int, diagnosis_keys, term_refs, document_id) -> int` (`term_refs` = `[(kind, term_key)]`; returns the pairs newly counted; commits), `linked_term_ids(conn, doctor_id, diagnosis_keys) -> set[int]` and `term_phrase_keys(conn, term_ids) -> set[str]`.

- [ ] **Step 1: Append the failing test.**

```python
def test_links_count_once_per_document_need_two_documents_and_stay_per_doctor(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "links.db"))
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    d1, d2 = (dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(2))
    now = "2026-10-21T08:00:00Z"

    def term(doctor, kind, key, spoken, strengths=()):
        tid = conn.execute("INSERT INTO spoken_terms(doctor_id, kind, term_key, spoken, uses, first_used_at, last_used_at)"
                           " VALUES (?, ?, ?, ?, 2, ?, ?)", (doctor, kind, key, spoken, now, now)).lastrowid
        conn.executemany("INSERT INTO spoken_term_strengths(term_id, strength, uses) VALUES (?, ?, ?)",
                         [(tid, s, n) for s, n in strengths])
        return tid
    dolo, cbc = term(7, "medicine", "dolo", "Dolo", [("650 mg", 2)]), term(7, "investigation", "cbc", "CBC")
    term(8, "medicine", "dolo", "Dolo")                                        # a colleague's own term, same key
    refs, keys = [("medicine", "dolo"), ("investigation", "cbc"), ("medicine", "nope")], ["acute pharyngitis", "fever"]
    assert sdb.record_links(conn, 7, keys, refs, d1) == 4                      # 2 keys x 2 known terms; "nope" skipped
    assert sdb.record_links(conn, 7, keys, refs, d1) == 0                      # the same document again (S5)
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis"]) == set()       # one document is not enough
    assert sdb.record_links(conn, 7, ["acute pharyngitis"], refs, d2) == 2
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis", "gastritis"]) == {dolo, cbc}
    assert sdb.linked_term_ids(conn, 7, ["fever"]) == sdb.linked_term_ids(conn, 8, ["acute pharyngitis"]) == set()
    assert sdb.linked_term_ids(conn, 7, []) == set()
    assert sdb.term_phrase_keys(conn, {dolo, cbc}) == {"dolo 650", "cbc"}     # the phrase doctor_hint_terms shows (A3)
    conn.execute("UPDATE spoken_terms SET removed_at = ? WHERE id = ?", (now, cbc))
    conn.commit()
    assert sdb.linked_term_ids(conn, 7, ["acute pharyngitis"]) == {dolo}      # a removed term is never lifted
    conn.close()
```

- [ ] **Step 2: Run it.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q -k record`. Expected: FAIL, `AttributeError: ... 'record_links'`.
- [ ] **Step 3: Implement** in `db/spoken.py`, following the ledger pattern of `db/formulary.py:8 record_confirmation`. Use `_utcnow` from `doctor_dictation.db`.
  - `record_links`: for each unique `(kind, term_key)`, look up `spoken_terms.id` for this `doctor_id`; skip it when the row is missing. For each unique non-empty key: `INSERT OR IGNORE` into `term_links` (count 0, `last_seen_at` now). Then select the link id. If `INSERT OR IGNORE INTO term_link_docs` has `rowcount` 1, run `count = count + 1, last_seen_at = now`. Commit once at the end.
  - `linked_term_ids`: `SELECT DISTINCT l.term_id FROM term_links l JOIN spoken_terms t ON t.id = l.term_id WHERE l.doctor_id = ? AND l.count >= ? AND t.removed_at IS NULL AND l.diagnosis_key IN (<one ? per key>)`, with `LINK_MIN`. Return `set()` without a query when there are no keys. Use at most `CONTEXT_LINES` keys.
  - `term_phrase_keys`: for each id, read `spoken` and `{strength: uses}` and return `spoken.key(spoken.phrase(spoken_text, spoken.usual_strength(uses)))`. Skip a missing id.
- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q`. Expected: 2 passed.
- [ ] **Step 5: Leave uncommitted.**

### Task 3: Learn the links on save

**Files:** Modify `doctor_dictation/api/spoken.py`. Append to `tests/test_term_links.py`.

**Interfaces:** Consumes `learn_spoken_terms` (A4), `spoken.diagnosis_keys`, `sdb.record_links`. Produces `_learn_links(conn, structured, terms, document_id, user_id) -> None`. It never raises.

- [ ] **Step 1: Append the fixtures and the failing test.**

```python
class Recorder:
    def __init__(self):
        self.calls = []

    async def transcribe(self, audio, filename, hints=()):
        self.calls.append({"audio": audio, "filename": filename, "hints": hints})
        return Transcript(text="hello", engine="recorder")


def _fake_pdf(structured, meta, out_path, layout=None):
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_bytes(b"%PDF-fake")
    return Path(out_path)


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                       # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", _fake_pdf)
    rec = Recorder()
    monkeypatch.setattr(api_stt, "make_stt", lambda settings: rec)
    with TestClient(create_app()) as c:
        yield c, rec


def _save(c, diagnosis, name, strength, document_id=None):
    row = {"form": "Tab.", "name": name, "strength": strength, "dose": "1-0-1", "status": "verified"}
    body = {"structured": {"patientName": "Asha Verma", "ageSex": "40 / F", "diagnosis": diagnosis, "rx": [row]},
            "confirmed_rows": [0], **({"document_id": document_id} if document_id else {})}
    r = c.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text
    return r.json()["document_id"]


def _links():
    conn = dbmod.get_conn()
    try:
        return [tuple(r) for r in conn.execute("SELECT l.diagnosis_key, t.term_key, l.count FROM term_links l"
                                               " JOIN spoken_terms t ON t.id = l.term_id ORDER BY 1, 2")]
    finally:
        conn.close()


def test_a_save_links_each_diagnosis_line_to_each_term_once_per_document(app_client, monkeypatch):
    c, _ = app_client
    first = _save(c, ["Acute pharyngitis", "Fever"], "Dolo", "650 mg")
    _save(c, ["acute  pharyngitis."], "Dolo", "650 mg")
    _save(c, ["Acute pharyngitis", "Fever"], "Dolo", "650 mg", document_id=first)        # a re-save counts nothing
    assert _links() == [("acute pharyngitis", "dolo", 2), ("fever", "dolo", 1)]
    monkeypatch.setattr(sdb, "record_links", lambda *a, **k: 1 / 0)
    _save(c, ["Fever"], "Dolo", "650 mg")                                               # S4: still saved (200)
    assert _links() == [("acute pharyngitis", "dolo", 2), ("fever", "dolo", 1)]
```

- [ ] **Step 2: Run it.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q -k save_links`. Expected: FAIL, `assert [] == [('acute pharyngitis', 'dolo', 2), ...]`.
- [ ] **Step 3: Implement `_learn_links`** in `api/spoken.py`.
  - Import the module as `from doctor_dictation.db import spoken as sdb` (the test patches the module attribute). Use the module's logger; add `log = logging.getLogger(__name__)` if H1 has none.
  - Body: `keys = spoken.diagnosis_keys(structured.get("diagnosis") if isinstance(structured, dict) else None)`. If there are keys and terms: `sdb.record_links(conn, int(user_id or 0), keys, [(t.kind, t.key) for t in terms], document_id)`.
  - Wrap the whole body in `try/except Exception` with `log.warning("spoken terms: could not record diagnosis links", exc_info=True)` and `# noqa: BLE001`, like `learn_from_save` (`api/formulary.py:75`).
  - In `learn_spoken_terms`, call `_learn_links(conn, structured, terms, document_id, user_id)` right after the `record_terms(...)` call. Pass H1's local list of `Term`s; re-find its name with `grep -n "record_terms(" doctor_dictation/api/spoken.py`. Place it before any H2 block. It has its own `try`, so a link failure never skips H2's work.
- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q`. Expected: 3 passed.
- [ ] **Step 5: Leave uncommitted.**

### Task 4: The `context` field and tier 2

**Files:** Modify `doctor_dictation/api/stt.py`. Append to `tests/test_term_links.py`.

**Interfaces:** Consumes `spoken.parse_context`, `diagnosis_keys`, `with_tier`, `sdb.linked_term_ids`, `term_phrase_keys`, and `_doctor_terms` (A5). Produces the route `transcribe(audio: UploadFile = File(...), context: Any = Form(None))`, `_prepare_audio(raw, filename, settings, context=None)` and `_linked_tier(conn, doctor_id, terms, context) -> list[HintTerm]`. H4 reads the parsed `context["patient"]` in the same `_doctor_terms(context)` call.

- [ ] **Step 1: Append the failing tests.**

```python
def _post(c, context=None, files=None):
    files = files or {"audio": ("note.webm", b"RAWBYTES", "audio/webm")}
    return c.post("/api/transcribe", files=files, data={} if context is None else {"context": context}, headers=H)


def test_a_correction_context_puts_linked_terms_first_and_never_reaches_the_engine(app_client, monkeypatch):
    c, rec = app_client
    for _ in range(2):
        _save(c, ["Acute pharyngitis"], "Dolo", "650 mg")
    for _ in range(3):
        _save(c, ["Gastritis"], "Pan", "40 mg")                                        # more used: first without context
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=70)
    ctx = json.dumps({"diagnosis": ["ACUTE  pharyngitis"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": ""}})
    plain, linked = _post(c), _post(c, ctx)
    assert plain.status_code == linked.status_code == 200 and plain.json() == linked.json()   # the body is unchanged
    h0, h1 = (list(call["hints"]) for call in rec.calls)
    assert h0.index("Pan 40") < h0.index("Dolo 650") and h1.index("Dolo 650") < h1.index("Pan 40")
    sent = " ".join(h0 + h1).casefold()
    assert "pharyngitis" not in sent and "asha" not in sent and "verma" not in sent   # S2: context never leaves
    assert all(set(call) == {"audio", "filename", "hints"} for call in rec.calls)


def test_a_malformed_context_is_ignored_with_one_log_line_and_the_same_body(app_client, monkeypatch, capsys):
    c, _ = app_client
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False)
    good = _post(c).json()
    assert _post(c, json.dumps({"diagnosis": []})).json() == good
    assert "context ignored" not in capsys.readouterr().out                           # valid and empty: silent
    audio = ("note.webm", b"RAWBYTES", "audio/webm")
    bad = [dict(context="not json"), dict(context="[1]"), dict(context=json.dumps({"diagnosis": "Asha fever"})),
           dict(context=json.dumps({"diagnosis": ["Asha"] * 11})), dict(context=json.dumps({"diagnosis": ["Asha" * 51]})),
           dict(context=json.dumps({"patient": {"name": 7}})), dict(context="Asha " * 900),
           dict(files={"audio": audio, "context": ("c.json", b'{"diagnosis": ["Asha"]}', "application/json")})]
    for kw in bad:
        r = _post(c, **kw)
        out = capsys.readouterr().out
        assert (r.status_code, r.json()) == (200, good), kw
        assert out.count("transcribe: context ignored (") == 1 and "Asha" not in out, (kw, out)
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_term_links.py -q -k "context"`. Expected: the first FAILS on `h1.index("Dolo 650") < h1.index("Pan 40")`. The second FAILS on the log-line count.
- [ ] **Step 3: Change the route** (`api/stt.py:48-49`, and the `_prepare_audio` call at `:64`).
  - Add `from typing import Any` and `Form` to the fastapi import. Add `from doctor_dictation.core import spoken` and `from doctor_dictation.db import spoken as sdb`.
  - The signature becomes `async def transcribe(audio: UploadFile = File(...), context: Any = Form(None)):`. Keep `Any`: `str` makes a file part a 422 (Disagreement 2).
  - After the `make_stt` block and before `_prepare_audio`, add:

```python
    ctx, problem = spoken.parse_context(context)           # index 5.6: never sent to the speech engine
    if problem:
        print(f"transcribe: context ignored ({problem})", flush=True)      # the reason only, never the content
    raw, filename, hints = await _prepare_audio(raw, audio.filename or "dictation.webm", settings, ctx)
```

- [ ] **Step 4: Thread it to `_doctor_terms`.** Give `_prepare_audio` a last parameter `context=None`. Pass it on: find H1's call with `grep -n "_doctor_terms" doctor_dictation/api/stt.py` and make it `asyncio.to_thread(_doctor_terms, context)`.
  - Inside `_doctor_terms`, in H1's open-connection block and right after the terms are read, add `terms = _linked_tier(conn, doctor_id, terms, context)`. Use H1's own variable names.
  - Add `_linked_tier(conn, doctor_id, terms, context)`: `keys = spoken.diagnosis_keys((context or {}).get("diagnosis"))`. Return `terms` when there are no keys or no terms. Else return `spoken.with_tier(terms, sdb.term_phrase_keys(conn, sdb.linked_term_ids(conn, doctor_id, keys)), 2)`. Any exception prints `hints: diagnosis links unavailable: <exception type>` and returns `terms` (`# noqa: BLE001`, like `_doctor_top`).

- [ ] **Step 5: Run.** Run: `.venv/bin/python -m pytest tests/test_term_links.py tests/test_transcribe_acc2.py tests/test_transcribe_route.py tests/test_hints.py -q`. Expected: all pass (`test_term_links.py`: 5 passed).
- [ ] **Step 6: Leave uncommitted.**

### Task 5: The page sends the context on a correction

**Files:** Modify `frontend/app.js` (around `transcribe`, `:486-490`) and `frontend/index.html:285`. Update the pins in `tests/test_frontend_vitals.py:52`, `test_frontend_confirm_next.py:164`, `test_frontend_ixlist_dom.py:368`, `test_frontend_generic_edit_dom.py:256`. Create `tests/test_frontend_speech_context.py`.

**Interfaces:** Produces `speechContext() -> string` (JSON, at most 4096 UTF-8 bytes) in `app.js`. It reads `readList("pDx")` (`:618`) and `text($("pName"|"pAge"|"pOp"))` (the same fields `serializeForm` reads, `:654-658`). The mode is `state.pendingMode`, set at record start (`:374`) from `canCorrect()` (`:403`, a draft is on the sheet).

- [ ] **Step 1: Write the failing tests.**

```python
"""Plan SH-H3: a spoken correction sends the sheet's diagnosis and patient as `context`; a first dictation sends none."""
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

FRONT = Path(__file__).resolve().parents[1] / "frontend"


def _fn(src, head):
    part = src[src.index(head):]
    return part[:part.index("\n}\n") + 3]


def test_a_correction_sends_the_sheets_diagnosis_and_patient_and_a_first_dictation_sends_nothing():
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    script = """
      globalThis.FormData = class { constructor() { this.f = {}; } append(k, v) { this.f[k] = v; } };
      const sent = []; globalThis.fetch = async (url, o) => { sent.push(o.body.f); return { ok: true, status: 200, json: async () => ({ transcript: "x" }) }; };
      const safeJson = async (r) => r.json(), setWorking = () => {}, setStep = () => {}, TRANSCRIBE_TIMEOUT_MS = 1000;
      const sheet = { pName: "  Asha Verma ", pAge: "40 / F", pOp: "OP 7" }; let dx = [" Acute pharyngitis ", "", "Fever"];
      const $ = (id) => ({ id }), text = (el) => sheet[el.id] || "", readList = (id) => (id === "pDx" ? dx : []);
      const state = { pendingMode: "correct", structured: { rx: [] } };
      """ + _fn(app, "function speechContext") + _fn(app, "async function transcribe(") + """
      (async () => {
        await transcribe("blob");
        state.pendingMode = "dictate"; await transcribe("blob");
        state.pendingMode = "correct"; state.structured = null; await transcribe("blob");
        dx = Array.from({ length: 12 }, (_, i) => String(i) + "x".repeat(250)); const many = JSON.parse(speechContext()).diagnosis;
        dx = Array.from({ length: 10 }, () => "अ".repeat(200)); const wide = speechContext();
        console.log(JSON.stringify({ keys: sent.map((f) => Object.keys(f)), first: JSON.parse(sent[0].context),
          many: [many.length, many[0].length, many[9].slice(0, 2)], bytes: new TextEncoder().encode(wide).length, lines: JSON.parse(wide).diagnosis.length }));
      })();"""
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    r = json.loads(out.stdout)
    assert r["keys"] == [["audio", "context"], ["audio"], ["audio"]]          # a correction only, and only with a draft
    assert r["first"] == {"diagnosis": ["Acute pharyngitis", "Fever"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": "OP 7"}}
    assert r["many"] == [10, 200, "9x"]                                       # at most 10 lines of 200 characters
    assert r["bytes"] <= 4096 and r["lines"] == 6                             # whole lines dropped from the end to fit


def test_the_page_loads_the_new_app_js_and_only_the_dictation_route_sends_context():
    app, html = (FRONT / "app.js").read_text(encoding="utf-8"), (FRONT / "index.html").read_text(encoding="utf-8")
    assert int(re.search(r"app\.js\?v=(\d+)", html).group(1)) >= 48
    assert app.count('fd.append("context", speechContext())') == 1 and "context" not in _fn(app, "async function transcribeName")
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_frontend_speech_context.py -q`. Expected: 2 FAIL (`ValueError: substring not found`, then the version assert).
- [ ] **Step 3: Add `speechContext` just above `async function transcribe(blob)`.** The first test was run against exactly this code in a scratch copy (`keys`, `first`, `many`, `bytes 3699`, `lines 6`).

```js
// A spoken correction tells the server the sheet's diagnosis and patient (plan SH-H3). The server never sends it to a speech engine.
function speechContext() {
  const cut = (v) => String(v == null ? "" : v).trim().slice(0, 200);
  const ctx = { diagnosis: readList("pDx").map(cut).filter(Boolean).slice(0, 10),
    patient: { name: cut(text($("pName"))), age_sex: cut(text($("pAge"))), op_no: cut(text($("pOp"))) } };
  while (ctx.diagnosis.length && new TextEncoder().encode(JSON.stringify(ctx)).length > 4096) ctx.diagnosis.pop();
  return JSON.stringify(ctx);
}
```

  Then, in `transcribe`, after `fd.append("audio", blob, "dictation.webm");`, add:
  `if (state.pendingMode === "correct" && state.structured) fd.append("context", speechContext());   // corrections only (plan SH-H3)`. Leave `transcribeName` (Spell it voice, `:512`) unchanged.
- [ ] **Step 4: Bump the cache-buster.** In `frontend/index.html:285`, raise `app.js?v=` by one (47 → 48 unless Task 0 found another number). Replace that exact string in the four pinned tests listed under **Files**. Re-find them with `grep -ln "app.js?v=47" tests/*.py`.
- [ ] **Step 5: Run.** Run: `.venv/bin/python -m pytest tests/test_frontend_speech_context.py tests/test_frontend_steps.py tests/test_frontend_spell_voice_dom.py tests/test_frontend_vitals.py tests/test_frontend_confirm_next.py tests/test_frontend_ixlist_dom.py tests/test_frontend_generic_edit_dom.py -q`. Expected: all pass. `test_frontend_steps.py:144` still slices `"async function transcribe"`; `speechContext` does not start with that text.
- [ ] **Step 6: Leave uncommitted.**

### Task 6: Isolation

**Files:** Create `tests/test_isolation_term_links.py`. Modify `tests/isolation_fixtures.py:41-42` (`TABLES` += `"term_links", "term_link_docs"`, so `fingerprint` covers them).

- [ ] **Step 1: Write the test.** It should pass right away if Tasks 1–4 are correct. Show that it guards: break `linked_term_ids` by removing `l.doctor_id = ? AND`, see the `mehta` assert fail, then restore.

```python
"""Diagnosis links stay with the doctor and the clinic that saved them (plan SH-H3). Offline; the seeded two-clinic world."""
import json

from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from isolation_fixtures import A, B, H, fingerprint, save_body, sql, user_id, world  # noqa: F401

CTX = json.dumps({"diagnosis": ["Acute pharyngitis"], "patient": {"name": "Asha Verma", "age_sex": "40 / F", "op_no": ""}})


def save(client, patient, diagnosis):
    body = save_body(patient, medicine="Dolo")
    body["structured"]["rx"][0]["strength"] = "650 mg"
    body["structured"]["diagnosis"] = [diagnosis]
    body["confirmed_rows"] = [0]
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text


def test_diagnosis_links_lift_only_the_saving_doctors_hints_in_their_own_clinic(world, monkeypatch):
    before_b = fingerprint(B)
    for patient in ("Asha Verma", "Lakshmi Narayan"):
        save(world.rao, patient, "Acute pharyngitis")
        save(world.mehta, "Ravi Kulkarni", "Fever")                     # same clinic, same drug, another diagnosis
    assert fingerprint(B) == before_b and sql(B, "SELECT COUNT(*) FROM term_links")[0][0] == 0
    rows = [tuple(r) for r in sql(A, "SELECT doctor_id, diagnosis_key, count FROM term_links ORDER BY diagnosis_key")]
    assert rows == [(user_id(world, "dr.rao"), "acute pharyngitis", 2), (user_id(world, "dr.mehta"), "fever", 2)]
    override_settings(monkeypatch, llm_provider="stub", allow_stub_providers=True, stt_chain=("stub",),
                      stt_use_hints=True, stt_trim_silence=False)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "mehta", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda terms, limit, who=who: (seen.setdefault(who, list(terms)), real(terms, limit))[1])
        r = getattr(world, who).post("/api/transcribe", data={"context": CTX},
                                     files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    tiers = {who: {t.phrase: t.tier for t in terms} for who, terms in seen.items()}
    assert tiers == {"rao": {"Dolo 650": 2}, "mehta": {"Dolo 650": 0}, "iyer": {}}
```

- [ ] **Step 2: Run.** Run: `.venv/bin/python -m pytest tests/test_isolation_term_links.py tests/test_isolation_formulary.py tests/test_isolation_routes.py -q`. Expected: all pass.
- [ ] **Step 3: Leave uncommitted.**

### Task 7: Mutations, whole suite, sizes, hand-over

- [ ] **Step 1: Mutations.** Apply each one alone. Run `.venv/bin/python -m pytest tests/test_term_links.py tests/test_isolation_term_links.py tests/test_frontend_speech_context.py -q`. See a failure, then revert. Report each mutation as "killed by test N".

| # | Mutation | Must fail |
|---|---|---|
| M1 | `LINK_MIN = 1`; or drop the `term_link_docs` check | 2 (and 3) |
| M2 | `linked_term_ids` without `t.removed_at IS NULL`, or without `l.doctor_id = ?` | 2 (and 6) |
| M3 | `_learn_links` without its `try` | 3 |
| M4 | `_linked_tier` returns `terms` unchanged | 4, 6 |
| M5 | no byte check; the log line prints `raw`; `context` typed as `str` | 1/5, 5, 5 (422) |
| M6 | the page appends `context` for every dictation | 7 |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: N + 8 passed, the same skip count, no failures.
- [ ] **Step 3: Sizes.** Run: `wc -l doctor_dictation/core/spoken.py doctor_dictation/db/spoken.py doctor_dictation/api/spoken.py doctor_dictation/api/stt.py doctor_dictation/api/persistence.py`. Expected: every file is under 500 lines; `api/persistence.py` is unchanged by H3.
- [ ] **Step 4: Leave uncommitted.** Changed files: the File Structure table. Hand over with the mutation results and the open questions below.

## Open questions for the owner

1. Approve cutting the near-tie part to card SH-B4 (Disagreement 1). 2. If H1's `doctor_hint_terms` caps its list (A3), a linked term outside the cap is not lifted: accept, or let `_linked_tier` add terms (that needs H1's weight rule)? 3. Index decision: `HintTerm.term_id` (Disagreement 3).

## Backlog card SH-B4 (proposed): diagnosis near-tie in Spell it

`POST /api/v1/rx/check-row` (`api/rx.py:55`) takes an optional `diagnosis` list with the 5.6 caps (a bad one is ignored, never a 400). The route reads the doctor's linked term keys and activates them in a ContextVar beside `_active` (`core/formulary.py:170`). `tie_break(scored, usage_of, linked_of=None)` (`:142`) sorts the band's clinic slots by `(-linked, -usage, -score, name)`; a lexicon name keeps its slot (S1). Only `options` and `suggestions` pass `linked_of`; `_best_alike` passes none, so Did you mean, `_DYM_CACHE` and the `/api/format` cache stay as they are. The page adds `diagnosis: readList("pDx")` to the check-row call. Size S (about 1 day, 3–4 tests). Do it only if real data shows clinic twins that share a generic.

## Self-Review

Coverage: migration and `diagnosis_key` (Task 1), links on save under S4/S5 (Tasks 2–3), the `context` field and tier 2 (Task 4), the page and pins (Task 5), isolation (Task 6). The near-tie part is cut, with its reasons and a card. The names are the same in every task. Deliberately out of scope: Spell it and Did you mean, patient matching (H4), vectors (SH-B3), splitting `app.js`, Starlette's 1 MB part limit.

# SH-H2: Corrected Mishearings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** A saved medicine row with `heard` "dollo" and name "Dolo" records the pair for that doctor, once per
document. From the second document the pair is active and its term leads that doctor's speech hints (tier 1). A clinic
admin lists and removes pairs in a "Corrected mishearings" section of the Team screen's Medicines tab. Spell it, Did you
mean and the row do not change (S1). Adds 12 tests. Runs AFTER H1, BEFORE H3.

**Goal:** Learn a doctor's repeated mishearings from saved rows and use them only to rank that doctor's hint list.

**Architecture:** A pure pair rule in `core/spoken.py`; SQL in `db/spoken.py`, counted with a ledger like
`db/formulary.py:8-23`; one guarded call inside H1's `learn_spoken_terms`; a tier lift in `api/stt.py _doctor_terms`.
Admin routes copy `api/formulary.py:125-153`. Page: a new `frontend/mishear.js`, wired by `frontend/team.js`.

**Tech Stack:** Python 3.12, FastAPI, stdlib sqlite3, vanilla JS, pytest, node (the frontend tests skip without it).

**Spec:** `docs/superpowers/plans/2026-10-21-sh-00-index-and-contracts.md` (binding): row 2, S1-S5, 5.1 (`012`), 5.2-5.3
(amended 2026-10-21), 5.5, D-SH3. Conventions: `2026-10-13-00-index-and-contracts.md` section 2.

**Assumptions about earlier plans** (H1 is not built; Task 0 finds each name with `grep -n`; H1's plan text is not used):

- A1 `core/spoken.py`: `Term`, `key(text)`, `terms_from_save(structured, known_patient_words)`, `rank(terms)`,
  `HintTerm(phrase, weight, tier=0, term_id=0, key="")`; `term_id` is `spoken_terms.id` (index 5.2, amended).
- A2 `db/spoken.py`: `record_terms(conn, doctor_id, terms, document_id)`; `doctor_hint_terms(conn, doctor_id, today)`
  returns EVERY live term of the doctor with `term_id` set, uncapped (index 5.3, amended). Table `spoken_terms` (011).
- A3 `api/spoken.py`: `learn_spoken_terms(conn, structured, document_id, user_id)`, called by `create_document` after
  `remember_from_save` (`api/persistence.py:348` today); doctor id `user_id or 0` (index 5.5).
- A4 `api/stt.py`: `_doctor_terms(context=None) -> list[HintTerm]` replaced `_doctor_top` (`:21` today); no scope
  (single-database mode) reads doctor 0. `build_hints(doctor_terms, limit)` applies S2 and the budget.
- A5 `tests/test_db.py:88-90` and `tests/test_authorship_db.py:52` list `011_spoken_terms.sql` last.

## Disagreements with the index

1. **The pair rule as written also records brand ↔ generic.** `heard_as` returns an alias of the same medicine too
   (`core/lasa.py:121-123`). Measured on 8c9ce76: "Paracetamol" with transcript "tab crocin 650" gives heard "crocin";
   "Azithromycin" with "tab azithral 500" gives "azithral". That name was said, not misheard. This plan skips a pair
   when `drugnames._exact_lookup(heard)` is non-empty and equals `_exact_lookup(name)`. It also applies S3 to `heard`
   and caps it (60 characters, 9 words): the page sends `heard` back (`frontend/rxview.js:234`) and the save keeps it
   unchecked (`core/correction.py:446-447`).
2. **The tab is "Medicines", not "Clinic medicines",** built by `frontend/clinlists.js:33-57`, not `team.js` (`:70`).
   The section goes into that panel (`#teamMeds`) from a new `mishear.js` that `team.js` wires.
3. **Routes and list/remove SQL are not named in the index.** Added: `GET /api/v1/spoken/mishearings`, `DELETE
   /api/v1/spoken/mishearings/{entry_id}`, `list_active_mishearings(conn)`, `remove_mishearing(conn, entry_id)`; fixed:
   `record_mishearings(conn, doctor_id, pairs, document_id) -> int`, `active_mishearing_term_ids(conn, doctor_id) ->
   set[int]`. A new admin route changes three pinned inventories (`tests/test_isolation_routes.py:31`, `:185-194`;
   `tests/test_isolation_formulary.py:69-70`). Their comments require that review, so Task 4 changes those assertions.

## What `heard` holds after a correction (checked on 8c9ce76)

- **Spell it "Use this" and Did you mean keep a fresh `heard`.** Both run `useName` (`frontend/rxview.js:140`, `:194`):
  it posts the chosen name with the visit transcript to check-row (`:153`), which re-grounds (`api/rx.py:47-52` →
  `core/rowcheck.py:73` → `core/lasa.py:152`). So `heard = heard_as(chosen, transcript)`. The page keeps it (`:161`),
  sends it on save (`:231-235`, `app.js:633`) and the save keeps it. Measured: "Dolo" with "tab dollo 650" → "dollo"
  (verified); "Pan 40" with "tab fan 40" → "fan 40". A real save (temp DB) stored `('Dolo', 'dollo', 'verified')`.
- **A correction makes a pair only when it is close in spelling** (ratio >= 0.8, length within 4: `lasa.py:19`, `:122`).
  "Rosuvas" for "rozavel" gives `heard` "": no pair. **Typing the name into the cell clears `heard`**
  (`frontend/rxstate.js:114-116`): no pair. A name the format step changed also carries `heard` and counts the same.

## Global Constraints

- S1: `core/rowcheck.py`, `core/candidates.py`, `core/formulary.py` and row `name`/`status`/`generic` stay untouched.
  S2: `heard` never reaches a speech engine. S3 on both words of a pair. S4: own `try/except` + log. S5: the ledger.
- Active at `confirm_count >= formulary.THRESHOLD` (2, `core/formulary.py:18`), per doctor (a pair hangs off a term).
- `core/` stays pure (`tests/test_core_purity.py`); no file over 500 lines (`tests/test_file_sizes.py:12`).
- Tests offline; `.venv/bin/python -m pytest tests/ -q`; single mode by hand only with `DB_PATH` on a temp file.
- No commits ("leave uncommitted"). Existing endpoints keep codes and shapes. Plan code blocks use one blank line
  between definitions to save space: write two in the files (PEP 8).

## Review Focus

| Input | Expected | Pinned in |
|---|---|---|
| Brand said, generic saved ("crocin" → Paracetamol) | No pair | Test 1 |
| A forged, oversize, non-text or patient-word `heard` from the page | Ignored | Test 1 |
| The same document saved again; H1's backfill run twice | Counted once | Test 2 |
| A removed pair; its old documents re-saved | Stays removed until 2 NEW documents | Test 5 |
| The pair step fails (locked database) | No exception; H1's terms still recorded | Test 3 |

## File Structure

New: `db/migrations/012_spoken_mishearings.sql`; `frontend/mishear.js` (~75 lines); tests
`test_spoken_mishearings.py` (6), `test_isolation_mishearings.py` (2), `test_frontend_mishearings.py` (4). Changed (H1
files): `core/spoken.py` (+25: the rule), `db/spoken.py` (+50: four SQL functions), `api/spoken.py` (+45: pair step,
two routes), `api/stt.py` (+3: tier lift), `api/app.py` (router, only if H1 did not register one). Changed (baseline):
`frontend/team.js` (283 → 287), `frontend/index.html`; test inventories and pins named in each task. Baseline on
8c9ce76 before H1: 2824 passed, 1 skipped. Expect N + 12 (N = the count after H1), same skips.

### Task 0: Preflight

- [ ] **Step 1: Find H1's names.** `grep -n "def key\|def terms_from_save\|def rank\|class HintTerm\|term_id"
  doctor_dictation/core/spoken.py`; `grep -n "def record_terms\|def doctor_hint_terms" doctor_dictation/db/spoken.py`;
  `grep -n "def learn_spoken_terms\|record_terms\|patient_words\|router\|^log" doctor_dictation/api/spoken.py`;
  `grep -n "_doctor_terms\|doctor_hint_terms" doctor_dictation/api/stt.py`; `grep -n spoken doctor_dictation/api/app.py`.
  Each A1-A4 name must exist. Note H1's variable names for the doctor id and the patient words in
  `learn_spoken_terms`. A differing name: use H1's and report it. Then run `.venv/bin/python -m pytest tests/ -q`; note N.

### Task 1: The migration and the pair rule (pure)

**Files:** Create `db/migrations/012_spoken_mishearings.sql`, `tests/test_spoken_mishearings.py`. Modify
`core/spoken.py`, `tests/test_db.py:88-90`, `tests/test_authorship_db.py:52`.

**Interfaces:** Produces `spoken.MAX_HEARD_CHARS = 60`, `spoken.MAX_HEARD_WORDS = 9`,
`spoken.mishearings_from_save(structured, known_patient_words) -> list[tuple[str, str]]` ((term key, heard)).

- [ ] **Step 1: Write the failing test.**
```python
"""Corrected mishearings (plan SH-H2): the pair rule, the ledger, tier 1 in the hints, the admin routes. Offline."""
import sqlite3

from fastapi.testclient import TestClient

from doctor_dictation import db as dbmod
from doctor_dictation.api import stt as api_stt
from doctor_dictation.api.app import create_app
from doctor_dictation.api.spoken import learn_spoken_terms
from doctor_dictation.core import spoken
from doctor_dictation.core.hints import build_hints
from doctor_dictation.db import spoken as sdb

H = {"X-DD-Client": "1"}
DOLO = {"name": "Dolo", "heard": "dollo"}

def test_pairs_come_only_from_rows_whose_heard_is_another_word():
    s = {"patientName": "Ravi Kumar", "rx": [
        {"name": "Dolo", "heard": "dollo"}, {"name": "Dolo", "heard": " DOLLO "},   # a pair; once per document
        {"name": "Crocin", "heard": ""},                     # said as written
        {"name": "Paracetamol", "heard": "crocin"},          # another name of the same medicine
        {"name": "Montair-LC", "heard": "montair lc"},       # the same words by key
        {"name": "Zorbexin", "heard": "Asha"}, {"name": "Zorbexin", "heard": "Ravi Kumar"},   # S3: patient word, person-like
        {"name": "Zorbexin", "heard": "z" * 61}, {"name": "Zorbexin", "heard": "a b c d e f g h i j"},   # too long
        {"name": "Zorbexin", "heard": 42}, "not a row",      # junk from the page
        {"name": "Zorbexin", "heard": "zorbexen"},           # an unknown name misheard: a pair (stored, never hinted)
    ]}
    term = lambda name: spoken.terms_from_save({"rx": [{"name": name}]}, frozenset())[0].key   # noqa: E731 - H1's key
    assert spoken.mishearings_from_save(s, frozenset({"asha"})) == [(term("Dolo"), "dollo"), (term("Zorbexin"), "zorbexen")]
    assert spoken.mishearings_from_save({"rx": "x"}, frozenset()) == spoken.mishearings_from_save(None, frozenset()) == []
    assert (spoken.MAX_HEARD_CHARS, spoken.MAX_HEARD_WORDS) == (60, 9)
```
- [ ] **Step 2: Run it.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py -q`. Expected: FAIL,
  `AttributeError: module 'doctor_dictation.core.spoken' has no attribute 'mishearings_from_save'`.
- [ ] **Step 3: The migration.** The `-- 012` block of index 5.1 byte for byte, under one comment line: `-- 012 (plan
  SH-H2): a doctor's misheard words, counted once per document; active at 2; a removal resets the count, like 009.`
- [ ] **Step 4: The rule in `core/spoken.py`**, after `terms_from_save`. Docstring: "[(term key, heard)] of a saved
  form (plan SH-H2): medicine rows whose heard is another word than the name." `MAX_HEARD_CHARS, MAX_HEARD_WORDS = 60,
  9` (check-row's name caps, `api/rx.py:16-17`, plus the one word `heard_as` may add). Import `person_like` from
  `.formulary` and `_exact_lookup` from `.drugnames` if H1 has not. Per row, in this order, skip on the first hit:
  1. not a dict, or `heard` not a `str`; then collapse whitespace in `heard`;
  2. `heard` empty or over the caps; `key(heard)` empty or equal to `key(name)`;
  3. `_exact_lookup(heard)` non-empty and equal to `_exact_lookup(name)` (another name of the same medicine);
  4. `person_like(heard)`, or a word of 3+ letters of `heard` in `known_patient_words` (S3);
  5. no medicine `Term` from `terms_from_save({"rx": [row], "patientName": structured.get("patientName", "")}, known)`.
  Else append `(term.key, heard)` unless `(term.key, key(heard))` is already in. A non-dict form or non-list `rx` → `[]`.
- [ ] **Step 5: Migration lists.** Add `"012_spoken_mishearings.sql"` after `"011_spoken_terms.sql"` in
  `tests/test_db.py:88-90` and `tests/test_authorship_db.py:52` (re-find: `grep -n 011_spoken_terms tests/*.py`).
- [ ] **Step 6: Run.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py tests/test_db.py tests/test_authorship_db.py tests/test_core_purity.py -q`. Expected: all pass.
- [ ] **Step 7: Leave uncommitted.**

### Task 2: The ledger, the save hook and tier 1

**Files:** Modify `db/spoken.py`, `api/spoken.py`, `api/stt.py`; append to `tests/test_spoken_mishearings.py`.

**Interfaces:** Consumes Task 1, A1-A4. Produces `sdb.record_mishearings(conn, doctor_id, pairs, document_id) -> int`
(pairs counted now), `sdb.active_mishearing_term_ids(conn, doctor_id) -> set[int]`, the SQL fragment `sdb.ACTIVE`.

- [ ] **Step 1: Append the failing tests.**
```python
def _db(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "s.db"))                # never the real dev database
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    return conn, (dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(20))

def rx(*rows):
    return {"patientName": "Ravi Kumar", "rx": [{"form": "Tab.", "strength": "", "status": "verified", **r} for r in rows]}

def test_a_pair_counts_once_per_document_and_is_active_from_the_second(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    first = next(docs)
    learn_spoken_terms(conn, rx(DOLO), first, None)
    learn_spoken_terms(conn, rx(DOLO), first, None)                                   # a re-save of the same document
    assert [tuple(r) for r in conn.execute("SELECT confirm_count, removed_at FROM spoken_mishearings")] == [(1, None)]
    assert sdb.active_mishearing_term_ids(conn, 0) == set()
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    (tid,) = sdb.active_mishearing_term_ids(conn, 0)
    assert conn.execute("SELECT spoken FROM spoken_terms WHERE id = ?", (tid,)).fetchone()[0] == "Dolo"
    assert sdb.active_mishearing_term_ids(conn, 7) == set()                         # another doctor: untouched
    assert sdb.record_mishearings(conn, 0, [("nosuchterm", "nosuchtern")], next(docs)) == 0   # no term: nothing stored
    assert conn.execute("SELECT COUNT(*) FROM spoken_mishearings").fetchone()[0] == 1
    conn.close()

def test_a_failing_pair_step_never_blocks_the_save_or_the_terms(tmp_path, monkeypatch, caplog):
    conn, docs = _db(tmp_path, monkeypatch)
    monkeypatch.setattr(sdb, "record_mishearings", lambda *_a: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)                            # no exception (S4)
    assert [r[0] for r in conn.execute("SELECT spoken FROM spoken_terms")] == ["Dolo"]   # H1's part still ran
    assert "spoken mishearings" in caplog.text
    conn.close()

def test_an_active_pair_puts_its_term_first_and_the_heard_word_never_leaves(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    for _ in range(3):
        learn_spoken_terms(conn, rx({"name": "Pan", "heard": ""}), next(docs), None)
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert [(h.phrase, h.tier) for h in spoken.rank(api_stt._doctor_terms(None))][:2] == [("Pan", 0), ("Dolo", 0)]
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)                            # the second document: active
    terms = api_stt._doctor_terms(None)
    assert [(h.phrase, h.tier) for h in spoken.rank(terms)][:2] == [("Dolo", 1), ("Pan", 0)]   # 2 uses beat 3 by tier
    hints = build_hints(terms, 70)
    assert hints[:2] == ["Dolo", "Pan"] and not [h for h in hints if "dollo" in h.casefold()]   # S2
    conn.close()
```
- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py -q`. Expected: 3 FAIL:
  `assert [] == [(1, None)]`; `AttributeError` on the `setattr` (no `record_mishearings`); `('Pan', 0)` still first.
- [ ] **Step 3: SQL in `db/spoken.py`** (import `THRESHOLD` from `core.formulary` and `key` from `core.spoken` if H1
  has not). `ACTIVE = "m.removed_at IS NULL AND m.confirm_count >= ? AND t.removed_at IS NULL"` (binds `THRESHOLD`).
  `record_mishearings` follows `db/formulary.py:8-23` for each pair: find the term (`SELECT id FROM spoken_terms WHERE
  doctor_id = ? AND kind = 'medicine' AND term_key = ?`; none: skip); `INSERT OR IGNORE` the pair (`heard_key =
  key(heard)`, `first_seen_at = last_seen_at = _utcnow()`) and read its id; `INSERT OR IGNORE` into
  `spoken_mishearing_docs`. Only when that inserted (`.rowcount`): `confirm_count + 1`, `last_seen_at = now`,
  `removed_at = CASE WHEN confirm_count + 1 >= THRESHOLD THEN NULL ELSE removed_at END`, and count it. One commit at
  the end; return the count. `active_mishearing_term_ids`: the set of `SELECT DISTINCT m.term_id FROM
  spoken_mishearings m JOIN spoken_terms t ON t.id = m.term_id WHERE t.doctor_id = ? AND {ACTIVE}`.
- [ ] **Step 4: The pair step in `api/spoken.py learn_spoken_terms`**, right after H1's `record_terms` call, in its own
  `try` (S4): `sdb.record_mishearings(conn, doctor_id, spoken.mishearings_from_save(structured, known), document_id)`;
  `except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved` →
  `log.warning("spoken mishearings: could not record pairs", exc_info=True)`. Use H1's doctor-id and patient-words
  variables (Task 0), else `fdb.patient_words(conn)` (`db/formulary.py:44`). Call through the module (test 3 patches it).
- [ ] **Step 5: The tier lift in `api/stt.py _doctor_terms`**, on H1's `doctor_hint_terms` result, same connection and
  doctor id: `active = sdb.active_mishearing_term_ids(conn, doctor_id)`, then
  `terms = [replace(h, tier=max(h.tier, 1)) if h.term_id in active else h for h in terms]` (`dataclasses.replace`).
- [ ] **Step 6: Run.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py -q`, then H1's test files
  (`grep -ln "learn_spoken_terms\|_doctor_terms" tests/*.py`). Expected: all pass (4 in the new file).
- [ ] **Step 7: Leave uncommitted.**

### Task 3: List and remove (admin routes)

**Files:** Modify `db/spoken.py`, `api/spoken.py`, `api/app.py` (only if H1 registered no spoken router); append to
`tests/test_spoken_mishearings.py`.

**Interfaces:** Produces `sdb.list_active_mishearings(conn) -> list[dict]` (keys `id, spoken, heard, confirm_count,
first_seen_at, last_seen_at, doctor_id, doctor`), `sdb.remove_mishearing(conn, entry_id) -> dict | None` (`{"spoken",
"heard"}`); `GET /api/v1/spoken/mishearings` → 200 `{"items"}` | 503; `DELETE /api/v1/spoken/mishearings/{entry_id}`
→ 200 `{"removed", "spoken", "heard"}` | 401 | 403 | 404 | 422 | 503.

- [ ] **Step 1: Append the failing tests.**
```python
def test_removal_is_soft_and_only_new_documents_bring_a_pair_back(tmp_path, monkeypatch):
    conn, docs = _db(tmp_path, monkeypatch)
    first = [next(docs), next(docs)]
    for d in first:
        learn_spoken_terms(conn, rx(DOLO), d, None)
    (item,) = sdb.list_active_mishearings(conn)
    assert (item["spoken"], item["heard"], item["confirm_count"], item["doctor_id"], item["doctor"]) == ("Dolo", "dollo", 2, 0, "")
    assert sdb.remove_mishearing(conn, item["id"]) == {"spoken": "Dolo", "heard": "dollo"}
    assert sdb.remove_mishearing(conn, item["id"]) is None and sdb.list_active_mishearings(conn) == []
    for d in first:
        learn_spoken_terms(conn, rx(DOLO), d, None)                                 # old documents re-saved: no count
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert sdb.active_mishearing_term_ids(conn, 0) == set()                         # 1 new document of 2
    learn_spoken_terms(conn, rx(DOLO), next(docs), None)
    assert len(sdb.active_mishearing_term_ids(conn, 0)) == 1
    assert conn.execute("SELECT COUNT(*) FROM spoken_mishearings").fetchone()[0] == 1   # the same row came back
    conn.close()

def test_the_routes_list_and_remove_like_the_formulary_routes_and_spell_it_is_unchanged(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "r.db"))
    row = {"form": "Tab.", "name": "Dolo", "status": "verified", "heard": "dollo"}
    ask, url = {"row": {"name": "dollo"}, "transcript": "tab dollo 650 twice daily"}, "/api/v1/spoken/mishearings"
    with TestClient(create_app()) as c:
        before = c.post("/api/v1/rx/check-row", json=ask, headers=H).json()
        for patient in ("Sita Devi", "Mohan Lal"):
            body = {"structured": {"patientName": patient, "ageSex": "40 / M", "opNo": "", "rx": [row]}, "confirmed_rows": []}
            assert c.post("/api/v1/documents", json=body, headers=H).status_code == 200
        (item,) = c.get(url, headers=H).json()["items"]
        assert set(item) == {"id", "spoken", "heard", "confirm_count", "first_seen_at", "last_seen_at", "doctor_id", "doctor"}
        assert (item["spoken"], item["heard"], item["confirm_count"]) == ("Dolo", "dollo", 2)
        assert c.post("/api/v1/rx/check-row", json=ask, headers=H).json() == before        # S1
        assert c.delete(f"{url}/0", headers=H).status_code == 422
        gone = c.delete(f"{url}/{item['id'] + 1}", headers=H)
        assert (gone.status_code, gone.json()) == (404, {"error": "no such mishearing"})
        r = c.delete(f"{url}/{item['id']}", headers=H)
        assert (r.status_code, r.json()) == (200, {"removed": item["id"], "spoken": "Dolo", "heard": "dollo"})
        assert c.get(url, headers=H).json() == {"items": []}

        monkeypatch.setattr(sdb, "list_active_mishearings", lambda _c: (_ for _ in ()).throw(sqlite3.OperationalError("locked")))
        assert (c.get(url, headers=H).status_code, c.get(url, headers=H).json()) == (503, {"error": "try again"})
    conn = dbmod.get_conn()
    (detail,) = [r[0] for r in conn.execute("SELECT detail FROM audit_log WHERE action = 'spoken.mishearing.remove'")]
    assert "dollo" in detail and "Dolo" in detail
    conn.close()
```
- [ ] **Step 2: Run them.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py -q`. Expected: 2 FAIL
  (`AttributeError: ... 'list_active_mishearings'`; the GET answers 404).
- [ ] **Step 3: SQL in `db/spoken.py`.** `list_active_mishearings`: SELECT `m.id, t.spoken, m.heard, m.confirm_count,
  m.first_seen_at, m.last_seen_at, t.doctor_id, COALESCE(NULLIF(u.display_name, ''), u.username, '') AS doctor` FROM
  `spoken_mishearings m JOIN spoken_terms t ON t.id = m.term_id LEFT JOIN users u ON u.id = t.doctor_id` WHERE
  `{ACTIVE}` ORDER BY `m.last_seen_at DESC, m.id DESC`, as dicts. `remove_mishearing` as `db/formulary.py:33-41`: the
  pair `WHERE m.id = ? AND {ACTIVE}`, None when absent, else `removed_at = _utcnow(), confirm_count = 0`, commit,
  return `{"spoken": ..., "heard": ...}`.
- [ ] **Step 4: Routes in `api/spoken.py`.** Copy `api/formulary.py:125-153`, changing only: import `DENIED, EntryId,
  _busy` from `doctor_dictation.api.formulary` (same 403 body and id range); paths `/api/v1/spoken/mishearings` and
  `/api/v1/spoken/mishearings/{entry_id}`; handlers `list_mishearings`, `remove_mishearing_route`; calls through the
  module (`sdb.list_active_mishearings`, `sdb.remove_mishearing`); the same 401 branch and `policy.can(ident,
  "formulary.manage")` check (admins only, `policy.py:11`); 404 `{"error": "no such mishearing"}`; audit
  `action="spoken.mishearing.remove", entity="spoken_mishearing", entity_id=str(entry_id), detail=pair`; log lines
  "spoken mishearings: list failed" / "remove failed"; 200 `{"removed": entry_id, **pair}`. The clinic scope comes from
  `dbmod.get_conn()`, as there. No `router` in H1's module: add one and add the module to the tuple at `api/app.py:83`.
- [ ] **Step 5: Run.** `.venv/bin/python -m pytest tests/test_spoken_mishearings.py tests/test_formulary_routes.py -q`.
  Expected: all pass (6 in the new file).
- [ ] **Step 6: Leave uncommitted.**

### Task 4: Clinic isolation

**Files:** Create `tests/test_isolation_mishearings.py`. Modify `tests/isolation_fixtures.py:41-42` (`TABLES`),
`tests/test_isolation_routes.py:31` and `CLASSIFIED` (`:185-194`), `tests/test_isolation_formulary.py:63-92`.

- [ ] **Step 1: Write the test file.**
```python
"""A doctor's corrected mishearings stay in that clinic and with that doctor (plan SH-H2). Offline; the two-clinic world."""
from isolation_fixtures import A, B, H, fingerprint, save_body, sql, user_id, world  # noqa: F401

LIST = "/api/v1/spoken/mishearings"

def misheard(client, patient):
    body = save_body(patient, medicine="Dolo")
    body["structured"]["rx"][0]["heard"] = "dollo"
    r = client.post("/api/v1/documents", json=body, headers=H)
    assert r.status_code == 200, r.text

def test_pairs_belong_to_the_doctor_and_the_clinic_that_saved_them(world):
    misheard(world.rao, "Asha Verma")
    misheard(world.rao, "Lakshmi Narayan")
    misheard(world.mehta, "Ravi Kulkarni")                                  # a colleague: one document only
    rows = sql(A, "SELECT t.doctor_id, m.heard, m.confirm_count FROM spoken_mishearings m"
                  " JOIN spoken_terms t ON t.id = m.term_id ORDER BY m.confirm_count DESC")
    assert [tuple(r) for r in rows] == [(user_id(world, "dr.rao"), "dollo", 2), (user_id(world, "dr.mehta"), "dollo", 1)]
    assert sql(B, "SELECT (SELECT COUNT(*) FROM spoken_mishearings) + (SELECT COUNT(*) FROM spoken_mishearing_docs)")[0][0] == 0
    (item,) = world.rao_admin.get(LIST, headers=H).json()["items"]                  # only the active pair
    assert item["doctor_id"] == user_id(world, "dr.rao") and (item["spoken"], item["heard"]) == ("Dolo", "dollo")
    assert world.iyer_admin.get(LIST, headers=H).json() == {"items": []}

def test_only_the_clinics_own_admin_removes_a_pair(world):
    misheard(world.rao, "Asha Verma")
    misheard(world.rao, "Lakshmi Narayan")
    (item,) = world.rao_admin.get(LIST, headers=H).json()["items"]
    url, before = f"{LIST}/{item['id']}", fingerprint(A)
    assert world.rao.delete(url, headers=H).status_code == 403                     # a doctor, not an admin
    assert world.iyer_admin.delete(url, headers=H).status_code == 404              # the other clinic's admin
    assert fingerprint(A) == before
    assert world.rao_admin.delete(url, headers=H).status_code == 200
    assert [tuple(r) for r in sql(A, "SELECT confirm_count, removed_at IS NOT NULL FROM spoken_mishearings")] == [(0, 1)]
```
- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_isolation_mishearings.py tests/test_isolation_routes.py tests/test_isolation_formulary.py -q`.
  Expected: the 2 new tests pass (Tasks 1-3 built the behaviour); `test_isolation_routes.py` FAILS: `table_for` names
  the new DELETE as an unmapped id route, and `CLASSIFIED` lacks the GET.
- [ ] **Step 3: Update the inventories.**
  - `test_isolation_routes.py:31`: `ADMIN_ONLY = ("/api/v1/formulary/", "/api/v1/users/", "/api/v1/spoken/mishearings/")`
    (the GET has no trailing slash, so it stays outside; `:88 len(routes) == 9` stays).
  - `CLASSIFIED`, after the formulary lines: `"GET /api/v1/spoken/mishearings": "list: test_isolation_mishearings.py"`,
    `"DELETE /api/v1/spoken/mishearings/{entry_id}": "admin only: test_isolation_formulary.py::test_the_admin_sweep_covers_every_admin_only_route_across_clinics"`.
  - `test_isolation_formulary.py`: `from test_isolation_mishearings import misheard`. In the admin sweep: put
    `("DELETE", "/api/v1/spoken/mishearings/{entry_id}")` second in the expected `ops`; after the two `learn` calls add
    `misheard(world.rao, "Asha Verma")`, `misheard(world.rao, "Lakshmi Narayan")`, `(pair,) =
    world.rao_admin.get("/api/v1/spoken/mishearings", headers=H).json()["items"]`; `url()` uses `pair["id"]` for a path
    starting `/api/v1/spoken/`, else `item["id"]`. No other assertion changes.
  - `isolation_fixtures.py` `TABLES`: append `"spoken_mishearings", "spoken_mishearing_docs"`.
- [ ] **Step 4: Run** the Step 2 command. Expected: all pass.
- [ ] **Step 5: Leave uncommitted.**

### Task 5: The "Corrected mishearings" section on the Team screen

**Files:** Create `frontend/mishear.js`, `tests/test_frontend_mishearings.py`. Modify `frontend/team.js:89-92,109-112`,
`frontend/index.html:289-291`, `tests/team_medicines_fakedom.js:42-47,88,97`, `tests/test_frontend_clinic_lists.py:54`,
`tests/test_frontend_owner_lists.py:44`.

**Interfaces:** Produces `window.Mishearings = { init(host), buildSection(), load(), clearLive() }`; ids `teamMishear`,
`teamMishearTitle`, `teamMishearRows`, `teamMishearLive`, `teamMishearEmpty`; button class `team-mishear-remove`.

- [ ] **Step 1: Teach the fake server** (`tests/team_medicines_fakedom.js`). After `let items = ...` (`:47`):
  `let mishear = (opts.mishearings || []).slice();`. Before the generic `DELETE` branch (`:88`):
```js
    if (url === "/api/v1/spoken/mishearings" && method === "GET") return reply(200, { items: mishear });
    if (method === "DELETE" && url.startsWith("/api/v1/spoken/mishearings/")) {        // opts.mishearDelete: [status, body]
      const r = opts.mishearDelete || [200, {}];
      if (r[0] < 300) mishear = mishear.filter((m) => url !== "/api/v1/spoken/mishearings/" + m.id);
      return reply(r[0], r[1]);
    }
```
  After the `clinlists.js` eval (`:97`), eval `frontend/mishear.js` the same way (comment: "after clinlists.js, before
  team.js, as in index.html"). Name both new opts in the comment at `:42-45`.
- [ ] **Step 2: Write the failing tests.** Copy `FRONT`, `FAKEDOM`, `_code` and `_page` from
  `tests/test_frontend_clinic_lists.py:11-41` (its `_page` opens the page as an admin).
```python
PAIRS = [{"id": 4, "spoken": "Dolo", "heard": "dollo", "confirm_count": 3, "doctor_id": 5, "doctor": "Dr. Rao"},
         {"id": 6, "spoken": "Pan", "heard": "fan", "confirm_count": 2, "doctor_id": 6, "doctor": "Dr. Mehta"}]
ROWS = "p.ids.teamMishearRows.children.map((tr) => tr.children.map((td) => td.textContent))"
FIRST = "p.ids.teamMishearRows.children[0].children[4].children[0]"

def test_mishear_is_plain_text_loads_between_clinlists_and_team_and_parses():
    js, html = _code("mishear.js"), (FRONT / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"innerHTML|outerHTML|insertAdjacentHTML|document\.write", js) and '"/api/v1/spoken/mishearings"' in js
    assert "mishear.js?v=1" in html and "team.js?v=6" in html
    assert html.index("clinlists.js?v=") < html.index("mishear.js?v=") < html.index("team.js?v=")
    if shutil.which("node"):
        assert subprocess.run([shutil.which("node"), "--check", str(FRONT / "mishear.js")], capture_output=True).returncode == 0

def test_an_admin_sees_the_pairs_in_the_medicines_tab_as_text():
    r = _page("await p.openMeds(); console.log(JSON.stringify({t: p.ids.teamMishearTitle.textContent, inMeds: p.ids.teamMishear.parentNode"
              " === p.ids.teamMeds, rows: %s, empty: p.ids.teamMishearEmpty.hidden, calls: p.calls}))" % ROWS, mishearings=PAIRS)
    assert (r["t"], r["inMeds"], r["empty"]) == ("Corrected mishearings", True, True)
    assert r["rows"] == [["dollo", "Dolo", "Dr. Rao", "3", "Remove"], ["fan", "Pan", "Dr. Mehta", "2", "Remove"]]
    assert "GET /api/v1/spoken/mishearings" in r["calls"]
    e = _page("await p.openMeds(); console.log(JSON.stringify({rows: %s, kids: p.ids.teamMishearRows.children[0].children[0].children.length}))"
              % ROWS, mishearings=[dict(PAIRS[0], heard="<img src=x onerror=alert(1)>")])
    assert e["rows"][0][0] == "<img src=x onerror=alert(1)>" and e["kids"] == 0
    n = _page("await p.openMeds(); console.log(JSON.stringify({rows: %s, empty: p.ids.teamMishearEmpty.hidden}))" % ROWS)
    assert n == {"rows": [], "empty": False}

def test_remove_asks_deletes_reloads_announces_and_a_decline_does_nothing():
    body = ("await p.openMeds(); p.calls.length = 0; const b = %s; const label = b.attrs['aria-label']; await b.click(); await p.tick();"
            " console.log(JSON.stringify({calls: p.calls, confirm: p.confirms[0] || '', label, live: p.ids.teamMishearLive.textContent,"
            " rows: p.ids.teamMishearRows.children.length, focus: (document.activeElement && document.activeElement.attrs.class) || ''}))" % FIRST)
    r = _page(body, mishearings=PAIRS)
    assert r["calls"] == ["DELETE /api/v1/spoken/mishearings/4", "GET /api/v1/spoken/mishearings"]
    assert '"dollo" to Dolo' in r["confirm"] and "two new documents" in r["confirm"]
    assert (r["label"], r["live"]) == ('Remove the pair "dollo" to Dolo', 'Removed the pair "dollo" to Dolo.')
    assert (r["rows"], r["focus"]) == (1, "team-mishear-remove")
    no = _page(body, mishearings=PAIRS, answers=[False])
    assert (no["calls"], no["live"], no["rows"]) == ([], "", 2)

def test_a_gone_pair_says_so_and_a_doctor_page_has_no_section():
    r = _page("await p.openMeds(); await %s.click(); await p.tick(); console.log(JSON.stringify(p.ids.teamError.textContent))" % FIRST,
              mishearings=PAIRS, mishearDelete=[404, {"error": "no such mishearing"}])
    assert r == "That pair was already removed. The list has been refreshed."
    d = _page("await p.openTeam(); console.log(JSON.stringify({sec: !!p.ids.teamMishear, calls: p.calls}))", role="doctor")
    assert d["sec"] is False and not [c for c in d["calls"] if "spoken" in c]
```
- [ ] **Step 3: Run them.** `.venv/bin/python -m pytest tests/test_frontend_mishearings.py -q`. Expected: 4 FAIL
  (`mishear.js` does not exist: ENOENT). Until Step 4 every fake-DOM Team test fails the same way.
- [ ] **Step 4: Write `frontend/mishear.js`.** One IIFE, `"use strict"`, a header naming plan SH-H2 and "built for
  admins by team.js; loaded after clinlists.js, before team.js". Mirror `clinlists.js`: `make` (`:24-29`), `host` and
  `init` (`:20`, `:30`), the late-answer guard of `load` (`:171-181`), `removeLearned` (`:190-200`). Fixed values:
  - `buildSection()`: `section#teamMishear.team-mishear` (`aria-labelledby="teamMishearTitle"`) holding
    `h3#teamMishearTitle` "Corrected mishearings"; `p.team-hint` "Words the speech engine wrote that a doctor corrected
    on two or more saved prescriptions. For that doctor, the corrected name is sent to the speech engine first. Removing
    a pair is not permanent: it comes back only after two new documents show it again."; `p#teamMishearLive.team-live`
    (`role="status"`); hidden `p#teamMishearEmpty.team-hint` "No corrected mishearings yet."; `div.team-table-box` >
    `table.team-table`, headers `Heard as`, `Corrected to`, `Doctor`, `Prescriptions`, `Actions`, `tbody#teamMishearRows`.
  - A row, text only: `heard`, `spoken`, `doctor || ""`, `String(Number(confirm_count) || 0)`, `td.team-row-actions`
    with `button.team-mishear-remove` "Remove" (`aria-label` `Remove the pair "<heard>" to <spoken>`).
  - `load()`: `GET /api/v1/spoken/mishearings` via `host.send`; keep `b.items` when it is an array, else `[]`.
  - Remove: confirm `Remove the pair "<heard>" to <spoken>? <spoken> is no longer sent first for this doctor. The pair
    comes back only after two new documents show it again.`; `DELETE /api/v1/spoken/mishearings/<Number(id)>` with the
    404 wording "That pair was already removed. The list has been refreshed."; reload; `host.showErr(msg)`; on success
    live text `Removed the pair "<heard>" to <spoken>.` and focus the Remove button now at the same index, else the
    previous one, else `#teamTabMeds` (also the focus after a failure).
- [ ] **Step 5: Wire it in `team.js`.** `showListTabs`, admin block, after the panels are appended (`:111`):
  `if (window.Mishearings) { window.Mishearings.init(host); el("teamMeds").append(window.Mishearings.buildSection()); }   // plan SH-H2`.
  `selectTab`: after `:89` add `if (window.Mishearings && el("teamMishear")) window.Mishearings.clearLive();`; `:92`
  becomes `else if (kind) { window.ClinicLists.load(kind); if (kind === "medicine" && window.Mishearings && el("teamMishear")) window.Mishearings.load(); }`.
- [ ] **Step 6: Load and cache-bust.** `index.html`: `<script src="mishear.js?v=1"></script>` after the `clinlists.js`
  line (`:289`); `team.js?v=5` → `?v=6` (`:291`). Change the pins `"team.js?v=5"` at `test_frontend_clinic_lists.py:54`
  and `test_frontend_owner_lists.py:44` to `"team.js?v=6"`. If `team.js` is already above v5, bump from there instead.
- [ ] **Step 7: Run.** `.venv/bin/python -m pytest tests/test_frontend_mishearings.py tests/test_frontend_team.py tests/test_frontend_team_medicines.py tests/test_frontend_clinic_lists.py tests/test_frontend_owner_lists.py tests/test_frontend_dates.py -q`.
  Expected: all pass. Tests that reset `p.calls` after `openMeds` are unaffected: the mishearings GET runs on tab
  open, never on a list reload.
- [ ] **Step 8: Leave uncommitted.**

### Task 6: Mutations, whole suite, sizes, one run by hand

- [ ] **Step 1: Mutations.** Apply each alone, run the three new test files, see a failure, revert. M1 drop the
  same-medicine check (test 1). M2 drop S3 on `heard` (test 1). M3 count without the `.rowcount` check (test 2). M4
  `remove_mishearing` keeps `confirm_count` (test 5). M5 no `try` around the pair step (test 3). M6 drop the tier lift
  (test 4). M7 drop `policy.can` from the DELETE (test 8). M8 set a cell with `innerHTML` (tests 9, 10).
- [ ] **Step 2: Whole suite.** `.venv/bin/python -m pytest tests/ -q`. Expected: N + 12 passed, same skip count.
- [ ] **Step 3: Sizes.** `wc -l doctor_dictation/core/spoken.py doctor_dictation/db/spoken.py doctor_dictation/api/spoken.py doctor_dictation/api/stt.py doctor_dictation/api/persistence.py frontend/team.js frontend/mishear.js`.
  Expected: all under 500; `api/persistence.py` not changed by this plan.
- [ ] **Step 4: By hand (single mode, temp database).** `export DB_PATH=$(mktemp -d)/h2.db`; run
  `.venv/bin/uvicorn doctor_dictation.main:app --port 8001`; POST Task 3's document body twice with `curl` (header
  `X-DD-Client: 1`); `curl localhost:8001/api/v1/spoken/mishearings` shows one pair with `confirm_count` 2. Run H1's
  `python -m doctor_dictation.admin backfill-spoken-terms` twice with the same `DB_PATH`: the count stays 2. Stop the
  server. (The Team screen needs multi-clinic sign-in; Task 5's tests cover it.)
- [ ] **Step 5: Leave uncommitted.** Hand over the changed files, the three disagreements and any H1 name that differed.

## Self-Review

- Every index item for H2 maps to a task; S1 is pinned by test 6; 401 is the copied branch, not separately tested.
  Names match index 5.2-5.3 as amended (lift by `HintTerm.term_id`, `max(tier, 1)`); new names: Disagreement 3.
- Out of scope: pairs on the main page; `heard` sent to any engine; pairs in Spell it, Did you mean or the LLM repair
  prompt (S1, backlog card (c)); editing a pair; clinic-wide pairs; any tier above 1.

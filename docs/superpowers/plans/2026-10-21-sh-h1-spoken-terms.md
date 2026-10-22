# SH-H1: Spoken Terms Become the Speech Hints Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** Every save records the doctor's medicines and tests as dictated ("Dolo", "650 mg", "CBC") in a new
per-doctor table. Speech hints are built from those words ("Dolo 650"), never from the generic, and only
hint-eligible phrases leave the clinic (S2). An admin command backfills old prescriptions. Adds 12 tests; changes 12
existing test files. Trial-run on a scratch copy of 8c9ce76 with the 2026-10-21 amendment: whole suite green.

**Goal:** Fill `spoken_terms` on save and by backfill, and send the doctor's own spoken phrases as hints.

**Architecture:** Pure rules in new `core/spoken.py`; SQL with a count-once ledger in new `db/spoken.py`; save hook in
new `api/spoken.py`. `build_hints` takes `HintTerm`s, checks S2 per phrase, budgets the rendered prompt.

**Tech Stack:** Python 3.12, FastAPI, stdlib sqlite3, pytest. No new dependency.

**Spec:** `2026-10-21-sh-00-index-and-contracts.md` (binding): row 1, decision 1, S1–S5, 5.1 (`011`), 5.2 (with the
2026-10-21 `term_id`/`key` amendment), 5.3–5.5. Conventions: `2026-10-13-00-index-and-contracts.md` section 2.

**Assumptions about earlier plans:** none (H1 is first). Preflight: re-read each file; re-find anchors with `grep -n`.

## Disagreements with the index (followed where possible; owner or coordinator to confirm)

1. **S3 and `person_like`.** On every term, `person_like` drops real tests and grounded brands ("Liver Function
   Test", "Thyroid Profile", "Blood Sugar", "Augmentin Duo" all return True). This plan uses `formulary.learnable`'s
   scope: the patient-words check on every term; `person_like` only on a term no list matched at save (medicine: no
   `lexicon_match` and `source != "clinic"`; test: empty `canonical`). "Ramesh Kumar" in a cell is still dropped.
2. **`learn_spoken_terms` gains an optional `patient_words=None`** (backfill reads patients once); contract args kept.
3. **Weight = `formulary.usage_score(uses, last_used_at, today)`** (log2(1 + uses), halved every `HALF_LIFE_DAYS`),
   not linear "decayed uses": linear lets a stale heavy term outrank fresh ones for months (the I1-r1 argument).
4. **`HintTerm` has no `kind`,** so S2 checks each phrase against the medicine lists and the investigation list.
5. **Seed-demo must call the hook** (`admin_demo.py:145`), or the demo and the hint tests at
   `tests/test_isolation_doctors.py:99` and `tests/test_isolation_routes.py:240` lose personalised hints.
6. **Some assertions change, not only expected strings:** owner decision 1 reverses `tests/test_hints.py:6`
   ("doctor names become canonical"); `tests/test_db.py:99` counts 11 migrations; three migration lists grow.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`); "today" is a parameter. No source file over 500 lines
  (`api/persistence.py` 470 → 472; `db/__init__.py` 489, untouched).
- S2: only `build_hints` output reaches a speech engine. S4: the hook never raises. S5: `spoken_term_docs` keyed on
  `document_id`; a re-save or a second backfill counts nothing.
- Doctor id: `ident.user_id` on save, `scope.user_id` on transcribe; **0** in single-database mode on both.
- Status codes and JSON shapes unchanged. `top_medicines` (`db/__init__.py:380`) stays; `api/stt.py` stops using it.
- Tests offline; single-mode tests use a temp `DB_PATH`; never `from conftest import *`. No commits: leave every
  change uncommitted. Command `.venv/bin/python -m pytest tests/ -q`.

## Review Focus

| Input | Expected | Pinned in |
|---|---|---|
| Free text in a strength cell; a grounded name that reads like a person | bare name hinted; grounded name recorded | Task 1 |
| A re-save; the backfill run twice; documents replayed out of date order | counted once; dates from the documents | Tasks 2, 3, 5 |
| Doctor says "Urimax 0.4" and the clinic layer has "Urimax" | one hint, "Urimax 0.4" (a phrase claims its base name) | Task 4 |
| The hook raises inside a save | the save answers 200 | Task 3 |

## File Structure and line budgets

| File | Change | Lines after |
|---|---|---|
| `doctor_dictation/db/migrations/011_spoken_terms.sql` | NEW: contract 5.1 first block, verbatim | ~30 |
| `doctor_dictation/core/spoken.py` | NEW: contract 5.2 | ≤ 160 |
| `db/spoken.py`; `api/spoken.py` | NEW: `record_terms`, `doctor_hint_terms`; `learn_spoken_terms`, `replay_saved` | ≤ 80; ≤ 70 |
| `core/hints.py`; `api/stt.py` | `prompt_text`, `eligible`, new `build_hints`; `_doctor_top` → `_doctor_terms` | ~80; ~75 |
| `api/persistence.py`; `admin_demo.py`; `admin.py` | hook call; seed calls the hook; `backfill-spoken-terms` | 472; 204; ~248 |
| `providers/stt/openai.py`, `providers/stt/local.py` | `prompt_text` | +2 each |
| `tests/test_spoken_terms.py`, `tests/test_isolation_spoken.py` | NEW: 10 + 2 tests | ~190, ~40 |
| Baseline on 8c9ce76 | 2825 collected: run the suite first, note N; expect N + 12 at the end | |

### Task 1: The pure rules (`core/spoken.py`)

**Files:** Create `doctor_dictation/core/spoken.py`, `tests/test_spoken_terms.py`.

**Interfaces:** Produces contract 5.2 exactly (frozen `Term`, `HintTerm(phrase, weight, tier=0, term_id=0, key="")`,
`key`, `terms_from_save`, `usual_strength`, `phrase`, `rank`), plus `USUAL_SHARE, USUAL_MIN = 60, 2`.

- [ ] **Step 1: Write the failing tests** (file header and three tests).

```python
"""The doctor's spoken terms become the speech hints (plan SH-H1): said = shown = printed = hinted. Offline."""
import json
from contextlib import closing
from datetime import date
from pathlib import Path

import pytest

from doctor_dictation import admin
from doctor_dictation import db as dbmod
from doctor_dictation.core import formulary as F
from doctor_dictation.core import investigations as I
from doctor_dictation.core import spoken as S
from doctor_dictation.core.determinism import load_lexicon

HT = S.HintTerm
DOLO = {"form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "status": "verified"}

@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())

def test_key_phrase_and_rank():
    assert S.key(" Dolo-650 & Co_ ") == "dolo 650 and co" and S.key("Vit. D3") == "vit d3" and S.key(None) == ""
    assert [S.phrase("Dolo", "650 mg"), S.phrase("Urimax", "0.4 mg"), S.phrase("Dolo", "650MG")] == ["Dolo 650", "Urimax 0.4", "Dolo 650"]
    assert S.phrase("Calpol", "120 mg/5ml") == "Calpol 120 mg/5ml" and S.phrase("Pan 40", "40 mg") == "Pan 40"
    assert S.phrase("Dolo", "") == "Dolo" and S.phrase("Dolo", "as told by Ramesh") == "Dolo"   # free text never sent
    assert [t.phrase for t in S.rank([HT("b", 1.0), HT("A", 1.0), HT("c", 2.0), HT("z", 0.1, tier=1)])] == ["z", "c", "A", "b"]

def test_usual_strength_needs_sixty_percent_and_two_uses():
    assert S.usual_strength({"650 mg": 3, "500 mg": 2}) == "650 mg"            # exactly 60%
    assert S.usual_strength({"650 mg": 59, "": 41}) == ""                       # 59%: no strength said counts as a use
    assert S.usual_strength({"650 mg": 60, "": 40}) == "650 mg"
    assert S.usual_strength({"650 mg": 1}) == ""                                # 100%, but one use
    assert S.usual_strength({"650 mg": 2, "500 mg": 2}) == "" and S.usual_strength({"": 5}) == S.usual_strength({}) == ""

def test_terms_keep_the_said_name_and_never_a_patient_word():
    form = {"patientName": "Chandrika Devi", "rx": [
        {"name": "Chandrika", "strength": "5 mg"},                                # this patient's own name
        {"name": "Ramu Syrup"},                                                   # another patient's name word
        {"name": "Ramesh Kumar"},                                                 # reads as a person, no list knows it
        {"name": "Augmentin Duo", "lexicon_match": "Amoxicillin + Clavulanic Acid"},   # person-like, but grounded
        {"name": "Dolo", "form": "Tab.", "strength": "650 mg", "lexicon_match": "Paracetamol", "generic": "Paracetamol"},
        {"name": "dolo", "strength": "500 mg"}, "junk", {"name": "x" * 61}],
        "investigations": [{"text": "Liver Function Test", "canonical": "Liver Function Test"},
                           {"text": "Blood Sugar", "canonical": ""}, "CBC"]}
    got = S.terms_from_save(form, frozenset({"ramu"}))
    assert [(t.kind, t.key, t.spoken) for t in got] == [
        ("medicine", "augmentin duo", "Augmentin Duo"), ("medicine", "dolo", "Dolo"),
        ("investigation", "liver function test", "Liver Function Test"), ("investigation", "cbc", "CBC")]
    assert got[1] == S.Term("medicine", "dolo", "Dolo", "Tab", "650 mg", "Paracetamol")   # the first row wins
    assert S.terms_from_save(None, ()) == [] and S.terms_from_save({"rx": "x"}, ()) == []
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py -q`. Expected: collection error
  `ImportError: cannot import name 'spoken' from 'doctor_dictation.core'`.
- [ ] **Step 3: Create `core/spoken.py`.** Imports: `re`, `Sequence`, `dataclass`, `from . import investigations`,
  `from .formulary import MAX_NAME, person_like`. Rules the tests leave open:
  - `key`: `re.sub(r"[\W_]+", " ", str(text or "").casefold().replace("&", " and ")).strip()`.
  - `terms_from_save`: patient words = `known_patient_words` ∪ words of `patientName` (casefolded). Medicines from
    `rx` dict rows (whitespace-collapsed; form without a trailing "."); tests from `investigations.coerce_items(...)`
    (spoken = `text`, generic = `canonical`). Skip an empty key, a name over `MAX_NAME`, a repeated `(kind, key)` and
    a private name: a 3+ letter word is a patient word, or not known (Disagreement 1) and `person_like`.
  - `usual_strength`: total = sum of all counts ("" included); best = highest count among non-empty strengths, ties
    by text; return it if `count >= USUAL_MIN and count * 100 >= USUAL_SHARE * total` (integers: no float edge).
  - `phrase`: the strength joins only if it fully matches (ignore case)
    `\d+(?:\.\d+)?\s*(?:mg|mcg|g|gm|ml|iu|units?|%)?(?:\s*/\s*\d*(?:\.\d+)?\s*(?:ml|g|gm|tab))?`; drop a trailing
    `\s*mg`; if `key(name)` already ends with `key(short)`, return the name alone.
  - `rank`: `sorted(terms, key=lambda t: (-t.tier, -t.weight, t.phrase.casefold(), t.phrase))`.
- [ ] **Step 4: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_core_purity.py -q`. Expected:
  all pass (3 in the new file).

### Task 2: Migration 011 and the SQL (`db/spoken.py`)

**Files:** Create `db/migrations/011_spoken_terms.sql`, `db/spoken.py`; modify `tests/test_db.py:90,99`,
`tests/test_authorship_db.py:52`, `tests/test_template_scope_db.py:46`; append to `tests/test_spoken_terms.py`.

**Interfaces:** Produces `record_terms(conn, doctor_id, terms, document_id) -> int` (terms counted now; COMMITS) and
`doctor_hint_terms(conn, doctor_id, today: date) -> list[HintTerm]` (every live term, uncapped, unranked, `term_id`
and `key` set).

- [ ] **Step 1: Append the failing tests.**

```python
def _doc(conn, at, rx):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "", None))
    return dbmod.save_document(conn, eid, at, {"rx": rx}, finalized_at=at)

def _fresh(tmp_path):
    conn = dbmod.get_conn(tmp_path / "s.db")
    dbmod.migrate(conn)
    return conn

def test_a_document_counts_once_and_the_use_is_dated_by_the_document(tmp_path):
    from doctor_dictation.db import spoken as sdb
    conn = _fresh(tmp_path)
    one, two = _doc(conn, "2026-10-01T09:00:00Z", [DOLO]), _doc(conn, "2026-10-11T09:00:00Z", [DOLO])
    terms = S.terms_from_save({"rx": [DOLO]}, ())
    assert [sdb.record_terms(conn, 0, terms, d) for d in (two, one, one)] == [1, 1, 0]   # out of order, then a re-save
    row = conn.execute("SELECT uses, first_used_at, last_used_at FROM spoken_terms").fetchone()
    assert tuple(row) == (2, "2026-10-01T09:00:00Z", "2026-10-11T09:00:00Z")
    assert [tuple(r) for r in conn.execute("SELECT strength, uses FROM spoken_term_strengths")] == [("650 mg", 2)]
    today = date(2026, 10, 11)
    assert sdb.doctor_hint_terms(conn, 0, today) == [HT("Dolo 650", F.usage_score(2, row[2], today), term_id=1, key="dolo")]
    assert sdb.doctor_hint_terms(conn, 7, today) == []                        # another doctor's terms are not mine
    conn.close()

def test_every_live_term_comes_back_uncapped_with_its_id_and_key(tmp_path):
    from doctor_dictation.db import spoken as sdb
    conn = _fresh(tmp_path)
    names = [e["canonical"] for e in load_lexicon()[:80]]
    rows = [{"name": n, "lexicon_match": n} for n in names]
    sdb.record_terms(conn, 3, S.terms_from_save({"rx": rows}, ()), _doc(conn, "2026-10-11T09:00:00Z", []))
    conn.execute("UPDATE spoken_terms SET removed_at = 'x' WHERE term_key = ?", (S.key(names[0]),))   # as H2 removes
    got = sdb.doctor_hint_terms(conn, 3, date(2026, 10, 11))
    assert len(got) == 79 and all(t.term_id > 0 and t.key == S.key(t.phrase) for t in got)   # far over 500 chars
    assert names[0] not in [t.phrase for t in got]
    conn.close()
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py -q`. Expected: 2 FAIL
  (`ModuleNotFoundError: No module named 'doctor_dictation.db.spoken'`).
- [ ] **Step 3: Create `011_spoken_terms.sql`:** contract 5.1's three `CREATE TABLE`s verbatim, under a short comment.
- [ ] **Step 4: Create `db/spoken.py`** (imports `core.spoken`, `core.formulary.usage_score`, `db._utcnow`).
  `record_terms` (one `conn.commit()` at the end): `at` = the document's `COALESCE(finalized_at, created_at)`, else
  `_utcnow()` (uses are dated by their document, so a backfill keeps real dates). Per term: `INSERT ... ON
  CONFLICT(doctor_id, kind, term_key) DO NOTHING`; `SELECT id`; `INSERT OR IGNORE INTO spoken_term_docs`, and skip the
  term when `rowcount` is 0; `UPDATE ... uses = uses + 1, first_used_at = MIN(first_used_at, ?), last_used_at =
  MAX(last_used_at, ?)`, `spoken` (and non-empty `form`/`generic`) only `CASE WHEN ? >= last_used_at`; medicines
  only, upsert `spoken_term_strengths` `uses + 1` ("" too: the "no strength said" use).
  `doctor_hint_terms`: one query for this doctor's live terms' strengths (`JOIN spoken_terms`, `removed_at IS NULL`)
  into `{term_id: {strength: uses}}`; then `SELECT id, term_key, spoken, uses, last_used_at FROM spoken_terms WHERE
  doctor_id = ? AND removed_at IS NULL ORDER BY id` (no `LIMIT`); per row `HintTerm(phrase(spoken,
  usual_strength(...)), usage_score(uses, last_used_at, today), term_id=id, key=term_key)`.
- [ ] **Step 5: Migration pins.** Append `"011_spoken_terms.sql"` to the lists at `tests/test_db.py:90`,
  `tests/test_authorship_db.py:52`, `tests/test_template_scope_db.py:46`; `tests/test_db.py:99` → `assert n == 11`.
- [ ] **Step 6: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_db.py tests/test_authorship_db.py tests/test_template_scope_db.py -q`.
  Expected: all pass (5 in the new file).

### Task 3: The save hook (S4) and the demo seed

**Files:** Create `api/spoken.py`; modify `api/persistence.py:15,348-349`, `admin_demo.py:22,145-146`; append to
`tests/test_spoken_terms.py`.

**Interfaces:** Produces `learn_spoken_terms(conn, structured, document_id, user_id, patient_words=None) -> None`
(never raises; doctor `user_id or 0`). The `app` fixture yields `(save, hints)`; Task 4 reuses it.

- [ ] **Step 1: Append the failing tests.**

```python
@pytest.fixture()
def app(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation.api import stt as stt_mod
    from doctor_dictation.api.app import create_app
    from doctor_dictation.config import override_settings
    from doctor_dictation.providers.stt.base import Transcript
    monkeypatch.setenv("DB_PATH", str(tmp_path / "app.db"))                  # never the real dev database
    monkeypatch.setattr("doctor_dictation.api.persistence.render_prescription", lambda *a, **k: 1 / 0)   # fail-soft PDF
    sent = []

    class Recorder:
        name, available = "recorder", staticmethod(lambda: True)

        async def transcribe(self, audio, filename, hints=()):
            sent.append(list(hints))
            return Transcript(text="hello", engine="recorder")
    monkeypatch.setattr(stt_mod, "make_stt", lambda settings: Recorder())
    override_settings(monkeypatch, stt_use_hints=True, stt_trim_silence=False, stt_hint_limit=12)
    with TestClient(create_app()) as client:
        def save(rows, patient="Anita Rao", confirmed=(), document_id=None):
            body = {"structured": {"patientName": patient, "ageSex": "40 / F", "opNo": "", "rx": [dict(r) for r in rows]},
                    "confirmed_rows": list(confirmed), "document_id": document_id}
            r = client.post("/api/v1/documents", json=body)
            assert r.status_code == 200, r.text
            return r.json()["document_id"]

        def hints():
            assert client.post("/api/transcribe", files={"audio": ("n.webm", b"RAW", "audio/webm")}).status_code == 200
            return sent[-1]
        yield save, hints

def _terms():
    with closing(dbmod.get_conn()) as conn:
        return [tuple(r) for r in conn.execute("SELECT doctor_id, kind, term_key, spoken, uses FROM spoken_terms ORDER BY id")]

def test_an_unknown_name_is_stored_not_sent_a_patient_word_is_never_stored_and_a_resave_counts_once(app):
    save, hints = app
    rows = [{"form": "Cap.", "name": "Urimax", "strength": "0.4 mg", "status": "unknown-medicine"},
            {"form": "Tab.", "name": "Chandrika", "status": "unknown-medicine"}]
    doc = save(rows, patient="Chandrika Devi", confirmed=(0, 1))
    save(rows, patient="Chandrika Devi", confirmed=(0, 1), document_id=doc)   # a re-save of the same document
    assert _terms() == [(0, "medicine", "urimax", "Urimax", 1)]
    assert not [h for h in hints() if "urimax" in h.casefold() or "chandrika" in h.casefold()]

def test_a_failing_hook_never_blocks_the_save(app, monkeypatch):
    from doctor_dictation.db import spoken as sdb
    save, _ = app
    monkeypatch.setattr(sdb, "record_terms", lambda *a: 1 / 0)
    assert save([DOLO]) and _terms() == []
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py -q`. Expected: the first FAILS
  (`assert [] == [(0, 'medicine', 'urimax', 'Urimax', 1)]`); the second already passes (no hook yet).
- [ ] **Step 3: Create `api/spoken.py`.** `learn_spoken_terms`, all in one `try`: words = `fdb.patient_words(conn)`
  if `patient_words is None`; `terms_from_save`; if any, `sdb.record_terms(conn, user_id or 0, terms, document_id)`;
  `except Exception` → `log.warning(..., exc_info=True)`, the `api/formulary.py:85` pattern.
- [ ] **Step 4: Call it.** `api/persistence.py`: import it after line 15; after `remember_from_save(...)`
  (`:348-349`) add `learn_spoken_terms(conn, validated, document_id, ident.user_id if ident else None)   # SH-H1`.
  (`validated` carries server-set `lexicon_match`/`source`; the new patient is already in `patients`.)
  `admin_demo.py`: import it; call `learn_spoken_terms(conn, form, document_id, author_id)` after `:145-146`.
- [ ] **Step 5: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_formulary_routes.py tests/test_investigations_api.py tests/test_admin_demo.py -q`.
  Expected: all pass (7 in the new file).

### Task 4: The hint pipeline (S2, `prompt_text`, `_doctor_terms`)

**Files:** Modify `core/hints.py:9-56`, `api/stt.py:21-44`, `providers/stt/openai.py:24`, `providers/stt/local.py:88`,
the existing tests in Step 6; append to `tests/test_spoken_terms.py`.

**Interfaces:** Produces `prompt_text(phrases) -> str` (contract 5.4), `eligible(text) -> bool`,
`build_hints(doctor_terms: Sequence[HintTerm] = (), limit=70) -> list[str]`, `api.stt._doctor_terms(context=None)
-> list[HintTerm]`. Consumes `db.spoken.doctor_hint_terms`.

- [ ] **Step 1: Append the failing tests.**

```python
def test_hints_are_the_doctors_phrases_and_only_eligible_ones(tmp_path, monkeypatch):
    from doctor_dictation.core.hints import build_hints, prompt_text
    assert prompt_text([]) == "" and prompt_text(["Dolo 650"]) == "Dolo 650."
    assert prompt_text(["Dolo 650", "Pan 40", "CBC"]) == "Dolo 650. Pan 40. CBC."
    out = build_hints([HT("Dolo 650", 1.6)], limit=70)
    assert out[0] == "Dolo 650" and "Dolo" not in out                           # never "Paracetamol" in its place
    many = build_hints([HT(e["canonical"], 1.0) for e in load_lexicon()[:80]], limit=200)
    assert 20 <= len(many) < 80 and len(prompt_text(many)) <= 500 >= len(prompt_text(out))   # the budget is here
    assert "Urimax 0.4" not in build_hints([HT("Urimax 0.4", 9.0)], limit=70)  # no list knows it: stored, never sent
    assert build_hints([HT("Pan D", 1.0), HT("Pan 40", 0.5)], limit=2) == ["Pan D", "Pan 40"]   # combo, base name
    F.activate(F.ClinicLayer((("Urimax", ""),)))
    assert build_hints([HT("Urimax 0.4", 9.0)], limit=3)[:2] == ["Urimax 0.4", "Diclofenac"]   # the phrase claims "Urimax"
    assert "CBC" not in build_hints([HT("CBC", 9.0)], limit=70)
    cat = tmp_path / "investigations.json"                                    # not built yet on main: serve one
    cat.write_text(json.dumps({"version": "t", "entries": [{"canonical": "Complete Blood Count", "aliases": ["cbc"]}]}))
    monkeypatch.setattr(I, "CATALOGUE_PATH", cat)
    monkeypatch.setattr(I, "_shipped_cache", None)
    assert build_hints([HT("CBC", 9.0)], limit=1) == ["CBC"]                  # a test the catalogue knows, as said

def test_dolo_650_saved_twice_is_hinted_as_said(app):
    save, hints = app
    save([DOLO])
    save([DOLO], patient="Bala Iyer")
    assert _terms() == [(0, "medicine", "dolo", "Dolo", 2)]
    got = hints()
    assert got[0] == "Dolo 650" and "Paracetamol" not in got[:1]             # before H1 the first hint was "Paracetamol"
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py -q`. Expected: 2 FAIL
  (`ImportError: cannot import name 'prompt_text'`; `assert 'Paracetamol' == 'Dolo 650'`).
- [ ] **Step 3: `core/hints.py`.** Imports: `re`, `Sequence`, `from . import investigations, spoken`,
  `from .combo import combo_suffix`, `from .determinism import _exact_lookup, load_lexicon`,
  `from .formulary import active_layer`, `from .spoken import HintTerm`. Delete `_doctor_canonical` (`:27-36`); keep
  `MAX_HINT_CHARS`, `_MAX_DOCTOR_NAME` (pinned by `tests/test_formulary.py`), `common_lexicon_names`. Update the
  docstring: the doctor's spoken forms first, as said; only hint-eligible phrases (S2).
  - `prompt_text`: `". ".join(phrases) + "."` if phrases, else `""`. `_base(text)`: strip trailing strengths,
    `(?:\s+\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)?)+$` (ignore case): "Dolo 650" → "Dolo"; "Dolo HIV2" stays whole.
  - `eligible(text)`: True when `_exact_lookup(n) or active_layer().get(n)` for `n` in (text, base), or
    `combo_suffix(base)`, or `investigations.lookup_in(text, investigations.clinic_entries())` is not None.
    `clinic_entries()` (`core/investigations.py:63`) reads the overlay `use_clinic_layer` already activates on
    `/api/transcribe` (`api/stt.py:48`); `lookup_in` is exact, never fuzzy.

```python
def build_hints(doctor_terms: Sequence[HintTerm] = (), limit: int = 70) -> list[str]:
    out, seen = [], set()
    for name in [*(t.phrase for t in spoken.rank(doctor_terms)), *active_layer().hint_names(), *common_lexicon_names()]:
        if len(out) >= max(limit, 0):
            break
        clean = " ".join(str(name).split())
        k = spoken.key(clean)
        if not k or k in seen or len(clean) > _MAX_DOCTOR_NAME or not eligible(clean):
            continue
        if len(prompt_text([*out, clean])) > MAX_HINT_CHARS:     # the budget is measured on the rendered prompt
            break
        seen.update({k, spoken.key(_base(clean))})               # "Urimax 0.4" also claims "Urimax"
        out.append(clean)
    return out
```

- [ ] **Step 4: `api/stt.py`.** Replace `_doctor_top` (`:21-32`) with `_doctor_terms(context=None)`: doctor id =
  `sc.user_id` when a scope with a user exists, else 0; in `closing(dbmod.get_conn())` return
  `spoken_db.doctor_hint_terms(conn, doctor_id, datetime.now(timezone.utc).date())`; keep `except NoScope: raise` and
  the logged `except Exception` → `[]`. `context` is unused until H3/H4. In `_prepare_audio` (`:42-44`):
  `terms = await asyncio.to_thread(_doctor_terms)`; `hints = tuple(build_hints(terms, settings.stt_hint_limit))`.
- [ ] **Step 5: Providers.** `openai.py:24` → `data["prompt"] = prompt_text(hints)`; `local.py:88` →
  `decode["initial_prompt"] += ". " + prompt_text(hints)`; both import `prompt_text` from `core.hints`.
- [ ] **Step 6: Update the existing tests** (each checked on the trial copy):

| File:line | Change |
|---|---|
| `tests/test_stt_providers.py:42`, `:79`, `:156` | `"Telmisartan. Metformin."`; `endswith(". Telmisartan. Metformin.")`; `"prompt": "Metformin."` |
| `tests/test_hints.py` | add `def terms(*names): return [HintTerm(n, float(len(names) - i)) for i, n in enumerate(names)]`; wrap every `build_hints` input in `terms(...)`; `:6` → `out[:2] == ["Tamsulosin", "paracetamol"]` (as saved); `:38` → `len(prompt_text(out))` |
| `tests/test_formulary.py:180,182,190`; `:184` | inputs `HintTerm(name, 1.0)` (Zorbexin 2.0 at `:182`); `len(prompt_text(out))` |
| `tests/test_transcribe_acc2.py:44-45` | seed two documents via `learn_spoken_terms(conn, form, save_document(...), None)`: `["Tamsulosin", "Tamsulosin", "Paracetamol"]`, then `["Tamsulosin"]` (a document counts once) |
| `tests/test_transcribe_acc2.py:57` | patch `route_mod.spoken_db.doctor_hint_terms` with `lambda conn, doctor_id, today: 1 / 0` |
| `tests/test_today_scope.py:87` | `learn_spoken_terms(conn, form, dbmod.save_document(conn, eid, "sha", form, ...), author)` |
| `tests/test_isolation_doctors.py:102`; `tests/test_isolation_routes.py:251` | spy keeps `{t.phrase for t in top}`; `[t.phrase for t in top]` |
| `tests/isolation_fixtures.py:223`; `tests/test_startup.py:58` | `stt._doctor_terms()` |

- [ ] **Step 7: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_hints.py tests/test_formulary.py tests/test_transcribe_acc2.py tests/test_today_scope.py tests/test_stt_providers.py tests/test_isolation_scope.py tests/test_startup.py tests/test_isolation_doctors.py tests/test_isolation_routes.py tests/test_isolation_formulary.py tests/test_overlay_lexicon.py tests/test_bench_run.py -q`.
  Expected: all pass (9 in the new file); `tests/test_isolation_formulary.py:44` needs no change.

### Task 5: The backfill command and the isolation tests

**Files:** Modify `api/spoken.py`, `admin.py:3,20-24,185-186,213`, `tests/isolation_fixtures.py:41-42`; create
`tests/test_isolation_spoken.py`; append to `tests/test_spoken_terms.py`.

**Interfaces:** Produces `api.spoken.replay_saved(conn, by_doctor: bool) -> tuple[int, int]` (documents read, new
uses) and `python -m doctor_dictation.admin backfill-spoken-terms` (exit 0; 1 if any database failed).

- [ ] **Step 1: Write the failing tests.** Append to `tests/test_spoken_terms.py`:

```python
def test_the_backfill_replays_saved_documents_once(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "old.db"))
    with closing(dbmod.get_conn()) as conn:
        dbmod.migrate(conn)
        _doc(conn, "2026-10-01T09:00:00Z", [DOLO])
        _doc(conn, "2026-10-02T09:00:00Z", [DOLO, {"name": "Pan", "strength": "40 mg"}])
    assert admin.main(["backfill-spoken-terms"]) == 0
    assert admin.main(["backfill-spoken-terms"]) == 0                        # the ledger: nothing counted twice
    out = capsys.readouterr().out.splitlines()
    assert out == ["single: 2 documents read, 3 new term uses", "single: 2 documents read, 0 new term uses"]
    assert [t[2:] for t in _terms()] == [("dolo", "Dolo", 2), ("pan", "Pan", 1)]
    monkeypatch.setenv("DB_PATH", str(tmp_path / "missing.db"))
    assert admin.main(["backfill-spoken-terms"]) == 1 and not (tmp_path / "missing.db").exists()
```

  Create `tests/test_isolation_spoken.py`:

```python
"""A doctor's spoken terms stay with that doctor in that clinic (plan SH-H1). Offline; the seeded two-clinic world."""
from doctor_dictation import admin
from doctor_dictation.api import stt as api_stt
from doctor_dictation.config import override_settings
from isolation_fixtures import A, B, H, sql, user_id, world  # noqa: F401

DOLO = {"form": "Tab.", "name": "Dolo", "strength": "650 mg", "dose": "1-0-1", "status": "verified"}

def test_a_doctors_spoken_terms_reach_only_that_doctors_hints(world, monkeypatch):
    for patient in ("Asha Verma", "Lakshmi Narayan"):
        body = {"structured": {"patientName": patient, "ageSex": "40 / F", "opNo": "", "rx": [dict(DOLO)]},
                "confirmed_rows": []}
        assert world.rao.post("/api/v1/documents", json=body, headers=H).status_code == 200
    override_settings(monkeypatch, stt_use_hints=True)
    real, seen = api_stt.build_hints, {}
    for who in ("rao", "mehta", "iyer"):
        monkeypatch.setattr(api_stt, "build_hints", lambda top, limit, who=who: seen.setdefault(who, real(top, limit)))
        r = getattr(world, who).post("/api/transcribe", files={"audio": ("a.webm", b"x" * 64, "audio/webm")}, headers=H)
        assert r.status_code == 200, r.text
    assert seen["rao"][0] == "Dolo 650" and "Dolo 650" not in seen["mehta"] + seen["iyer"]
    rows = sql(A, "SELECT doctor_id, uses FROM spoken_terms WHERE term_key = 'dolo'")
    assert [tuple(r) for r in rows] == [(user_id(world, "dr.rao"), 2)]
    assert sql(B, "SELECT COUNT(*) FROM spoken_terms WHERE term_key = 'dolo'")[0][0] == 0

def test_the_backfill_credits_each_author_in_their_own_clinic(world, capsys):
    for t in ("spoken_term_docs", "spoken_term_strengths", "spoken_terms"):
        sql(A, f"DELETE FROM {t}")                                            # as before H1: documents, no terms
    before_b = [tuple(r) for r in sql(B, "SELECT * FROM spoken_terms ORDER BY id")]
    assert admin.main(["backfill-spoken-terms"]) == 0
    assert capsys.readouterr().out.splitlines() == ["iyer: 2 documents read, 0 new term uses",
                                                    "rao: 3 documents read, 5 new term uses"]
    rao, mehta = user_id(world, "dr.rao"), user_id(world, "dr.mehta")
    assert {tuple(r) for r in sql(A, "SELECT doctor_id, term_key FROM spoken_terms")} == {
        (rao, "paracetamol"), (rao, "amlodipine"), (rao, "telmisartan"), (mehta, "cetirizine"), (mehta, "montelukast")}
    assert [tuple(r) for r in sql(B, "SELECT * FROM spoken_terms ORDER BY id")] == before_b
```

- [ ] **Step 2: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_isolation_spoken.py -q`.
  Expected: both backfill tests FAIL (argparse exit 2, invalid choice `backfill-spoken-terms`); the hint isolation
  test already passes.
- [ ] **Step 3: `replay_saved` in `api/spoken.py`.** Read patient words once; for every finalized document with JSON
  (`documents JOIN encounters`, `ORDER BY d.id`; bad JSON skipped) call `learn_spoken_terms(conn, structured, id,
  e.doctor_id if by_doctor else None, words)`; return (documents parsed, `SUM(uses)` after − before). NULL → doctor 0.
- [ ] **Step 4: `admin.py`.** `_backfill_spoken(_args) -> int` loops over `promotion.clinic_dbs()` (`promotion.py:104`:
  `("single", DB_PATH)` or each registered clinic). Per database, in `try/except (OSError, sqlite3.Error)`: a missing
  file raises `FileNotFoundError(f"no database at {path}")` (never created); `dbmod.init_db(path)` (applies 011);
  `replay_saved(conn, by_doctor=multi_clinic_enabled())`; print `f"{label}: {docs} documents read, {uses} new term
  uses"`; on error print `f"{label}: FAILED {exc}"` to stderr. Return 1 if any failed. Register it in `COMMANDS`
  (`:185-186`), add a sub-parser before `admin_demo.register` (`:213`), name it in the docstring (`:3`). Add the three new
  tables to `TABLES` (`tests/isolation_fixtures.py:41-42`) so every fingerprint check covers them.
- [ ] **Step 5: Run.** `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_isolation_spoken.py tests/test_isolation_formulary.py tests/test_isolation_routes.py tests/test_isolation_doctors.py tests/test_admin.py tests/test_admin_demo.py tests/test_promotion.py -q`.
  Expected: all pass (10 + 2 in the new files).

### Task 6: Mutations, whole suite, sizes and hand-over

- [ ] **Step 1: Mutations.** Apply each alone; run `.venv/bin/python -m pytest tests/test_spoken_terms.py tests/test_isolation_spoken.py -q`;
  see a failure; revert. Report "killed by <test>" for each.

| # | Mutation | Must fail |
|---|---|---|
| M1 | `USUAL_SHARE = 59`; drop `count >= USUAL_MIN`; `person_like` on known names | usual strength; terms |
| M2 | count when the ledger insert was ignored; `at = _utcnow()`; `LIMIT 30` | counts once; uncapped |
| M3 | `build_hints` without `eligible`; or `seen` without the base key | hints (Urimax) |
| M4 | `_doctor_terms` passes `None` for doctor 0; or delete the persistence hook | Dolo 650 twice |
| M5 | `replay_saved` ignores `by_doctor` | backfill credits each author |

- [ ] **Step 2: Whole suite.** `.venv/bin/python -m pytest tests/ -q`. Expected: N + 12, same skips, no failure.
- [ ] **Step 3: Sizes and hand-over.** `wc -l` on the File Structure files: inside budget (`api/persistence.py` 472).
  Leave uncommitted; list the 11 source files, 2 new and 12 changed test files. Hand over to H2.

## Self-Review

- Coverage: 011, 5.2 with the amendment, uncapped `doctor_hint_terms` (Tasks 1–2); hook, S4 (Task 3); S2, budget,
  `prompt_text`, `_doctor_terms` (Task 4); backfill both modes, isolation (Task 5). Must-haves: Dolo 650, never
  Paracetamol (4); Urimax (3–4); patient word (1, 3); re-save (2–3); usual strength, prompt format (1, 4).
- Out of scope: H2–H4 tiers, `diagnosis_key`, the `context` field, Spell it and Did you mean (S1 untouched), a
  removal UI (H2), keyword providers (AssemblyAI and Muse keep the list), deleting `top_medicines`, building
  `core/lexicon/investigations.json` (absent on `main`, so today only clinic-overlay tests are hint-eligible).

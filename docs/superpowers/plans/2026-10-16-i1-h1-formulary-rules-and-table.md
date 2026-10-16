# Clinic Formulary, Part 1: Rules, Layer, Table and Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The data side of the clinic formulary: the pure rules for learning a name (junk bounds, once per document, patient-name guard), the immutable `ClinicLayer`, and the per-clinic table with its per-document ledger and soft removal. Nothing matches names yet (I1-h2), nothing is served (I1-h3).

**Architecture:** `core/formulary.py` holds pure rules and the layer (stdlib only; per-clinic data comes in as data). A new migration `009` creates `clinic_formulary` and `clinic_formulary_docs`; `db/formulary.py` is SQL only (`db/__init__.py` is 487 lines, so new SQL cannot go there).

**Tech Stack:** Python 3 / FastAPI / sqlite3 (stdlib), vanilla JS, pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Clinic formulary") and table row "Clinic formulary"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 1, 2, 5, 6; sections 4.1, 4.2, 4.3).

**Assumptions about earlier plans:** none besides the baseline suite. This is part 1 of 4 (I1-h1 rules and table, I1-h2 grounding and hints, I1-h3 API and cache, I1-h4 isolation and Team tab). Order: I1-h1, then I1-h2, then I1-h3, then I1-h4 (each needs the previous).

**Produces (consumed by I1-h2 to I1-h4):** `core/formulary.py`: `key(name) -> str`, `clean_name(raw) -> str`, `learnable(structured, confirmed_rows) -> list[(name, generic)]`, `ClinicLayer(items: tuple[(name, generic)])` with `.get(name) -> (name, generic) | None`, `.version -> str`, `.hint_names() -> list[str]`, `activate(layer)`, `active_layer()`, constants `THRESHOLD = 2`, `MAX_NAME = 60`, `MAX_WORDS = 5`, `MAX_HINTS = 10`, `HINT_CHARS = 150`. `db/formulary.py`: `record_confirmation(conn, key, name, generic, document_id, user_id) -> int`, `list_active(conn) -> list[dict]` (keys `id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by`), `remove(conn, entry_id) -> str | None`. Migration `009_clinic_formulary.sql`. `tests/test_formulary.py` (the first 3 tests) and `tests/test_formulary_db.py`.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): `core/formulary.py` imports only the standard library and `core.candidates`/`core.determinism` (lazily). Per-clinic data comes in as data.
- Changes to `core/determinism.py`: at most 4 net lines (this plan: +1). No source file over 500 lines (`db/__init__.py` is 487 lines, so the new SQL lives in `db/formulary.py`).
- Existing endpoints keep their status codes and JSON shapes; rows gain only `source` (and `lookalike` for a clinic name flagged as a look-alike). `preserve_untouched_rx_status` also restores `source` (`core/correction.py:273`).
- A clinic name is verified for its NAME only: no strength options, dose check `cannot-check`. Another clinic never sees a name: every query runs on the scoped clinic database (`db/__init__.py:35-44`).
- Tests offline: stub LLM (`STUB_LLM_JSON`), fake PDF renderer, no network. Test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

- A patient's name typed into a medicine cell must not become a drug (name bounds, at most 5 words, a name made only of the patient's words is skipped, two separate documents needed). Pinned in Task 1.
- Saving the same document again (re-save, double click) must not count twice; a name removed by an admin must not come back from old documents. Pinned in Task 2.

## Decisions (and why)

1. **Trigger.** `api/persistence.py:194` already blocks any row not `verified` unless its index is in `confirmed_rows`. The hook runs after the document is stored (after the audit call, `:289-299`) and learns from rows whose index is in `confirmed_rows` AND whose name the lexicon does not know (`_canonical_lookup`, `core/determinism.py:226`). The row's `status` text is not used: the client could send anything. Names are read from `structured["rx"]` BEFORE `validate_structured` (which drops empty rows and shifts indexes).
2. **Once per document.** Table `clinic_formulary_docs(formulary_id, document_id)` is the ledger; `INSERT OR IGNORE` makes a re-save change nothing. `confirm_count` is only ever incremented when the ledger insert really inserted.
3. **Junk.** 3 to 60 characters (60 is `hints._MAX_DOCTOR_NAME`, `core/hints.py:14`), letters, digits, space and `. ' + / -`, starting with a letter, at most 5 words, at least 3 letters; a name whose words are all inside the document's `patientName` is skipped. A patient's name that is not on that document's `patientName` still needs two separate prescriptions and can be removed by an admin.
4. **Removal rule: a removed name needs a fresh 2 confirmations from NEW documents.** Blocking it forever would punish a drug the clinic really starts to use; silent relearning from the same old prescriptions is prevented because removal keeps the ledger and zeroes `confirm_count` (soft delete: `removed_at` set, row kept). Tested in Task 2.

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/core/formulary.py` | NEW: rules and layer (this part), grounding hook (I1-h2) |
| `doctor_dictation/db/migrations/009_clinic_formulary.sql` | NEW table + ledger. Latest on disk is `008`; migrations reach every clinic file through `db.migrate` (`init_db` in single mode, `clinics.migrate_clinic`/`migrate_all` at start-up in multi-clinic mode, `clinics.py:14-23`, `:47-63`) |
| `doctor_dictation/db/formulary.py` | NEW: SQL only |
| `tests/test_formulary.py`, `tests/test_formulary_db.py` | NEW |
| `tests/test_db.py`, `tests/test_template_scope_db.py`, `tests/test_authorship_db.py` | setup values updated for the new migration |

Adds 6 tests. Baseline: run the suite first and note the count (944 passed, 1 skipped when this was written); expect baseline + 6.

---

### Task 1: The rules and the layer (pure)

**Files:** Create `doctor_dictation/core/formulary.py`, `tests/test_formulary.py`.

**Interfaces:** Produces `key(name) -> str` (casefolded, single-spaced), `clean_name(raw) -> str` ("" for junk, else the name with case normalised: ALL CAPS or all lower becomes Capitalised words, mixed case kept), `learnable(structured, confirmed_rows) -> list[(name, generic)]`, `ClinicLayer(items: tuple[(name, generic)])` with `.get(name) -> (name, generic) | None`, `.version -> str`, `.hint_names() -> list[str]`, `activate(layer)`, `active_layer()`, constants `THRESHOLD = 2`, `MAX_NAME = 60`, `MAX_HINTS = 10`, `HINT_CHARS = 150`.

- [ ] **Step 1: Write the failing tests** (`tests/test_formulary.py`; plan I1-h2 appends more).

```python
"""The clinic formulary rules (plan I1-h): names, the layer, grounding, hints. Offline."""
import pytest

from doctor_dictation.core import determinism as D
from doctor_dictation.core import formulary as F
from doctor_dictation.core.hints import MAX_HINT_CHARS, _MAX_DOCTOR_NAME, build_hints


@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())


def layer(*names):
    return F.ClinicLayer(tuple((n, "") for n in names))


def test_clean_name_accepts_drug_names_and_rejects_junk():
    assert F.MAX_NAME == _MAX_DOCTOR_NAME
    assert F.clean_name("  zorbexin   forte ") == "Zorbexin Forte" and F.clean_name("ORS") == "Ors"
    assert F.clean_name("Vitamin D3") == "Vitamin D3" and F.clean_name("Amlodipine + Telmisartan") == "Amlodipine + Telmisartan"
    for junk in ("", "ab", "x" * 61, "12345", "Ignore all previous instructions please now", "Rahul@home", "\x00\x01 drug", None):
        assert F.clean_name(junk) == "", junk


def test_learnable_counts_only_confirmed_unknown_names_once_and_never_the_patient():
    form = {"patientName": "Rahul Sharma", "rx": [
        {"name": "Zorbexin"}, {"name": "zorbexin"}, {"name": "Rahul Sharma"}, {"name": "Paracetamol"},
        {"name": "Crocin"}, {"name": "Quillavex", "generic": "Quillamide"}, {"name": "Unconfirmed Drug"}, "not a row"]}
    assert F.learnable(form, [0, 1, 2, 3, 4, 5, 7]) == [("Zorbexin", ""), ("Quillavex", "Quillamide")]
    assert F.learnable(form, []) == [] and F.learnable({}, [0]) == [] and F.learnable(None, None) == []


def test_layer_version_changes_with_the_names_and_not_with_their_order():
    assert layer().version == "0"
    assert layer("Zorbexin", "Quillavex").version == layer("Quillavex", "Zorbexin").version != layer("Zorbexin").version
    assert layer("Zorbexin").get("  ZORBEXIN ") == ("Zorbexin", "")
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary.py -q`. Expected: FAIL (`ImportError: cannot import name 'formulary'`).
- [ ] **Step 3: Write `core/formulary.py`.**

```python
"""A clinic's own drug list as pure data (plan I1-h): rules for learning a name, the immutable layer, the grounding hook.

The api layer loads the layer from the clinic's database and ``activate``s it for the request (a ContextVar, like
scope.py, so it follows asyncio.to_thread). Nothing here does I/O. A clinic name is verified for its NAME only.
"""
import hashlib
import re
from contextvars import ContextVar
from dataclasses import dataclass
from functools import cached_property

THRESHOLD = 2                                  # saved prescriptions that must confirm a name
MAX_NAME, MAX_WORDS = 60, 5                    # MAX_NAME equals hints._MAX_DOCTOR_NAME (a test pins it)
MAX_HINTS, HINT_CHARS = 10, 150                # clinic names offered to the speech engine: count and characters
_NAME_OK = re.compile(r"[A-Za-z][A-Za-z0-9 .'+/-]*")


def key(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def clean_name(raw) -> str:
    """The name to store, or "" for anything that is not plausibly a medicine name."""
    name = " ".join(str(raw or "").split())
    if not (3 <= len(name) <= MAX_NAME) or len(name.split()) > MAX_WORDS or not _NAME_OK.fullmatch(name):
        return ""
    if sum(c.isalpha() for c in name) < 3:
        return ""
    return re.sub(r"[A-Za-z]+", lambda m: m.group(0).capitalize(), name) if name.isupper() or name.islower() else name


def learnable(structured, confirmed_rows) -> list[tuple[str, str]]:
    """[(name, generic)] a saved form teaches: confirmed rows whose name the lexicon does not know, once per name.

    The doctor's confirmation, not the row's status text, is the trigger (the client could send any status), and a
    name made only of the patient's own name words is never learned (a patient typed into a medicine cell)."""
    from .determinism import _canonical_lookup
    rows = structured.get("rx") if isinstance(structured, dict) else None
    confirmed = {i for i in (confirmed_rows or []) if isinstance(i, int)}
    patient = {w.casefold() for w in str(structured.get("patientName") or "").split()} if isinstance(structured, dict) else set()
    out, seen = [], set()
    for i, row in enumerate(rows if isinstance(rows, list) else []):
        name = clean_name(row.get("name")) if i in confirmed and isinstance(row, dict) else ""
        if not name or key(name) in seen or _canonical_lookup(name) or {w.casefold() for w in name.split()} <= patient:
            continue
        seen.add(key(name))
        out.append((name, clean_name(row.get("generic"))))
    return out


@dataclass(frozen=True)
class ClinicLayer:
    """Active names, most recently seen first: ((name, generic or ''), ...)."""
    items: tuple = ()

    @cached_property
    def _by_key(self) -> dict:
        return {key(n): (n, g) for n, g in self.items}

    @cached_property
    def version(self) -> str:
        """Changes whenever a name is added or removed ("0" when empty); part of the /api/format cache key."""
        return hashlib.sha1("|".join(sorted(self._by_key)).encode()).hexdigest()[:8] if self.items else "0"

    def get(self, name):
        return self._by_key.get(key(name))

    def hint_names(self) -> list[str]:
        """The newest names that fit MAX_HINTS and HINT_CHARS, so they cannot crowd the 500-character hint budget."""
        out, used = [], 0
        for name, _generic in self.items:
            if len(out) >= MAX_HINTS or used + len(name) + 2 > HINT_CHARS:
                break
            out.append(name)
            used += len(name) + 2
        return out


_active: ContextVar[ClinicLayer] = ContextVar("dd_clinic_layer", default=ClinicLayer())


def active_layer() -> ClinicLayer:
    return _active.get()


def activate(layer: ClinicLayer) -> None:
    _active.set(layer)
```

- [ ] **Step 4: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary.py -q` then `.venv/bin/python -m pytest tests/test_core_purity.py -q`. Expected: `3 passed`, then the purity file passes (the new module imports only the standard library at module level).
- [ ] **Step 5: Leave uncommitted.**

---

---

### Task 2: The table, the ledger and soft removal

**Files:** Create `doctor_dictation/db/migrations/009_clinic_formulary.sql`, `doctor_dictation/db/formulary.py`, `tests/test_formulary_db.py`; Modify `tests/test_db.py`, `tests/test_template_scope_db.py`, `tests/test_authorship_db.py`.

**Interfaces:** Consumes `core.formulary.THRESHOLD`, `key`. Produces `record_confirmation(conn, key, name, generic, document_id, user_id) -> int` (the count after this call), `list_active(conn) -> list[dict]` (newest first; keys `id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by`), `remove(conn, entry_id) -> str | None` (the name, or None when this database has no ACTIVE entry with that id).

- [ ] **Step 1: Write the failing tests.**

```python
"""The per-clinic learned drug list in SQLite (plan I1-h): the ledger, the threshold and soft removal. Offline."""
import pytest

from doctor_dictation import db as dbmod
from doctor_dictation.core.formulary import key
from doctor_dictation.db import formulary as fdb


@pytest.fixture()
def conn(tmp_path):
    c = dbmod.get_conn(tmp_path / "f.db")
    dbmod.migrate(c)
    yield c
    c.close()


@pytest.fixture()
def docs(conn):
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    return [dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(4)]


def count(conn, doc, name="Zorbexin"):
    return fdb.record_confirmation(conn, key(name), name, "", doc, None)


def test_a_name_needs_two_different_documents_and_a_resave_never_double_counts(conn, docs):
    d1, d2, d3, _ = docs
    assert (count(conn, d1), count(conn, d1), count(conn, d1)) == (1, 1, 1)             # the same document again
    assert fdb.list_active(conn) == []
    assert count(conn, d2) == 2
    (row,) = fdb.list_active(conn)
    assert (row["name"], row["confirm_count"], row["generic"]) == ("Zorbexin", 2, None)
    assert count(conn, d3) == 3 and len(fdb.list_active(conn)) == 1


def test_a_removed_name_needs_two_fresh_documents_and_old_ones_do_not_count(conn, docs):
    d1, d2, d3, d4 = docs
    count(conn, d1), count(conn, d2)
    (row,) = fdb.list_active(conn)
    assert fdb.remove(conn, row["id"]) == "Zorbexin" and fdb.remove(conn, row["id"]) is None   # second removal: not active
    assert fdb.list_active(conn) == []
    assert count(conn, d1) == 0 and count(conn, d2) == 0 and fdb.list_active(conn) == []       # re-saving old documents
    assert count(conn, d3) == 1 and fdb.list_active(conn) == []                                # one new one is not enough
    assert count(conn, d4) == 2 and [r["name"] for r in fdb.list_active(conn)] == ["Zorbexin"]
    assert conn.execute("SELECT removed_at FROM clinic_formulary").fetchone()[0] is None


def test_the_name_key_is_unique(conn, docs):
    count(conn, docs[0])
    with pytest.raises(Exception):
        conn.execute("INSERT INTO clinic_formulary(name_key, name, first_seen_at, last_seen_at) VALUES ('zorbexin','Z','x','x')")
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary_db.py -q`. Expected: collection error `ImportError: cannot import name 'formulary' from 'doctor_dictation.db'`.
- [ ] **Step 3: Write the migration** (applied once per clinic file by `db.migrate`, recorded in `schema_migrations`).

```sql
-- 009: this clinic's own drug list, learned from confirmed prescriptions. One row per name (name_key = casefolded).
-- A name is ACTIVE when removed_at IS NULL and confirm_count >= 2. A removal sets removed_at and resets confirm_count;
-- the ledger below keeps the documents already counted, so only NEW prescriptions count towards a re-learn.
CREATE TABLE clinic_formulary (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name_key      TEXT    NOT NULL UNIQUE,
    name          TEXT    NOT NULL,
    generic       TEXT,
    confirm_count INTEGER NOT NULL DEFAULT 0,
    first_seen_at TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    added_by      INTEGER REFERENCES users(id),
    removed_at    TEXT
);
CREATE TABLE clinic_formulary_docs (
    formulary_id INTEGER NOT NULL REFERENCES clinic_formulary(id),
    document_id  INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (formulary_id, document_id)
);
```

- [ ] **Step 4: Write `db/formulary.py`.**

```python
"""The clinic's learned drug list (spec I1-h). SQL only; the rules (names, threshold) live in core/formulary.py."""
from doctor_dictation.core.formulary import THRESHOLD
from doctor_dictation.db import _utcnow

COLUMNS = "id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by"


def record_confirmation(conn, key, name, generic, document_id, user_id) -> int:
    """Count one saved DOCUMENT for a name. The same document again (a re-save) changes nothing. Returns the count."""
    now = _utcnow()
    row = conn.execute("SELECT id FROM clinic_formulary WHERE name_key = ?", (key,)).fetchone()
    fid = row["id"] if row else conn.execute(
        "INSERT INTO clinic_formulary(name_key, name, generic, first_seen_at, last_seen_at) VALUES (?, ?, ?, ?, ?)",
        (key, name, generic or None, now, now)).lastrowid
    if conn.execute("INSERT OR IGNORE INTO clinic_formulary_docs(formulary_id, document_id) VALUES (?, ?)",
                    (fid, document_id)).rowcount:
        conn.execute(
            "UPDATE clinic_formulary SET confirm_count = confirm_count + 1, last_seen_at = ?,"
            " removed_at = CASE WHEN confirm_count + 1 >= ? THEN NULL ELSE removed_at END,"
            " added_by = CASE WHEN confirm_count + 1 >= ? THEN ? ELSE added_by END WHERE id = ?",
            (now, THRESHOLD, THRESHOLD, user_id, fid))
    conn.commit()
    return conn.execute("SELECT confirm_count FROM clinic_formulary WHERE id = ?", (fid,)).fetchone()[0]


def list_active(conn) -> list[dict]:
    """Active names, most recently seen first."""
    rows = conn.execute(f"SELECT {COLUMNS} FROM clinic_formulary WHERE removed_at IS NULL AND confirm_count >= ?"
                        " ORDER BY last_seen_at DESC, id DESC", (THRESHOLD,)).fetchall()
    return [dict(r) for r in rows]


def remove(conn, entry_id) -> str | None:
    """Soft-remove an ACTIVE entry: returns its name, or None when this clinic has no such active entry."""
    row = conn.execute("SELECT name FROM clinic_formulary WHERE id = ? AND removed_at IS NULL AND confirm_count >= ?",
                       (entry_id, THRESHOLD)).fetchone()
    if row is None:
        return None
    conn.execute("UPDATE clinic_formulary SET removed_at = ?, confirm_count = 0 WHERE id = ?", (_utcnow(), entry_id))
    conn.commit()
    return row["name"]
```

- [ ] **Step 5: Update the four existing assertions a new migration forces** (setup values only; no assertion changes meaning): in `tests/test_db.py` the list of applied versions and `n == 8`; in `tests/test_template_scope_db.py` and `tests/test_authorship_db.py` the lists of versions applied on top of an older database.

```diff
- "007_templates_scope.sql", "008_clinic_profile_prefix.sql"]
+ "007_templates_scope.sql", "008_clinic_profile_prefix.sql",
+                      "009_clinic_formulary.sql"]
```
```diff
- assert n == 8
+ assert n == 9
```
```diff
- assert applied == ["007_templates_scope.sql", "008_clinic_profile_prefix.sql"]
+ assert applied == ["007_templates_scope.sql", "008_clinic_profile_prefix.sql", "009_clinic_formulary.sql"]
```
```diff
-                                     "008_clinic_profile_prefix.sql"]
+                                     "008_clinic_profile_prefix.sql", "009_clinic_formulary.sql"]
```

- [ ] **Step 6: Run.** Run: `.venv/bin/python -m pytest tests/test_formulary_db.py tests/test_db.py tests/test_template_scope_db.py tests/test_authorship_db.py -q`. Expected: all pass (`test_formulary_db.py`: 3 passed).
- [ ] **Step 7: Leave uncommitted.**

---

## Self-review

Rules and layer (Task 1), table, ledger and removal rule (Task 2). Names match the Produces block. Not done here: matching, hints, API, UI (I1-h2 to I1-h4).

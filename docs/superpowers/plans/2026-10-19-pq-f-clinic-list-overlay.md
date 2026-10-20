# PQ-f: Clinic List Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each clinic owns its medicine and investigation lists as an overlay (add / edit / hide) on top of the shipped lists, with list screens on the Team page, an owner-only shared-list review that exports a changes file, and an operator command that folds that file into the shipped JSON.

**Architecture:** One table per clinic database (`clinic_overlay`, migration 010) stores only the clinic's changes. A pure function (`core/overlay.effective_entries`) lays them over the shipped list. A per-request ContextVar (same pattern as `use_clinic_layer`) makes `determinism.load_lexicon()` return the effective list, memoised per overlay version so every identity-keyed cache stays correct. The owner's shared-list edits never touch a running list: they are exported and applied to the repo by `python -m doctor_dictation.admin apply-list-changes`.

**Tech Stack:** Python 3 / FastAPI / SQLite (stdlib `sqlite3`), vanilla JS (no framework), pytest, node fake-DOM tests.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` ("Decisions made": decision 3, 3a, "clinic lists (overlay)"); shared contract "Clinic overlay (plan f)" and "Learning threshold (owner rule, 2026-10-19; plans f, g, h)" in `docs/superpowers/plans/2026-10-19-pq-00-index.md`.

**Owner answers 2026-10-19:** Q16 removing a shared entry stays a manual repo edit (OK). Q17 a clinic may change a shipped medicine's generic (clinic `edit` with `generic`), audited as `list.edit`. Q18 the list tabs are admin-only for now. Q19 owner pending edits live in `DATA_DIR/owner/list-changes.json` (OK). Learning threshold: a doctor's entry from a prescription goes live only after `formulary.THRESHOLD` (2) confirmed saves in different prescriptions with the same value; admin edits are live at once.

## Global Constraints

- Contract names are fixed: table `clinic_overlay` (+ `confirm_count`), table `clinic_overlay_docs`; `db/overlay.py: upsert, list_rows, reset, record_confirmation, approve`; active rule `removed_at IS NULL AND (source = 'admin' OR confirm_count >= formulary.THRESHOLD)`; `core/overlay.py: effective_entries(kind, shipped, rows) -> (entries, flags)`; flag reasons `"shipped-changed"`, `"safety-override"`; env `OWNER_USERNAMES`; export `{"kind", "changes": [{"action", "entry_key", "data"}]}`; command `apply-list-changes <file>`.
- Learned and clinic data is stored only in `/data/clinics/<slug>/app.db`; the app never writes `drugs.json` / `investigations.json`. Only the operator command writes shipped files, in the repo, then commit + deploy.
- `doctor_dictation/core/*` stays stdlib-only and I/O-free (`tests/test_core_purity.py`).
- No source file over 500 lines (`tests/test_file_sizes.py` for Python; same rule for JS). `frontend/app.js` (1251 lines) is not touched.
- Every clinic list write checks `policy.can(ident, "formulary.manage")` (`policy.py:9`, `:26-27`) and writes one `audit_log` row (`db/__init__.py:260`). Everyone is admin today (`accounts.py:21`): acceptable for MVP 1.
- Frontend: no `innerHTML`/`insertAdjacentHTML`, no external hosts (pinned by `tests/test_frontend_team_medicines.py`); bump `?v=` on every changed static file (`frontend/index.html:12`, `:267`).
- Tests: `.venv/bin/python -m pytest -q`. The autouse `DB_PATH` fixture (`tests/conftest.py`) keeps the dev DB safe.
- "Commit" steps: ask the owner first (index, shared rules).

## Review Focus

1. **Two clinics' requests interleave on worker threads.** The single-slot caches read their global twice (`determinism.py:124-126`, `surface.py:62-64`, `lasa.py:52-53`, `candidates.py:72-75`): with per-clinic lists, a thread can get the other clinic's map. Expected: clinic A's added brand never grounds in clinic B. Test: Task 5 `test_interleaved_threads_never_cross`.
2. **The shipped entry dicts are shared by every clinic.** Any in-place change in `effective_entries` would leak one clinic's edit into all. Test: Task 2 `test_shipped_list_is_never_mutated`.
3. **A clinic adds a brand the shipped list already maps to another generic** ("Zerodol" → own combination). Without care the name becomes ambiguous (`surface.ambiguous_names`) and reads unverified. Expected: the clinic wins. Test: Task 2 `test_add_takes_a_name_a_shipped_entry_claims`.
4. **The `/api/format` cache serves the pre-edit answer after a list edit** (`api/format.py:101`). Test: Task 5 `test_format_cache_misses_after_a_list_edit`.
5. **`apply-list-changes` produces a `drugs.json` that `build.py --check` rejects** (`drugs.json` is built from `seed_extra.json` + `imported.json`, `build.py:177-182`, and `imported.json` re-adds brands, `lexicon_import.py:170-185`). Expected: refused, nothing written. Test: Task 10 `test_an_edit_that_imported_json_would_undo_is_refused`.

## Decisions taken in this plan (owner may overrule)

- **Learned names** (`clinic_formulary`, migration 009) stay the 2-confirmation counter. Active learned names not already in the effective list appear on the Medicines screen as `learned` rows. Editing one writes an overlay `add` (it then shows as clinic-added); "Remove" keeps today's soft removal (`api/formulary.py:83-101`). Nothing is written to the overlay automatically.
- **`source`** values: `"admin"` = written from the clinic list screen (live at once); `"doctor"` = from a prescription through `record_confirmation` (plans g, h; pending until `THRESHOLD`); `"learned"` = reserved, treated like `"doctor"` by the active rule.
- **Pending rows never reach `effective_entries`.** `list_rows` returns active rows only; the list screen reads pending rows separately (`list_rows(..., pending=True)`) and shows them as "Pending (n of 2)".
- **Medicine `add` needs a generic.** An add with an empty generic would get an empty `canonical`, which `_alias_map` skips (`determinism.py:100`). A name without a generic stays a learned name.
- **Owner export supports `add` and `edit` only.** `build.compute_merged` unions with the current `drugs.json` (`build.py:123-144`), so removing a shared entry is a manual repo edit. `edit` of a shipped entry may change `aliases`, `brands`, `safety` (medicine) or `aliases`, `category`, `print`, `safety` (investigation), never `canonical`.
- **Owner pending changes** are kept server-side in `DATA_DIR/owner/list-changes.json` (atomic write), so a reload loses nothing. Usernames are globally unique (`directory/migrations/001_directory.sql:12-13`, `COLLATE NOCASE`), so bare usernames in `OWNER_USERNAMES` are safe.
- **`apply-list-changes`** is a dry run unless `--confirm` (same rule as `promote-apply`, `promotion.py:216-217`). Contract addition, reported.

## File Structure

| File | Responsibility |
|---|---|
| `doctor_dictation/db/migrations/010_clinic_overlay.sql` (create) | Tables `clinic_overlay`, `clinic_overlay_docs` |
| `doctor_dictation/db/overlay.py` (create) | SQL only: `upsert`, `list_rows`, `reset`, `record_confirmation`, `approve` |
| `doctor_dictation/core/overlay.py` (create) | Pure: `entry_sha`, `validate_data`, `effective_entries`, `screen_rows`; ContextVar state, `effective_view`, shipped-loader registry |
| `doctor_dictation/core/lexmemo.py` (create) | `per_lexicon`: race-free, few-slot cache keyed on list identity |
| `doctor_dictation/core/determinism.py` (modify) | `shipped_lexicon`, `load_lexicon` via overlay, `lexicon_identity` |
| `doctor_dictation/core/{surface,lasa,candidates,formulary}.py` (modify) | Caches on `per_lexicon`; `_twin` keyed on `lexicon_identity` |
| `doctor_dictation/api/formulary.py`, `api/format.py` (modify) | Activate the overlay with the layer; cache key |
| `doctor_dictation/api/lists.py` (create) | Clinic list routes |
| `doctor_dictation/policy.py`, `api/auth.py` (modify) | `is_owner`; `/auth/me` returns `is_owner` |
| `doctor_dictation/api/owner_lists.py` (create) | Owner review routes, pending store, export |
| `doctor_dictation/listchanges.py` (create), `admin.py` (modify) | `apply-list-changes` |
| `frontend/clinlists.js`, `frontend/listedit.js`, `frontend/ownerlists.js` (create) | List panels, edit dialog, owner tab |
| `frontend/team.js`, `team.css`, `index.html` (modify) | Tabs; learned-list code moves to `clinlists.js` |

---

### Task 0: Preflight

- [ ] **Step 1:** Re-read `core/determinism.py`, `core/formulary.py`, `api/formulary.py`, `api/format.py`, `frontend/team.js`, `frontend/index.html`: plans a–e change them first (plan a adds `_exact_lookup`; plan e may bump `?v=`). Update the line numbers below where they moved.
- [ ] **Step 2:** Run `.venv/bin/python -m pytest -q`. Expected: all pass. Record the count.

### Task 1: Migration 010 and `db/overlay.py`

**Files:**
- Create: `doctor_dictation/db/migrations/010_clinic_overlay.sql`, `doctor_dictation/db/overlay.py`
- Test: `tests/test_overlay_db.py`

**Interfaces:**
- Consumes: `formulary.THRESHOLD` (`core/formulary.py:18`).
- Produces:
  - `upsert(conn, kind, entry_key, action, data: dict, base_sha, source, user_id) -> int` (row id). Admin edits; live at once.
  - `list_rows(conn, kind, *, pending: bool = False) -> list[dict]` — `pending=False`: active rows only (`removed_at IS NULL AND (source = 'admin' OR confirm_count >= THRESHOLD)`); `pending=True`: not-removed rows that are not active. `data` parsed to a dict; each dict has `source` and `confirm_count`; ordered by `entry_key`.
  - `reset(conn, kind, entry_key) -> bool`.
  - `record_confirmation(conn, kind, entry_key, action, data: dict, base_sha, document_id, user_id) -> int` — returns the count; source `'doctor'`. Rules: no row → insert, count 1, ledger `{document_id}`; same data (sorted-key JSON equal) and document not in `clinic_overlay_docs` → count + 1; same document again → unchanged; different data, or a removed row → take the new data, clear the ledger, count 1, `removed_at = NULL`. A live `'admin'` row is never changed by a doctor save (returns 0; decision taken here).
  - `approve(conn, kind, entry_key, user_id) -> bool` — a pending row (not removed, source not `'admin'`) gets `source = 'admin'`; `False` for any other row. The route writes the audit row (Task 6).

- [ ] **Step 1: Write the failing tests** (open a temp DB with `dbmod.get_conn(tmp_path / "a.db")` + `dbmod.migrate`; a helper `doc(conn) -> int` inserts a `documents` row):

```python
def test_upsert_inserts_then_updates_one_row(conn):
    i = overlay.upsert(conn, "medicine", "zerodol-p", "add", {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}, "", "admin", 1)
    j = overlay.upsert(conn, "medicine", "zerodol-p", "add", {"name": "Zerodol-P", "generic": "X"}, "", "admin", 2)
    rows = overlay.list_rows(conn, "medicine")
    assert i == j and len(rows) == 1 and rows[0]["data"] == {"name": "Zerodol-P", "generic": "X"}
    assert rows[0]["created_by"] == 1                      # first writer kept; who changed it lives in audit_log

def test_reset_hides_the_row_and_upsert_revives_it(conn): ...   # reset -> True, list_rows == [], reset again -> False, upsert -> listed, removed_at None
def test_kinds_are_separate(conn): ...                          # same entry_key under "investigation" is its own row
def test_check_constraints_reject_bad_kind_action_source(conn): # sqlite3.IntegrityError for kind "drug", action "delete", source "x"

G = {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}
def confirm(conn, d, data=G): return overlay.record_confirmation(conn, "medicine", "zerodol-p", "add", data, "", d, 1)

def test_resave_of_the_same_document_never_counts_twice(conn):
    d = doc(conn)
    assert confirm(conn, d) == 1 and confirm(conn, d) == 1
    assert overlay.list_rows(conn, "medicine") == []
    assert overlay.list_rows(conn, "medicine", pending=True)[0]["confirm_count"] == 1
def test_different_data_restarts_at_1(conn):
    confirm(conn, doc(conn))
    assert confirm(conn, doc(conn), {"name": "Zerodol-P", "generic": "Aceclofenac"}) == 1
    assert overlay.list_rows(conn, "medicine", pending=True)[0]["data"]["generic"] == "Aceclofenac"
def test_reaching_threshold_activates(conn):
    confirm(conn, doc(conn))
    assert confirm(conn, doc(conn)) == formulary.THRESHOLD
    assert [r["entry_key"] for r in overlay.list_rows(conn, "medicine")] == ["zerodol-p"]
    assert overlay.list_rows(conn, "medicine", pending=True) == []
def test_admin_source_is_active_at_0(conn):
    overlay.upsert(conn, "medicine", "zerodol-p", "add", G, "", "admin", 1)
    assert overlay.list_rows(conn, "medicine")[0]["confirm_count"] == 0
    assert confirm(conn, doc(conn), {"name": "Zerodol-P", "generic": "X"}) == 0   # doctor save leaves a live admin row
def test_removed_rows_are_inactive(conn):
    confirm(conn, doc(conn)); confirm(conn, doc(conn)); overlay.reset(conn, "medicine", "zerodol-p")
    assert overlay.list_rows(conn, "medicine") == [] and overlay.list_rows(conn, "medicine", pending=True) == []
    assert confirm(conn, doc(conn)) == 1                                           # revived as pending
def test_approve_sets_source_admin(conn):
    confirm(conn, doc(conn))
    assert overlay.approve(conn, "medicine", "zerodol-p", 2) is True
    assert overlay.list_rows(conn, "medicine")[0]["source"] == "admin"
    assert overlay.approve(conn, "medicine", "zerodol-p", 2) is False             # already active
    assert overlay.approve(conn, "medicine", "nope", 2) is False
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest -q tests/test_overlay_db.py`. Expected: FAIL (no module / no table).
- [ ] **Step 3: Write the migration.** Columns exactly as the contract: `id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL CHECK (kind IN ('medicine','investigation')), entry_key TEXT NOT NULL, action TEXT NOT NULL CHECK (action IN ('add','edit','hide')), data TEXT NOT NULL DEFAULT '{}', base_sha TEXT NOT NULL DEFAULT '', source TEXT NOT NULL CHECK (source IN ('doctor','admin','learned')), confirm_count INTEGER NOT NULL DEFAULT 0, created_by INTEGER REFERENCES users(id), created_at TEXT NOT NULL, updated_at TEXT NOT NULL, removed_at TEXT, UNIQUE(kind, entry_key)`. Then `clinic_overlay_docs(overlay_id INTEGER NOT NULL REFERENCES clinic_overlay(id), document_id INTEGER NOT NULL REFERENCES documents(id), PRIMARY KEY (overlay_id, document_id))`. Header comment in the style of `009_clinic_formulary.sql:1-3`, stating the active rule.
- [ ] **Step 4: Implement `db/overlay.py`.** `upsert` = `INSERT … ON CONFLICT(kind, entry_key) DO UPDATE SET action, data, base_sha, source, updated_at, removed_at = NULL` (keeps `created_by`, `created_at`, `confirm_count`), then `conn.commit()` like `db/formulary.py:22`. `data` stored with `json.dumps(data, sort_keys=True, ensure_ascii=False)`. Timestamps from `db._utcnow`. Active rule as one SQL fragment `_ACTIVE` with `THRESHOLD` bound as a parameter (pattern: `db/formulary.py:29`). `record_confirmation` compares the stored `data` text with the new `json.dumps(...)` text; restart = `DELETE FROM clinic_overlay_docs WHERE overlay_id = ?` + insert this document + `confirm_count = 1`; count = `INSERT OR IGNORE` into the ledger, then `confirm_count + 1` only when a row was inserted (`cursor.rowcount == 1`). One `commit` per call.
- [ ] **Step 5:** Run the tests, then `.venv/bin/python -m pytest -q tests/test_db.py tests/test_directory.py`. Expected: PASS (fix any test that pins the migration list).
- [ ] **Step 6: Commit** `feat(overlay): migration 010 clinic_overlay with confirmation threshold, db/overlay.py`.

### Task 2: Pure merge — `entry_sha`, `validate_data`, `effective_entries`

**Files:**
- Create: `doctor_dictation/core/overlay.py`
- Test: `tests/test_overlay_core.py`

**Interfaces:**
- Consumes: `formulary.key` (`core/formulary.py:26`), `formulary.clean_name` (`:30`).
- Produces:
  - `KINDS = ("medicine", "investigation")`
  - `entry_key_of(entry: dict) -> str` — `formulary.key(entry["canonical"])`.
  - `entry_sha(entry: dict) -> str` — sha256 hex of `json.dumps(entry, sort_keys=True, ensure_ascii=False, separators=(",", ":"))`.
  - `validate_data(kind: str, action: str, data, owner: bool = False) -> dict` — cleaned copy or `ValueError(<message a person can read>)`.
  - `effective_entries(kind, shipped: list[dict], rows: list[dict]) -> tuple[list[dict], list[dict]]` (contract).

Rules `validate_data` enforces:

| Key | Kinds / actions | Rule |
|---|---|---|
| `name` | add (both kinds) | `formulary.clean_name` non-empty |
| `generic` | medicine add (required), medicine edit (clinic only) | 3–120 chars, `[A-Za-z][A-Za-z0-9 .,'+/()%-]*` |
| `aliases`, `brands` | edit/add; `brands` medicine only | list, ≤ 20 / ≤ 40 items, each `clean_name` non-empty, de-duplicated by `key` |
| `category`, `print` | investigation | ≤ 40 / ≤ 30 chars, same character set as `generic` |
| `safety` | only when `owner=True` | bool |
| any other key, or `hide` with data | — | `ValueError` |

`effective_entries` algorithm (the tests pin each line):

```
by_key = key(canonical) -> shipped entry; output starts as shipped order, every touched entry a NEW dict
for row in rows (sorted by entry_key):
  base = by_key.get(row.entry_key)
  safety = base and base.get("safety") is True
  add  : base None -> append built entry; base present -> replace with built entry + flag shipped-changed
  edit : base None -> append built entry (from data) + flag shipped-changed
         safety -> keep base + flag safety-override
         else   -> replace with merged(base, data); flag shipped-changed when entry_sha(base) != row.base_sha
  hide : safety -> keep base + flag safety-override; else drop; flag shipped-changed when base and sha differs
then for each clinic add/edit name N: remove N from other entries' brands/aliases (copies);
  if such an entry has safety -> drop the clinic entry instead + flag safety-override
built medicine entry   = {"canonical": generic, "brands": [name] if key(name) != key(generic) else [], "aliases": data aliases or [],
                          "forms": [], "strengths": [], "clinic": True}
built investigation    = {"canonical": name, "aliases": [...], "category": "", "print": "", "clinic": True} (data overrides)
merged medicine edit   = {**base, "canonical": generic or base canonical, aliases/brands from data when present}
merged investigation   = {**base, aliases/category/print from data when present}
flags sorted by entry_key; one flag per entry_key
```

- [ ] **Step 1: Write the failing tests.** Fixture:

```python
SHIPPED = [
    {"canonical": "Aceclofenac", "aliases": ["aceclofenac"], "brands": ["Zerodol"], "forms": ["Tab."], "strengths": ["100 mg"]},
    {"canonical": "Paracetamol", "aliases": ["paracetamol"], "brands": ["Crocin", "Dolo"], "forms": [], "strengths": ["650 mg"], "safety": True},
]
def row(key, action, data, base_sha=""): return {"entry_key": key, "action": action, "data": data, "base_sha": base_sha}

def test_no_rows_gives_the_shipped_entries_and_no_flags():
    assert O.effective_entries("medicine", SHIPPED, []) == (SHIPPED, [])
def test_add_appends_a_clinic_entry():
    e, f = O.effective_entries("medicine", SHIPPED, [row("zerodol-p", "add", {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"})])
    assert e[-1] == {"canonical": "Aceclofenac + Paracetamol", "brands": ["Zerodol-P"], "aliases": [], "forms": [], "strengths": [], "clinic": True} and f == []
def test_edit_with_current_base_sha_has_no_flag(): ...          # aliases ["acf"] replace; strengths kept ["100 mg"]
def test_edit_with_stale_base_sha_keeps_the_clinic_edit_and_flags_it():
    _, f = O.effective_entries("medicine", SHIPPED, [row("aceclofenac", "edit", {"aliases": ["acf"]}, "stale")])
    assert f == [{"entry_key": "aceclofenac", "reason": "shipped-changed"}]
def test_hide_drops_the_entry(): ...
def test_a_safety_entry_wins_over_edit_and_hide():                # Paracetamol kept unchanged, reason "safety-override"
def test_add_takes_a_name_a_shipped_entry_claims():
    e, _ = O.effective_entries("medicine", SHIPPED, [row("zerodol", "add", {"name": "Zerodol", "generic": "Aceclofenac + Paracetamol"})])
    assert e[0]["brands"] == [] and e[-1]["brands"] == ["Zerodol"]
def test_add_of_a_name_a_safety_entry_claims_is_dropped_and_flagged(): # "Dolo" -> not in output as clinic entry, safety-override
def test_shipped_list_is_never_mutated():                          # deepcopy before; run every case above; compare
def test_investigation_add_and_edit(): ...                         # {"name": "RFT", "category": "Blood"} -> canonical "RFT", clinic True
def test_validate_data_rules():                                   # one assert per table row above, incl. "<b>x</b>" generic -> ValueError,
                                                                   # 21 aliases -> ValueError, {"safety": True} -> ValueError unless owner=True
def test_entry_sha_ignores_key_order():
    assert O.entry_sha({"a": 1, "b": 2}) == O.entry_sha({"b": 2, "a": 1})
```

- [ ] **Step 2:** Run `.venv/bin/python -m pytest -q tests/test_overlay_core.py`. Expected: FAIL (no module).
- [ ] **Step 3:** Implement the four functions in `core/overlay.py` (stdlib + `from . import formulary` lazily inside functions if needed to avoid an import cycle; `formulary` does not import `determinism` at module level, `core/formulary.py:15`).
- [ ] **Step 4:** Run the tests and `tests/test_core_purity.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(overlay): effective_entries with shipped-changed and safety-override flags`.

### Task 3: Request activation and `effective_view`

**Files:**
- Modify: `doctor_dictation/core/overlay.py`
- Test: `tests/test_overlay_core.py`

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class OverlayState: rows: tuple = (); version: str = "0"`; method `rows_for(kind) -> list[dict]`.
  - `state_from_rows(rows: list[dict]) -> OverlayState` — `version` = first 8 hex of sha1 over the sorted `(kind, entry_key, action, json(data, sort_keys), base_sha)` tuples; `"0"` when empty. Content-addressed: two clinics with identical rows share one effective list (correct, same content).
  - `activate(state: OverlayState) -> None`, `active() -> OverlayState` — ContextVar `dd_clinic_overlay`, default empty state (same pattern and docstring warning as `core/formulary.py:166-193`).
  - `effective_view(kind: str, shipped: list[dict]) -> list[dict]` — returns `shipped` itself (same object) when the active state has no rows of `kind`; else the memoised `effective_entries(...)[0]`, keyed `(kind, id(shipped), version)`, storing `shipped` beside it and checking `is`; at most 32 slots, oldest evicted. **This is the hook plan h's `investigations.json` loader calls:** `overlay.effective_view("investigation", catalogue_entries)`.
  - `register_shipped(kind: str, loader: Callable[[], list[dict]]) -> None`, `shipped(kind: str) -> list[dict]` — `[]` for a kind with no loader (investigation until plan h registers its loader).

- [ ] **Step 1: Write the failing tests:** `test_effective_view_is_the_shipped_list_itself_without_rows` (`is`), `test_effective_view_is_one_object_per_version` (`is` across two calls; a new state with one more row gives a different object), `test_version_is_0_when_empty_and_changes_with_any_field`, `test_state_follows_asyncio_to_thread`, `test_two_contexts_see_their_own_view` (`contextvars.copy_context().run`), `test_shipped_of_an_unregistered_kind_is_empty`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. `core/overlay.py` must stay under 500 lines.
- [ ] **Step 4:** Run. Expected: PASS.
- [ ] **Step 5: Commit** `feat(overlay): per-request overlay state and effective_view`.

### Task 4: Race-free lexicon caches (`core/lexmemo.py`)

**Files:**
- Create: `doctor_dictation/core/lexmemo.py`
- Modify: `core/determinism.py:117-126` (`_maps`), `core/surface.py:57-64` (`_hidden_brands`), `core/lasa.py:21`, `:46-85` (`_index`), `core/candidates.py:60-76` (`_rows`), `tests/test_combination_brands.py:132`
- Test: `tests/test_lexmemo.py`

**Interfaces:**
- Produces: `per_lexicon(slot: dict, lex: list, build: Callable[[], T]) -> T` — one `slot.get(id(lex))` read into a local; a hit only when `hit[0] is lex`; else `value = build()`, store `(lex, value)`; at most `MAX_SLOTS = 8` (drop the oldest insertion). Never reads the global twice.

Why: today each cache holds one lexicon and checks then reads its global in two steps. With one list per clinic overlay, two threads can interleave the check and the read (Review Focus 1), and alternating clinics rebuild the O(n²) look-alike index (`lasa.py:57-66`) on every switch.

- [ ] **Step 1: Write the failing tests:** `test_same_list_builds_once`, `test_equal_content_new_list_rebuilds` (identity, not equality), `test_ninth_list_evicts_the_oldest`, and `test_alternating_lexicons_do_not_rebuild` — monkeypatch `D._lexicon_cache` to list A, then B, then A; spy on `surface.surface_map`; assert two builds, and `D._maps()` / `surface._hidden_brands(lex)` / `lasa._index()` / `candidates._rows()` each return values for the current list.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `per_lexicon`; convert the four caches to `_slot: dict = {}` + `per_lexicon`. Change `tests/test_combination_brands.py:132` from `(None, None)` to `{}` (the only test that resets one of these globals).
- [ ] **Step 4:** Run `.venv/bin/python -m pytest -q tests/test_lexmemo.py tests/test_lasa.py tests/test_candidates.py tests/test_combination_brands.py tests/test_determinism.py`. Expected: PASS.
- [ ] **Step 5: Commit** `refactor(core): identity-keyed lexicon caches without the check-then-read race`.

### Task 5: `load_lexicon` returns the effective list; activation and cache keys

**Files:**
- Modify: `core/determinism.py:60-86`, `core/formulary.py:196-205`, `api/formulary.py:30-52`, `api/format.py:101`
- Test: `tests/test_overlay_lexicon.py`

**Interfaces:**
- Consumes: `overlay.effective_view`, `overlay.active`, `overlay.state_from_rows`, `overlay.register_shipped` (Task 3); `db.overlay.list_rows` (Task 1).
- Produces:
  - `determinism.shipped_lexicon() -> list` — today's `load_lexicon` body (still caches in `_lexicon_cache`, so the 15 test lines that monkeypatch `_lexicon_cache` keep working).
  - `determinism.load_lexicon() -> list` — `overlay.effective_view("medicine", shipped_lexicon())`. Plans a and g call it unchanged.
  - `determinism.lexicon_identity() -> str` — `f"{lexicon_version()}+{overlay.active().version}"`. `lexicon_version()` stays the shipped version (health, engine strings: `api/health.py:50`, `api/format.py:112`).
  - `determinism` registers `overlay.register_shipped("medicine", shipped_lexicon)` at import.
  - `api/formulary.load_overlay() -> overlay.OverlayState` — reads `list_rows(conn, kind)` (active rows only, so pending rows never reach `effective_entries`) for both kinds; `sqlite3.Error` → logged, empty state (same fail-safe as `load_layer`, `api/formulary.py:33-38`).
  - `use_clinic_layer` activates both the layer and the overlay in one `asyncio.to_thread` hop; no route changes (`format.py:92`, `:186`, `persistence.py:185`, `stt.py:48`, `rx.py:55` already depend on it).

- [ ] **Step 1: Write the failing tests:**

```python
ADD = {"kind": "medicine", "entry_key": "zerodol-p", "action": "add",
       "data": {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}, "base_sha": ""}

def test_without_overlay_load_lexicon_is_the_shipped_list():
    assert D.load_lexicon() is D.shipped_lexicon()
def test_a_clinic_added_brand_grounds_verified_with_the_clinic_generic():
    overlay.activate(overlay.state_from_rows([ADD]))
    (row,), _ = D.ground_rx([{"name": "Zerodol-P", "strength": ""}], "tab zerodol-p twice daily")
    assert (row["status"], row["lexicon_match"], row["generic"]) == ("verified", "Aceclofenac + Paracetamol", "Aceclofenac + Paracetamol")
def test_a_hidden_entry_reads_unknown(): ...                       # hide "acarbose" -> status "unknown-medicine"
def test_interleaved_threads_never_cross():
    # two states (ADD vs empty); 200 tasks on ThreadPoolExecutor(8), each run in copy_context() of its state;
    # every "with ADD" result is verified, every "empty" result is not "verified" for Zerodol-P
def test_lexicon_identity_changes_with_the_overlay_version(): ...
def test_format_cache_misses_after_a_list_edit(...):
    # multi-clinic TestClient (patterns: tests/test_formulary_routes.py `_offline`, authorship_fixtures.as_user):
    # POST /api/format twice -> second "cached": True; db.overlay.upsert(...) in the clinic DB; POST again -> "cached": False
def test_check_row_route_sees_the_overlay(...): ...               # POST /api/v1/rx/check-row for Zerodol-P -> verified
def test_a_pending_row_does_not_reach_the_lexicon(...): ...       # one record_confirmation in the clinic DB -> Zerodol-P not verified;
                                                                  # a second (other document) -> verified
```

- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement the `determinism` changes; change `formulary._lexicon_twin` to pass `lexicon_identity()` into `_twin` (its `lru_cache` key, `core/formulary.py:196-205`); add `overlay.active().version` to `ckey` at `api/format.py:101` (`f"{slug}:{layer.version}:{overlay.active().version}:{key}:…"`); extend `use_clinic_layer`.
- [ ] **Step 4:** Run the new tests, then the full suite. Expected: all PASS, count = Task 0 count + new tests.
- [ ] **Step 5: Commit** `feat(overlay): load_lexicon returns the clinic's effective medicine list`.

### Task 6: Clinic list routes (`api/lists.py`)

**Files:**
- Create: `doctor_dictation/api/lists.py`
- Modify: `core/overlay.py` (add `screen_rows`), `api/app.py:80` (router tuple)
- Test: `tests/test_lists_routes.py`, `tests/test_overlay_core.py`

**Interfaces:**
- Consumes: Tasks 1–3; `db.formulary.list_active` (`db/formulary.py:26`); `authorship.identity`; `policy.can`; `dbmod.log_audit`.
- Produces:
  - `overlay.screen_rows(kind, shipped, rows, learned: list[dict], pending: list[dict] = ()) -> list[dict]`, pure. Each item: `{"entry_key", "badge": "shipped"|"clinic-added"|"clinic-edited"|"hidden"|"learned", "flag": ""|"shipped-changed"|"safety-override", "entry": <effective entry, or the shipped entry for hidden>, "shipped": <shipped entry or None>, "base_sha_now": <entry_sha(shipped) or "">, "formulary_id": <int or None>, "pending": None | {"count": n, "threshold": THRESHOLD, "action", "data"}}`. `pending` comes from `list_rows(conn, kind, pending=True)`: it is attached to the item with the same `entry_key` (a shipped entry a doctor is re-generic-ing), or makes its own item (badge `"learned"`, `entry` built from its data) when no item has that key. Hidden rows are listed (so they can be reset). Learned rows: active `clinic_formulary` names whose key is not a canonical, brand or alias in the effective list; `entry = {"canonical": generic or "", "brands": [name]}`. Order: flagged first, then by `entry_key`.
  - `GET /api/v1/lists/{kind}` → `{"kind", "items": [...], "flags": <count>, "pending": <count>}` (reads active and pending rows). `kind` not in `KINDS` → 404.
  - `POST /api/v1/lists/{kind}/changes`, body `{"op": "add"|"edit"|"hide"|"reset"|"keep-mine"|"take-new"|"approve", "entry_key": str (1–60), "data": dict = {}}` (body, not path: keys contain `/` and spaces). Answers `{"item": <screen row after the change>}`.

| op | Precondition | Effect | Audit `action` |
|---|---|---|---|
| add | key not a shipped canonical (409 "already in the shared list: edit it") | `upsert(add, validate_data(...), "", "admin")`; `entry_key` must equal `key(data.name)` (400) | `list.add` |
| edit | shipped entry or an existing clinic add (404 otherwise) | on a shipped entry: `upsert(edit, data, entry_sha(shipped))`; on a clinic add: `upsert(add, data, "")` | `list.edit` |
| hide | shipped entry (404) | `upsert(hide, {}, entry_sha(shipped))` | `list.hide` |
| reset | an overlay row (404) | `reset` ("Reset to default") | `list.reset` |
| keep-mine | row flagged `shipped-changed` (409) | `upsert` same action and data, `base_sha = entry_sha(current shipped)` | `list.keep-mine` |
| take-new | row flagged (409) | `reset` | `list.take-new` |
| approve | a pending row (404) | `db.overlay.approve` ("Approve now"; live at once) | `list.approve` |

  Every admin op writes through `upsert` with source `"admin"`, so an admin edit of a pending key replaces the doctor's value and is live at once. An `edit` with `generic` on a shipped medicine is allowed (owner answer Q17) and audited like any edit.

  Audit: `entity = "list." + kind`, `entity_id = entry_key`, `detail = {"before": <row or None>, "after": <data or None>}`. Permission as `api/formulary.py:86-90`: no identity in multi-clinic mode → 401; `policy.can(ident, "formulary.manage")` false → 403. Validation errors → 400 `{"error": <ValueError text>}`. `sqlite3.Error` → 503 `{"error": "try again"}` (`api/formulary.py:69-70`).

- [ ] **Step 1: Write the failing tests:** `screen_rows` badge cases (one per badge, plus a learned name already added by the overlay is not listed twice); routes: `test_add_then_list_shows_clinic_added`, `test_edit_of_a_shipped_entry_stores_its_sha`, `test_hide_then_reset_restores_shipped`, `test_keep_mine_clears_the_flag` (store a row with `base_sha="stale"`, op keep-mine → flag ""), `test_take_new_removes_the_row`, `test_pending_row_is_listed_with_its_count` (one `record_confirmation` → item `pending == {"count": 1, "threshold": 2, …}`, not in the lexicon), `test_approve_makes_it_live_and_audits` (`list.approve` row; `GET` shows no `pending`; approve again → 404), `test_every_write_is_audited` (one `audit_log` row per op with the action names above), `test_a_doctor_gets_403_and_nothing_changes` (pattern: `tests/test_team_admin_only.py:20`), `test_bad_input_is_400_and_nothing_written` (unknown op → 422; 21 aliases → 400; `entry_key` ≠ `key(name)` → 400; add of "aceclofenac" → 409), `test_other_clinic_cannot_see_or_reset` (pattern: `tests/test_isolation_formulary.py`).
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement `screen_rows` and the router; register it in `api/app.py:80`.
- [ ] **Step 4:** Run the new tests plus `tests/test_formulary_routes.py tests/test_isolation_formulary.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(lists): clinic list routes with audit and formulary.manage`.

### Task 7: Medicines and Investigations tabs (read, filter, learned Remove)

**Files:**
- Create: `frontend/clinlists.js`
- Modify: `frontend/team.js:69-175` (move out `buildMeds`, `renderMeds`, `loadNames`, `loadMeds`, `focusAfterRemoval`, `removeMed`; tabs become People | Medicines | Investigations), `frontend/team.css`, `frontend/index.html:12`, `:267` (add `<script src="clinlists.js?v=1">` before `team.js`; `team.js?v=4`, `team.css?v=3`)
- Modify: `tests/team_medicines_fakedom.js` (load `clinlists.js` before `team.js`; answer `GET /api/v1/lists/{kind}`), `tests/test_frontend_team_medicines.py`
- Test: `tests/test_frontend_clinic_lists.py`

**Interfaces:**
- Consumes: `GET /api/v1/lists/{kind}` (Task 6); `DELETE /api/v1/formulary/{id}` (unchanged).
- Produces: `window.ClinicLists = { buildPanel(kind) -> Element, load(kind) -> Promise<void>, rerender(kind) -> void }`, used by team.js and Task 8. Element ids: Medicines keeps `teamTabMeds`, `teamMeds`, `teamMedRows`, `teamMedLive`, `teamMedEmpty` (existing tests find them); Investigations uses `teamTabTests`, `teamTests`, `teamTestRows`, `teamTestLive`, `teamTestEmpty`. Filter: `<input type="search">` plus a "Only changed or flagged" checkbox, client-side.

Badge text (exact copy): `shipped` "Shared list"; `clinic-added` "Added by clinic"; `clinic-edited` "Edited by clinic"; `hidden` "Hidden"; `learned` "Learned". Flag text: `shipped-changed` "Updated in the shared list"; `safety-override` "Safety entry: the shared list is used". Pending marker (item `pending` set): "Pending (n of 2)" (`n` = `pending.count`, `2` = `pending.threshold`), shown in the Source column with the pending value (e.g. generic) beside it; the "Only changed or flagged" filter keeps pending rows. Medicine columns: Medicine | Generic | Brands | Source | Actions. Investigation columns: Test | Print | Category | Source | Actions.

- [ ] **Step 1: Write the failing tests:** static pins (`clinlists.js` has no `innerHTML`, no external host, uses `"/api/v1/lists/"`; `index.html` loads `clinlists.js?v=` before `team.js?v=`, and `team.js?v=4`); fakedom: `test_a_doctor_page_has_no_list_tabs`, `test_admin_sees_three_tabs_and_medicines_lists_badges` (rows show "Shared list", "Added by clinic", "Learned"), `test_flagged_rows_come_first_with_their_text`, `test_pending_row_shows_pending_1_of_2`, `test_filter_narrows_rows_without_a_new_request` (calls count unchanged), `test_learned_row_remove_keeps_todays_wording_and_focus` (move the existing remove/focus/stale-load assertions; keep every behaviour assertion, update only column and text pins).
- [ ] **Step 2:** Run `.venv/bin/python -m pytest -q tests/test_frontend_clinic_lists.py tests/test_frontend_team_medicines.py tests/test_frontend_team.py`. Expected: FAIL.
- [ ] **Step 3:** Implement `clinlists.js`; slim `team.js` to tab wiring (check `wc -l frontend/team.js` < 500, expected about 260).
- [ ] **Step 4:** Run the same command plus `tests/test_frontend_dates.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(team): Medicines and Investigations tabs list the clinic's effective lists`.

### Task 8: Edit, add, hide, reset, Keep mine / Take new on the list tabs

**Files:**
- Create: `frontend/listedit.js`
- Modify: `frontend/clinlists.js`, `frontend/team.css`, `frontend/index.html` (`listedit.js?v=1` before `clinlists.js`; `clinlists.js?v=2`, `team.css?v=4`)
- Test: `tests/test_frontend_clinic_lists.py`, `tests/team_medicines_fakedom.js` (answer `POST /api/v1/lists/{kind}/changes`)

**Interfaces:**
- Consumes: `POST /api/v1/lists/{kind}/changes` (Task 6).
- Produces: `window.ListEdit.open(kind, item | null, {owner: bool}) -> Promise<{op, entry_key, data} | null>` — a `<dialog>` form; medicine fields Name, Generic, Aliases, Brands (comma-separated); investigation fields Name, Aliases, Category, Print; Safety checkbox only when `owner`. Name is read-only on edit. Cancel resolves `null`. Task 11 reuses it.

Row actions by state (exact labels): shipped → Edit, Hide; clinic-added → Edit, Reset to default; clinic-edited → Edit, Reset to default; hidden → Reset to default; learned → Edit, Remove; flag `shipped-changed` → Keep mine, Take new; flag `safety-override` → Reset to default; item with `pending` → Approve now (posts `{"op": "approve", "entry_key", "data": {}}`, no confirm; live announces "Approved Zerodol-P."), plus Edit (an admin edit replaces the pending value and is live at once). Panel header: "Add a medicine" / "Add a test". Hide and Reset ask `window.confirm` first. A 4xx answer shows the server `error` in `#teamError` and reloads the list (pattern: `team.js:274-278`). After a change the list reloads and `#teamMedLive` / `#teamTestLive` announces it (e.g. "Hidden Acarbose.").

- [ ] **Step 1: Write the failing tests:** one fakedom test per action asserting the exact POST body (e.g. Hide on Acarbose → `{"op": "hide", "entry_key": "acarbose", "data": {}}`), the confirm text for Hide and Reset, Keep mine / Take new only on flagged rows, Approve now only on pending rows (exact POST body above), a learned row's Edit posts `op "add"` with its name and typed generic, a 409 shows the server text, no `innerHTML` in `listedit.js`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep `clinlists.js` and `listedit.js` each under 500 lines.
- [ ] **Step 4:** Run the frontend tests. Expected: PASS.
- [ ] **Step 5: Commit** `feat(team): edit, hide, add and reset on the clinic lists`.

### Task 9: Owner gate, pending store and export API

**Files:**
- Modify: `doctor_dictation/policy.py` (add `is_owner`), `doctor_dictation/api/auth.py:100-106` (add `"is_owner"`), `.env.example` (document `OWNER_USERNAMES`)
- Create: `doctor_dictation/api/owner_lists.py`; register in `api/app.py:80`
- Test: `tests/test_owner_lists.py`

**Interfaces:**
- Consumes: `overlay.shipped(kind)`, `overlay.validate_data(..., owner=True)`, `overlay.entry_key_of`, `promotion.write_atomic` (`promotion.py:87-95`), `scope.data_root`.
- Produces:
  - `policy.is_owner(user) -> bool` — `user` not None and `user.username.casefold()` in the comma-separated, stripped, casefolded `OWNER_USERNAMES`; unset or empty → False.
  - `PENDING_PATH = data_root() / "owner" / "list-changes.json"`, shape `{"medicine": [change], "investigation": [change]}`, one change per `entry_key`; read/write under a `threading.Lock`.
  - `GET /api/v1/owner/lists/{kind}` → `{"items": [{"entry_key", "entry": <shipped>, "pending": <change or None>}], "pending": [<changes for keys not in shipped (adds)>]}`.
  - `POST /api/v1/owner/lists/{kind}/changes`, body `{"op": "add"|"edit"|"drop", "entry_key", "data"}` — `add`: key not shipped (409); `edit`: key shipped (404), no `generic`/`name` keys; `drop` removes the pending change. Audited in the owner's clinic `audit_log` as `owner-list.<op>`.
  - `GET /api/v1/owner/lists/{kind}/export` → the contract file `{"kind", "changes": [{"action", "entry_key", "data"}]}`, `Content-Disposition: attachment; filename="list-changes-<kind>-<YYYY-MM-DD>.json"`. Exporting does not clear the pending list (the owner drops changes after the deploy).
  - Every owner route: single-database mode or not an owner → 404 `{"error": "not found"}` (does not reveal the screen).

- [ ] **Step 1: Write the failing tests:** `test_is_owner_reads_the_env` (unset, `" Naren , x"` matches `naren`), `test_non_owner_and_single_mode_get_404`, `test_owner_edit_with_safety_is_pending_and_exported` (export body equals `{"kind": "medicine", "changes": [{"action": "edit", "entry_key": "paracetamol", "data": {"safety": True}}]}`), `test_add_of_a_shipped_key_is_409`, `test_edit_may_not_change_the_generic` (400), `test_drop_removes_the_change`, `test_pending_survives_a_new_app` (new `create_app()` reads the file), `test_pending_write_is_atomic` (monkeypatch `os.replace` to raise → old file intact), `test_me_says_is_owner`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run the tests plus `tests/test_auth_routes.py tests/test_policy_audit.py`. Expected: PASS.
- [ ] **Step 5: Commit** `feat(owner): shared-list review store and export, OWNER_USERNAMES gate`.

### Task 10: `apply-list-changes` operator command

**Files:**
- Create: `doctor_dictation/listchanges.py`
- Modify: `doctor_dictation/admin.py:208-209` (`listchanges.register(sub, COMMANDS)`, like `promotion.register`)
- Test: `tests/test_listchanges.py`

**Interfaces:**
- Consumes: `build.load_drugs`, `load_seed`, `layered_seed`, `compute_merged`, `sort_entries`, `serialize`, `write_drugs`, `check_source`, `do_check`, `DEFAULT_SEED` (`core/lexicon/build.py:52-260`); `overlay.validate_data(..., owner=True)`, `overlay.entry_key_of`.
- Produces:
  - `read_changes(path) -> tuple[str, list[dict]]` — validates the whole file first; `ValueError` names the first bad change by index.
  - `plan_medicines(changes, seed: list[dict], current: dict) -> tuple[list[dict], dict]` — `(new seed, new drugs data)`, in memory. `add`: a new complete entry (Task 2 "built medicine entry" without `clinic`), refused when its name is already a canonical, brand or alias. `edit`: the shipped entry with the data applied; seed entry replaced (or the entry copied in from `drugs.json` when only `imported.json` has it). New seed sorted with `sort_entries`, keys sorted, as `seed_extra.json` is today. Then `compute_merged(current, layered_seed-equivalent of the new seed)`; every intended entry must come out byte-equal, else `ValueError("… imported.json re-adds brand X; edit imported.json by hand")`.
  - `plan_investigations(changes, catalogue: dict) -> dict` — `investigations.json` (plan h's format), entries sorted by canonical key, `version` via `build.bump_minor` when changed. File missing → `ValueError("investigations.json does not exist yet (plan h)")`.
  - CLI: `python -m doctor_dictation.admin apply-list-changes <file> [--confirm]`. Without `--confirm`: prints the plan, writes nothing, exit 2. With it: writes `seed_extra.json` then `drugs.json` (with one `sources` record `{"id": "admin-list-<first 8 hex of the file's sha256>", "name": "app admin list review", "licence": "authored by the app admin; no third-party data", "input_sha256", "merged_at"}` through `check_source`), then runs `do_check(DEFAULT_SEED)` and exits 1 if it fails. No change → "no change", exit 0, nothing rewritten. Invalid file → `error: …`, exit 1, nothing written. Ends by printing "now commit drugs.json and seed_extra.json, then deploy".

- [ ] **Step 1: Write the failing tests** on tmp copies (fixture pattern: `tests/test_lexicon_import.py:26-31`, monkeypatching `build.DRUGS_JSON`, `build.IMPORTED_JSON`, `build.DEFAULT_SEED`): `test_dry_run_writes_nothing` (bytes unchanged, exit 2), `test_confirm_adds_the_entry_bumps_the_minor_and_records_a_source` (version `x.y.z` → `x.(y+1).0`, one new `sources` id `admin-list-…`, `do_check(DEFAULT_SEED) == 0`), `test_edit_sets_safety_and_check_stays_in_sync`, `test_rerun_is_no_change`, `test_invalid_files_write_nothing` (parametrised: action "hide", unknown key, missing generic, `entry_key` ≠ key of name, edit of an unknown canonical, not JSON), `test_an_edit_that_imported_json_would_undo_is_refused`, `test_investigations_without_a_catalogue_is_an_error`, `test_admin_help_lists_the_command`.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement. Keep `listchanges.py` under 500 lines.
- [ ] **Step 4:** Run the tests plus `tests/test_combination_brands.py::test_build_check_is_in_sync tests/test_admin.py`. Expected: PASS; the real `drugs.json` is unchanged (`git diff --stat doctor_dictation/core/lexicon` empty).
- [ ] **Step 5: Commit** `feat(admin): apply-list-changes folds an exported changes file into the shipped lists`.

### Task 11: Owner "Shared lists" tab

**Files:**
- Create: `frontend/ownerlists.js`
- Modify: `frontend/team.js` (fourth tab "Shared lists" only when `/api/v1/auth/me` says `is_owner`), `frontend/index.html` (`ownerlists.js?v=1` before `team.js`; `team.js?v=5`), `tests/team_medicines_fakedom.js` (owner routes; `me.is_owner`)
- Test: `tests/test_frontend_owner_lists.py`

**Interfaces:**
- Consumes: owner routes (Task 9); `ListEdit.open(kind, item, {owner: true})` (Task 8).
- Produces: `window.OwnerLists = { buildPanel() -> Element, load(kind) }`. Panel: Medicines / Investigations switch, filter, rows with "Pending change" marker, Edit, Add, "Discard change", and "Download changes (N)" which fetches the export and saves it through a `Blob` + `<a download>`. Hint copy (exact): "Changes here do not change any clinic's list. Download the file and give it to the operator to apply, commit and deploy."

- [ ] **Step 1: Write the failing tests:** `test_no_shared_lists_tab_without_is_owner`, `test_owner_edit_posts_the_change_with_safety`, `test_download_uses_the_export_route_and_a_blob`, `test_discard_posts_drop`, static: no `innerHTML`, no external host.
- [ ] **Step 2:** Run. Expected: FAIL.
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** Run all frontend tests and the full suite. Expected: PASS.
- [ ] **Step 5: Commit** `feat(owner): Shared lists tab with download of the changes file`.

---

## Self-review notes

- Spec coverage: learning threshold — migration 010 columns, active rule, `record_confirmation`, `approve` (1), pending kept out of the lexicon (5), "Pending (n of 2)" + Approve now (6–8); overlay table and merge (Tasks 1–3), shipped-changed / safety-override (2, 6, 8), `load_lexicon` under overlay and caches (4, 5), investigation kind and plan h hook (2, 3), clinic screens with badges and all actions (6–8), audit + `formulary.manage` (6), owner review/export (9, 11), operator fold-in with `sources` + version bump (10), learned rows (6–8).
- Not done here: the `investigations.json` catalogue and loader (plan h registers `overlay.register_shipped("investigation", …)` and calls `effective_view`); doctor-generic and remembered-test overlay writes (plans g, h call `db.overlay.record_confirmation` on save, never `upsert`); removing a shared entry through the export (manual repo edit).

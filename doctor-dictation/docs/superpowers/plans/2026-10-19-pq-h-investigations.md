# PQ-h Investigations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ground every investigation like a medicine: a shipped catalogue merged with the clinic overlay, a "was it dictated?"
check, item objects with a status, a red item that blocks Save, the decision-4 print rule, and an editable sheet list with
"Remember for this clinic".

**Architecture:** A new pure module `core/investigations.py` owns the catalogue lookup, the item shape, the dictated check
(reusing `prose` word matching), print text and the Save screen. The API activates the clinic's effective list per request
(a ContextVar, like `formulary.activate`), converts LLM strings to items after validation, checks them in the response
(never in the cache), gates Save with a 409, and records a confirmation for ticked items. A new page module
`frontend/ixlist.js` renders and reads the items; `app.js` only gets hooks.

**Tech Stack:** Python 3.12, FastAPI, SQLite (plan f's `clinic_overlay`), stdlib `difflib`/`csv`; vanilla JS under node fake-DOM tests.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` (section 3; "Decisions made" 2, 3, 4 and
"clinic lists (overlay)"), with the shared contract in `docs/superpowers/plans/2026-10-19-pq-00-index.md` ("Investigations (plan h)") and "Learning threshold (owner rule, 2026-10-19; plans f, g, h)".

**Owner answers 2026-10-19:** Q23 the owner reviews `investigations-draft.csv`; it blocks only Task 1 Step 6 (catalogue).
Q24 the bracket shows the full name (`print_text`). Q25 a remembered test with no category is fine (set on plan f's list
screen). Q26 the offline demo stays as planned: only dictated tests, with `DEMO_WARNING`.

## Global Constraints

- Item shape `{"text", "canonical", "status", "source"}`; status `"verified"` | `"new"` | `"not-dictated"` | `""`; source `"dictated"` | `"doctor"`. A plain string still loads as `status ""` (unchecked).
- A test not heard in the dictation (red, `not-dictated`) blocks Save (409, like `screen_unverified`) until kept (source becomes `"doctor"`) or removed; `new` (amber) warns only.
- A hand-typed item (source `"doctor"`) is never `not-dictated`.
- Print: `text`, plus ` (canonical)` when the two differ case-insensitively; an unknown test prints `text` alone ("RFT (Renal Function Test)"; "Renal Function Test" when dictated in full).
- A sheet edit changes that prescription only. A ticked "Remember for this clinic" calls `db/overlay.record_confirmation` (kind `'investigation'`), never `upsert`; the row is live only after `formulary.THRESHOLD` (2) saves in different prescriptions with the same data (different data restarts the count). The prescription always prints what the doctor entered.
- Everything learned stays in the clinic's own `app.db`; never write to the shipped `investigations.json` at runtime.
- The LLM output schema stays `"investigations": ["string"]`; strings become items after `validate_structured`.
- Files stay under 500 lines (`tests/test_file_sizes.py`); `frontend/app.js` (1251 lines) gets hooks only. `core/` stays stdlib-only (`tests/test_core_purity.py`).
- Bump `?v=` on every changed static file; tests pin some (`tests/test_frontend_dates.py:106-108`).
- Tests run with `.venv/bin/python -m pytest`; the autouse `DB_PATH` fixture keeps the dev DB safe. No commit without the owner's word.

## Review Focus

1. **The AI writes the full name of a dictated short code** ("RFT" said, "Renal Function Test" written): must be `verified`, not red. Test in Task 3.
2. **Speech spells a code as letters** ("r f t", "R.F.T.", "usg k u b"): must count as heard. Test in Task 3.
3. **An old saved document with plain-string investigations** is reopened, printed and re-saved: loads, prints as before, never blocks. Tests in Tasks 6 and 8.
4. **A spoken correction that does not mention tests**: every item keeps its status and source, including a red item the doctor already kept. Test in Task 5.
5. **A forged or stale canonical from the page** (`"<b>x</b>"`, or a name the catalogue does not give): the server regrades it and print escapes it. Tests in Tasks 6 and 8.

---

### Task 0: Preflight (no code)

- [ ] **Step 1:** Re-read the files this plan edits; plans a–g ran first and changed them: `core/determinism.py` (`validate_structured`, :356-400), `core/prose.py`, `core/fallback.py`, `api/format.py` (`_answer` :85-89, `correct` :186-228), `api/persistence.py` (`DocumentCreate` :116-121, gate :208-221, `learn_from_save` call :319), `pdf/sheet.py` (:21-25, :318-319), `frontend/app.js` (`serializeForm` :646-663, `renderSheet` :916, delete/undo :765-815, 409 branch :1065-1075), `frontend/index.html` (:111-112, :255-267).
- [ ] **Step 2:** Confirm plan f shipped: `db/overlay.py` `record_confirmation`/`list_rows` (active rows only, `confirm_count`, `clinic_overlay_docs`), `formulary.THRESHOLD`, `core/overlay.py` `effective_entries`, and how a shipped entry's `entry_key` and an `add` row's entry are built for kind `'investigation'`. If f keys investigation entries by anything other than `investigations.key(canonical)` (Task 2), or exposes a sha helper for `base_sha`, use f's names and note it in the task commit.
- [ ] **Step 3:** Confirm plan d's prompt rule in `SYSTEM_PROMPT` and `CORRECTION_INSTRUCTION` ("Copy each test as dictated. Never add a test that was not dictated. If none, return []."). This plan does not edit prompts.
- [ ] **Step 4:** Confirm plan e's inline list in `pdf/sheet.py` calls `investigations.print_text` for items (index contract). If it does, Task 8 Step 3 is a no-op.
- [ ] **Step 5:** Confirm the owner reviewed `docs/working/2026-10-19-prescription-quality/investigations-draft.csv` and removed the `NOT REVIEWED` first line (Q23). Do not start Task 1 Step 6 without it; nothing else waits on it.
- [ ] **Step 6:** Baseline: `.venv/bin/python -m pytest -q` — Expected: all pass.

---

### Task 1: Catalogue build (CSV → `investigations.json`)

**Files:**
- Create: `doctor_dictation/core/lexicon/build_investigations.py`
- Create: `doctor_dictation/core/lexicon/investigations.json` (generated, Step 6)
- Test: `tests/test_investigations_build.py`

**Interfaces:**
- Produces: `key(text) -> str`; `rows_from_csv(text: str, allow_draft: bool = False) -> list[dict]`; `build(csv_path: Path, out_path: Path, version: str) -> dict` (returns the written document); CLI `python -m doctor_dictation.core.lexicon.build_investigations <csv> [--version X.Y.Z]` writing `doctor_dictation/core/lexicon/investigations.json`.
- JSON shape (contract): `{"version": str, "entries": [{"canonical", "aliases": [str], "category", "print"}]}`; an optional `"safety": true` column value is copied when present.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_row_becomes_an_entry_with_split_aliases():
    csv_text = "canonical,aliases,category,print\nRenal Function Test,rft;kft; kidney function test ,Blood,RFT\n"
    assert rows_from_csv(csv_text) == [{"canonical": "Renal Function Test", "aliases": ["rft", "kft", "kidney function test"],
                                        "category": "Blood", "print": "RFT"}]

def test_hash_lines_are_skipped_but_an_unreviewed_draft_is_refused():
    body = "canonical,aliases,category,print\nESR,esr,Blood,ESR\n"
    assert rows_from_csv("# reviewed 2026-10-20\n" + body)[0]["canonical"] == "ESR"
    with pytest.raises(ValueError, match="NOT REVIEWED"):
        rows_from_csv("# DRAFT - NOT REVIEWED\n" + body)
    assert rows_from_csv("# DRAFT - NOT REVIEWED\n" + body, allow_draft=True)

def test_a_name_claimed_by_two_entries_is_refused():
    clash = "canonical,aliases,category,print\nA Test,abc,Blood,A\nB Test,ABC,Blood,B\n"
    with pytest.raises(ValueError, match="abc"):
        rows_from_csv(clash)

def test_blank_canonical_or_unknown_category_is_refused():   # categories: the 10 of the draft CSV
    for bad in (",x,Blood,X", "T,x,Bloods,T"):
        with pytest.raises(ValueError):
            rows_from_csv("canonical,aliases,category,print\n" + bad + "\n")

def test_the_draft_csv_builds(tmp_path):     # the reviewed file must stay valid
    doc = build(DRAFT_CSV, tmp_path / "ix.json", "1.0.0")   # DRAFT_CSV read with allow_draft only until review lands
    assert 140 <= len(doc["entries"]) <= 200 and doc["version"] == "1.0.0"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations_build.py` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** `rows_from_csv` and `build` in `build_investigations.py`. Uniqueness uses `investigations.key` semantics (casefold; `&` → ` and `; non-alphanumerics → space; collapse), over canonical + aliases + print of every entry; a repeat inside one entry is deduplicated, across entries it is an error naming the key. `CATEGORIES = ("Blood", "Urine", "Stool", "Microbiology", "Hormones", "Tumour markers", "Imaging", "Cardiac", "Urology", "Other")`. Refuse when any `#` line contains `NOT REVIEWED` unless `allow_draft`. Write JSON with `ensure_ascii=False, indent=1`, entries in CSV order. Define `key(text) -> str` here (the one copy of the rule); Task 2's `investigations.key` delegates to it.
- [ ] **Step 4: Run** the test file — Expected: PASS.
- [ ] **Step 5: Commit** (ask the owner first): `git add doctor_dictation/core/lexicon/build_investigations.py tests/test_investigations_build.py` / `feat(pq-h): investigation catalogue builder`.
- [ ] **Step 6:** After the owner's review, run `.venv/bin/python -m doctor_dictation.core.lexicon.build_investigations docs/working/2026-10-19-prescription-quality/investigations-draft.csv --version 1.0.0`; commit `investigations.json` separately (`data(pq-h): reviewed investigation catalogue v1.0.0`).

---

### Task 2: Item model, catalogue lookup, print text

**Files:**
- Create: `doctor_dictation/core/investigations.py`
- Test: `tests/test_investigations.py`

**Interfaces:**
- Produces (all in `doctor_dictation/core/investigations.py`):
  - `CATALOGUE_PATH: Path` (`core/lexicon/investigations.json`); `STATUSES = ("verified", "new", "not-dictated", "")`; `SOURCES = ("dictated", "doctor")`; `TEXT_CHARS = 200`; `QUALIFIERS = ("repeat", "follow up", "followup")`.
  - `key(text) -> str` — the Task 1 rule.
  - `shipped() -> list[dict]` — cached entries of the JSON; `[]` on a missing/bad file (like `determinism.load_lexicon`, :60-71).
  - `activate(entries: list[dict]) -> None`; `entries() -> list[dict]` — the active clinic's effective entries (ContextVar), else `shipped()`.
  - `lookup(text: str) -> dict | None` — the entry whose canonical, alias or print equals `key(text)`, retried once with a leading `QUALIFIERS` word stripped; exact only, never fuzzy.
  - `coerce_items(values) -> list[dict]` — strings → `{"text": s, "canonical": "", "status": "", "source": "dictated"}`; dicts keep known fields, unknown status → `""`, unknown source → `"dictated"`, non-str canonical → `""`; text whitespace-collapsed and cut to `TEXT_CHARS`; blank text and other types dropped. Never mutates.
  - `flatten(form: dict) -> dict` — shallow copy whose `investigations` is the list of item texts (for the correction LLM and `ops`).
  - `print_text(item: str | dict) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
CAT = [{"canonical": "Renal Function Test", "aliases": ["rft", "kft"], "category": "Blood", "print": "RFT"},
       {"canonical": "Ultrasound Kidneys Ureters and Bladder", "aliases": ["usg kub"], "category": "Imaging", "print": "USG KUB"}]

def test_lookup_is_exact_on_any_name_with_punctuation_and_a_qualifier_ignored():
    activate(CAT)
    assert lookup("R.F.T")["canonical"] == "Renal Function Test" and lookup("kft")["print"] == "RFT"
    assert lookup("USG-KUB")["print"] == "USG KUB" and lookup("Repeat USG KUB")["print"] == "USG KUB"
    assert lookup("RFTs") is None and lookup("") is None          # never fuzzy

def test_without_an_active_clinic_list_the_shipped_catalogue_is_used(monkeypatch, tmp_path):
    p = tmp_path / "ix.json"; p.write_text(json.dumps({"version": "t", "entries": CAT}))
    monkeypatch.setattr(I, "CATALOGUE_PATH", p); monkeypatch.setattr(I, "_shipped_cache", None)
    assert I.entries() == CAT

def test_legacy_strings_and_bad_items_coerce_safely():
    got = coerce_items(["CBC", " ", 5, {"text": "  RFT ", "status": "bogus", "source": "x", "canonical": 3},
                       {"text": "", "status": "verified"}, {"text": "x" * 300}])
    assert got[0] == {"text": "CBC", "canonical": "", "status": "", "source": "dictated"}
    assert got[1] == {"text": "RFT", "canonical": "", "status": "", "source": "dictated"}
    assert len(got) == 3 and len(got[2]["text"]) == TEXT_CHARS
    assert coerce_items(None) == [] and coerce_items("CBC") == []

def test_print_text_follows_decision_4():
    assert print_text({"text": "RFT", "canonical": "Renal Function Test"}) == "RFT (Renal Function Test)"
    assert print_text({"text": "renal function test", "canonical": "Renal Function Test"}) == "renal function test"
    assert print_text({"text": "Uroflow at home", "canonical": ""}) == "Uroflow at home"
    assert print_text("CBC") == "CBC" and print_text(None) == ""

def test_key_agrees_with_the_builder():
    from doctor_dictation.core.lexicon import build_investigations as B
    for s in ("Urine C&S", "S. Creatinine", "TLC/DC", "  X-ray  KUB "):
        assert key(s) == B.key(s)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations.py` — Expected: FAIL (module not found).
- [ ] **Step 3: Implement** the module. The lookup index (key → entry) is cached per `entries()` list identity, like `determinism._maps` (:117-126). `key` delegates to `build_investigations.key` (both stdlib; core may import `core.lexicon`).
- [ ] **Step 4: Run** the test file plus `tests/test_core_purity.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(pq-h): investigation items, catalogue lookup and print text`.

---

### Task 3: "Was it dictated?" check

**Files:**
- Modify: `doctor_dictation/core/prose.py:23-45` (extract helpers; `unheard` behaviour unchanged)
- Modify: `doctor_dictation/core/investigations.py`
- Test: `tests/test_investigations.py`, existing `tests/test_sections_prose.py`

**Interfaces:**
- Produces in `prose.py`: `heard_words(*transcripts) -> tuple[set, list, int]` (heard words, sorted non-numeric pool, said negations) and `missing_words(text: str, heard: tuple[set, list, int], min_word: int = MIN_WORD, frame: frozenset = FRAME) -> list[str]` — the body of the inner loop at :30-42. `unheard` calls both.
- Produces in `investigations.py`: `IX_FRAME: frozenset` (`FRAME` plus `of and the for with in on to at or test tests level levels serum report repeat follow up advised advise done study profile scan`); `heard(text: str, entry: dict | None, *transcripts) -> bool`; `check_items(values, *transcripts) -> list[dict]` (new dicts, coerced first).

Rules for `check_items`, per item:

| source | heard | in `lookup` | status | canonical |
|---|---|---|---|---|
| doctor | (not checked) | yes / no | verified / new | entry canonical / item canonical |
| dictated | no | — | not-dictated | entry canonical or "" |
| dictated | yes | yes / no | verified / new | entry canonical / "" |

`heard` is true when (a) any canonical, alias or print of `entry`, as whole words, is in a transcript, or (b) `missing_words(text, …, min_word=2, frame=IX_FRAME)` is empty. Both sides first join runs of 2+ single-letter words ("r f t" → "rft").

- [ ] **Step 1: Write the failing tests**

```python
def test_a_dictated_short_code_written_in_full_is_verified():                 # Review Focus 1
    activate(CAT)
    [i] = check_items(["Renal Function Test"], "advise rft and review")
    assert (i["status"], i["canonical"], i["source"]) == ("verified", "Renal Function Test", "dictated")

def test_letters_spelled_by_speech_count_as_heard():                          # Review Focus 2
    activate(CAT)
    assert [i["status"] for i in check_items(["RFT", "USG KUB"], "get r f t and usg k u b done")] == ["verified", "verified"]

def test_an_invented_test_is_red_and_a_heard_unknown_one_is_amber():
    activate(CAT)
    got = check_items(["Brain impulses", "ECG", "Uroflow at home"], "do uroflow at home, rft")
    assert [i["status"] for i in got] == ["not-dictated", "not-dictated", "new"]   # "ECG" was never said

def test_a_doctor_item_is_never_red():
    activate(CAT)
    got = check_items([{"text": "ECG", "source": "doctor"}, {"text": "kft", "source": "doctor"}], "nothing said")
    assert [(i["status"], i["canonical"]) for i in got] == [("new", ""), ("verified", "Renal Function Test")]

def test_check_items_never_mutates_its_input():
    items = [{"text": "RFT", "canonical": "", "status": "", "source": "dictated"}]
    check_items(items, "rft"); assert items[0]["status"] == ""
```

Existing `tests/test_sections_prose.py:70-99` must still pass unchanged.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations.py tests/test_sections_prose.py` — Expected: new tests FAIL, prose tests PASS.
- [ ] **Step 3: Implement** the two `prose` helpers (move code, no behaviour change), then `IX_FRAME`, `heard`, `check_items`.
- [ ] **Step 4: Run** the same command — Expected: all PASS.
- [ ] **Step 5: Commit** `feat(pq-h): was-it-dictated check for investigations`.

---

### Task 4: Format path: strings → items, checked in the response; clinic list activation; demo fallback labelled

**Files:**
- Modify: `doctor_dictation/core/determinism.py:364-381` (investigations through `coerce_items`, same count cap and warning text)
- Modify: `doctor_dictation/api/format.py:85-89` (`_answer`), `:92`, `:111`, `:171` (route dependency; demo warning)
- Modify: `doctor_dictation/core/fallback.py:59-60`, `:83-100`
- Create: `doctor_dictation/api/investigations.py`
- Modify: `doctor_dictation/api/app.py:80` (register router)
- Test: `tests/test_investigations_api.py`; existing `tests/test_rules_split.py:87-95`

**Interfaces:**
- Consumes: `db/overlay.py: list_rows(conn, kind)`; `core/overlay.py: effective_entries(kind, shipped, rows) -> (entries, flags)` (plan f).
- Produces in `api/investigations.py`: `load_entries() -> list[dict]` (effective `'investigation'` entries; `sqlite3.Error` → `shipped()`, logged, like `api/formulary.load_layer` :30-38); `async use_investigations() -> None` (route dependency: `investigations.activate(await asyncio.to_thread(load_entries))`); `POST /api/v1/investigations/lookup` body `{"text": str}` (max 200 chars, else 422) → `{"canonical": str, "status": "verified" | "new"}`.
- Produces in `fallback.py`: `is_demo(t: str) -> bool` (renamed from `_is_demo`); `DEMO_WARNING = "Offline demo example: a fixed sample note. Check every line before saving."`.
- `_answer` adds `s["investigations"] = investigations.check_items(s.get("investigations"), raw, normalized)` on the copy; the cached `structured` keeps unchecked items, so a remembered test that goes live is seen on the next answer.

- [ ] **Step 1: Write the failing tests**

```python
def test_format_returns_items_with_statuses_and_caches_them_unchecked(monkeypatch):
    _FORMAT_CACHE.clear(); activate_catalogue(monkeypatch, CAT)                 # helper: monkeypatch CATALOGUE_PATH
    _stub_llm(monkeypatch, [{"investigations": ["RFT", "Brain impulses"], "rx": []}])
    j = TestClient(M.app).post("/api/format", json={"transcript": "fever, advise rft"}).json()
    assert [(i["text"], i["status"]) for i in j["structured"]["investigations"]] == [("RFT", "verified"), ("Brain impulses", "not-dictated")]
    assert all(i["status"] == "" for v in _FORMAT_CACHE.values() for i in v["structured"]["investigations"])

def test_validate_caps_items_with_the_old_warning_and_keeps_item_fields():
    out, w = validate_structured({"investigations": [f"T{i}" for i in range(14)]}, "")
    assert len(out["investigations"]) == 12 and "investigations: truncated 2 rows beyond the 12-row limit" in w
    out, _ = validate_structured({"investigations": [{"text": "RFT", "status": "verified", "source": "doctor", "canonical": "X"}]}, "")
    assert out["investigations"][0] == {"text": "RFT", "canonical": "X", "status": "verified", "source": "doctor"}

def test_the_demo_note_lists_only_dictated_tests_and_is_labelled(monkeypatch):
    out = fallback_format(normalize_transcript(DEMO))
    assert out["investigations"] == ["Urine culture", "Serum creatinine"]       # the golden demo dictates exactly these
    # /api/format with no LLM: warnings contain DEMO_WARNING

def test_lookup_endpoint_reads_the_clinic_list_and_caps_input(tclient):
    assert tclient.post("/api/v1/investigations/lookup", json={"text": "kft"}).json()["status"] in ("verified", "new")
    assert tclient.post("/api/v1/investigations/lookup", json={"text": "x" * 201}).status_code == 422
```

Add one overlay test once plan f exists: an active `add` row (source `admin`, or confirmed twice) for "Uroflow at home" makes `lookup` answer `verified` inside a request with `use_investigations`.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations_api.py tests/test_rules_split.py tests/test_determinism.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement.** In `fallback.py` change the demo's investigations to `["Urine culture", "Serum creatinine"]` and rename `_is_demo` → `is_demo`. In `format.py` append `DEMO_WARNING` to `warnings` when `is_demo(normalized.lower())` on both fallback paths (:111, :171). Add `Depends(use_investigations)` to `/api/format`.
- [ ] **Step 4: Run** the full suite `.venv/bin/python -m pytest -q` — Expected: PASS. Fix any test that compared `investigations` to plain strings after `validate_structured` by comparing `[i["text"] for i in …]`; do not weaken the assertion.
- [ ] **Step 5: Commit** `feat(pq-h): investigations become checked items on format`.

---

### Task 5: Spoken correction keeps item statuses

**Files:**
- Modify: `doctor_dictation/core/investigations.py`
- Modify: `doctor_dictation/api/format.py:186-228`
- Test: `tests/test_investigations_api.py`

**Interfaces:**
- Produces: `reconcile(previous, items, *transcripts) -> list[dict]` — an item whose `key(text)` equals a previous item's keeps that item's canonical, status and source (first match wins, each previous item used once); every other item goes through `check_items` against the correction transcripts.
- `correct()` flow: `flat = investigations.flatten(current)`; pass `flat` (not `current`) to `extract_correction` and `apply_ops`; after `_validate`, set `structured["investigations"] = reconcile(coerce_items(current.get("investigations")), structured["investigations"], text, normalized)`. `ops.py` and `CORRECTION_INSTRUCTION` are unchanged: they keep seeing strings.

- [ ] **Step 1: Write the failing tests**

```python
FORM = {"investigations": [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"},
                           {"text": "ECG", "canonical": "Electrocardiogram", "status": "verified", "source": "doctor"},
                           "CBC"], "rx": []}

def test_a_correction_about_medicines_keeps_every_item(monkeypatch):            # Review Focus 4
    _stub_llm(monkeypatch, [{"rx": [{"name": "Dolo 650", "dose": "1-0-1"}]}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "dolo twice daily", "current_form": FORM}).json()
    assert j["structured"]["investigations"] == coerce_items(FORM["investigations"])   # CBC stays unchecked ("")

def test_a_replaced_test_is_checked_against_the_correction(monkeypatch):
    _stub_llm(monkeypatch, [{"replace": {"investigations": [{"from": "RFT", "to": "KFT"}]}}])
    j = TestClient(M.app).post("/api/v1/correct", json={"transcript": "not rft, kft", "current_form": FORM}).json()
    assert j["structured"]["investigations"][0]["text"] == "KFT" and j["structured"]["investigations"][0]["status"] == "verified"

def test_the_llm_sees_strings_not_items(monkeypatch):
    calls = _stub_llm(monkeypatch, [{}])
    TestClient(M.app).post("/api/v1/correct", json={"transcript": "ok", "current_form": FORM})
    assert '"investigations": ["RFT", "ECG", "CBC"]' in calls["messages"][0][1]["content"]
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations_api.py tests/test_correction.py tests/test_correction_ops.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** `reconcile` and the `correct()` changes; add `Depends(use_investigations)` to `/api/v1/correct`.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(pq-h): corrections keep investigation statuses`.

---

### Task 6: Save gate and server regrade

**Files:**
- Modify: `doctor_dictation/core/investigations.py`
- Modify: `doctor_dictation/api/persistence.py:185`, `:208-221`
- Test: `tests/test_investigations_save.py`

**Interfaces:**
- Produces: `screen(structured: dict) -> list[dict]` — `[{"index", "text"}]` for items with status `not-dictated` and source `dictated`, in order; `regrade(items) -> list[dict]`:
  - source `dictated`, status `""` or `not-dictated`: unchanged;
  - source `dictated`, status `verified`/`new`: canonical and status from `lookup(text)` (the page's canonical is discarded);
  - source `doctor`: status from `lookup(text)`; canonical = the item's own when non-empty, else the entry's.
- 409 body (contract addition): `{"error": "unverified medicines" if block else "investigations not dictated", "block": block, "investigations_block": ix_block}` whenever either list is non-empty. `block` stays a list (possibly empty), so the page's existing branch still runs.
- After `validate_structured`: `validated["investigations"] = investigations.regrade(validated["investigations"])`.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_red_item_blocks_save_until_kept_or_removed(tclient):
    red = {"text": "Brain impulses", "canonical": "", "status": "not-dictated", "source": "dictated"}
    r = tclient.post("/api/v1/documents", json={"structured": {"patientName": "A", "investigations": [red], "rx": []}})
    assert r.status_code == 409 and r.json() == {"error": "investigations not dictated", "block": [],
                                                 "investigations_block": [{"index": 0, "text": "Brain impulses"}]}
    kept = dict(red, source="doctor")
    assert tclient.post("/api/v1/documents", json={"structured": {"patientName": "A", "investigations": [kept], "rx": []}}).status_code == 200

def test_an_amber_item_saves(tclient): ...           # status "new" -> 200, stored status "new"

def test_a_forged_canonical_is_regraded(tclient):    # Review Focus 5: stored canonical is the catalogue's, not "<b>x</b>"
    ...

def test_an_old_document_with_strings_resaves_without_a_block(tclient):          # Review Focus 3
    ...                                                # save {"investigations": ["CBC"]} -> 200; stored item status ""

def test_both_gates_report_together(tclient): ...     # unverified rx row + red item -> error "unverified medicines", both lists
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations_save.py tests/test_safety.py tests/test_db.py` — Expected: new tests FAIL.
- [ ] **Step 3: Implement** `screen`, `regrade`, the gate and the regrade call; add `Depends(use_investigations)` to `POST /api/v1/documents`.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(pq-h): not-dictated investigations block Save`.

---

### Task 7: "Remember for this clinic" records a confirmation

**Files:**
- Modify: `doctor_dictation/core/investigations.py`
- Modify: `doctor_dictation/api/investigations.py`
- Modify: `doctor_dictation/api/persistence.py:116-121` (`DocumentCreate`), `:319` (call after `learn_from_save`)
- Test: `tests/test_investigations_remember.py`

**Interfaces:**
- Consumes: `db/overlay.py: record_confirmation(conn, kind, entry_key, action, data: dict, base_sha, document_id, user_id) -> int` (plan f; returns the count; never `upsert`); `formulary.THRESHOLD` (2).
- Produces: `remember_row(item: dict, entries: list[dict], shipped: list[dict]) -> dict | None` returning `{"action": "add" | "edit", "entry_key", "data", "base_entry": dict | None}`; overlay `data` for kind `'investigation'` is a full entry `{"canonical", "aliases", "category", "print"}`.
- Produces: `api/investigations.py: remember_from_save(conn, items: list[dict], indexes: list[int], document_id: int, user_id) -> int` (confirmations recorded; per row calls `record_confirmation(conn, 'investigation', row["entry_key"], row["action"], row["data"], base_sha, document_id, user_id)` with `entry_key = investigations.key(canonical-or-text)`; never raises; audit action `investigation.remember` with `{"entry_key", "action", "count"}`, unless plan f already audits). The row stays pending (not in `effective_entries`) until the count reaches `THRESHOLD`.
- `DocumentCreate.remember_investigations: list[int] = []` (indexes into the saved list).

`remember_row` cases (T = item text, C = item canonical, E_T = `lookup(T)`, E_C = `lookup(C)`):

| Case | Result |
|---|---|
| E_T is None, C empty or `key(C) == key(T)` | add, key(T), `{"canonical": T, "aliases": [], "category": "", "print": ""}` |
| E_T is None, E_C exists | edit E_C: aliases + [T] |
| E_T is None, C set, E_C is None | add, key(C), `{"canonical": C, "aliases": [T], …}` |
| E_T exists, C empty or equals E_T canonical | None (nothing to learn) |
| E_T exists, C set, E_C is None | edit E_T: canonical = C, old canonical kept as an alias |
| E_T and E_C exist and differ | None (conflict; the page says "already in the list as …") |

An "edit" of an entry that is not in `shipped` (a clinic `add`) is written as action `add` under its own key, `base_entry` None. `entry_key` of an edit = `key(shipped canonical)`. `base_sha` = plan f's sha of `base_entry`, `''` for add.

- [ ] **Step 1: Write the failing tests** — one per table row on `remember_row`, plus:

```python
UF = {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"}
# helpers: _save(tc, item, doc_id=None) saves/re-saves with remember [0] -> id; _status = fresh /api/format status; _count(key)

def test_first_save_is_pending_and_a_second_document_makes_it_live(tclient, monkeypatch):
    _save(tclient, UF); assert _status(tclient, monkeypatch, "Uroflow at home") == "new"        # pending, 1 of 2
    _save(tclient, UF); assert _status(tclient, monkeypatch, "Uroflow at home") == "verified"   # THRESHOLD reached

def test_resaving_the_same_document_does_not_count_twice(tclient):
    d = _save(tclient, UF); _save(tclient, UF, doc_id=d); assert _count(key("Uroflow at home")) == 1   # still pending

def test_different_data_restarts_the_count(tclient):       # edit of shipped RFT, two different full names
    rft = {"text": "RFT", "status": "verified", "source": "doctor"}
    _save(tclient, dict(rft, canonical="Kidney Profile")); _save(tclient, dict(rft, canonical="Kidney Panel"))
    assert _count(key("Renal Function Test")) == 1          # restarted; the saved prescription keeps "Kidney Panel"

def test_bad_indexes_and_a_failing_write_never_block(tclient, monkeypatch): ...  # [5, -1, "x"] ignored; record_confirmation raises -> 200, logged
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_investigations_remember.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `remember_row`, `remember_from_save`, the `DocumentCreate` field and the call (pass the regraded `validated["investigations"]` and the saved document id).
- [ ] **Step 4: Run** the file plus `tests/test_file_sizes.py` — Expected: PASS (persistence.py stays under 500).
- [ ] **Step 5: Commit** `feat(pq-h): remember an investigation for this clinic`.

---

### Task 8: Print

**Files:**
- Modify: `doctor_dictation/pdf/sheet.py:21-25` and `:318-319` (or plan e's inline list)
- Test: `tests/test_pdf_sheet.py`

**Interfaces:**
- Consumes: `investigations.print_text(item)` (Task 2). `pdf/` may import `core` (it already imports `core.followup`, :5).

- [ ] **Step 1: Write the failing tests**

```python
def test_investigations_print_as_dictated_with_the_full_name():
    html = build_sheet_html({"investigations": [{"text": "RFT", "canonical": "Renal Function Test", "status": "verified", "source": "dictated"},
                                                {"text": "Uroflow at home", "canonical": "", "status": "new", "source": "dictated"},
                                                "CBC"]}, META)
    assert "RFT (Renal Function Test)" in html and "Uroflow at home" in html and "CBC" in html
    assert "verified" not in html and "dictated" not in html          # status and source never print

def test_a_canonical_is_escaped():
    html = build_sheet_html({"investigations": [{"text": "X", "canonical": "<b>y</b>", "status": "new", "source": "doctor"}]}, META)
    assert "&lt;b&gt;y&lt;/b&gt;" in html and "<b>y</b>" not in html
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_pdf_sheet.py tests/test_sections_prose.py` — Expected: new tests FAIL (dicts print as Python reprs today).
- [ ] **Step 3: Implement:** the investigations list renders `print_text(v)` per value, escaped; other lists unchanged.
- [ ] **Step 4: Run** the same command — Expected: PASS.
- [ ] **Step 5: Commit** `feat(pq-h): print investigations as dictated plus full name`.

---

### Task 9: Sheet UI — `frontend/ixlist.js`

**Files:**
- Create: `frontend/ixlist.js`, `frontend/ixlist.css`
- Modify: `frontend/index.html:112` (`<ul id="pIx" class="ix-list">`, no `editable-list`, so `fixLists` at `app.js:827-831` ignores it), add `ixlist.css?v=1` after `rx.css` and `ixlist.js?v=1` before `app.js`; bump `app.js?v=`
- Modify: `frontend/app.js:651` (read), `:916` (render), `:765-815` (delete/undo), `:820-822` (x-button routing), `:567` (correction keeps nothing extra), 409 branch (~:1065)
- Test: `tests/test_frontend_ixlist_dom.py` (node fake DOM, pattern of `tests/test_frontend_rxspell_dom.py` `_run`)

**Interfaces:**
- Produces `window.IxList`:
  - `init(hooks)` — `{post(url, body, ms) -> Promise, onChange(), onRemove(item, pos)}`.
  - `render(ul, values)`; `read(ul) -> list[item]`; `rememberIndexes(ul) -> number[]`; `insert(ul, item, pos) -> Element` (for Undo); `remove(li) -> {item, pos}`; `showBlocked(ul, block)` (marks `[{index, text}]` red with focus on the first); `printText(item) -> string` (same rule as Python `print_text`).
- Per item `<li class="ix-item" data-status data-source>`: `.ix-text` (contenteditable), `.ix-full` (" (canonical)" when it differs; prints), and no-print: `.ix-chip` (verified "In list" green, new "New test" amber, not-dictated "Not dictated" red, "" none), a "Keep" button (red only), a "Remember for this clinic" checkbox (status new, or after an edit) that reveals a "Full name" input bound to `canonical`, and an x button `data-action="delete-ix"`. A no-print "+ Add test" button after the list adds an empty doctor item.
- Editing `.ix-text` sets source `"doctor"` and calls `POST /api/v1/investigations/lookup` (debounced 400 ms, newest answer wins) to set canonical and status. "Keep" sets source `"doctor"` and status `canonical ? "verified" : "new"`. Voice correction uses the existing correction mic; Task 5 keeps the other items.
- app.js: `serializeForm` uses `IxList.read`; save payload adds `remember_investigations: IxList.rememberIndexes($("pIx"))`; `deleteIx(li)` pushes undo `{type: "ix", pos, item}`; `undoDelete` calls `IxList.insert`; the 409 branch calls `IxList.showBlocked` when `e.data.investigations_block` is non-empty and words the message for medicines, tests or both ("Save blocked: 1 test was not heard in the dictation. Keep it or remove it, then Save again.").

- [ ] **Step 1: Write the failing tests**

```python
def test_items_render_with_a_status_chip_and_read_back_unchanged(): ...
    # render 4 items (verified / new / not-dictated / legacy string) -> chips ["In list", "New test", "Not dictated", ""];
    # read() returns the same objects; the legacy string reads back as {"text": "CBC", "canonical": "", "status": "", "source": "dictated"}
def test_print_text_matches_the_server(): ...
    # IxList.printText over the Task 2 cases == investigations.print_text over the same cases (one JSON table, both sides)
def test_editing_the_text_makes_it_the_doctors_and_asks_the_server(): ...
    # input on .ix-text -> source "doctor", one post to /api/v1/investigations/lookup; a stale answer is dropped
def test_keep_clears_red_and_remember_reveals_full_name(): ...
    # Keep -> source "doctor", chip not red; tick -> "Full name" input shown, its value becomes item.canonical; rememberIndexes == [i]
def test_text_is_never_markup(): ...                  # item text "<img src=x>" set via textContent
def test_show_blocked_marks_the_named_items(): ...
def test_index_html_pins(): ...                       # ixlist.js?v=1 before app.js?v=; pIx has class ix-list
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_frontend_ixlist_dom.py` — Expected: FAIL.
- [ ] **Step 3: Implement** `ixlist.js` (target under 300 lines) and `ixlist.css` (status colours as tokens; red/amber/green match `rx.css` row states), then the app.js hooks.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_frontend_*.py tests/test_file_sizes.py` — Expected: PASS.
- [ ] **Step 5: Commit** `feat(pq-h): editable investigation items on the sheet`.

---

### Task 10: Full verification

- [ ] **Step 1: Run** `.venv/bin/python -m pytest -q` — Expected: all pass.
- [ ] **Step 2:** Ask the owner to run the app once (agents do not start it): dictate "advise RFT and USG KUB", check green items, type "ECG", check amber, save, reopen, print; dictate a demo where the AI adds a test, check red blocks Save.
- [ ] **Step 3:** List changed files for the owner; no commit without the word.

## Deliberately out of scope

- The clinic investigation list screen (view, edit, reset) and the admin review/export: plan f.
- Grouping investigations by category in print: plan e (the `category` field is ready).
- Prompt rules about tests: plan d.
- Cross-clinic promotion of learned tests (`promotion.py`): manual operator step (MVP 1 scope rule).
- Fuzzy matching of test names: exact match only; unknown spellings stay amber until a remembered test reaches `THRESHOLD` confirmations.

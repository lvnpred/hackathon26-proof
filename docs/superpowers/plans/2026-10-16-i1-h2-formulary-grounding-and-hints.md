# Clinic Formulary, Part 2: Grounding, Hints and `source` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a name on the clinic's list verified for its NAME only (`source: "clinic"`, no strengths, no dose check), stopped for confirmation when it sounds like a lexicon drug, offered to the speech engine inside the existing hint budget, and kept through corrections.

**Architecture:** `core/formulary.py` gains `ground_clinic` and `row_extras`; `core/determinism.py` gets one net line (the unknown branch of `_ground_row` calls `ground_clinic(...) or` the old tuple; the row dict spreads `row_extras`). The layer is read from the active `ContextVar`, so no function signature in `determinism.py` changes.

**Tech Stack:** Python 3 / FastAPI / sqlite3 (stdlib), vanilla JS, pytest. No new dependency.

**Spec:** `docs/superpowers/plans/2026-10-16-medication-name-accuracy.md` section 2d ("Clinic formulary") and table row "Clinic formulary"; contracts in `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` (facts 1, 2, 5, 6; sections 4.1, 4.2, 4.3).

**Assumptions about earlier plans** (re-find every anchor with `grep -n`; line numbers below are from the repository as it stood before I1-a..I1-g)**:**
- I1-h1 is applied. From it this part uses exactly: `core.formulary.key`, `clean_name`, `learnable`, `ClinicLayer(items)` with `.get(name)`, `.version`, `.hint_names()`, `activate(layer)`, `active_layer()`, constants `THRESHOLD`, `MAX_NAME`, `MAX_WORDS`, `MAX_HINTS = 10`, `HINT_CHARS = 150`; and `tests/test_formulary.py` (its head: `D`, `F`, `build_hints`, `MAX_HINT_CHARS`, `layer()`, the autouse fixture that resets the layer).
- I1-a: `core/lasa.py` and status `lookalike-check`; `lookalike_flag` must return `""` for a row whose `lexicon_match` is empty (check with `grep -n "def lookalike_flag" doctor_dictation/core/lasa.py`). I1-b frees room in `core/determinism.py`; this plan needs only one line there (482 lines now; 483 after).
- I1-c: `dose-check` never fires for a row with no lexicon match (clinic names are `cannot-check`). I1-d: moves the per-row block of `validate_structured` into `rowcheck.ground_with_notes`; if it has landed, put I1-h2 Task 1's `**formulary.row_extras(...)` addition in that function's returned dict instead (`grep -n '"lexicon_match"' doctor_dictation/core/*.py`), and give `api/rx.py` the same `dependencies=[Depends(use_clinic_layer)]` as `/api/format` (I1-h3 Task 1 Step 6).

**Produces (consumed by I1-h3 and I1-h4):** `core.formulary.ground_clinic(name, transcript_lower, in_transcript) -> (status, "", issue | None) | None`, `row_extras(name, lexicon_match, status) -> dict`, constants `VERIFIED`, `UNVERIFIED_NAME`, `LOOKALIKE`; rows from `validate_structured` carry `source` (`"clinic"` or `"lexicon"`) and `lookalike` for a flagged clinic name; `build_hints` includes the active layer's names; `preserve_untouched_rx_status` restores `source`.

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): `core/formulary.py` imports only the standard library and `core.candidates`/`core.determinism` (lazily). Per-clinic data comes in as data.
- Changes to `core/determinism.py`: at most 4 net lines (this plan: +1). No source file over 500 lines (`db/__init__.py` is 487 lines, so the new SQL lives in `db/formulary.py`).
- Existing endpoints keep their status codes and JSON shapes; rows gain only `source` (and `lookalike` for a clinic name flagged as a look-alike). `preserve_untouched_rx_status` also restores `source` (`core/correction.py:273`).
- A clinic name is verified for its NAME only: no strength options, dose check `cannot-check`. Another clinic never sees a name: every query runs on the scoped clinic database (`db/__init__.py:35-44`).
- Tests offline: stub LLM (`STUB_LLM_JSON`), fake PDF renderer, no network. Test command `.venv/bin/python -m pytest tests/ -q`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

- A learned name that sounds like a lexicon drug must still be stopped for confirmation (`lookalike-check`), never silently verified. Pinned in Task 1.
- 30 long learned names must not crowd the 500-character speech-hint budget, and a patient's name still must not reach the hints. Pinned in Task 1.
- A correction must not lose a row's `source`. Pinned in Task 1.

## Decisions (and why)

5. **Grounding order (contract 4.2).** A name on the clinic list is not `unknown-medicine`; then `unverified-name` if nobody said it; no strength check and no dose check (nothing to compare with); then `lookalike-check` if it sounds like a lexicon drug; else `verified` with `source: "clinic"`. Contract 4.3's `lasa.twins(canonical)` takes a lexicon canonical and a clinic name has none, so the sound-alike test is the existing `suggest_candidates` index (`core/candidates.py:89`, score 0.78 and up, the same index I1-d uses for suggestions); the named drug is returned in the row's `lookalike`. I1-a's guard still runs for every row that has a `lexicon_match`. Lookup is exact (case and spacing only): a learned name is never fuzzy-matched, so it cannot capture a misheard lexicon word.
6. **How the layer reaches the matcher.** Passing a layer through `ground_rx -> validate_structured -> _ground_row -> _canonical_lookup` would cost about 8 lines in `determinism.py`. Instead `formulary.activate(layer)` sets a `ContextVar` in a FastAPI dependency (`use_clinic_layer`, async so the value stays in the request's context); `asyncio.to_thread` copies the context (`scope.py:5-6` relies on the same). `core` functions still accept data only; tests call `activate()` directly.
8. **Hints.** `core/hints.py:_doctor_canonical` (`:26-34`) drops names the lexicon lacks. It now also keeps names on the active layer, and `build_hints` adds the newest 10 clinic names (at most 150 characters together) after the doctor's own and before the common lexicon names. The 500-character budget lives in `core/hints.py:13` (`MAX_HINT_CHARS`), not in `api/stt.py`; the loop at `:42-53` still enforces it. `build_hints`' call in `api/stt.py:43` is unchanged (an isolation test replaces it with `spy(top, limit)`).

## File Structure

| File | Change |
|---|---|
| `doctor_dictation/core/formulary.py` | grounding half (appended) |
| `doctor_dictation/core/determinism.py` | +1 net line (482 now, 483 after) |
| `doctor_dictation/core/hints.py`, `core/correction.py` | layer names kept and offered; `source` restored |
| `tests/test_formulary.py` | 4 more tests |

Adds 4 tests. Baseline: the suite as it stands after I1-h1; expect that count + 4.

---

### Task 1: Grounding, hints and `source` (the hook into `determinism.py`)

**Files:** Modify `doctor_dictation/core/formulary.py`, `core/determinism.py`, `core/hints.py`, `core/correction.py`, `tests/test_formulary.py`.

**Interfaces:** Produces `ground_clinic(name, transcript_lower, in_transcript) -> (status, "", issue | None) | None` (None when the name is not on the active layer), `row_extras(name, lexicon_match, status) -> dict` (`{"source": "lexicon"}`, or `{"source": "clinic"}` plus `lookalike` when flagged), constants `VERIFIED`, `UNVERIFIED_NAME`, `LOOKALIKE`.

- [ ] **Step 1: Append the failing tests** to `tests/test_formulary.py`.

```python


def test_a_clinic_name_is_verified_for_its_name_only_with_source_clinic():
    F.activate(layer("Zorbexin"))
    out, _ = D.validate_structured({"rx": [{"name": "Zorbexin", "strength": "10 mg"}, {"name": "Paracetamol"},
                                           {"name": "Quillavex"}]}, "give zorbexin 10 mg and paracetamol and quillavex")
    zor, para, other = out["rx"]
    assert (zor["status"], zor["source"], zor["lexicon_match"]) == ("verified", "clinic", "")
    assert (para["status"], para["source"]) == ("verified", "lexicon")
    assert (other["status"], other["source"]) == ("unknown-medicine", "lexicon")        # not on the clinic's list
    out, _ = D.validate_structured({"rx": [{"name": "Zorbexin"}]}, "give something else")
    assert out["rx"][0]["status"] == "unverified-name"                                  # still has to be dictated


def test_a_clinic_name_that_sounds_like_a_lexicon_drug_is_flagged_and_names_the_twin():
    F.activate(layer("Amlodipin Besy"))
    assert D._canonical_lookup("Amlodipin Besy") == ""                                 # the lexicon alone misses it
    out, _ = D.validate_structured({"rx": [{"name": "Amlodipin Besy"}]}, "amlodipin besy daily")
    row = out["rx"][0]
    assert (row["status"], row["source"], row["lookalike"]) == ("lookalike-check", "clinic", "Amlodipine")
    assert F.VERIFIED == D.RX_VERIFIED and F.UNVERIFIED_NAME == D.RX_UNVERIFIED_NAME


def test_a_correction_keeps_the_source_of_rows_it_does_not_name():
    from doctor_dictation.core.correction import preserve_untouched_rx_status
    current = {"rx": [{"name": "Zorbexin", "status": "verified", "lexicon_match": "", "source": "clinic"}]}
    fresh = {"rx": [{"name": "Zorbexin", "status": "unknown-medicine", "lexicon_match": "", "source": "lexicon"}]}
    assert preserve_untouched_rx_status(current, {}, fresh)["rx"][0] == current["rx"][0]


def test_hints_keep_clinic_names_inside_the_budget_and_still_leave_room_for_the_lexicon():
    assert build_hints(["Zorbexin"], limit=5)[0] != "Zorbexin"                       # no layer: dropped, as before
    F.activate(layer("Zorbexin", *[f"Longnamedclinicmedicine{i} Forte Plus" for i in range(40)]))
    out = build_hints(["Zorbexin", "Ramesh Kumar"], limit=70)
    assert out[0] == "Zorbexin" and "Ramesh Kumar" not in out
    assert len(", ".join(out)) <= MAX_HINT_CHARS and len(out) >= 20 and "Paracetamol" in out
    assert len(F.active_layer().hint_names()) <= F.MAX_HINTS and len(", ".join(F.active_layer().hint_names())) <= F.HINT_CHARS
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary.py -q`. Expected: 4 FAIL (`AttributeError`/`KeyError: 'source'`), 3 pass.
- [ ] **Step 3: Extend `core/formulary.py`:** the imports, the three status constants, and the grounding half appended at the end.

```diff
- from functools import cached_property
+ from functools import cached_property, lru_cache
+ 
+ from .candidates import suggest_candidates
```
```diff
- _NAME_OK = re.compile(r"[A-Za-z][A-Za-z0-9 .'+/-]*")
+ _NAME_OK = re.compile(r"[A-Za-z][A-Za-z0-9 .'+/-]*")
+ VERIFIED, UNVERIFIED_NAME, LOOKALIKE = "verified", "unverified-name", "lookalike-check"
```
```python


@lru_cache(maxsize=512)
def _twin(name_key: str, lexicon_version: str) -> str:
    found = suggest_candidates(name_key, 1)
    return found[0] if found else ""


def _lexicon_twin(name) -> str:
    from .determinism import lexicon_version
    return _twin(key(name), lexicon_version())


def ground_clinic(name, transcript_lower, in_transcript):
    """(status, lexicon_match, issue) for a name on this clinic's list, else None. Called after the lexicon missed.

    Grounding order (contract 4.2): not clearly dictated, then look-alike of a lexicon drug, then verified. A learned
    name never gets strengths or a dose check, and never silently stands in for a similar-sounding lexicon drug."""
    if active_layer().get(name) is None:
        return None
    if not in_transcript(name, transcript_lower):
        return (UNVERIFIED_NAME, "", f"'{name}': not clearly dictated in transcript")
    twin = _lexicon_twin(name)
    if twin:
        return (LOOKALIKE, "", f"'{name}': known to the clinic but sounds like {twin}")
    return (VERIFIED, "", None)


def row_extras(name, match, status) -> dict:
    """The row keys this plan owns: ``source``, and ``lookalike`` for a clinic name flagged as a look-alike."""
    if match or active_layer().get(name) is None:
        return {"source": "lexicon"}
    return {"source": "clinic", **({"lookalike": _lexicon_twin(name)} if status == LOOKALIKE else {})}
```

- [ ] **Step 4: The hook in `core/determinism.py`** (net +1 line: the import; the unknown branch of `_ground_row`, `:254-256`, gains `ground_clinic(...) or` on the same return; the row dict at `:466-471` gains `**formulary.row_extras(...)` on the `lexicon_match` line). If I1-a/I1-c/I1-d changed these lines, apply the same three changes to the same statements wherever they now live.

```diff
- from .candidates import suggest_candidates
+ from . import formulary
+ from .candidates import suggest_candidates
```
```diff
-             return (RX_UNKNOWN_MEDICINE, "",
-                     f"'{name}': {UNKNOWN_MEDICINE_TEXT} ({lexicon_size()} entries)")
+             return formulary.ground_clinic(name, transcript_lower, _name_in_transcript) or (
+                 RX_UNKNOWN_MEDICINE, "", f"'{name}': {UNKNOWN_MEDICINE_TEXT} ({lexicon_size()} entries)")
```
```diff
-             "lexicon_match": match,
-         })
+             "lexicon_match": match, **formulary.row_extras(name, match, status),
+         })
```

- [ ] **Step 5: Hints and correction.** In `core/hints.py` the import (`:11`); then the two lines `canon = _canonical_lookup(clean)` / `if canon:` of `_doctor_canonical` (`:31-32`) become the block below, so names on the layer survive; the `for name in [...]` line of `build_hints` (`:42`) gains the newest clinic names; in `core/correction.py` the field tuple (`:273`) gains `"source"`.

```diff
- from .determinism import _canonical_lookup, load_lexicon
+ from .determinism import _canonical_lookup, load_lexicon
+ from .formulary import active_layer
```
```python
            hit = active_layer().get(clean)
            canon = _canonical_lookup(clean) or (hit[0] if hit else "")      # the clinic's own names are kept too
            if canon:
                out.append(canon)
```
```diff
-     for name in [*_doctor_canonical(doctor_top), *common_lexicon_names()]:
+     for name in [*_doctor_canonical(doctor_top), *active_layer().hint_names(), *common_lexicon_names()]:
```
```diff
-         for field in ("status", "lexicon_match", "instructions"):
+         for field in ("status", "lexicon_match", "instructions", "source"):
```

- [ ] **Step 6: Run.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: baseline + 4 passed (this part's four new tests) and no failure; `wc -l doctor_dictation/core/determinism.py` prints 483.
- [ ] **Step 7: Leave uncommitted.**

---

## Self-review

Grounding order and look-alike (Task 1, decision 5), hints budget (decision 8), `source` (row dict, correction). Names match I1-h1's Produces block. Not done here: loading the layer for a request, learning on save, the cache key (I1-h3).

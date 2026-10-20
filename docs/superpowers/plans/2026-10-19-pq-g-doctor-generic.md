# PQ-g: Doctor-Entered Generic + AI Suggestion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The doctor can type, dictate or accept (one tap) a medicine's generic; it is stored with `generic_source: "doctor"`,
never recalculated by the server, printed exactly as entered, and joins the clinic list after `formulary.THRESHOLD` (2)
confirmed saves in different prescriptions with the same generic.

**Architecture:** A pure module (`core/doctor_generic.py`) owns the generic text rules (validation, correction patch
whitelist, save-time settle). `rowcheck.ground_with_notes` carries a doctor generic and an AI suggestion through every
path; `preserve_untouched_rx_status` skips recalculating doctor rows. The AI suggestion is one more field in the
`/api/format` LLM reply. The save counts a confirmed doctor generic toward the clinic overlay
(`db/overlay.record_confirmation`, never `upsert`) and audits it. A new `frontend/genericedit.js` draws the editable
generic line, the "Remember for this clinic" tick and the "AI suggests" line, called from `rxview.js`.

**Tech Stack:** Python 3 / FastAPI, SQLite, vanilla JS (node fake-DOM tests), pytest.

**Spec:** `2026-10-19-prescription-quality-brainstorm.md` (sections 1-2, "Decisions made" decision 1, overlay) and the
contract `2026-10-19-pq-00-index.md` (binding: "Learning threshold (owner rule, 2026-10-19; plans f, g, h)").

**Owner answers 2026-10-19:** Q20 overriding a listed generic changes THIS prescription only unless the row's "Remember
for this clinic" is ticked; an unknown brand (incl. `combo_base` rows) counts without a tick. Q21 a spoken generic needs
confirmation: yes. Q22 changing the medicine name clears the doctor's generic: yes.

## Global Constraints

- Contract names, verbatim: `generic_source` is `""` | `"lexicon"` | `"doctor"`; `generic_suggestion` is the AI composition, `""` when none, "Never printed, never learned" (index:31-32).
- "when `generic_source == "doctor"`, no server path recalculates `generic` (`RECOMPUTED_ROW_FIELDS`, `preserve_untouched_rx_status`, `rowcheck`)" (index:34-35).
- Keep `SYSTEM_PROMPT`'s sentence "never replace a brand with its generic" byte-identical (`api/format.py:48`).
- The suggestion exists only for a row whose name has no exact lexicon match (`_exact_lookup(name) == ""`, plan a). The rules-only fallback has none.
- Learning threshold (index:80-94), on save: `record_confirmation(conn, "medicine", entry_key, action, {"name", "generic"}, base_sha, document_id, user_id)`, never `upsert`. The row goes live after `formulary.THRESHOLD` (2) confirmed saves in different documents with the same generic; a different generic restarts the count at 1. The prescription always prints what the doctor entered.
- Q20: a listed brand (`_exact_lookup(name) != ""`) counts only when its rx index is in `DocumentCreate.remember_generics: list[int] = []` (mirrors plan h's `remember_investigations`); an unknown brand counts without it.
- Everything learned is clinic-specific (spec:37-39): never write `drugs.json`.
- Files stay under 500 lines; `frontend/app.js` (1251 lines) gets one-line hooks only. Bump every changed static file's `?v=` pin in `frontend/index.html`.
- Tests: `.venv/bin/python -m pytest -q -x tests/<file>`. No commit without the owner's word: each "Commit" step asks first.

## Review Focus

1. **LLM echoes the current generic in a correction patch** (`{"name": "Pan 40", "dose": "1-0-1", "generic": "Pantoprazole"}` for a dose change): no doctor generic, no pending flag. Test in Task 4.
2. **Doctor generic on a brand whose generic is hidden or fuzzy-matched** (Fefol, `generic_hidden`, `surface.py:67-80`; "Zerodol-P"): the doctor's text shows and prints, `_generic_of` never blanks it. Test in Task 2.
3. **Name changed after the generic was entered** (hand edit, Spell it, spoken `replace`): the old brand's generic must not stay under the new name. Tests in Task 2 (ops) and Task 6 (page).
4. **Reopened saved prescription with a doctor generic, saved again**: no new confirmation demanded, the count does not rise (docs ledger). Test in Task 5.
5. **Hostile or garbled generic text** (`<script>`, 500 characters, `"+ +"`, 7 ingredients): rejected with a message on the page and at the server, never printed raw. Tests in Tasks 1, 5 and 7.

## Contract additions this plan makes (record them in the index at Task 1)

| Field | Type | Meaning | Stored? |
|---|---|---|---|
| `generic_pending` | bool | A doctor generic entered in this session that the doctor has not yet confirmed-and-saved. Blocks Save until the row is confirmed. | No: `settle` removes it at save |
| `generic_suggestion_unknown` | list[str] | Components of `generic_suggestion` that are not a known canonical (amber). Derived from the suggestion. | Recomputed on every validate |
| `DocumentCreate.remember_generics` | list[int] | rx indexes ticked "Remember for this clinic" (needed only for a listed brand) | No: request only |

Why `generic_pending`, not "status = ''" (`app.js:956-957`): a generic edit must keep a verified name's grounding, and a spoken
generic on a verified row would otherwise need no confirmation and never be counted (learning reads `confirmed_rows`).

### Task 1: The generic text rules (`core/doctor_generic.py`)

**Files:**
- Create: `doctor_dictation/core/doctor_generic.py`
- Modify: `docs/superpowers/plans/2026-10-19-pq-00-index.md` (add the two row fields above to the row table, owner plan g;
  add `DocumentCreate.remember_generics: list[int]` beside plan h's `remember_investigations` — the index needs it)
- Test: `tests/test_doctor_generic.py`

**Interfaces:**
- Consumes: plan a `determinism._exact_lookup(name) -> str`; `determinism.load_lexicon()` (plan f: effective entries). Both imported lazily (rowcheck imports this module; determinism imports rowcheck lazily, `rowcheck.py:23`).
- Produces:
  - `MAX_GENERIC_CHARS = 160`, `MAX_COMPONENTS = 6`, `DOCTOR = "doctor"`
  - `DOCTOR_GENERIC_FIELDS = ("generic_source", "generic_suggestion", "generic_suggestion_unknown", "generic_pending")`
  - `generic_problem(raw) -> str` — "" when valid, else one of the five `MESSAGES` below
  - `clean_generic(raw) -> str` — the stored text, or "" when `generic_problem` is not ""
  - `unknown_components(generic: str) -> list[str]`
  - `doctor_fields(item: dict, name: str) -> dict` (Task 2 uses it)
  - `strip_llm_fields(draft: dict) -> dict` (Task 3) and `patch_generics(current: dict, patch: dict) -> tuple[dict, list[str]]` (Task 4)
  - `settle(validated: dict) -> dict` and `new_doctor_generics(structured: dict, confirmed_rows, remember_generics) -> list[tuple[int, str, str]]` (Task 5)
- [ ] **Step 0: Preflight.** Re-read `core/determinism.py`, `core/combo.py` and plan a's Interfaces: confirm `_exact_lookup`
  exists as contracted and that plan a's "Add generic" row signal is `combo_base` (filled by `surface.generic_fields`;
  Task 7 hooks it). Re-read plan f's Interfaces for `record_confirmation`, `entry_sha`, `shipped_lexicon()` (Task 5).
- [ ] **Step 1: Write the failing tests**

```python
from doctor_dictation.core import doctor_generic as G
def test_clean_generic_normalises_separators_and_keeps_the_doctors_case():
    assert G.clean_generic("Aceclofenac+Paracetamol") == "Aceclofenac + Paracetamol"
    assert G.clean_generic("  aceclofenac   plus  paracetamol ") == "aceclofenac + paracetamol"
    assert G.clean_generic("Paracetamol + paracetamol") == "Paracetamol"          # duplicate component, first spelling kept
    assert G.clean_generic("Calcium Carbonate + Vitamin D3") == "Calcium Carbonate + Vitamin D3"
def test_clean_generic_rejects_bad_text_with_a_message():
    cases = {"": G.MESSAGES["empty"], "Aceclofenac + ": G.MESSAGES["parts"], "+ +": G.MESSAGES["parts"],
             "x" * 161: G.MESSAGES["long"], "<script>": G.MESSAGES["chars"], "A1": G.MESSAGES["chars"],
             " + ".join(f"Drug{c}" for c in "abcdefg"): G.MESSAGES["many"]}
    for raw, msg in cases.items():
        assert G.generic_problem(raw) == msg and G.clean_generic(raw) == ""
    assert G.clean_generic(None) == "" and G.clean_generic(["x"]) == ""
def test_unknown_components_lists_what_no_lexicon_canonical_names(monkeypatch):
    monkeypatch.setattr("doctor_dictation.core.determinism.load_lexicon",
                        lambda: [{"canonical": "Aceclofenac"}, {"canonical": "Paracetamol"}, {"canonical": "Calcium + Vitamin D3"}])
    assert G.unknown_components("Aceclofenac + paracetamol") == []
    assert G.unknown_components("Aceclofenac + Serratiopeptidase") == ["Serratiopeptidase"]
    assert G.unknown_components("Vitamin D3") == []                                # a combination canonical is split too
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q -x tests/test_doctor_generic.py` — Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement `generic_problem`, `clean_generic`, `unknown_components`.** Exact copy for `MESSAGES`:

```python
MESSAGES = {
    "empty": "Type the generic, or press Cancel.",
    "long": "The generic is too long (160 characters at most).",
    "parts": "Separate the ingredients with +, for example Aceclofenac + Paracetamol.",
    "many": "At most 6 ingredients.",
    "chars": "Use letters, digits, spaces and . , ' ( ) / - only.",
}
```

  Rules, in this order: non-string or blank → `empty`; collapse whitespace; the word `plus` (case-insensitive, whole
  word) becomes `+`; more than 160 characters → `long`; split on `+`, any blank component → `parts`; more than 6 distinct
  components → `many`; each component must fullmatch `[A-Za-z][A-Za-z0-9 .,'()/-]*` and hold 3+ letters, else `chars`.
  Join distinct components (casefold, first spelling wins) with `" + "`. `unknown_components` splits every effective
  canonical on `+` into a casefolded set.
- [ ] **Step 4: Run the test** — Expected: PASS.
- [ ] **Step 5: Add the two rows and `remember_generics` to the index, commit** (ask first): `feat(pq-g): generic text rules for a doctor-entered generic`.

### Task 2: The server keeps a doctor generic (row builder, untouched rows, renames, learning, print)

**Files:**
- Modify: `doctor_dictation/core/doctor_generic.py` (`doctor_fields`)
- Modify: `doctor_dictation/core/rowcheck.py:68-75` (the returned row: today the effective whitelist of row keys)
- Modify: `doctor_dictation/core/correction.py:289-298`, `:401-412` (`RECOMPUTED_ROW_FIELDS` loop in `preserve_untouched_rx_status`)
- Modify: `doctor_dictation/core/ops.py:81` (`_regrounded` drops `DOCTOR_GENERIC_FIELDS` too)
- Modify: `doctor_dictation/core/formulary.py:67-74` (`learnable` skips doctor rows; they go to the overlay, Task 5)
- Test: `tests/test_doctor_generic_rows.py`

**Interfaces:**
- Consumes: Task 1; plan a's `generic_source` computation inside `ground_with_notes` (`""`/`"lexicon"`).
- Produces: every grounded row carries `generic_source` (always), and `generic_suggestion` (str), `generic_suggestion_unknown`
  (list) always; `generic_pending` only on a doctor row. `doctor_fields(item, name) -> dict` returns the keys to overlay on the
  lexicon-built row: for `item["generic_source"] == "doctor"` with a valid `clean_generic(item["generic"])`:
  `{"generic": cleaned, "generic_source": "doctor", "generic_pending": item.get("generic_pending") is True}` plus the kept
  suggestion; otherwise `{}` for the generic, and the suggestion rule: `clean_generic(item["generic_suggestion"])` kept only when
  `_exact_lookup(name) == ""` and it differs from `name` case-insensitively, else `""`.
- [ ] **Step 0: Preflight.** Re-read `rowcheck.py`, `correction.py`, `ops.py`, `formulary.py` (plans a and c changed them).
- [ ] **Step 1: Write the failing tests**

```python
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.ops import apply_ops
from doctor_dictation.core.formulary import learnable
from doctor_dictation.pdf.sheet import _rx_rows
DOC = {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "doctor", "generic_pending": True}
def test_validate_keeps_a_doctor_generic_on_an_unknown_combination():
    out, _ = validate_structured({"rx": [DOC]}, "zerodol-p")
    r = out["rx"][0]
    assert (r["generic"], r["generic_source"], r["generic_pending"]) == ("Aceclofenac + Paracetamol", "doctor", True)
def test_validate_drops_an_invalid_doctor_generic_and_warns():
    out, warns = validate_structured({"rx": [{**DOC, "generic": "<b>x</b>"}]}, "zerodol-p")
    assert out["rx"][0]["generic_source"] != "doctor" and "generic_pending" not in out["rx"][0]
    assert any("generic" in w for w in warns)
def test_a_lexicon_generic_sent_by_the_client_is_never_trusted():
    out, _ = validate_structured({"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "lexicon"}]}, "zerodol-p")
    assert out["rx"][0]["generic"] == "" and out["rx"][0]["generic_source"] == ""
def test_a_hidden_generic_brand_still_shows_the_doctors_generic():          # Review Focus 2
    out, _ = validate_structured({"rx": [{**DOC, "name": "Fefol"}]}, "fefol")
    assert out["rx"][0]["generic"] == "Aceclofenac + Paracetamol"
def test_suggestion_kept_only_without_an_exact_match():
    out, _ = validate_structured({"rx": [{"name": "Zerodol-P", "generic_suggestion": "aceclofenac plus paracetamol"},
                                        {"name": "Crocin", "generic_suggestion": "Paracetamol"},
                                        {"name": "Zerodol-P", "generic_suggestion": "Zerodol-P"}]}, "zerodol-p crocin")
    assert [r["generic_suggestion"] for r in out["rx"]] == ["aceclofenac + paracetamol", "", ""]
def test_untouched_doctor_row_is_not_recalculated_on_a_correction_or_save():
    current = {"rx": [{**DOC, "status": "unknown-medicine", "lexicon_match": ""}, {"name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol"}]}
    validated, _ = validate_structured(current, "")
    preserve_untouched_rx_status(current, {}, validated)
    assert validated["rx"][0]["generic"] == "Aceclofenac + Paracetamol" and validated["rx"][0]["generic_source"] == "doctor"
    status_less = {"rx": [{k: v for k, v in DOC.items()}]}                   # a prior row without a status keeps it too
    v2, _ = validate_structured(status_less, ""); preserve_untouched_rx_status(status_less, {}, v2)
    assert v2["rx"][0]["generic"] == "Aceclofenac + Paracetamol"
def test_a_spoken_rename_drops_the_old_brands_doctor_generic():           # Review Focus 3
    _cur, _patch, _notes, _t = apply_ops({"rx": [dict(DOC)]}, {"replace": {"rx": [{"from": "Zerodol-P", "to": "Zerodol-SP"}]}})
    assert not any(k in _cur["rx"][0] for k in ("generic", "generic_source", "generic_pending"))
def test_learnable_leaves_doctor_generic_rows_to_the_overlay():
    assert learnable({"rx": [dict(DOC)]}, [0]) == []
def test_print_shows_the_doctors_generic_as_entered_and_never_the_suggestion():
    html = _rx_rows([{"name": "Zerodol-P", "generic": "aceclofenac + Paracetamol", "generic_source": "doctor",
                      "generic_suggestion": "Aceclofenac + Paracetamol"}, {"name": "Xyz", "generic": "", "generic_suggestion": "Secretol"}])
    assert "generic: aceclofenac + Paracetamol" in html and "Secretol" not in html
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q -x tests/test_doctor_generic_rows.py` — Expected: FAIL on the first test.
- [ ] **Step 3: Implement.** `rowcheck.ground_with_notes`: after building the row dict, `row.update(doctor_fields(item, name))`
  and default `generic_suggestion_unknown = unknown_components(row["generic_suggestion"])`; an item that claimed `"doctor"` but
  failed `clean_generic` adds the note `f"rx[{index}] {name}: generic not kept ({problem})"`. `preserve_untouched_rx_status`:
  for a row with `generic_source == "doctor"`, skip `generic` in the `DERIVED_ROW_FIELDS` loop (both the pop branch at
  `:402-403` and the recompute branch at `:407-408`); add a helper `_doctor_generic(row) -> bool`. If plan a put
  `generic_source` into `RECOMPUTED_ROW_FIELDS`, skip it the same way. `ops._regrounded`: exclude `*DOCTOR_GENERIC_FIELDS`.
  `learnable`: `continue` when `row.get("generic_source") == "doctor"`. `pdf/sheet.py:96-97` needs no change (it prints
  `generic`); the test pins it.
- [ ] **Step 4: Run** the new file plus `tests/test_correction.py tests/test_correction_ops.py tests/test_rowcheck.py tests/test_formulary.py tests/test_pdf_sheet.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `feat(pq-g): a doctor generic survives validate, corrections and save`.

### Task 3: AI suggestion in the same `/api/format` call

**Files:**
- Modify: `doctor_dictation/api/format.py:41-63` (`SYSTEM_PROMPT`: one rule + one schema key)
- Test: `tests/test_generic_suggestion_format.py`

**Interfaces:**
- Consumes: Task 2 (`ground_with_notes` keeps/drops the suggestion); `_stub_llm` from `tests/test_correction.py:90`.
- Produces: `/api/format` rows carry `generic_suggestion` and `generic_suggestion_unknown`; `generic_source` never `"doctor"`.
- [ ] **Step 0: Preflight.** Re-read `api/format.py` (plan d rewrote the rules and schema). Number the new rule after plan d's last.
- [ ] **Step 1: Write the failing tests**

```python
from test_correction import _stub_llm
from fastapi.testclient import TestClient
import doctor_dictation.main as M
from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.config import override_settings
def test_prompt_keeps_the_brand_rule_and_asks_for_a_separate_suggestion():
    assert "never replace a brand with its generic" in SYSTEM_PROMPT
    assert '"generic_suggestion"' in SYSTEM_PROMPT and "Never put it in \"name\"" in SYSTEM_PROMPT
def test_suggestion_reaches_the_row_only_without_an_exact_match(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic_suggestion": "Aceclofenac + Paracetamol", "dose": "1-0-1"},
                                   {"name": "Crocin", "generic_suggestion": "Paracetamol", "dose": "SOS"}]})
    rows = TestClient(M.app).post("/api/format", json={"transcript": "tab zerodol-p twice daily, crocin as needed"}).json()["structured"]["rx"]
    assert [r["generic_suggestion"] for r in rows] == ["Aceclofenac + Paracetamol", ""]
    assert [r["generic"] for r in rows][0] == "" and all(r["generic_source"] != "doctor" for r in rows)
def test_a_doctor_source_from_the_llm_is_ignored(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac", "generic_source": "doctor"}]})
    row = TestClient(M.app).post("/api/format", json={"transcript": "zerodol-p"}).json()["structured"]["rx"][0]
    assert row["generic_source"] != "doctor" and row["generic"] == ""
def test_the_rules_only_fallback_has_no_suggestion(monkeypatch):
    override_settings(monkeypatch, openai_api_key="", deepseek_api_key="")
    rows = TestClient(M.app).post("/api/format", json={"transcript": "tab zerodol-p 1-0-1 for 5 days"}).json()["structured"]["rx"]
    assert all(r["generic_suggestion"] == "" for r in rows)
```

- [ ] **Step 2: Run** — Expected: FAIL (prompt text; LLM `generic_source: "doctor"` passes through `ground_with_notes` until the next step).
- [ ] **Step 3: Implement.** `/api/format` must not let the LLM set a doctor generic: before `_validate` (`format.py:157`), drop
  `generic`, `generic_source`, `generic_pending` from every draft row (a helper `doctor_generic.strip_llm_fields(draft) -> dict`
  in Task 1's module). Rule text (exact copy):
  `"<N>. For each rx row also return \"generic_suggestion\": for a brand name you recognise, its active ingredients joined by \" + \" (for example \"Aceclofenac + Paracetamol\"). Use \"\" when the name is already a generic or you are not sure. It is a suggestion for the doctor only. Never put it in \"name\"."`
  Schema rx object gains `"generic_suggestion": "string: ingredients joined by ' + ', or empty"`.
- [ ] **Step 4: Run** this file plus `tests/test_brand_as_dictated.py tests/test_determinism.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `feat(pq-g): AI generic suggestion in the format call`.

### Task 4: A spoken correction can set the generic

**Files:**
- Modify: `doctor_dictation/core/correction.py:39-79` (rule 10 + example), `:416-424` (`build_correction_messages` hides suggestion fields)
- Modify: `doctor_dictation/core/doctor_generic.py` (`patch_generics`)
- Modify: `doctor_dictation/api/format.py:216-218` (call `patch_generics` after `apply_ops`, before `resolve_blank_names`; add its warnings to the response's `warnings`)
- Test: `tests/test_doctor_generic_correction.py`

**Interfaces:**
- Consumes: Tasks 1-2; plan c's `changed_rows` (a generic-only patch row is a patch-named row, so it is in `changed_rows`).
- Produces: `patch_generics(current, patch) -> (patch_copy, warnings)` — the patch whitelist for generic keys. For each patch rx
  row: drop `generic_source`, `generic_suggestion`, `generic_suggestion_unknown`, `generic_pending` (the model never sets them);
  a `generic` equal (casefold) to the current same-name row's `generic` is dropped (an echo, Review Focus 1); any other `generic`
  that passes `clean_generic` becomes `{"generic": cleaned, "generic_source": "doctor", "generic_pending": True}`; one that fails
  is dropped with the warning `f"The generic for {name} was not changed: {problem}"`. Never mutates its inputs.
- [ ] **Step 0: Preflight.** Re-read `correction.py`, `api/format.py` `correct()` (plans c and d edited both).
- [ ] **Step 1: Write the failing tests**

```python
from test_correction import _stub_llm
from fastapi.testclient import TestClient
import doctor_dictation.main as M
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION, build_correction_messages
from doctor_dictation.core.doctor_generic import patch_generics
FORM = {"rx": [{"name": "Zerodol-P", "status": "unknown-medicine", "lexicon_match": "", "dose": "1-0-1"},
               {"name": "Pan 40", "status": "verified", "lexicon_match": "Pantoprazole", "generic": "Pantoprazole"}]}
def test_instruction_teaches_the_generic_key_with_the_owner_example():
    assert '"generic of Zerodol-P is aceclofenac plus paracetamol" -> {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}' in CORRECTION_INSTRUCTION
    assert "Never return \"generic_source\"" in CORRECTION_INSTRUCTION
def test_patch_whitelist():
    p, w = patch_generics(FORM, {"rx": [{"name": "Zerodol-P", "generic": "aceclofenac plus paracetamol", "generic_source": "lexicon"},
                                        {"name": "Pan 40", "dose": "1-0-1", "generic": "pantoprazole"},
                                        {"name": "Dolo", "generic": "<x>"}]})
    assert p["rx"][0] == {"name": "Zerodol-P", "generic": "aceclofenac + paracetamol", "generic_source": "doctor", "generic_pending": True}
    assert p["rx"][1] == {"name": "Pan 40", "dose": "1-0-1"}                  # Review Focus 1: an echo is not a doctor generic
    assert "generic" not in p["rx"][2] and w == ["The generic for Dolo was not changed: " + "Use letters, digits, spaces and . , ' ( ) / - only."]
def test_the_model_never_sees_suggestion_fields():
    form = {"rx": [{"name": "Zerodol-P", "generic_suggestion": "X", "generic_suggestion_unknown": ["X"], "generic_pending": True}]}
    sent = build_correction_messages("t", form)[1]["content"]
    assert "generic_suggestion" not in sent and "generic_pending" not in sent
def test_spoken_generic_end_to_end(monkeypatch):
    _stub_llm(monkeypatch, {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]})
    res = TestClient(M.app).post("/api/v1/correct", json={"transcript": "generic of zerodol-p is aceclofenac plus paracetamol", "current_form": FORM}).json()
    row = res["structured"]["rx"][0]
    assert (row["generic"], row["generic_source"], row["generic_pending"]) == ("Aceclofenac + Paracetamol", "doctor", True)
    assert res["structured"]["rx"][1]["generic"] == "Pantoprazole" and 0 in res.get("changed_rows", [0])
```

- [ ] **Step 2: Run** — Expected: FAIL (`ImportError: patch_generics`).
- [ ] **Step 3: Implement.** Rule text (exact copy, appended after rule 9, before "Examples:"):
  `'10. To set or change a medicine\'s generic (its composition), return that rx row with "name" and "generic": the ingredients joined by " + ". Use "generic" ONLY when the doctor states the generic or composition. Never return "generic_source" or "generic_suggestion".\n'`
  and the example line `'- "generic of Zerodol-P is aceclofenac plus paracetamol" -> {"rx": [{"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"}]}\n'`
  (keep the existing last example last). `build_correction_messages` copies `current_form` and removes
  `generic_suggestion`, `generic_suggestion_unknown`, `generic_pending` from each rx row.
- [ ] **Step 4: Run** this file plus `tests/test_correction.py tests/test_correction_ops.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `feat(pq-g): spoken correction sets a doctor generic`.

### Task 5: Save gate, settle, clinic overlay confirmation count, audit

**Files:**
- Modify: `doctor_dictation/core/safety.py:27-48` (`screen_unverified` blocks pending and invalid doctor generics)
- Modify: `doctor_dictation/core/doctor_generic.py` (`settle`, `new_doctor_generics`)
- Modify: `doctor_dictation/api/persistence.py:220-221` (call `settle(validated)`), `:319` (call `learn_doctor_generics` beside `learn_from_save`); `DocumentCreate` gains `remember_generics: list[int] = []`
- Modify: `doctor_dictation/api/formulary.py` (add `learn_doctor_generics`)
- Test: `tests/test_doctor_generic_save.py`

**Interfaces:**
- Consumes: Task 1; `db/overlay.py: record_confirmation(conn, kind, entry_key, action, data, base_sha, document_id, user_id) -> int`
  (returns the count; index:88-90), `list_rows`; plan f's `shipped_lexicon()` and `entry_sha` (checked at Task 1 Step 0);
  `formulary.key`, `formulary.THRESHOLD` (`core/formulary.py`); `dbmod.log_audit` (`db/__init__.py:260`).
- Produces:
  - `screen_unverified` adds `{"index", "name", "status", "generic": "pending"}` for a row with `generic_source == "doctor"`,
    `generic_pending is True` and its index not confirmed, and `"generic": "invalid"` for a doctor row whose `generic` fails
    `clean_generic` (confirmed or not). A row already blocked for its status gets the `generic` key on the same entry (one entry per row).
  - `settle(validated) -> dict`: pops `generic_pending` from every row; mutates and returns.
  - `new_doctor_generics(structured, confirmed_rows, remember_generics) -> [(index, name, generic)]`: raw rows with
    `generic_source == "doctor"`, `generic_pending is True`, index in `confirmed_rows`, valid name (`formulary.clean_name`) and
    valid generic; a listed brand (`_exact_lookup(name) != ""`) also needs its index in `remember_generics` (Q20); once per name key.
  - `learn_doctor_generics(conn, structured, confirmed_rows, remember_generics, document_id, user_id) -> None` (`api/formulary.py`):
    for each entry, action `"edit"` when the name is an exact brand/alias of a SHIPPED entry (base_sha `entry_sha`), else `"add"`
    (base_sha `""`); `count = record_confirmation(conn, "medicine", formulary.key(name), action, {"name": name, "generic": generic},
    base_sha, document_id, user_id)`; then `log_audit(conn, action="generic.doctor", entity="clinic_overlay",
    entity_id=formulary.key(name), detail={"name", "generic", "action", "document_id", "count", "from_suggestion":
    generic.casefold() == row's generic_suggestion.casefold()})`. Never `upsert`: nothing is live before `THRESHOLD`. Any
    exception is logged and swallowed, like `learn_from_save` (`api/formulary.py:65-66`): the prescription is already saved.
- [ ] **Step 0: Preflight.** Re-read `safety.py`, `persistence.py`, `api/formulary.py`, `db/overlay.py`, `core/overlay.py`.
  Keep our audit row even if `record_confirmation` writes one. Confirm the `/api/format` cache key includes the overlay
  version (`format.py:101`); if not, stop and ask (a generic that went live would not show until the cache entry ages out).
- [ ] **Step 1: Write the failing tests** (client fixture as `tests/test_safety.py:24`; sketched tests use the first save test's fixtures, each comment is its assertion)

```python
DOC = {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol", "generic_source": "doctor", "generic_pending": True,
       "status": "unknown-medicine", "lexicon_match": "", "generic_suggestion": "Aceclofenac + Paracetamol"}
def test_gate_blocks_an_unconfirmed_doctor_generic_even_on_a_verified_row():
    row = {**DOC, "name": "Crocin", "status": "verified", "lexicon_match": "Paracetamol"}
    assert screen_unverified({"rx": [row]}, []) == [{"index": 0, "name": "Crocin", "status": "verified", "generic": "pending"}]
    assert screen_unverified({"rx": [row]}, [0]) == []
    assert screen_unverified({"rx": [{**row, "generic": "<x>"}]}, [0])[0]["generic"] == "invalid"     # Review Focus 5
def test_first_save_is_pending_not_in_the_clinic_list(monkeypatch):
    c = _client(monkeypatch)
    res = c.post("/api/v1/documents", json={"structured": {"rx": [DOC]}, "confirmed_rows": [0]}).json()
    stored = dbmod.get_document(conn, res["document_id"])        # parse its structured JSON
    assert "generic_pending" not in stored_rx[0] and stored_rx[0]["generic"] == "Aceclofenac + Paracetamol"
    rows = overlay.list_rows(conn, "medicine")
    assert [(r["entry_key"], r["action"], r["source"], r["confirm_count"], json.loads(r["data"])) for r in rows] == \
        [("zerodol-p", "add", "doctor", 1, {"name": "Zerodol-P", "generic": "Aceclofenac + Paracetamol"})]
    assert _exact_lookup("Zerodol-P") == ""                       # under the clinic layer: not in the effective list
    audit = [a for a in audit_rows(conn) if a["action"] == "generic.doctor"]
    assert len(audit) == 1 and json.loads(audit[0]["detail"])["from_suggestion"] is True
def test_second_save_in_another_document_goes_live(monkeypatch):
    # two saves, two documents, same generic -> confirm_count 2; offline /api/format "tab zerodol-p 1-0-1" ->
    # row generic "Aceclofenac + Paracetamol", generic_source "lexicon"
def test_resave_of_the_same_document_stays_pending(monkeypatch):   # Review Focus 4
    # first save; re-save with that document_id: (a) the stored structured, confirmed_rows=[] -> 200, no new confirmation;
    # (b) DOC re-confirmed, confirmed_rows=[0] -> confirm_count still 1, _exact_lookup("Zerodol-P") == ""
def test_a_different_generic_restarts_the_count(monkeypatch):
    # doc 1 "Aceclofenac + Paracetamol", doc 2 "Aceclofenac + Serratiopeptidase" -> one row, confirm_count 1, second data, not live
def test_a_listed_brand_counts_only_with_remember(monkeypatch):    # Q20
    # Crocin (shipped exact brand), doctor generic "Paracetamol + Caffeine", confirmed, no remember_generics -> no overlay row,
    # stored row prints "Paracetamol + Caffeine"; two documents with remember_generics=[0] -> one "edit" row, base_sha
    # non-empty, confirm_count 2; a combo_base row (Zerodol-P) counts without remember_generics (first test)
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q -x tests/test_doctor_generic_save.py` — Expected: FAIL on the gate test.
- [ ] **Step 3: Implement** the Produces list. In `create_document`, `settle(validated)` goes right after
  `strip_grounding_markers(validated)` (`persistence.py:221`); `learn_doctor_generics(conn, structured, req.confirmed_rows,
  req.remember_generics, document_id, uid)` goes right after `learn_from_save` (`:319`) and reads the raw `structured`, whose indexes match `confirmed_rows`.
- [ ] **Step 4: Run** this file plus `tests/test_safety.py tests/test_formulary_routes.py tests/test_isolation_formulary.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `feat(pq-g): save gate and clinic list count for a doctor generic`.

### Task 6: Page row rules (rxstate.js, rxview.js wire, app.js hooks)

**Files:**
- Modify: `frontend/rxstate.js:15-24` (`metaOf`), `:74-100` (`rowState`), `:102-107` (`afterEdit`)
- Modify: `frontend/rxview.js:228-230` (`wire`, new export `needsYou(tr)`)
- Modify: `frontend/app.js:933` (`openRows` uses `RxView.needsYou(tr)`), `:981-982` (`refreshBlockPanel` filter, same predicate)
- Modify: `frontend/index.html:258,260` (`rxstate.js?v=8`, `rxview.js?v=9`; `app.js` pin +1)
- Test: `tests/test_frontend_doctor_generic.py`

**Interfaces:**
- Consumes: the row fields of Tasks 2-4.
- Produces:
  - `metaOf` adds `generic_source`, `generic_suggestion` (strings), `generic_pending` (`r.generic_pending === true`),
    `generic_suggestion_unknown` (`optsOf`).
  - `rowState(row, ctx)`: when not confirmed and `row.generic_pending === true` and the state would be `ok` or `known`, the state
    is `confirm` with `canSpell: false`, label `"Confirm generic"` and reason (exact copy)
    `"You entered the generic " + generic + ". Confirm the row before saving."`; a `dose`/`confirm` state keeps its own reason.
  - `afterEdit(meta, "name")` also clears `generic_source`, `generic_suggestion`, `generic_suggestion_unknown`, `generic_pending`,
    and the page-only `generic_listed`, `remember_generic` (Task 7) (Q22).
  - `RxView.wire(tr)` keeps `heard`, `lookalike` first and adds `generic`, `generic_source`, `generic_pending` only when
    `generic_source === "doctor"`, and `generic_suggestion` only when non-empty (so `tests/test_frontend_rxrow.py:238-250` and
    `tests/test_frontend_schedule_dom.py:93-94` stay green unchanged).
  - `RxView.needsYou(tr) -> bool` — `!isBlank(tr) && RxState.rowState(rowOf(tr), ctxOf(tr)).needsYou`.
- [ ] **Step 0: Preflight.** Re-read `rxstate.js`, `rxview.js`, `app.js:925-990` (plans a and c edit them; plan c changes the
  confirmation clearing at `app.js:570-572`).
- [ ] **Step 1: Write the failing tests** (node, like `tests/test_frontend_rxrow.py` `_view_node`)

```python
def test_pending_doctor_generic_turns_a_matched_row_into_confirm_generic():
    r = _state("""RxState.rowState({status: "verified", generic_pending: true, generic: "A + B"}, {})""")
    assert (r["state"], r["label"], r["canSpell"], r["needsYou"]) == ("confirm", "Confirm generic", False, True)
    assert r["reason"] == "You entered the generic A + B. Confirm the row before saving."
    assert _state("""RxState.rowState({status: "verified", generic_pending: true}, {confirmed: true}).state""") == "you"
    assert _state("""RxState.rowState({status: "dose-check", generic_pending: true, dose_note: "n"}, {}).state""") == "dose"
def test_a_name_edit_drops_every_generic_field():                  # Review Focus 3
    m = _state("""RxState.afterEdit(RxState.metaOf({generic: "A", generic_source: "doctor", generic_pending: true,
                   generic_suggestion: "S", generic_suggestion_unknown: ["S"]}), "name")""")
    assert (m["generic"], m["generic_source"], m["generic_pending"], m["generic_suggestion"], m["generic_suggestion_unknown"]) == ("", "", False, "", [])
def test_wire_sends_a_doctor_generic_and_a_suggestion_only():
    r = _view_node("""(() => { const a = {}, b = {}; RxView.attach(a, {generic: "A + B", generic_source: "doctor", generic_pending: true});
                       RxView.attach(b, {generic: "Pantoprazole", generic_source: "lexicon", generic_suggestion: "S"});
                       return [RxView.wire(a), RxView.wire(b)]; })()""")
    assert r[0] == {"heard": "", "lookalike": "", "generic": "A + B", "generic_source": "doctor", "generic_pending": True}
    assert r[1] == {"heard": "", "lookalike": "", "generic_suggestion": "S"}
def test_open_rows_and_the_block_panel_use_the_same_predicate_as_the_bar():
    app = _read("app.js")
    assert "RxView.needsYou(tr)" in app.split("function openRows()")[1].split("}")[0]
```

- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** the Produces list; bump the pins.
- [ ] **Step 4: Run** this file plus `tests/test_frontend_rxrow.py tests/test_frontend_rxspell_dom.py tests/test_frontend_schedule_dom.py tests/test_frontend_spell_modal_dom.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `feat(pq-g): page row rules for a pending doctor generic`.

### Task 7: The editable generic line and "AI suggests" (genericedit.js, rx.css)

**Files:**
- Create: `frontend/genericedit.js` (`window.GenericEdit`, under 200 lines)
- Modify: `frontend/rxview.js:49-55` (generic line: call `GenericEdit.render(tr, r, st, H)`; keep the `rx-gen-tag` branch for a generic-named row)
- Modify: `frontend/rx.css` (after `:69-74`), `frontend/index.html` (load `genericedit.js?v=1` after `rxview.js`, before `app.js`; `rx.css?v=8`; `rxview.js` pin +1 again if Task 6 already shipped)
- Modify: `frontend/app.js` save payload (one line: `remember_generics: GenericEdit.rememberIndexes(rows)`, same row order as `confirmed_rows`)
- Modify: `tests/test_frontend_rxspell_dom.py:97-103` (`_run` also requires `genericedit.js`)
- Test: `tests/test_frontend_generic_edit_dom.py`

**Interfaces:**
- Consumes: Task 6 meta fields; RxView hooks `H.confirmed()`, `H.changed()`, `H.working()`; plan a's `combo_base` row field.
- Produces: `GenericEdit.render(tr, rxState, st, hooks)`, `GenericEdit.problem(text) -> string` (same five messages and rules as
  `doctor_generic.MESSAGES`; client mirror only, the server stays the authority), `GenericEdit.rememberIndexes(rows) -> number[]`
  (indexes of rows with `generic_source === "doctor"` and `meta.remember_generic === true`; sent as `remember_generics`).

Behaviour (copy the strings exactly):

| Row | Line under the name (`div.rx-genbox`, built once per row, NOT `.rx-extra`) |
|---|---|
| `generic` set, differs from the name | `generic: <span class="rx-gen-text" contenteditable>` — prints (today's `.rx-gen`), editable unless view-only |
| `combo_base` set, no generic, no suggestion | button `Add generic` (no-print) → the empty editable span, focused |
| doctor generic replaced a listed one (`meta.generic_listed`) | after the text: `<label class="no-print"><input type="checkbox" class="rx-gen-remember"> Remember for this clinic</label>`, unticked; sets `meta.remember_generic` |
| `generic_suggestion` set, `generic` empty, source not doctor | `AI suggests: <b>X</b>` `[Use this]` `[Type my own]`, whole line `no-print`; class `amber` when `generic_suggestion_unknown` is non-empty, with title `"Not in the medicine list: " + list.join(", ")` |

  - Typing in the span: the span's own `input` listener calls `stopPropagation()` (so `app.js:949-961` does not set status `""`),
    then on each input sets `meta.generic` (trimmed text), `generic_source = "doctor"`, `generic_pending = true` (and
    `generic_listed = true` when the source was `"lexicon"`; Q20: without the tick only this prescription changes), deletes the row
    from `H.confirmed()`, re-renders the state cell only (never rebuilds a focused span), calls `H.changed()`.
    A `problem(text)` other than "" shows in the row's `.rx-note` and keeps the row in `confirm`.
  - `Use this`: same effect with `generic = generic_suggestion`; focus moves to the row's state cell.
  - `Type my own`: shows the empty editable span, focused; the suggestion line hides.
  - Emptying the span on a doctor row: `generic = ""`, `generic_source = ""`, `generic_pending = false` (the doctor removed it).
  - Enter key in the span: blur, no newline.
- [ ] **Step 0: Preflight.** Re-read `rxview.js` and plan a's rendering of `combo_base`; if plan a draws its own prompt
  in `rxview.js`, replace that drawing with `GenericEdit.render` so one place draws the line.
- [ ] **Step 1: Write the failing tests** (fake DOM via `_run`; sketched tests use the first test's fixtures, each comment is its assertion)

```python
def test_typing_a_generic_marks_the_row_doctor_pending_and_unconfirmed():
    r = _run("""const tr = mkRow("g1", "verified", {name: "Crocin"}, {generic: "Paracetamol", generic_source: "lexicon"});
      confirmed.add("g1"); const s = tr.querySelector(".rx-gen-text"); s.textContent = "Paracetamol + Caffeine"; s.dispatch("input");
      console.log(JSON.stringify({m: RxView.wire(tr), c: confirmed.has("g1"), st: tr.dataset.rxstate, status: tr.dataset.status}));""")
    assert r == {"m": {"heard": "", "lookalike": "", "generic": "Paracetamol + Caffeine", "generic_source": "doctor", "generic_pending": True},
                 "c": False, "st": "confirm", "status": "verified"}
def test_use_this_accepts_the_suggestion_and_type_my_own_opens_an_empty_box():
    # row with generic_suggestion "Aceclofenac + Paracetamol": line text "AI suggests: Aceclofenac + Paracetamol", buttons ["Use this", "Type my own"];
    # click Use this -> wire generic == suggestion, generic_source "doctor"; a second row: Type my own -> ".rx-gen-text" empty and focused
def test_amber_when_a_component_is_unknown_and_the_suggestion_never_prints():
    # generic_suggestion_unknown ["Serratiopeptidase"] -> line has classes "rx-sugg no-print amber" and title "Not in the medicine list: Serratiopeptidase"
def test_remember_tick_only_on_an_overridden_listed_generic():      # Q20
    # first test's row after typing: "Remember for this clinic" shown, rememberIndexes [] -> tick -> [0]; combo_base row: no tick
def test_problem_mirrors_the_server_messages():                     # Review Focus 5
    # for each raw in Task 1's cases: GenericEdit.problem(raw) == doctor_generic.generic_problem(raw)
def test_view_only_shows_text_without_edit_or_buttons():
    # Authorship.isViewOnly() true -> span has no contenteditable, no "Use this"/"Add generic" buttons
def test_the_page_loads_genericedit_between_rxview_and_app():
    # index.html order rxview.js?v= < genericedit.js?v= < app.js?v=; rx.css?v=8
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q -x tests/test_frontend_generic_edit_dom.py` — Expected: FAIL.
- [ ] **Step 3: Implement `genericedit.js` and the CSS.** CSS: `.rx-genbox .rx-gen-text` underlined dotted on screen only;
  `.rx-sugg` muted; `.rx-sugg.amber { color: var(--warn); background:#fff8e1; }` (tokens from `styles.css:6`, `:151`);
  `@media print { .rx-genbox .rx-gen-text { border:0; } }`.
- [ ] **Step 4: Run** the whole frontend suite: `.venv/bin/python -m pytest -q -x tests/ -k frontend` — Expected: PASS.
- [ ] **Step 5: Run the full suite** `.venv/bin/python -m pytest -q` — Expected: PASS. **Commit** (ask first): `feat(pq-g): editable generic and AI suggestion on the sheet`.

## Out of scope

Accepting the suggestion by voice; a "Remember" tick by voice; a doctor generic on a generic-named row (the `rx-gen-tag`
path stays); the clinic list screens, `approve` and the pending display (plan f); composition-as-a-list data (spec option E).

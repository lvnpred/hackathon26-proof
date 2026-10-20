# PQ-d: Prompt Rules, Cross-Section Duplicate Cleanup, Vitals Field Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop the AI from guessing a dosage form, putting one item in two sections, restating demographics in prose and
inventing tests; clean the duplicates it still makes; add a `vitals` field that is extracted, validated, corrected,
edited on the page and saved.

**Architecture:** The five new prompt rules live once in a new pure module `core/promptrules.py` and are spliced into
both `SYSTEM_PROMPT` and `CORRECTION_INSTRUCTION`, so the two cannot drift. Vitals live in a new pure module
`core/vitals.py` (coerce, merge, extract from text), called from `validate_structured`, the rules-only fallback and
`merge_form`. A new pure module `core/tidy.py` runs after validation on `/api/format` and `/api/v1/correct` (never on
Save) and removes cross-section duplicates. The page gets a small vitals row in a new `frontend/vitals.js`.

**Tech Stack:** Python 3 / FastAPI, stdlib `re` in `doctor_dictation/core` (purity test), vanilla JS browser globals
tested under node with a fake DOM, pytest.

**Spec:** `docs/superpowers/plans/2026-10-19-prescription-quality-brainstorm.md` (section 0 "Gaps in the prompts",
section 5 causes 1-3) and the shared contract `docs/superpowers/plans/2026-10-19-pq-00-index.md` ("Vitals (plan d)").

**Owner answers 2026-10-19:** Q11 the cleanup (`core/tidy.py`) does not run on Save (Task 6 as written). Q12 removing a
vital by voice is out of scope: OK (the doctor clears it on the page). Q13 vitals are stored with units ("88/min",
"72 kg", "98%", "101 F"): OK (`VITALS_RULE` and the `extract_vitals` table as written). No task changes.

## Global Constraints

- `structured.vitals = {"bp", "pulse", "weight", "spo2", "temp"}`, strings, `""` when not dictated (contract). No other keys.
- The same rules go into both `SYSTEM_PROMPT` and `CORRECTION_INSTRUCTION` (spec section 0, last line).
- Investigations stay a list of strings in this plan; plan h turns them into objects. Do not touch the demo fallback's
  hard-coded investigations (`core/fallback.py:83-100`).
- Do not touch `doctor_dictation/pdf/sheet.py`: printing vitals is plan e. The page's vitals row is `no-print`.
- `doctor_dictation/core` stays stdlib-only (`tests/test_core_purity.py`).
- Files stay under 500 lines: `core/determinism.py` (410) and `core/correction.py` (443) get only a few lines each;
  `frontend/app.js` (1251) gets only call sites, all page code goes in `frontend/vitals.js`.
- Bump `?v=` pins of changed static files: `app.js?v=36` -> `37`, `styles.css?v=11` -> `12`, new `vitals.js?v=1`.
- Tests: `.venv/bin/python -m pytest`; never run the app against the real DB. No commit without the owner's word.
- Preflight for every task: re-read the files it edits; plans a-c run first and may have moved line numbers.

## Review Focus

1. A document saved before this plan (no `vitals` key) is reopened and re-saved: the page shows an empty vitals row,
   Save stores five `""` values, nothing crashes. Tests: Task 3 (`validate_structured({}, "")`), Task 7 (`render(undefined)`).
2. A complaint that only *contains* a diagnosis ("Fever with chills" vs diagnosis "Fever") must stay; only a normalized
   exact match is dropped. Test: Task 6.
3. A number that is not an age at the start of a sentence ("5 mm calculus, right side", "3 days fever") must stay; an
   age clause later in the sentence must stay. Test: Task 6.
4. A correction that states one vital ("BP is now 130/80") must keep the other vitals. Test: Task 5.
5. The AI returns `vitals` in the wrong shape (a string "BP 140/90, pulse 88", numbers, `null`, a list): it is coerced,
   never a 500. Test: Task 3.

### Task 1: Shared prompt rules in both prompts

**Files:**
- Create: `doctor_dictation/core/promptrules.py`
- Modify: `doctor_dictation/api/format.py:41-63` (`SYSTEM_PROMPT`), `doctor_dictation/core/correction.py:39-79` (`CORRECTION_INSTRUCTION`)
- Test: `tests/test_prompt_rules.py` (new)

**Interfaces:**
- Produces: `promptrules.FORM_RULE`, `ONE_SECTION_RULE`, `NO_DEMOGRAPHICS_RULE`, `INVESTIGATIONS_RULE`, `VITALS_RULE`
  (all `str`), `SHARED_RULES: tuple[str, ...]` (those five, in that order), `rules_text(start: int) -> str`
  (`"<start>. <rule>\n<start+1>. <rule>\n..."`).

Exact rule text (the tests pin it):

```python
FORM_RULE = ('form: use the form as dictated ("tablet" -> "Tab.", "capsule" -> "Cap.", "syrup" -> "Syr.", '
             '"injection" -> "Inj."). If no form was dictated, use "". Never guess a form from the medicine name.')
ONE_SECTION_RULE = ("Each item goes into exactly one section: never put the same text in both complaints and diagnosis.")
NO_DEMOGRAPHICS_RULE = ("Never repeat the patient name, age, sex or vitals in complaints, diagnosis or advice; "
                        "they go only in patientName, ageSex and vitals.")
INVESTIGATIONS_RULE = ("investigations: copy each test as dictated. Never add a test that was not dictated. If none "
                       'was dictated, return []. Tests that share a body site stay one item: "X-ray, CT and MRI of '
                       'head and hip" is one item, not three.')
VITALS_RULE = ('vitals: copy only the vitals dictated, with digits: bp "140/90", pulse "88/min", weight "72 kg", '
               'spo2 "98%", temp "101 F". Use "" for each vital not dictated.')
```

- [ ] **Step 1: Write the failing tests** in `tests/test_prompt_rules.py`

```python
from doctor_dictation.api.format import SYSTEM_PROMPT
from doctor_dictation.core import promptrules as R
from doctor_dictation.core.correction import CORRECTION_INSTRUCTION

def test_every_shared_rule_is_in_both_prompts():
    assert len(R.SHARED_RULES) == 5
    for rule in R.SHARED_RULES:
        assert rule in SYSTEM_PROMPT and rule in CORRECTION_INSTRUCTION, rule

def test_rule_text_carries_the_spec_wording():
    assert 'If no form was dictated, use ""' in R.FORM_RULE
    assert "exactly one section" in R.ONE_SECTION_RULE
    assert "Never repeat the patient name, age, sex or vitals" in R.NO_DEMOGRAPHICS_RULE
    assert "Never add a test that was not dictated" in R.INVESTIGATIONS_RULE and "return []" in R.INVESTIGATIONS_RULE
    assert '"X-ray, CT and MRI of head and hip" is one item' in R.INVESTIGATIONS_RULE

def test_rules_text_numbers_from_start():
    assert R.rules_text(8).splitlines()[0].startswith("8. form:") and R.rules_text(8).splitlines()[4].startswith("12. vitals:")

def test_format_schema_has_vitals_and_an_empty_form():
    schema = SYSTEM_PROMPT[SYSTEM_PROMPT.index("{\n"):]
    assert '"vitals": {"bp": "string", "pulse": "string", "weight": "string", "spo2": "string", "temp": "string"}' in schema
    assert '"form": "Tab.|Cap.|Syr.|Inj.|empty"' in schema
    assert schema.index('"opNo"') < schema.index('"vitals"') < schema.index('"complaints"')

def test_correction_prompt_patches_one_vital():
    assert 'return only the vitals the correction states, for example {"vitals": {"bp": "130/80"}}' in CORRECTION_INSTRUCTION
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_prompt_rules.py` — Expected: FAIL (`No module named ...promptrules`).
- [ ] **Step 3: Create `core/promptrules.py`** with the constants above and `rules_text(start: int) -> str`.
- [ ] **Step 4: Edit `SYSTEM_PROMPT`** (`api/format.py:41-63`): rule 1 also names "Vitals"; insert `promptrules.rules_text(8)`
  after rule 7; the JSON-schema rule (today rule 8, `format.py:52`) becomes rule 13. In the schema add the `"vitals"`
  line after `"opNo"` exactly as the test pins it, and change rx `"form"` to `"Tab.|Cap.|Syr.|Inj.|empty"`. The
  inserted text must not contain `"{\n"` (`tests/test_sections_prose.py:55` finds the schema by it).
- [ ] **Step 5: Edit `CORRECTION_INSTRUCTION`** (`correction.py:39-79`): after rule 9, add `promptrules.rules_text(10)`
  then rule 15, verbatim: `'15. vitals: return only the vitals the correction states, for example {"vitals": {"bp": "130/80"}}; the other vitals keep their values.\n'`.
  Keep `"\n2."` as the first rule-2 marker (`tests/test_brand_as_dictated.py:234`).
- [ ] **Step 6: Run** `.venv/bin/python -m pytest -q tests/test_prompt_rules.py tests/test_sections_prose.py tests/test_correction.py tests/test_correction_ops.py tests/test_brand_as_dictated.py tests/test_core_purity.py` — Expected: PASS.
- [ ] **Step 7: Commit** (ask the owner first): `git add doctor_dictation/core/promptrules.py doctor_dictation/api/format.py doctor_dictation/core/correction.py tests/test_prompt_rules.py && git commit -m "Prompt rules: form as dictated, one section, no demographics in prose, no added tests, vitals"`

### Task 2: A form that was not dictated stays ""

Today `rowcheck.ground_with_notes` defaults a missing or unknown form to `"Tab."` (`core/rowcheck.py:25-27`), which
printed "Tab. Insulin Aspart". The dose check already ignores a defaulted form (`rowcheck.py:54`: `given` is `""`
unless the input form equals the output form; `dosing.check_dose` skips the form check when `form` is `""`,
`core/dosing.py:131`), so returning `""` keeps grounding and the dose check unchanged.

**Files:**
- Modify: `doctor_dictation/core/rowcheck.py:25-27`; comments at `doctor_dictation/api/rx.py:48-49` and `doctor_dictation/core/fallback.py:206`
- Test: `tests/test_rowcheck.py:52-54`, `tests/test_dosing_grounding.py:93`

**Interfaces:**
- Produces: `rowcheck._coerce_form(value) -> str`: an `ALLOWED_FORMS` value unchanged; else the first three letters
  (case-insensitive) `tab|cap|syr|inj` map to `"Tab."|"Cap."|"Syr."|"Inj."`; else `""`.

- [ ] **Step 1: Update the tests.** In `tests/test_rowcheck.py:52-54` replace the loop with:

```python
    for form, shown in (({}, ""), ({"form": ""}, ""), ({"form": "empty"}, ""), ({"form": "Tablet"}, "Tab.")):
        got = rowcheck.ground_one({**base, **form}, text, text, "45 / M")
        assert (got["status"], got["form"], got["dose_note"]) == ("verified", shown, "")   # never a form mismatch
```

In `tests/test_dosing_grounding.py:93` expect `("", "", "")` (comment: "no form spoken: none printed"). Add to
`tests/test_rowcheck.py`:

```python
def test_a_form_given_as_dictated_is_still_checked():
    use_fixture(...)  # same Amikacin fixture as test_only_an_explicit_wrong_form_is_a_form_mismatch
    got = rowcheck.ground_one({"name": "Amikacin", "strength": "500 mg", "dose": "1-0-0", "form": "Tab."}, "amikacin 500 mg", "amikacin 500 mg", "45 / M")
    assert got["status"] == "dose-check"
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_rowcheck.py tests/test_dosing_grounding.py` — Expected: FAIL (form is `"Tab."`).
- [ ] **Step 3: Implement `_coerce_form`** and use it at `rowcheck.py:25-27`. Update the two comments (`api/rx.py:48`: the
  page now echoes `""` for an undictated form; `fallback.py:206`: drop "(validated later to Tab.)").
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q` (whole suite: other tests may pin the `"Tab."` default) — Expected: PASS. A test that pinned the default changes to `""`, with a one-line comment.
- [ ] **Step 5: Commit** (ask first): `"Form: an undictated form stays empty instead of Tab."`

### Task 3: `core/vitals.py` and validation

**Files:**
- Create: `doctor_dictation/core/vitals.py`
- Modify: `doctor_dictation/core/determinism.py:375-385` (`validate_structured` output)
- Test: `tests/test_vitals.py` (new)

**Interfaces:**
- Produces:
  - `VITAL_KEYS = ("bp", "pulse", "weight", "spo2", "temp")`, `VITAL_CHARS = 20`
  - `extract_vitals(text: str) -> dict` — five keys; values per the table below; `""` when absent.
  - `coerce_vitals(value) -> tuple[dict, list[str]]` — dict: each known key's value `str(v)` (str/int/float only),
    whitespace collapsed, stripped, cut to `VITAL_CHARS` with warning `"vitals.<key>: shortened to 20 characters"`;
    unknown keys dropped; a `str` value is read with `extract_vitals`; any other type gives five `""`.
  - `merge_vitals(current, patch) -> dict` — `coerce_vitals(current)[0]`, then each non-empty patch value overwrites.
  - `is_vitals_only(text: str) -> bool` — True when removing every `extract_vitals` match, units, `and`, and
    punctuation leaves no word of 2+ letters and no digit.
  - `same_reading(a: str, b: str) -> bool` — the lists of numbers (`\d+(?:\.\d+)?`) in `a` and `b` are equal and non-empty.

`extract_vitals` (case-insensitive, digits only; spoken number words are out of scope):

| Input fragment | Key | Value |
|---|---|---|
| `BP 140/90`, `bp 140 by 90`, `blood pressure 140 over 90` | bp | `140/90` |
| `pulse 88`, `pulse rate 88 per minute`, `PR 88`, `heart rate 88` | pulse | `88/min` |
| `weight 72 kg`, `wt 72.5`, `weight 72 kgs` | weight | `72 kg`, `72.5 kg` |
| `SpO2 98%`, `spo2 98 percent`, `saturation 98` | spo2 | `98%` |
| `temperature 101 F`, `temp 38.5 c`, `temp 101` | temp | `101 F`, `38.5 C`, `101` |

- [ ] **Step 1: Write the failing tests** in `tests/test_vitals.py`

```python
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.vitals import VITAL_KEYS, coerce_vitals, extract_vitals, is_vitals_only, merge_vitals, same_reading

EMPTY = dict.fromkeys(VITAL_KEYS, "")

def test_extract_reads_each_vital():
    v = extract_vitals("BP 140/90, pulse 88, weight 72 kg, SpO2 98%, temperature 101 F. fever for 3 days")
    assert v == {"bp": "140/90", "pulse": "88/min", "weight": "72 kg", "spo2": "98%", "temp": "101 F"}
    assert extract_vitals("blood pressure 140 over 90, heart rate 88 per minute, temp 38.5 c")["bp"] == "140/90"
    assert extract_vitals("temp 38.5 c")["temp"] == "38.5 C" and extract_vitals("fever 5 days, 45 mm stone") == EMPTY

def test_coerce_any_shape():                                  # Review Focus 1 and 5
    assert validate_structured({}, "")[0]["vitals"] == EMPTY
    for bad in (None, [], 7, {"bp": None, "x": "1"}):
        assert coerce_vitals(bad)[0] == EMPTY
    assert coerce_vitals({"pulse": 88, "bp": " 140 / 90 "})[0] == {**EMPTY, "pulse": "88", "bp": "140 / 90"}
    assert coerce_vitals("BP 140/90, pulse 88")[0] == {**EMPTY, "bp": "140/90", "pulse": "88/min"}
    v, w = coerce_vitals({"temp": "x" * 30})
    assert v["temp"] == "x" * 20 and w == ["vitals.temp: shortened to 20 characters"]

def test_merge_keeps_unstated_vitals():
    assert merge_vitals({"bp": "140/90", "pulse": "88/min"}, {"bp": "130/80", "pulse": ""}) == {**EMPTY, "bp": "130/80", "pulse": "88/min"}
    assert merge_vitals(None, None) == EMPTY

def test_vitals_only_and_same_reading():
    assert is_vitals_only("BP 140/90, pulse 88, weight 72 kg, SpO2 98%, temperature 101 F")
    assert not is_vitals_only("BP 140/90, fever for 3 days")
    assert same_reading("88", "88/min") and not same_reading("140/90", "130/90") and not same_reading("", "")

def test_validate_reports_the_cut_and_save_keeps_vitals(tmp_path, monkeypatch):
    out, warnings = validate_structured({"vitals": {"bp": "140/90"}}, "")
    assert out["vitals"]["bp"] == "140/90" and not any("vitals" in w for w in warnings)
    # Save round trip: POST /api/v1/documents with vitals, GET /api/v1/documents/{id} returns them
    # (use the render_prescription stub of tests/test_sections_prose.py:110-115 and TestClient(M.app)).
```

Finish the last test with the save round trip as commented: `structured.vitals.bp == "140/90"` after GET.

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_vitals.py` — Expected: FAIL (`No module named ...vitals`).
- [ ] **Step 3: Implement `core/vitals.py`** (stdlib `re` only).
- [ ] **Step 4: Wire `validate_structured`**: after building `out` (`determinism.py:375-385`), add
  `out["vitals"], notes = vitals.coerce_vitals(d.get("vitals")); warnings += notes`. Key order: put `"vitals"` after
  `"opNo"` in `out`. Import with a relative import; `vitals.py` must not import `determinism` at module level.
- [ ] **Step 5: Run** `.venv/bin/python -m pytest -q` — Expected: PASS (`tests/test_today.py:161` compares a stored
  form, not a validated one; if another test compares a validated dict exactly, add `"vitals"` to its expectation).
- [ ] **Step 6: Commit** (ask first): `"Vitals: coerce, merge, extract; validate_structured always returns vitals"`

### Task 4: Vitals in the rules-only fallback

Today the rules path puts a vitals sentence into complaints: `fallback_format(normalize_transcript("78 year old male. BP 140/90, pulse 88, ..."))`
returns `complaints == ["BP 140/90, pulse 88, weight 72 kg, SpO2 98%, temperature 101 F", "Fever for 3 days"]` (probed on `main`).

**Files:**
- Modify: `doctor_dictation/core/fallback.py` (rules branch only: the `out` dict at `:72-82` and the final `return out` at `:225`; not the demo branch `:83-100`)
- Test: `tests/test_vitals.py`

**Interfaces:**
- Consumes: `extract_vitals`, `is_vitals_only` (Task 3).

- [ ] **Step 1: Write the failing test**

```python
def test_rules_path_fills_vitals_and_drops_the_vitals_sentence():
    from doctor_dictation.core.determinism import normalize_transcript
    from doctor_dictation.core.fallback import fallback_format
    out = fallback_format(normalize_transcript("78 year old male. BP 140/90, pulse 88, weight 72 kg, SpO2 98%, "
                                               "temperature 101 F. fever for three days. tab dolo 650 mg twice daily"))
    assert out["vitals"] == {"bp": "140/90", "pulse": "88/min", "weight": "72 kg", "spo2": "98%", "temp": "101 F"}
    assert out["complaints"] == ["Fever for 3 days"]
    assert fallback_format("BP 140/90, fever for 3 days")["complaints"]      # a mixed sentence is kept whole
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_vitals.py -k rules_path` — Expected: FAIL (`KeyError: 'vitals'`).
- [ ] **Step 3: Implement**: `"vitals": dict.fromkeys(VITAL_KEYS, "")` in the initial `out`; before the final `return out`,
  set `out["vitals"] = extract_vitals(text)` and drop complaints for which `is_vitals_only` is True.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_vitals.py tests/test_rules_rows.py tests/test_rules_split.py tests/test_determinism.py tests/test_sections_prose.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `"Rules path: vitals field, vitals-only sentence leaves complaints"`

### Task 5: Vitals in a spoken correction

`merge_form` (`core/correction.py:242-266`) handles a key that is neither a list nor a scalar with `out[key] = pat_val`
(`:261-262`): a patch `{"vitals": {"bp": "130/80"}}` would wipe the pulse.

**Files:**
- Modify: `doctor_dictation/core/correction.py:242-266`
- Test: `tests/test_vitals.py`

**Interfaces:**
- Consumes: `merge_vitals` (Task 3). Produces: `merge_form` merges `vitals` per key.

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_form_patches_one_vital():                                    # Review Focus 4
    from doctor_dictation.core.correction import merge_form
    cur = {"vitals": {"bp": "140/90", "pulse": "88/min"}, "complaints": ["Fever"]}
    out = merge_form(cur, {"vitals": {"bp": "130/80"}})
    assert out["vitals"]["bp"] == "130/80" and out["vitals"]["pulse"] == "88/min" and out["complaints"] == ["Fever"]
    assert merge_form(cur, {})["vitals"]["bp"] == "140/90"

def test_correct_route_keeps_other_vitals(monkeypatch):
    # stub the LLM with patch {"vitals": {"bp": "130/80"}} (copy _stub_llm from tests/test_correction.py:90)
    # POST /api/v1/correct {"transcript": "BP is now 130 by 80", "current_form": cur}
    # assert j["structured"]["vitals"] == {"bp": "130/80", "pulse": "88/min", "weight": "", "spo2": "", "temp": ""}
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_vitals.py -k "merge_form or correct_route"` — Expected: FAIL (pulse lost).
- [ ] **Step 3: Implement**: in `merge_form`, a `key == "vitals"` branch: `out["vitals"] = merge_vitals(cur_val, pat_val)`.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_vitals.py tests/test_correction.py tests/test_correction_ops.py` — Expected: PASS.
- [ ] **Step 5: Commit** (ask first): `"Correction: a spoken vital patches that vital only"`

### Task 6: `core/tidy.py`: cross-section duplicate cleanup

Runs after validation on `/api/format` (all three branches) and `/api/v1/correct`; never on Save, so a doctor's own
text is never rewritten at Save. Placed in a new module because `determinism.py` is at 410 lines.

**Files:**
- Create: `doctor_dictation/core/tidy.py`
- Modify: `doctor_dictation/api/format.py:70-72` (`_validate`), `:110-111`, `:157-158`, `:170-171`, `:219-228`
- Test: `tests/test_tidy.py` (new)

**Interfaces:**
- Consumes: `prose.PROSE_FIELDS` (`core/prose.py:6`), `vitals.extract_vitals`, `is_vitals_only`, `same_reading` (Task 3).
- Produces: `tidy_sections(structured: dict, fields: tuple[str, ...] = PROSE_FIELDS) -> list[str]` — mutates
  `structured`, returns one warning per change. In `fields`, in order:
  1. **Demographics lead:** strip a leading clause and re-capitalise the first letter; drop the item if nothing is left.
     The clause is: optional the stored `patientName` (casefolded match) then `[,;:]`; then an age-sex phrase
     `(?:a\s+)?\d{1,3}\s*-?\s*(?:y|yr|yrs|year|years)\.?(?:\s*-?\s*old)?(?:\s*/?\s*(?:male|female|man|woman|boy|girl|m|f))?\b`
     or `\d{1,3}\s*/\s*[mf]\b`; then a separator: `\s*[,;:.]\s*`, or `\s+(?:with|having)\s+` (removed), or
     `\s+(?=c/o|h/o|k/c/o)` (the c/o stays). No separator, or the phrase is not at the start: unchanged.
     Warning: `"<field>[<i>]: removed the patient's details from the start (they print in the patient line)"`.
  2. **Vitals-only item:** an item with `is_vitals_only` True whose extracted vitals do not conflict with
     `structured["vitals"]` (a key is a conflict when both are non-empty and not `same_reading`): fill the empty vitals
     from it and drop the item. Warning: `"<field>[<i>]: moved to vitals"`. A conflict keeps the item.
  3. **Same item in two sections** (when `fields` is non-empty): drop each complaint whose normalized text equals a
     normalized diagnosis item (casefold, whitespace collapsed, `" .,;:"` stripped at both ends).
     Warning: `"complaints: dropped \"<text>\", the same as a diagnosis"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_tidy.py`

```python
from doctor_dictation.core.tidy import tidy_sections

def _s(**kw):
    base = {"patientName": "", "complaints": [], "diagnosis": [], "vitals": dict.fromkeys(("bp", "pulse", "weight", "spo2", "temp"), "")}
    return {**base, **kw}

def test_drops_a_complaint_equal_to_a_diagnosis():                      # spec 5, cause 1 (document 11)
    s = _s(complaints=["Headaches.", "Fever with chills"], diagnosis=["headaches", "Fever"])
    w = tidy_sections(s)
    assert s["complaints"] == ["Fever with chills"] and s["diagnosis"] == ["headaches", "Fever"]   # Review Focus 2
    assert w == ['complaints: dropped "Headaches.", the same as a diagnosis']

def test_strips_a_leading_demographics_clause():                        # spec 5, cause 2
    s = _s(patientName="Rahul Sharma", complaints=["78 yr old male, c/o fever for 3 days", "Rahul Sharma, 45 / M: cough",
                                                   "45-year-old female with knee pain", "65 yrs M c/o giddiness", "78 yr old male."])
    tidy_sections(s)
    assert s["complaints"] == ["C/o fever for 3 days", "Cough", "Knee pain", "C/o giddiness"]

def test_leaves_numbers_that_are_not_a_leading_age():                  # Review Focus 3
    keep = ["5 mm calculus, right side", "3 days fever", "Fever in a 78 yr old male, since 2 days", "45 years history of smoking"]
    s = _s(complaints=list(keep))
    assert tidy_sections(s) == [] and s["complaints"] == keep

def test_moves_a_vitals_only_line_unless_it_conflicts():
    s = _s(complaints=["BP 140/90, pulse 88", "Fever"]); s["vitals"]["pulse"] = "88"
    tidy_sections(s)
    assert s["complaints"] == ["Fever"] and s["vitals"]["bp"] == "140/90" and s["vitals"]["pulse"] == "88"
    s = _s(complaints=["BP 150/100"]); s["vitals"]["bp"] = "140/90"
    tidy_sections(s)
    assert s["complaints"] == ["BP 150/100"]

def test_fields_limits_the_scope():
    s = _s(complaints=["78 yr old male, cough"], diagnosis=["78 yr old male, bronchitis"])
    tidy_sections(s, ("diagnosis",))
    assert s["complaints"] == ["78 yr old male, cough"] and s["diagnosis"] == ["Bronchitis"]

def test_format_and_correct_routes_tidy(monkeypatch):
    # /api/format: stub make_llm (pattern: tests/test_sections_prose.py:153) whose complete_json returns
    #   {"complaints": ["Headache", "78 yr old male, c/o fever"], "diagnosis": ["headache"], "rx": []}
    #   -> j["structured"]["complaints"] == ["C/o fever"]; the two warnings are in j["warnings"]
    # /api/v1/correct: stub patch {"diagnosis": ["Cough"]}, current_form complaints ["Cough", "78 yr old male, fever"]
    #   -> complaints == ["78 yr old male, fever"]  (dedupe runs; the untouched complaint is not stripped)
```

Use a unique transcript in the format test (the in-memory cache key includes it, `format.py:101`).

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_tidy.py` — Expected: FAIL (`No module named ...tidy`).
- [ ] **Step 3: Implement `core/tidy.py`.**
- [ ] **Step 4: Wire `/api/format`**: add `async def _validate_draft(data, transcript, raw) -> tuple[dict, list]` in
  `format.py` = `_validate` + `tidy_sections(structured)` + `prose.cap_items(structured)`; use it in the three branches
  (`:110-111`, `:157-158`, `:170-171`) instead of `_validate` + `cap_items`. Tidy runs before `cache_put`.
- [ ] **Step 5: Wire `/api/v1/correct`**: after `flag_unsure_rows` (`format.py:222`), `fields = tuple(f for f in
  prose.PROSE_FIELDS if isinstance(patch2.get(f), list) and patch2.get(f))`; `tidy_notes = tidy_sections(structured, fields)`
  only when `fields`; append `tidy_notes` to the response `warnings` (`:228`).
- [ ] **Step 6: Run** `.venv/bin/python -m pytest -q` — Expected: PASS.
- [ ] **Step 7: Commit** (ask first): `"Cleanup: same item in two sections, demographics lead, vitals-only line"`

### Task 7: Vitals row on the page

**Files:**
- Create: `frontend/vitals.js`
- Modify: `frontend/index.html:98-104` (row under `.patient-row`), `:264-265` (script tag), `:7` (`styles.css?v=12`);
  `frontend/styles.css:110-112`; `frontend/app.js:646-648` (`serializeForm`), `:911` (`renderSheet`), `:1214-1221` (New patient), `index.html:265` (`app.js?v=37`)
- Test: `tests/test_frontend_vitals.py` (new); bump pins in tests that assert them

**Interfaces:**
- Consumes: the five `structured.vitals` keys.
- Produces: `window.Vitals = { KEYS, render(v), read() }`. `KEYS = ["bp", "pulse", "weight", "spo2", "temp"]`;
  element ids `vBp, vPulse, vWeight, vSpo2, vTemp`. `render(v)` sets each `textContent` from `v[key]` (non-string or
  missing -> `""`); `read()` returns all five keys, text with whitespace collapsed and trimmed.

Markup (inside `#sheet`, so the existing `sheetEl` input listener at `app.js:949-950` marks the sheet dirty):

```html
<div class="sub vitals-row no-print" id="pVitals" role="group" aria-label="Vitals">
  <span class="vl">BP</span><span class="pf pv" id="vBp" contenteditable="true" data-placeholder="140/90"></span>
  <!-- same pair for Pulse/vPulse "88/min", Weight/vWeight "72 kg", SpO2/vSpo2 "98%", Temp/vTemp "101 F" -->
</div>
```

`no-print`: printing vitals is plan e (PDF). CSS: `.vitals-row` reuses `.patient-row`'s flex layout with a smaller
gap; `.pv { min-width:48px }`; `.vl { font-size:12px; color:#555 }`.

- [ ] **Step 1: Write the failing tests** in `tests/test_frontend_vitals.py` (node + fake DOM, pattern `tests/test_frontend_sections.py:12-27`)

```python
def test_render_and_read_round_trip():
    r = _run("""Vitals.render({ bp: "140/90", pulse: 88, weight: "  72   kg " }); const a = Vitals.read();
      Vitals.render(undefined); const b = Vitals.read();
      console.log(JSON.stringify({ a, b, text: els.vPulse.textContent }));""")
    assert r["a"] == {"bp": "140/90", "pulse": "", "weight": "72 kg", "spo2": "", "temp": ""}   # a number is not text: ""
    assert r["b"] == dict.fromkeys(("bp", "pulse", "weight", "spo2", "temp"), "") and r["text"] == ""   # Review Focus 1

def test_page_wires_vitals():
    app = (FRONT / "app.js").read_text(encoding="utf-8")
    assert "base.vitals = Vitals.read();" in app and "Vitals.render(s.vitals);" in app and "Vitals.render({});" in app
    html = (FRONT / "index.html").read_text(encoding="utf-8")
    assert html.index("vitals.js?v=1") < html.index("app.js?v=37") and 'id="pVitals"' in html and "styles.css?v=12" in html
    assert 'class="sub vitals-row no-print"' in html
```

- [ ] **Step 2: Run** `.venv/bin/python -m pytest -q tests/test_frontend_vitals.py` — Expected: FAIL (no `vitals.js`).
- [ ] **Step 3: Implement** `frontend/vitals.js` (IIFE, `"use strict"`, like `frontend/sections.js`), the markup, CSS,
  script tag `<script src="vitals.js?v=1"></script>` before `app.js`, and the three `app.js` call sites:
  `base.vitals = Vitals.read();` after `base.opNo` (`:648`); `Vitals.render(s.vitals);` after `setText($("pOp"), ...)`
  (`:912`); `Vitals.render({});` in New patient after `setText($("pOp"), "")` (`:1216`). Bump the pins.
- [ ] **Step 4: Run** `.venv/bin/python -m pytest -q tests/test_frontend_vitals.py tests/test_frontend_*.py` — Expected: PASS (fix any test pinning `app.js?v=36` or `styles.css?v=11`).
- [ ] **Step 5: Commit** (ask first): `"Page: vitals row (edit, save, correction carries it)"`

### Task 8: Whole suite and live-LLM check

- [ ] **Step 1: Run** `.venv/bin/python -m pytest -q` — Expected: all pass, no new skips beyond node-missing ones.
- [ ] **Step 2: Manual, owner's machine, with an LLM key and a temp `DB_PATH`** (never the dev DB). Dictate or POST to
  `/api/format`: `"Patient Ravi 78 year old male, BP 140 by 90, pulse 88. Headache for 2 days. Diagnosis headache.
  Insulin aspart 10 units before food. Get X-ray, CT and MRI of head and hip."` Expected: `vitals.bp == "140/90"`,
  `pulse` set; complaints do not start with "78" and do not repeat "Headache" from diagnosis; the insulin row's
  `form` is `"Inj."` or `""`, never `"Tab."`; `investigations == ["X-ray, CT and MRI of head and hip"]` (one item, nothing
  added). Then correct with "BP is now 130 by 80": only `bp` changes. Restart the server first: the format cache is
  in memory (`determinism.py:403-410`) and holds pre-change answers. Record pass/fail per line in the hand-off note.

---

## Out of scope (left deliberately)

- Printing vitals and the empty form on the PDF (`pdf/sheet.py:93` prints `form` then name): plan e.
- Investigation objects, catalogue and the demo fallback's hard-coded tests (`core/fallback.py:59-60`, `:83-100`): plan h.
- Removing a vital by voice ("remove the pulse"): the doctor clears it on the page; `ops.apply_ops` is unchanged.
- Spoken number words in the rules path ("one forty by ninety" normalizes to "1 forty by ninety"): digits only.
- Sending the raw transcript alongside the normalized one (spec section 0, last gap row): not decided by the owner.

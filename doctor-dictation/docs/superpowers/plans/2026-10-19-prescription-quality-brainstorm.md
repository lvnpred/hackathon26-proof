# Prescription quality: generics, confirmations, investigations, print

**Status:** Brainstorm and proposal only. No code written. Written 2026-10-19 from a code read of `main` (9bf466e) and the
saved documents in the dev database. Turn the approved items into task-by-task plans before building.

## Summary (read this first)

Six problems, each traced to a cause in the code. None of them is mainly a prompt-wording problem.

| # | Problem | Root cause | Proposed direction |
|---|---|---|---|
| 1 | Some generics are wrong | The fuzzy name lookup (84 % similarity) maps a combination brand to its single-drug parent: "Zerodol-P" gets "Aceclofenac" only | Generic only on an exact match; detect brand suffixes; doctor-editable generic with a source; AI check only as a disagree flag |
| 2 | Generics cannot be edited | The screen shows the generic as text only, and the server recalculates it on every correction and save | Store `generic_source`; a doctor's generic is never recalculated and is learned into the clinic list |
| 3 | Investigations are made up | Investigations have no reference list and no "was it dictated?" check; the prompt never forbids adding tests | Investigation catalogue + transcript check + clinic list with "Add to list", like medicines |
| 4 | Confirmed rows ask again after a correction | Confirmations live only in browser memory and every correction clears all of them; they are never saved on the row | Clear only the changed rows; store confirmation on the row; tie it to a row fingerprint |
| 5 | Name/age/vitals print twice | The template prints them once; the repeats come from content: the same item in two sections, demographics restated in the history text, no vitals field, possibly pre-printed letterhead labels | Vitals field; prompt rules; cleanup step that removes duplicates across sections; letterhead reader skips fill-in labels |
| 6 | Print wastes space | Every section prints, empty ones as "—"; lists print one bullet per line | Skip empty sections; inline lists; group investigations by category; tighter Rx table |

### Decisions needed

1. **Generics:** build A+B only (fast, stops wrong prints) or A+B+C (also doctor-editable generics with a source)? See section 1.
2. **Investigations:** should a test that was never dictated **block** Save, or **warn** only? (Lean: warn; a red "not dictated" item may block.)
3. **Investigations:** what seeds the catalogue: a curated list of about 150 tests, a LOINC common subset, or the clinic's lab price list?
4. **Investigations print:** canonical name, short code ("RFT"), or as dictated? (Lean: short code.)
5. **Duplicates:** share one PDF that shows the duplicated fields, to confirm which cause in section 5 applies.

### Decisions made

- **2026-10-19, decision 1:** build A + B + C. Show a generic only on an exact match ("100 % confident"); otherwise
  leave it blank and let the doctor dictate or type it. The app stores the doctor's generic and learns it.
  - The AI may suggest a generic (a separate field in the same format call); it fills the blank only when the doctor
    taps "Use this", and then counts as the doctor's (`generic_source: doctor`). Never printed or learned before that.
  - ~~A doctor-entered generic goes live in the clinic list right away~~ Superseded by the learning threshold below.
  - `formulary.learnable` must use exact matching too; today a near match ("Zerodol-P" ≈ "zerodol") blocks learning.
- **2026-10-19, decision 2:** a test not heard in the dictation (red) blocks Save until the doctor keeps or removes it;
  a heard but unknown test (amber) warns only. A hand-typed test is the doctor's own, never red.
- **2026-10-19, scope (MVP 1):** everything learned is clinic-specific: stored in that clinic's own database
  (`/data/clinics/<slug>/app.db`), never written into the shipped files (`drugs.json`, the future
  `investigations.json`), which a code update replaces. Cross-clinic promotion stays a manual operator step.
- **2026-10-19, decision 3:** seed the investigation catalogue with a curated list of about 150 common Indian OPD
  tests; the owner reviews it. New requirement: screens to view the medicine and investigation lists, with edit, so
  the review is easy (extends the Team page's "Clinic medicines" tab, which today lists and removes only:
  `api/formulary.py:73`, `:83`).
- **2026-10-19, decision 3a:** the app admin edits the shared lists on a review screen; edits are saved as pending
  changes and exported, then folded into `drugs.json` / `investigations.json` by a commit and deploy (git stays the
  source of truth).
- **2026-10-19, clinic lists (overlay):** each clinic owns its medicine and investigation lists as an **overlay**: the
  clinic's `app.db` stores only its changes (add, edit, hide) on top of the shipped list, which stays the fallback.
  Shipped fixes reach every entry a clinic has not touched. When a shipped change hits an entry the clinic edited,
  the **clinic wins** and its list screen flags "updated in the shared list" (Keep mine / Take new). A shipped entry
  with a **`safety` mark** (set only by the app admin) overrides the clinic edit, with a notice. Learned medicines,
  doctor generics and learned tests become overlay rows. Every clinic edit is audited and has "Reset to default".
- **2026-10-19, decision 4:** an investigation prints as dictated, plus the catalogue's full name in brackets when the
  two differ ("RFT (Renal Function Test)"; "Renal Function Test" alone when dictated in full; an unknown test as
  dictated). Each item is editable on the sheet (voice correction, typing, remove); an item is
  `{text, canonical, status, source}`. A sheet edit changes that prescription only, unless the doctor ticks
  "Remember for this clinic", which writes an overlay row (counted towards the learning threshold below).
- **2026-10-19, learning threshold (supersedes "right away"):** nothing a doctor enters on a prescription joins the
  clinic list on the first save. A doctor generic (medicines) and a "Remember for this clinic" test (investigations)
  become a **pending** clinic-list row; it goes live after **2** confirmed saves in different prescriptions with the
  same value (one constant, `formulary.THRESHOLD`, the rule `clinic_formulary` already uses; raise to 3 by changing it).
  A different value restarts the count. The prescription itself still prints what the doctor entered. Edits a clinic
  admin makes on the clinic list screen are deliberate and go live at once; the screen shows pending rows
  ("1 of 2") with "Approve now". Reason: keeps one-off misspellings out of the clinic list.
- **2026-10-19, decision 5 (duplicates):** the owner's PDF (gsr-clinic, OP-20261019-001) shows the cause is the
  **letterhead**: the vision reader copied the pad's blank fill-in labels ("Name: M F Age: Date:" in the header,
  "Visit After / Submit" in the footer) as literal text lines, and the app prints its own patient line too. Build:
  (1) the letterhead reader skips fill-in labels (prompt rule in `templates/builder.py` + a code filter);
  (3) the letterhead review screen can delete a line, with likely fill-in lines pre-ticked "remove" (today a cleared
  line is rejected: `pdf/layout.py:49-52`); (4) when the same profile field (phone, address) is in both header and
  footer, the review screen asks which to keep. Fill-in slots (2) deferred: backlog card (al). No separate operator
  fix for gsr-clinic: the delete-a-line screen (3) fixes it. Causes 1-3 of section 5 (same item in two sections,
  demographics in prose, no vitals field) remain valid fixes for other documents.

### Out of scope here

No code changes. The app was not run. The PDF with the duplicates was not seen; `encounter_13.pdf` shows none.

---

## 0. What prompt is sent to the AI

The app makes three AI calls. Only the first two touch prescriptions.

| Call | Prompt | What the AI gets |
|---|---|---|
| Structure a dictation (`/api/format`) | `SYSTEM_PROMPT` | System prompt, then `Raw Dictated Audio Transcript: """<normalized text>"""`. Up to `FORMAT_LLM_CAP` repair rounds when drug names do not ground. |
| Apply a spoken correction (`/api/v1/correct`) | `CORRECTION_INSTRUCTION` | The current form and the correction text; returns only the changes (a patch). |
| Read a letterhead photo | `VISION_SYSTEM` | Not related to prescription content. |

The AI never decides the generic. The prompt says "never replace a brand with its generic"; the generic is added by code
afterwards. A prompt change therefore cannot fix wrong generics.

### Gaps in the prompts (with evidence)

| Gap | Evidence | Proposed rule |
|---|---|---|
| No rule on the dosage form | Document 13: "Tab. Insulin Aspart" (insulin is an injection) | "Use the form as dictated; if not dictated, use \"\"." |
| No rule that an item belongs to one section | Document 11: "Headaches", "mathimarku" in both complaints and diagnosis | "Each item goes into exactly one section." |
| No vitals field in the output schema | Vitals land in complaints or diagnosis, or are dropped | Add `vitals` (BP, pulse, weight, SpO2, temperature) |
| No rule keeping name/age out of the history text | Rule 5 extracts them; rule 7 does not forbid restating them | "Never repeat name, age, sex or vitals in prose sections." |
| No rule against adding investigations | Document 13: "Brain impulses" printed as a test | "Copy each test as dictated. Never add a test that was not dictated. If none, return []." |
| Tests are split and the body site copied onto each | Document 11: "X-ray / CT scan / MRI of the head and hip" as three items | "Keep \"X-ray, CT and MRI of head and hip\" as one item." |
| The AI sees only the normalized transcript | If the drug-name cleanup changes a word wrongly, the AI cannot see the original | Consider sending the raw transcript alongside, marked as reference |

The same rules go into both `SYSTEM_PROMPT` and `CORRECTION_INSTRUCTION`, so a correction cannot reintroduce a problem.

---

## 1. Generics are wrong

### How it works today

```
dictated name ─► exact brand/alias match? ─yes─► generic = that entry's canonical
                        │no
                        └─► closest key at 84 % similarity ─► generic = that key's canonical
```

Each entry in `drugs.json` has exactly one `canonical`. The generic shown and printed is that canonical. A combination
product is right only when it was added as its own entry (Shelcal, Ultracet are). Only 7 entries use `generic_hidden`.

### Probe against the live `drugs.json`

| Dictated | Matched to | Generic shown | Correct composition |
|---|---|---|---|
| Zerodol-P | zerodol | Aceclofenac | Aceclofenac + Paracetamol |
| Pantop-D | pantop | Pantoprazole | Pantoprazole + Domperidone |
| Glycomet-GP | glycomet | Metformin | Metformin + Glimepiride |
| Amlong-A | amlong | Amlodipine | Amlodipine + Atenolol |
| Ecosprin-AV | ecosprin | Aspirin | Aspirin + Atorvastatin |

The brand import already rejects this trap ("Amozid-CV is heard as Amozid", check 5 in `lexicon_import.py`). The runtime
lookup does not apply the same caution.

### Options

| Option | What it does | Cost | Safety gain |
|---|---|---|---|
| **A. Exact-only generic** | Show a generic only on an exact brand or alias match. A fuzzy match may still suggest the name, but the generic stays blank. | Small | High: removes every case in the probe |
| **B. Suffix detection** | Name = known brand + suffix (-P, -D, -GP, -AV, -CV, -XT, -LC, -AM, -H, Plus, Forte, MR, SR…) → unknown combination: blank generic, "Add generic" prompt. | Small | High |
| **C. Doctor-editable generic with a source** | Store `generic_source`: `lexicon`, `doctor` or `llm`. A doctor's generic is stored, never recalculated, and learned into `clinic_formulary` (which already stores name and generic). | Medium | Puts the doctor in charge |
| **D. AI check before writing** | Small extra call: "Brand X as dictated. Is Y the right composition?" Disagreement turns the row amber. The AI never writes the generic. | Medium + latency | Medium: the AI can invent Indian brand compositions |
| **E. Better data** | Store a composition as a list, not one name. Source it from the CDCI brand→generic map the import already uses. | Large | Highest, long term |

Principle: the drug list **suggests**, the doctor **decides**, the AI only **flags disagreement**.

```
dictated name
  ├─ exact brand/alias match ──► generic from drug list        (source: lexicon)
  ├─ fuzzy or brand+suffix ────► generic blank, "Add generic"  (needs doctor)
  └─ doctor types or edits ────► stored, never recalculated    (source: doctor)
                                  └─► learned into the clinic drug list
  optional: AI check disagrees ──► row turns amber; nothing is overwritten
```

**Recommendation:** A and B now, C next, E as data work, D only as a disagree flag.

---

## 2. Generics cannot be edited

- The screen renders the generic as a display-only line under the name.
- The server recalculates it from `name` + `lexicon_match` on every correction and save (`RECOMPUTED_ROW_FIELDS`).

An input box alone is not enough: the server would overwrite it. Needed:

1. A `generic_source` field on the row. `doctor` means "never recalculate".
2. An editable generic on the screen. Editing it sets the source to `doctor` and needs the row confirmed.
3. Learning: a confirmed doctor generic is written to `clinic_formulary`, so the next dictation of that brand shows it.
4. Print: show the doctor's generic exactly as entered.

---

## 3. Investigations are not grounded (new feature)

### Today: investigations vs medications

| Step | Medications | Investigations |
|---|---|---|
| Reference list | `drugs.json` (brands, aliases) | **None** |
| "Was it dictated?" check | Yes | **No** (`prose.unheard` covers complaints and diagnosis only) |
| Validation | Grounded, with a status on each row | Only cut to a maximum length |
| Clinic learns from saves | `clinic_formulary`, confirmed rows only | **None** |
| Prompt rule | "Never invent… drugs" | Only "Extract… Investigations Advised" |

The offline fallback also hard-codes demo investigations ("Urine Culture & Sensitivity, Serum Creatinine, Follow-up USG
KUB"). It triggers only when every demo phrase is present, but it can print tests nobody dictated.

### Proposed flow

```
dictated text ──► AI extracts tests (as dictated, no expansion)
                      │
           ┌──────────┴───────────┐
   heard in transcript?       not heard
           │                      └──► RED: "not dictated" — remove or confirm
     in catalogue / clinic list?
       ├─ yes ──► GREEN: canonical name ("RFT" → Renal Function Test)
       └─ no  ──► AMBER: "New test — add to clinic list?"
                        └─ doctor confirms ──► saved in clinic list, green next time
```

### Parts

1. **Investigation catalogue** (`investigations.json`): canonical name, aliases, category, short print code.

   ```json
   {"canonical": "Complete Blood Count", "aliases": ["cbc", "hemogram"], "category": "Blood", "print": "CBC"}
   ```

2. **"Was it dictated?" check** for each investigation item, reusing the matching that medicines and `prose.unheard` use.
3. **A status on each item.** Investigations become objects `{text, canonical, status, source}` instead of plain strings.
   Old documents still load: a plain string reads as unchecked.
4. **Clinic investigations list** with an "Add to list" action. Only confirmed items are learned (same rule as
   `formulary.learnable`). Items used across many clinics can be promoted to the catalogue through `promotion.py`.
5. **Prompt rules** in both prompts (see section 0).
6. **Fallback cleanup:** make the demo example test-only, or label its output clearly.

Bonus: the catalogue's category gives the grouped print in section 6 almost for free.

### Open choices

| Question | Options | Lean |
|---|---|---|
| Does an unverified test block Save? | Block, or warn only | Warn only; a red "not dictated" item may block |
| First catalogue source | Curated ~150 tests, LOINC common subset, clinic lab price list | Curated now, clinic list grows it; the lab list if the clinic has one |
| What prints | Canonical, short code, as dictated | Short code |

---

## 4. Confirmations are lost after a correction

Confirmations exist only in browser memory (`state.confirmed`). They are not on the row and not in the database.

| Event | What happens | Correct? |
|---|---|---|
| Spoken correction | `state.confirmed.clear()` wipes **all** rows, even untouched ones | No: the server keeps untouched rows' status on purpose (`preserve_untouched_rx_status`) |
| `/api/v1/correct` request | Confirmations are not sent | No |
| Save | `confirmed_rows` goes only into the audit log | No: the stored prescription does not record it |
| Reopen a saved document | Confirmations cleared | No: follows from the save behaviour |
| Hand edit of a row | That row's confirmation cleared | Yes, keep |

### Fix ideas

1. **Clear only the changed rows.** The server already knows which rows the correction named; return them as
   `changed_rows`. Smallest fix.
2. **Store the confirmation on the row:** `confirmed_by`, `confirmed_at` in the stored prescription. Survives save and reopen.
3. **Tie it to a row fingerprint** of name, strength, form and dose. If a correction leaves all four unchanged, the
   confirmation stays; any change invalidates it automatically.

---

## 5. Name/age/vitals printed twice

The PDF template prints name, age and OP number once on page 1. Pages 2+ repeat them in the top margin, and that is
turned off on the first page. `encounter_13.pdf` shows no duplication. The repeats come from content.

| Likely cause | Status | Fix |
|---|---|---|
| Same item in two sections | **Confirmed**: document 11 | Prompt rule + cleanup step that drops a complaint equal to a diagnosis item |
| AI restates demographics/vitals in the history ("78 yr old male, BP 140/90, c/o…") | Likely; nothing forbids it | Prompt rule; cleanup step strips a leading demographics clause |
| No vitals field | **Confirmed** in the schema | Add `vitals`, print once under the patient line |
| Letterhead with pre-printed "Name: / Age:" labels read as literal text | Possible | Letterhead reader skips fill-in labels |

---

## 6. Print layout: save space

**Before** (document 11):

```
INVESTIGATIONS ADVISED
  • X-ray of the head and hip
  • CT scan of the head and hip
  • MRI of the head and hip
```

**After:**

```
Investigations: X-ray, CT, MRI — head & hip
```

Ideas, cheapest first:

1. **Skip empty sections** instead of printing "—". Biggest saving for the least effort.
2. **Inline short lists:** investigations and advice on one line, separated by commas or "·".
3. **Group investigations by category:** "Blood: CBC, RFT · Imaging: USG KUB, MRI brain". Needs the catalogue (section 3).
4. **Complaints and diagnosis side by side** in two columns.
5. **Tighter Rx table:** one column "1-0-1 · After food · 5 days"; drop Instructions when every row's is empty.
6. **Vitals strip** under the patient line: "BP 130/80 · P 82 · Wt 64 kg".

Sketch of a compact page body:

```
18 Oct 2026 | OP-20261018-001 | Rajinikanth 78 / M
BP 130/80 · P 82 · Wt 64 kg
──────────────────────────────────────────────────────────
History                          | Diagnosis
C/o fever with chills, 3 days.   | Viral fever
──────────────────────────────────────────────────────────
Investigations: Blood: CBC, RFT · Imaging: USG KUB
Rx
 1  Tab. Paracetamol 650 mg   1-0-1 · After food · 5 days
 2  Tab. Zerodol-P            1-0-1 · After food · 3 days
       generic: Aceclofenac + Paracetamol
Advice: Fluids 3 L/day · Rest
Review: 1 week (Sun 25 Oct 2026)
```

---

## Suggested order

| Step | Item | Why first |
|---|---|---|
| 1 | Generics A + B | Stops wrong compositions printing; small |
| 2 | Confirmations: clear only changed rows | Small; removes daily friction |
| 3 | Prompt rules (form, one section, no added tests, no demographics in prose) | Text-only change; cuts duplicates and invented tests |
| 4 | Print: skip empty sections, inline lists | Small template change |
| 5 | Investigations catalogue + transcript check + clinic list | Larger; needs decisions 2–4 |
| 6 | Generics C (editable, with source); confirmation stored on the row | Data model change |
| 7 | Vitals field + compact layout + grouped investigations | Builds on 3 and 5 |
| 8 | Generics E (composition as a list) | Data work |

---

## Appendix: code references

| Claim | Location |
|---|---|
| Format system prompt | `doctor_dictation/api/format.py:41-63` |
| Format user message | `doctor_dictation/api/format.py:120-123` |
| Repair loop | `doctor_dictation/api/format.py:132-153` |
| "Never replace a brand with its generic" | `doctor_dictation/api/format.py:48` |
| Output schema (no vitals) | `doctor_dictation/api/format.py:53-63` |
| Correction prompt | `doctor_dictation/core/correction.py:39-79` |
| Correction endpoint (no confirmations sent) | `doctor_dictation/api/format.py:180-228` |
| Letterhead vision prompt | `doctor_dictation/templates/builder.py:16-51` |
| Fuzzy canonical lookup (0.84) | `doctor_dictation/core/determinism.py:241-255` |
| Alias map, brands claimed second | `doctor_dictation/core/determinism.py:89-114` |
| Generic = lexicon match | `doctor_dictation/core/surface.py:47-54`, `doctor_dictation/core/determinism.py:328` |
| `generic_hidden` | `doctor_dictation/core/surface.py:57-80` |
| Generic recalculated on correction/save | `doctor_dictation/core/correction.py:270-298`, `doctor_dictation/core/rowcheck.py:72` |
| Generic display-only on screen | `frontend/rxview.js:50-51` |
| Generic printed under the brand | `doctor_dictation/pdf/sheet.py:96-97` |
| Import check 5 (brand + suffix trap) | `doctor_dictation/core/lexicon/lexicon_import.py` docstring |
| Clinic list stores name + generic | `doctor_dictation/core/formulary.py:55-74` |
| Investigations only length-capped | `doctor_dictation/core/determinism.py:381` |
| Unheard check covers prose only | `doctor_dictation/core/prose.py:6` |
| Fallback demo investigations | `doctor_dictation/core/fallback.py:59-60`, `:83-100` |
| Confirmation set in browser | `frontend/app.js:38` |
| Correction clears all confirmations | `frontend/app.js:570-572` |
| Reopen clears confirmations | `frontend/app.js:311` |
| Hand edit clears that row | `frontend/app.js:954-956` |
| Server keeps untouched rows' status | `doctor_dictation/core/correction.py:364-376` |
| `confirmed_rows` only in audit log | `doctor_dictation/api/persistence.py:308-319` |
| Patient line printed once | `doctor_dictation/pdf/sheet.py:313` |
| Pages 2+ identifier, off on page 1 | `doctor_dictation/pdf/sheet.py:240-249` |
| Empty sections print "—"; one bullet per item | `doctor_dictation/pdf/sheet.py:21-32`, `:88`, `:318-319` |
| Evidence: "Tab. Insulin Aspart", "Brain impulses" | dev DB, document 13 |
| Evidence: same items in complaints and diagnosis; split tests | dev DB, document 11 |

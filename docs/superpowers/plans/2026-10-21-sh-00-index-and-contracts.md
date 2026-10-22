# Spoken hints (SH): plan index and shared contracts

**Status:** plans being written (2026-10-21). Code baseline: `main` at 8c9ce76 (hints and silence trimming on,
first save records the speech settings). Explainer for the owner: https://claude.ai/artifact/5R6M5a6m2M6znMpiYTyV7o

This file is the single source of truth for names, tables and interfaces that cross plan boundaries. The four plans
are written in parallel and rely on this file, not on each other's text. Conventions in
`docs/superpowers/plans/2026-10-13-00-index-and-contracts.md` section 2 apply (writing-plans header, under 500 lines,
no commits, test-first with real code, offline tests, `.venv/bin/python -m pytest tests/ -q`, verify before quoting
line numbers). Every plan starts with a preflight step: re-read the files it edits, because earlier plans in the order
will have changed them. When a plan and this file disagree, this file wins; report the disagreement.

## 1. Order

| # | Plan file | Builds | Needs | Estimate |
|---|---|---|---|---|
| 1 | `2026-10-21-sh-h1-spoken-terms.md` | `spoken_terms` table + ledger, filled on save, backfill command; hints become the doctor's spoken forms (with usual strength), sentence-style prompt | baseline | 3–4 days |
| 2 | `2026-10-21-sh-h2-mishearings.md` | `spoken_mishearings` (heard → saved) from saved rows' `heard`; tier 1 in hints; admin list and remove | H1 | 2–3 days |
| 3 | `2026-10-21-sh-h3-diagnosis-links.md` | `term_links` diagnosis ↔ term; optional `context` field on `/api/transcribe`; correction recordings send the draft's diagnosis; tier 2 in hints (near-tie cut to SH-B4, 2026-10-21) | H1 | 3 days |
| 4 | `2026-10-21-sh-h4-patient-context.md` | Patient found from the spoken name/OP number after transcription (no UI step); the patient's earlier terms are tier 3 in correction hints (near-tie cut to SH-B4) | H1, H3 (the `context` field) | 2–3 days |

Backlog (not planned): section 7.

## 2. Owner decisions (2026-10-21, binding)

1. **Said = shown = printed = hinted.** Whatever the doctor dictates (brand or generic, with strength when spoken or
   added) is shown and printed as dictated, and the hint list is built from those same spoken forms. A hint never
   replaces a spoken name with another name (today `core/hints.py:26` turns "Dolo" into "Paracetamol"; H1 ends that).
2. **No "pick the patient first" step.** The patient is named inside the dictation. H4 uses the spoken name/OP number
   after transcription (option A). The early-clip variant (option B) is backlog card SH-B1.
3. Hints and trimming stay on (`.env.production.example`, commit 8c9ce76).
4. Diagnosis-aware matching uses counts (`term_links`), not vectors. Vectors are backlog card SH-B3.

**Owner answers to the plan writers' questions (2026-10-21, "accept all recommendations"):**

5. H1: the person-like filter runs only on names no medicine or test list knows; the patient-word check runs on all.
   Term weight = `formulary.usage_score` (log2 of uses, decayed), the clinic list's rule.
6. H2: everyone in the clinic may read the mishearing list; only admins remove (the clinic medicine list's rule).
   Names the doctor TYPES over a misheard one are not learned now (backlog SH-B5).
7. H4: patient rows with the same name, age and sex count as ONE person for the lookup (read-only grouping; records
   are never merged). The spoken name must match EXACTLY after casefolding and collapsing spaces (no 0.9 fuzzy
   match: "Asha Verma" vs "Usha Verma" scores 0.9). This replaces the similarity rule in section 5.6.
8. H3/H4: the near-tie cut stands (SH-B4).
9. Investigations catalogue: the owner will review `docs/working/2026-10-19-prescription-quality/investigations-draft.csv`
   so plan PQ-h Task 1 Step 6 can ship `core/lexicon/investigations.json` (absent on `main`; grounding is off).

## 3. Safety and privacy rules (every plan)

- **S1 (no boost; backlog card (c) of `2026-10-17-i1-backlog-suggestion-ideas.md` stands).** No context source
  (doctor usage, mishearing pairs, diagnosis links, patient history) changes a row's `name`, `status` or `generic`,
  and none moves a candidate in Spell it or Did you mean outside the I1-r1 near-tie band (`round(top - score, 6) <=
  0.03`, `formulary.tie_break`). Inside the band, context may reorder. A lexicon name keeps its slot.
- **S2 (what may leave the clinic).** Only medicine and investigation phrases go to a speech engine, and only
  *hint-eligible* ones: a medicine whose base name `drugnames._exact_lookup` knows (brand, alias or generic) or
  that `formulary.active_layer().get` returns; an investigation the catalogue or clinic overlay knows. Anything else
  is stored but never sent. Diagnosis text, patient names and the `context` field never go to a speech engine.
- **S3 (patient words).** A term is not recorded when `formulary.person_like(name)` is true or a word of 3+ letters is
  in `fdb.patient_words(conn)`, the same rule as `formulary.learnable` (`core/formulary.py:55`).
- **S4 (never blocks a save).** Every save hook is wrapped like `learn_from_save` (`api/formulary.py:75`): log and
  continue. The prescription is already saved.
- **S5 (count once).** Every count uses a `*_docs` ledger keyed on `document_id`, so a re-save never counts twice
  (pattern: `db/formulary.py:8 record_confirmation`).

## 4. Facts found in the code (verified 2026-10-21 on 8c9ce76)

1. `build_hints(doctor_top, limit)` (`core/hints.py:39`) fills a 500-character budget (`MAX_HINT_CHARS`, `:13`) from:
   `_doctor_canonical(doctor_top)` (`:26`), `active_layer().hint_names()` (`core/formulary.py:108`, max 10 names /
   150 chars), `common_lexicon_names()` (`:18`, ranked by brand count). `_doctor_canonical` runs each name through
   `_canonical_lookup` (`core/drugnames.py:234`), which returns the GENERIC and drops "Dolo 650", "Pan 40", "Urimax".
2. `_doctor_top` (`api/stt.py:21`) calls `top_medicines(conn, min(30, limit), doctor_id=scope.user_id)`
   (`db/__init__.py:380`, scans the newest `TOP_MEDICINES_WINDOW = 500` finalized documents' JSON every request).
3. Prompt-style providers join hints with ", ": `OpenAiCompatibleStt.transcribe` (`providers/stt/openai.py:22`,
   OpenAI and Groq), `providers/stt/local.py:87-88` (appends to `initial_prompt`). Keyword providers take a list:
   AssemblyAI `keyterms` (`providers/stt/assemblyai.py:37`, `MAX_KEYTERM_WORDS`), Muse `keywords`
   (`providers/stt/muse.py`, `_request`).
4. A saved Rx row holds `name` (as dictated or corrected), `strength`, `form`, `generic`, `generic_source`, `heard`,
   `doctor_confirmed`, `source`, `status` (checked on a real saved row). `heard` = the raw-transcript words the name
   came from, "" when the name is in the transcript as written (`core/lasa.py:100 heard_as`).
5. Save path (`api/persistence.py`, `create_document`): after the document row and audit, it calls `learn_from_save`,
   `learn_doctor_generics`, `remember_from_save` in that order. `ident.user_id` is the doctor in multi-clinic mode;
   `ident` is None in single-database mode.
6. Migrations: numbered SQL in `db/migrations/`, applied by filename (`db/__init__.py:80 migrate`). Latest: `010`.
   Each clinic has its own database; every new table needs an isolation test like `tests/test_isolation_formulary.py`.
7. `POST /api/transcribe` (`api/stt.py:47`) takes only `audio`. The page calls it from `transcribe(blob)`
   (`frontend/app.js:486`) for both the first dictation and spoken corrections; a correction then posts
   `/api/v1/correct` with `current_form` (`frontend/app.js:572`).
8. Patients are matched only by OP number today (`db/__init__.py:151 find_patient_by_op`). `patients(name, age_sex,
   op_no)`, `encounters(patient_id, doctor_id)`, `documents(encounter_id, structured_json)`.
9. Usage decay exists: `HALF_LIFE_DAYS = 30` (`core/formulary.py:21`). Reuse the same decay for term weight.

## 5. Contracts

### 5.1 Tables (each plan owns one migration; numbers are fixed here)

```sql
-- 011_spoken_terms.sql (H1)
CREATE TABLE spoken_terms (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id     INTEGER NOT NULL DEFAULT 0,      -- users.id; 0 = single-database mode
    kind          TEXT    NOT NULL CHECK (kind IN ('medicine','investigation')),
    term_key      TEXT    NOT NULL,                -- spoken.key(spoken)
    spoken        TEXT    NOT NULL,                -- as shown and printed, no strength: "Dolo"
    form          TEXT    NOT NULL DEFAULT '',     -- latest form seen: "Tab"
    generic       TEXT    NOT NULL DEFAULT '',     -- checks only; never hinted in place of spoken
    uses          INTEGER NOT NULL DEFAULT 0,
    first_used_at TEXT    NOT NULL,
    last_used_at  TEXT    NOT NULL,
    removed_at    TEXT,
    UNIQUE (doctor_id, kind, term_key)
);
CREATE TABLE spoken_term_strengths (
    term_id  INTEGER NOT NULL REFERENCES spoken_terms(id),
    strength TEXT    NOT NULL,                     -- as saved: "650 mg"
    uses     INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (term_id, strength)
);
CREATE TABLE spoken_term_docs (
    term_id     INTEGER NOT NULL REFERENCES spoken_terms(id),
    document_id INTEGER NOT NULL REFERENCES documents(id),
    PRIMARY KEY (term_id, document_id)
);

-- 012_spoken_mishearings.sql (H2)
CREATE TABLE spoken_mishearings (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    term_id       INTEGER NOT NULL REFERENCES spoken_terms(id),
    heard_key     TEXT    NOT NULL,                -- spoken.key(heard)
    heard         TEXT    NOT NULL,                -- "dollo"
    confirm_count INTEGER NOT NULL DEFAULT 0,      -- active at >= formulary.THRESHOLD (2)
    first_seen_at TEXT    NOT NULL,
    last_seen_at  TEXT    NOT NULL,
    removed_at    TEXT,
    UNIQUE (term_id, heard_key)
);
CREATE TABLE spoken_mishearing_docs (mishearing_id INTEGER NOT NULL REFERENCES spoken_mishearings(id),
    document_id INTEGER NOT NULL REFERENCES documents(id), PRIMARY KEY (mishearing_id, document_id));

-- 013_term_links.sql (H3)
CREATE TABLE term_links (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    doctor_id     INTEGER NOT NULL DEFAULT 0,
    diagnosis_key TEXT    NOT NULL,                -- spoken.diagnosis_key(line)
    term_id       INTEGER NOT NULL REFERENCES spoken_terms(id),
    count         INTEGER NOT NULL DEFAULT 0,      -- used at >= 2
    last_seen_at  TEXT    NOT NULL,
    UNIQUE (doctor_id, diagnosis_key, term_id)
);
CREATE TABLE term_link_docs (link_id INTEGER NOT NULL REFERENCES term_links(id),
    document_id INTEGER NOT NULL REFERENCES documents(id), PRIMARY KEY (link_id, document_id));
```

H4 adds no table: a patient's earlier terms come from `documents` joined to `encounters` (section 5.6).
**Hackathon note:** `docs/hackathon/02-architecture.md` planned `011_timeline.sql` on the `hackathon` branch. Once
these land on `main`, the timeline migration takes the next free number (014 or later).

### 5.2 `core/spoken.py` (pure, H1; H2–H4 add functions, never change these)

```python
@dataclass(frozen=True)
class Term:            # one saved row's contribution
    kind: str          # "medicine" | "investigation"
    key: str
    spoken: str        # "Dolo"
    form: str          # "Tab" or ""
    strength: str      # "650 mg" or ""
    generic: str

@dataclass(frozen=True)
class HintTerm:        # one candidate for the hint list
    phrase: str        # "Dolo 650"
    weight: float      # decayed uses (HALF_LIFE_DAYS)
    tier: int = 0      # 0 plain, 1 misheard before (H2), 2 diagnosis-linked (H3), 3 this patient (H4)
    term_id: int = 0   # spoken_terms.id (amended 2026-10-21): H2/H3 lift tiers by id; 0 = not from the table
    key: str = ""      # spoken.key(spoken) (amended 2026-10-21): H4 matches patient terms by key

def key(text) -> str                                  # casefold, "&" -> " and ", non-alphanumerics -> one space, strip
def terms_from_save(structured, known_patient_words) -> list[Term]   # medicines from rx, investigations from items; S3
def usual_strength(strength_uses: dict[str, int]) -> str            # the strength in >= 60% of uses and >= 2 uses, else ""
def phrase(spoken: str, usual: str) -> str                          # "Dolo" + "650 mg" -> "Dolo 650" (a trailing " mg" dropped)
def rank(terms: Sequence[HintTerm]) -> list[HintTerm]               # tier desc, weight desc, phrase casefold
def diagnosis_key(line: str) -> str                                 # H3: key(line)[:80]; "" when under 3 letters
```

### 5.3 Hint pipeline

- `core/hints.py build_hints(doctor_terms: Sequence[HintTerm] = (), limit: int = 70) -> list[str]`. H1 changes the
  first source from `_doctor_canonical(names)` to `rank(doctor_terms)` phrases, keeps the clinic layer and common
  lexicon sources after it, keeps the 500-character budget measured on the **rendered prompt** (section 5.4), and
  applies S2 to every phrase. Duplicates across sources compare by `spoken.key`.
- `api/stt.py _doctor_top` is replaced by `_doctor_terms(context) -> list[HintTerm]` (H1 adds it with
  `context=None`; H3/H4 fill tiers from the context). It reads the tables through `db/spoken.py`, never by scanning
  documents (the `top_medicines` scan stays for any other caller; check with `grep -n top_medicines`).
- `db/spoken.py` (SQL only): `record_terms(conn, doctor_id, terms, document_id)` (H1),
  `doctor_hint_terms(conn, doctor_id, today) -> list[HintTerm]` (H1; returns EVERY live term of the doctor with
  `term_id` and `key` set, uncapped, so a tier lift can reach any term; `build_hints` applies the budget), `record_mishearings(...)` and
  `active_mishearing_term_ids(...)` (H2), `record_links(...)` and `linked_term_ids(conn, doctor_id,
  diagnosis_keys) -> set[int]` (H3), `patient_term_keys(conn, patient_ids, doctor_id, visits=3) -> set[str]` (H4; one id or the ids of one
  same-name/age/sex group, item 7; the 3-visit window spans the group).

### 5.4 Prompt rendering

`core/hints.py prompt_text(phrases) -> str` = `". ".join(phrases) + "."` when there are phrases, else "". Used by
`OpenAiCompatibleStt` and `local.py` instead of `", ".join` (H1). Keyword providers keep the list. Existing tests that
assert the comma form change only their expected string.

### 5.5 Save hook

`api/spoken.py learn_spoken_terms(conn, structured, document_id, user_id) -> None`, called in `create_document`
right after `remember_from_save`, under S4. H1 records terms; H2 adds the mishearings and H3 the diagnosis links
inside the same function (one hook, one place). A backfill command `python -m doctor_dictation.admin
backfill-spoken-terms` (H1) replays every finalized document of every clinic through the same function; the ledger
makes it safe to run twice.

### 5.6 The `context` field (H3 defines, H4 uses)

`POST /api/transcribe` accepts an optional multipart field `context`: a JSON string of at most 4096 bytes,
`{"diagnosis": [str], "patient": {"name": str, "age_sex": str, "op_no": str}}` (at most 10 diagnosis lines of 200
characters each). Missing, malformed or oversize: ignored (one log line), never a 4xx; status codes and the 200 body
do not change. The page sends it only when a draft is on the sheet (a spoken correction), built from the sheet's
diagnosis lines and patient fields. H4's patient rule: OP number exact match, else name similarity >= 0.9
(casefolded, spaces collapsed) with the same sex letter and age within one year when both give them; exactly one
candidate or nothing. Candidates: in multi-clinic mode only patients with an encounter by this doctor.

## 6. Open decisions for the owner (defaults apply until answered)

- **D-SH1** A separate, labelled "You used before / For this diagnosis / This patient's earlier medicines" group in
  Spell it, below the sound-alikes and never the first button. Default: **not built** (backlog SH-B2).
- **D-SH2** Usual strength rule: >= 60% of uses and >= 2 uses. Default as stated.
- **D-SH3** H2 admin view lives on the Team screen's "Clinic medicines" tab. Default as stated.

## 7. Backlog cards (not planned)

- **SH-B1 Early clip for patient hints (option B).** About 10 s into a recording, upload the audio so far for a quick
  transcription, find the patient (section 5.6 rule) and have patient hints ready before Stop. Needs the recorder to
  emit chunks (`mr.start()` with no timeslice today, `frontend/app.js:377`). Cost: ~10 s extra audio per visit; no
  extra wait. Size M (~3 days). Pick up only if the per-save settings data shows first dictations still miss names a
  patient regularly takes.
- **SH-B2 Labelled context group in Spell it** (D-SH1). Size S–M. Needs an owner yes; must keep S1.
- **SH-B4 Near-tie context in Spell it** (cut from H3 and H4, 2026-10-21). `/api/format`'s cache key
  (`api/format.py:125-126`) has no doctor id and is built before the diagnosis exists, and Did you mean is computed
  inside the cached draft (`_DYM_CACHE`, `core/rowcheck.py:239`), so context there would leak between doctors or
  go stale. Safer route: send the diagnosis and patient fields on `POST /api/v1/rx/check-row` and apply the 0.03
  near-tie rule in Spell it only. Size M. Must keep S1.
- **SH-B5 Learn from typed fixes.** Typing a name clears the row's `heard` (`frontend/rxstate.js:116`), so H2 learns
  nothing from it. Keep the last heard text when the doctor types over a misheard name. Size S. Must keep S1.
- **SH-B3 Vectors for diagnosis wording** ("throat infection" ≈ "pharyngitis"), local only (`sqlite-vec` + a small
  local embedding model). Only if exact `diagnosis_key` matches prove too narrow in real data.

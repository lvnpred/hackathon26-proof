# I1-r1: Usage Ranking of the Clinic Formulary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Summary.** This plan builds rows 1 and 3 of the usage-ranking brainstorm. Row 1: the clinic's learned names go to the speech engine most-used first. Today they go most-recently-seen first. Row 3: in Spell it, usage only breaks near-ties between the clinic's own sound-alike names. No page change, no schema change, no change to the `/api/format` cache key. Adds 8 tests. Runs AFTER I1-h3 and I1-h4, and BEFORE the final whole-branch review.

**Decision needed from the owner (one).** Approve Decision 3: the clinic's learned names may appear in Spell it suggestions, for rows that have no lexicon match, at their plain sound-alike score (no boost). Today they never appear there (`core/rowcheck.py:77-89` offers lexicon names only). Without this, row 3 has nothing to reorder, because a lexicon drug always has a clinic count of zero (`core/formulary.py:64` never learns a lexicon name). If the answer is no, do Tasks 1, 2 and 4 only (5 tests).

**Goal:** Rank the clinic layer by usage blended with recency (speech hints), and use that usage as a tie-break only among near-equal clinic sound-alikes (Spell it, `POST /api/v1/rx/check-row`).

**Architecture:** The rank is pure: `core/formulary.py` gains `usage_score`, `ranked_layer`, `tie_break` and `sound_alikes`. `ClinicLayer` gains one optional field, `usage`. The api layer (`api/formulary.load_layer`, I1-h3) builds the layer with `ranked_layer` instead of in recency order. `core/candidates.py` exposes the scores it already computes. `core/rowcheck.suggestions` calls `sound_alikes` for rows with no lexicon match. The SQL, the Team tab and the page stay unchanged.

**Tech Stack:** Python 3 / FastAPI / sqlite3 (stdlib), vanilla JS, pytest. No new dependency.

**Spec:** the owner's choice of rows 1 and 3 of the usage-ranking brainstorm (`.superpowers/sdd/2026-10-16-i1-h-formulary/progress.md:23`). Contracts: `docs/superpowers/plans/2026-10-16-i1-00-index-and-contracts.md` sections 4.1 (row JSON unchanged), 4.4 (`suggestions` list) and 4.5 (page state unchanged).

**Assumptions about earlier plans** (re-find every anchor with `grep -n`; line numbers are from the worktree on 2026-10-17, with I1-h1 and I1-h2 applied and I1-h3/I1-h4 not yet built)**:**

- Produced by I1-h1/I1-h2 and on disk now: `core.formulary.key`, `ClinicLayer(items)` with `.get`, `.version`, `.hint_names()`, `activate`, `active_layer`, `MAX_HINTS = 10`, `HINT_CHARS = 150`, `THRESHOLD = 2` (`core/formulary.py:15-109`); `db.formulary.record_confirmation`, `list_active` (keys `id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by`, `ORDER BY last_seen_at DESC, id DESC`), `remove` (sets `confirm_count = 0`) (`db/formulary.py:8-41`); `build_hints` order doctor names, layer names, lexicon names inside 500 characters (`core/hints.py:39-56`); `rowcheck.suggestions` (`core/rowcheck.py:77-89`).
- Produced by I1-h3 (not built yet; taken from the I1-h3 plan text and the rulings in `progress.md:11-22`): (A1) `api/formulary.load_layer()` returns `formulary.ClinicLayer(tuple((r["name"], r["generic"] or "") for r in fdb.list_active(conn)))` inside a `try/except sqlite3.Error`; (A2) the async dependency `use_clinic_layer` sits on `POST /api/v1/rx/check-row` (and on format, correct, transcribe, documents); (A3) the `/api/format` cache key is `clinic:layer-version:key:rawhash` with `ClinicLayer.version`; (A4) `tests/conftest.py` has an autouse temp `DB_PATH` fixture that lets a test set its own `DB_PATH`; (A5) the fail-loud guard is a pin test plus a once-per-process warning when a request reads the default empty layer, a log line and not an exception. Checked against the I1-h3 work in progress on 2026-10-17: A1 matches `api/formulary.py:29` word for word, A2 is at `api/rx.py:54`, and A5 is the app-wide `request_scoped` dependency (`api/formulary.py:35-37`). Re-check after I1-h3 lands.
- Produced by I1-h4: (A6) the Team "Clinic medicines" tab shows `GET /api/v1/formulary` in the order the API gives (`list_active` order). This plan changes neither.

**Produces:** `core.formulary`: `HALF_LIFE_DAYS = 30`, `BAND = 0.03`, `POOL = 3`, `usage_score(confirm_count, last_seen_at, today) -> float`, `ranked_layer(rows, today) -> ClinicLayer`, `ClinicLayer.usage` and `.usage_of(name) -> float`, `tie_break(scored, usage_of) -> list[str]`, `sound_alikes(name, k=POOL) -> list[str]`. `core.candidates`: `scored_candidates(name, k=3) -> list[(canonical, score)]`, `similarity(name, spelling) -> float`. New file `tests/test_formulary_usage.py` (8 tests).

## Global Constraints

- `core/` stays pure (`tests/test_core_purity.py`): the new code imports only `math`, `datetime` and `core.candidates`. Usage comes in as data (the rows), and "today" is a parameter.
- No source file over 500 lines (`tests/test_file_sizes.py:12`). Untouched by this plan: `core/determinism.py` (408), `core/correction.py` (431 now), `db/__init__.py` (487), `api/persistence.py` (421 after I1-h3), `db/formulary.py` (41).
- Existing endpoints keep their status codes and JSON shapes. `GET /api/v1/formulary` exposes no usage field. Row JSON (contract 4.1) gains nothing.
- No PHI: the rank reads only `confirm_count` and `last_seen_at` of names already learned (`db/formulary.py:5`). No patient, doctor or document identity enters the rank.
- Tests offline: stub LLM, no network. Test command `.venv/bin/python -m pytest tests/ -q`. In the worktree, `-c` probes need `PYTHONPATH=.`. No commits: every "commit" step is "leave uncommitted".

## Review Focus

The inputs most likely to bite, and where each is pinned:

| Input | Expected | Pinned in |
|---|---|---|
| One drug confirmed 200 times vs a brand-new look-alike | Hints: the 200-count drug stays ahead. Spell it: if the typed name is closer to the new one by more than 0.03, the new one stays first ("Zorbexem": Zorbexim 1.0 before Zorbexin 0.79) | Tests 1, 6 |
| A removed name | Not in the layer, so no hint and no suggestion; `usage_of` is 0.0 | Test 4 |
| A removed name learned again | Count restarts at 2 (`db/formulary.py:39`), so it ranks as new | Test 4 |
| Cold clinic, empty layer | Hints and suggestions exactly as today | Tests 3, 6 |
| Two near-equal twins (vowel twins score an exact 1.0 tie) | The more used first; a lexicon name keeps its slot | Tests 5, 6 |
| Very high counts, future or bad dates | No overflow; `2**63 - 1` scores 63.0; a future date counts as today; a bad date scores 0.0 | Test 2 |
| A lexicon-matched row, a dictated brand | Suggestions exactly as today; the row keeps the dictated name | Tests 6, 7 |

## Decisions (and why)

1. **The blend (row 1).** `score = log2(1 + confirm_count) × 0.5 ^ (age_days / 30)`, rounded to 6 places. `age_days` is whole UTC days from `last_seen_at` to today, never below 0. Ties go to the more recently seen name, then to the name key (`key(name)`), so the order is total and does not depend on input order.
   - **Why log2.** Counts are heavy-tailed. log2 keeps a 200-use drug well ahead of a 2-use one (7.65 vs 1.58), but stops it from ruling for years. With a linear count, a drug confirmed 10^6 times and unused for a year still scores about 244, above every fresh name.
   - **Why a 30-day half-life.** A clinic's stock changes over months. After 30 idle days a name keeps half its weight; after 90 days, one eighth. A heavy user yields to a fresh 2-count name only after a long gap: count 3 after 11 idle days, count 8 after 30, count 200 after 69.
   - **Why exponential, not steps.** A step rule (1.0 up to 30 days, then 0.5, then 0.25) makes many names tie and flips order in jumps at the step edges. The exponential is still one line and fully deterministic, because the age is in whole days and the score is rounded.
2. **Worked example** (today 2026-10-17; `list_active` order is the recency order).

   | Drug | `confirm_count` | `last_seen_at` | age | log2(1+n) | decay | score |
   |---|---|---|---|---|---|---|
   | Zorbexin | 200 | 2026-10-16T09:00:00Z | 1 | 7.651052 | 0.977160 | **7.476301** |
   | Quillavex | 2 | 2026-10-17T08:00:00Z | 0 | 1.584963 | 1.000000 | **1.584963** |
   | Morvexa | 40 | 2026-07-19T10:00:00Z | 90 | 5.357552 | 0.125000 | **0.669694** |

   Today (recency): Quillavex, Zorbexin, Morvexa. After r1: Zorbexin, Quillavex, Morvexa. With a linear count the stale Morvexa (40 × 0.125 = 5.0) would beat the fresh Quillavex (2.0); log2 prevents that.
3. **Clinic names in Spell it (OWNER DECISION, row 3 prerequisite).** For a row with NO lexicon match (an unknown name or a clinic name), the clinic's single-word names join the sound-alike pool at their plain `similarity` score, with the same 0.78 floor (`core/candidates.py:10`). There is no boost. A row WITH a lexicon match keeps today's list exactly, because every clinic name offered there would be a look-alike of a lexicon drug. Multi-word clinic names stay out, as the lexicon index already skips spellings with a space (`core/candidates.py:72`). A picked clinic name is re-grounded by check-row like any typed name, and `ground_clinic` still flags a lexicon look-alike (`core/formulary.py:134-135`).
4. **The near-tie rule (row 3).** The band is every candidate within 0.03 of the TOP candidate's score (`round(top - score, 6) <= 0.03`). Inside the band, the clinic names trade places by usage, more used first. Then come score, then name. A lexicon name keeps its exact slot. Nothing enters or leaves the band. A clinic row's own name leads its list, like the lexicon match leads a lexicon row (`core/rowcheck.py:84`). So usage never moves the dictated name.
   - **Why 0.03.** The score is `0.5 × spelling ratio + 0.5 × phonetic-key ratio`, plus 0.15 for equal keys, capped at 1.0 (`core/candidates.py:78-86`). One consonant changes the score by about 0.15 (zorbexin vs zorbexim: 0.854; zorvexa vs zorbexa: 0.829). A vowel often costs nothing: the key drops vowels, and the equal-key bonus hits the 1.0 cap (dolvex vs Dolvexa: 1.0; vs Dolvexi: 1.0). So exact ties at 1.0 are common between vowel twins, and those are the ties usage should break. 0.03 is under one fifth of a consonant step, so usage never beats a real spelling difference. One extra trailing letter is still inside (dolvex vs Dolvexol: 0.983). Measured on 300 one-vowel typos of lexicon spellings: of the 65 typos with two candidates at 0.78 or more, 6 had their top two within 0.03, 11 within 0.05 and 24 within 0.10. The band catches ties, not differences. A real brand pair such as Zyloric and Zovirax scores 0.548 apart, so it is never in one band.
   - **Why slots.** If usage could move a clinic name above a lexicon name, a popular local name would push a closer lexicon drug down. That is the look-alike risk of backlog card (c). With fixed slots, "a lexicon drug with a clinic count of zero is unaffected" holds exactly.
5. **The cache version stays a function of the SET of names** (`core/formulary.py:82-85`, unchanged). `/api/format` reads the layer only through `get` (`core/formulary.py:130-147`, `core/rowcheck.py:65`). It returns no suggestions and builds no hints, so order and usage cannot change its output. Usage changes on every save, and the decay changes every day. Putting usage in the version would empty the cache on every save for no change in output. Hints (`api/stt.py:41-43`) and check-row (`api/rx.py:53-69`) are not cached. Rule for later plans: a plan that puts suggestions or hint order into a cached response must add usage to the key.
6. **How usage reaches rowcheck.** Usage travels inside the `ClinicLayer` that `use_clinic_layer` activates for the request (A2). `check_row` runs `_ground` through `asyncio.to_thread`, which copies the context (`api/rx.py:67`). If a route forgets the dependency, the default empty layer applies (`core/formulary.py:101`). That fails open: no clinic names and no usage, and never another clinic's names. I1-h3's pin test and warning (A5) make that loud. The Team list keeps its recency order: `list_active` is unchanged, and only `load_layer` re-ranks.
7. **The page stays unchanged.** `rxview.js` shows `res.suggestions` in the order received. It de-duplicates, cuts at 6 (`frontend/rxview.js:149`) and adds one button per name in that order (`:152`). The cell keeps the dictated name until a button is tapped (`:152`), under the "Did you mean" label (`:140`). Test 8 pins this.

## File Structure and line budgets

| File | Change | Lines now → after (budget) |
|---|---|---|
| `doctor_dictation/core/formulary.py` | `usage_score`, `ranked_layer`, `ClinicLayer.usage`, `tie_break`, `sound_alikes` | 147 → about 212 (≤ 230) |
| `doctor_dictation/core/candidates.py` | `scored_candidates` (body moved out of `suggest_candidates`), `similarity` | 107 → about 122 (≤ 130) |
| `doctor_dictation/core/rowcheck.py` | `suggestions`: own clinic name, `sound_alikes` for unmatched rows | 89 → about 92 (≤ 95) |
| `doctor_dictation/api/formulary.py` (I1-h3) | `load_layer` calls `ranked_layer` | +1 net |
| `tests/test_formulary_usage.py` | NEW, 8 tests | about 190 (≤ 250) |

Adds 8 tests. Baseline: run the suite after I1-h4 and note the count N. Expect N + 8 passed, with the same skip count.

---

### Task 1: The usage score and the ranked layer (pure)

**Files:** Modify `doctor_dictation/core/formulary.py`; Create `tests/test_formulary_usage.py`.

**Interfaces:** Produces `HALF_LIFE_DAYS`, `usage_score(confirm_count, last_seen_at, today: date) -> float`, `ranked_layer(rows, today: date) -> ClinicLayer`, `ClinicLayer.usage: tuple = ()`, `ClinicLayer.usage_of(name) -> float`.

- [ ] **Step 1: Write the failing tests.**

```python
"""Usage ranking of the clinic formulary (plan I1-r1): hint order and the Spell it near-tie rule. Offline."""
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from doctor_dictation.core import formulary as F
from doctor_dictation.core import rowcheck
from doctor_dictation.core.candidates import suggest_candidates
from doctor_dictation.core.hints import build_hints

TODAY = date(2026, 10, 17)


@pytest.fixture(autouse=True)
def _no_layer_leaks():
    F.activate(F.ClinicLayer())
    yield
    F.activate(F.ClinicLayer())


def row(name, count, last_seen):
    """One db.formulary.list_active row."""
    return {"id": 0, "name": name, "generic": None, "confirm_count": count, "first_seen_at": last_seen,
            "last_seen_at": last_seen, "added_by": None}


def names(layer):
    return [n for n, _ in layer.items]


def test_usage_blends_the_count_with_recency_as_in_the_worked_example():
    rows = [row("Quillavex", 2, "2026-10-17T08:00:00Z"),          # list_active order: most recently seen first
            row("Zorbexin", 200, "2026-10-16T09:00:00Z"),
            row("Morvexa", 40, "2026-07-19T10:00:00Z")]
    assert [F.usage_score(r["confirm_count"], r["last_seen_at"], TODAY) for r in rows] == [1.584963, 7.476301, 0.669694]
    layer = F.ranked_layer(rows, TODAY)
    assert names(layer) == ["Zorbexin", "Quillavex", "Morvexa"]
    assert layer.usage_of(" ZORBEXIN ") == 7.476301 and layer.usage_of("Paracetamol") == 0.0
    assert F.HALF_LIFE_DAYS == 30


def test_ties_are_deterministic_and_odd_rows_neither_crash_nor_lead():
    same = [row("Zeta", 3, "2026-10-12T08:00:00Z"), row("Alfa", 3, "2026-10-12T08:00:00Z"),
            row("Beta", 3, "2026-10-12T09:00:00Z")]                  # one day, one count: equal scores
    assert names(F.ranked_layer(same, TODAY)) == ["Beta", "Alfa", "Zeta"]          # newer first, then the name key
    assert names(F.ranked_layer(list(reversed(same)), TODAY)) == ["Beta", "Alfa", "Zeta"]   # input order is irrelevant
    odd = [row("Future", 2, "2027-01-01T00:00:00Z"), row("Garbled", 9, "not a date"),
           row("Huge", 2**63 - 1, "2026-10-17T00:00:00Z"), row("Ancient", 10**6, "1990-01-01T00:00:00Z"),
           row("Nulls", None, None)]
    layer = F.ranked_layer(odd, TODAY)
    assert names(layer)[:2] == ["Huge", "Future"] and set(names(layer)[2:]) == {"Garbled", "Ancient", "Nulls"}
    assert (layer.usage_of("Huge"), layer.usage_of("Future")) == (63.0, 1.584963)     # no overflow; future = today
    assert layer.usage_of("Garbled") == layer.usage_of("Ancient") == layer.usage_of("Nulls") == 0.0


def test_hints_follow_usage_inside_the_same_caps_and_the_cache_version_follows_the_names_only():
    rows = [row(f"Drug{chr(97 + i)}x", i + 2, "2026-10-17T00:00:00Z") for i in range(11)]   # Drugax least used
    layer = F.ranked_layer(rows, TODAY)
    assert layer.hint_names() == [f"Drug{chr(97 + i)}x" for i in range(10, 0, -1)]      # the least used is left out
    assert layer.version == F.ClinicLayer(tuple((r["name"], "") for r in rows)).version    # usage is not in the key
    long = F.ranked_layer([row("W" * 50 + str(i), 10 - i, "2026-10-17T00:00:00Z") for i in range(4)], TODAY)
    assert long.hint_names() == ["W" * 50 + "0", "W" * 50 + "1"] and len(", ".join(long.hint_names())) <= F.HINT_CHARS
    cold = build_hints([], limit=70)
    F.activate(layer)
    assert build_hints([], limit=70)[:10] == layer.hint_names()
    F.activate(F.ranked_layer([], TODAY))
    assert F.active_layer() == F.ClinicLayer() and F.active_layer().version == "0" and build_hints([], limit=70) == cold
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py -q`. Expected: 3 FAIL (`AttributeError: module 'doctor_dictation.core.formulary' has no attribute 'usage_score'`).
- [ ] **Step 3: Extend `core/formulary.py`.** Add the imports and the constant; give `ClinicLayer` the `usage` field; add the two functions after the class.

```diff
 import hashlib
+import math
 import re
 from contextvars import ContextVar
 from dataclasses import dataclass
+from datetime import date
 from functools import cached_property, lru_cache
```
```diff
 MAX_HINTS, HINT_CHARS = 10, 150                # clinic names offered to the speech engine: count and characters
+HALF_LIFE_DAYS = 30                            # usage halves for every 30 days a name goes unconfirmed (plan I1-r1)
```
```python
@dataclass(frozen=True)
class ClinicLayer:
    """Active names in rank order: ((name, generic or ''), ...); ranked_layer puts the most used first (I1-r1).

    ``usage`` is ((name key, usage score), ...); a name missing from it scores 0.0. Neither the order nor the
    usage is part of ``version``: /api/format reads the layer only through ``get``."""
    items: tuple = ()
    usage: tuple = ()

    @cached_property
    def _usage(self) -> dict:
        return dict(self.usage)

    def usage_of(self, name) -> float:
        return self._usage.get(key(name), 0.0)
```

Keep `_by_key`, `version`, `get` and `hint_names` as they are. Change only the first docstring line of `hint_names` to `"""The highest-ranked names that fit MAX_HINTS and HINT_CHARS, ...`. Then add after the class:

```python
def usage_score(confirm_count, last_seen_at, today: date) -> float:
    """log2(1 + confirm_count), halved for every HALF_LIFE_DAYS whole days since last_seen_at, rounded to 6 places.

    A future date counts as today; a missing count or an unreadable date scores 0.0 (it ranks last, never first)."""
    try:
        age = max(0, (today - date.fromisoformat(str(last_seen_at)[:10])).days)
        count = max(0, int(confirm_count))
    except (TypeError, ValueError, OverflowError):
        return 0.0
    return round(math.log2(1 + count) * 0.5 ** (age / HALF_LIFE_DAYS), 6)


def ranked_layer(rows, today: date) -> ClinicLayer:
    """The layer for db.formulary.list_active rows, most used first. Ties: more recently seen, then the name key."""
    rows = [r for r in rows or () if str(r.get("name") or "").strip()]
    score = {key(r["name"]): usage_score(r.get("confirm_count"), r.get("last_seen_at"), today) for r in rows}
    rows = sorted(rows, key=lambda r: key(r["name"]))                                     # three stable sorts,
    rows = sorted(rows, key=lambda r: str(r.get("last_seen_at") or ""), reverse=True)     # least important first
    rows = sorted(rows, key=lambda r: -score[key(r["name"])])
    return ClinicLayer(tuple((r["name"], r.get("generic") or "") for r in rows),
                       tuple((key(r["name"]), score[key(r["name"])]) for r in rows))
```

- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py tests/test_formulary.py tests/test_core_purity.py -q`. Expected: all pass (`test_formulary_usage.py`: 3 passed). `tests/test_formulary.py:36-43` still passes: `hint_names` reads `items` in their order.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 2: Load the ranked layer for each request

**Files:** Modify `doctor_dictation/api/formulary.py` (created by I1-h3); append to `tests/test_formulary_usage.py`.

**Interfaces:** Consumes A1 (`load_layer`), `db.formulary.list_active`, `record_confirmation`, `remove`. Produces nothing new: `load_layer()` keeps its signature and its fallback to an empty layer.

- [ ] **Step 1: Append the failing test.**

```python


def test_the_loaded_layer_ranks_by_usage_and_a_removed_name_restarts_from_a_fresh_count(tmp_path, monkeypatch):
    from doctor_dictation import db as dbmod
    from doctor_dictation.api.formulary import load_layer
    from doctor_dictation.db import formulary as fdb
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))           # never the real dev database
    conn = dbmod.get_conn()
    dbmod.migrate(conn)
    eid = dbmod.create_encounter(conn, dbmod.create_patient(conn, "P", "40 / M", None))
    docs = iter([dbmod.save_document(conn, eid, f"sha{i}", {"rx": []}) for i in range(10)])
    today = datetime.now(timezone.utc).date()

    def confirm(name, times, days_ago):
        for _ in range(times):
            fdb.record_confirmation(conn, F.key(name), name, "", next(docs), None)
        conn.execute("UPDATE clinic_formulary SET last_seen_at = ? WHERE name_key = ?",
                     ((today - timedelta(days=days_ago)).isoformat() + "T08:00:00Z", F.key(name)))
        conn.commit()
    confirm("Zorbexin", 6, 3)
    confirm("Quillavex", 2, 0)
    assert [r["name"] for r in fdb.list_active(conn)] == ["Quillavex", "Zorbexin"]   # the Team list: most recent first
    assert names(load_layer()) == ["Zorbexin", "Quillavex"]                         # the hints: most used first
    (zor,) = [r for r in fdb.list_active(conn) if r["name"] == "Zorbexin"]
    assert fdb.remove(conn, zor["id"]) == "Zorbexin"
    gone = load_layer()
    assert names(gone) == ["Quillavex"] and gone.usage_of("Zorbexin") == 0.0       # a removed name never ranks
    confirm("Zorbexin", 2, 0)                                                         # learned again from 2 new documents
    back = load_layer()
    assert back.usage_of("Zorbexin") == back.usage_of("Quillavex") == 1.584963       # the count restarted at 2, not 8
    assert names(back) == ["Quillavex", "Zorbexin"]                                  # equal usage, same time: name key
    conn.close()
```

- [ ] **Step 2: Run it.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py -q -k loaded_layer`. Expected: FAIL at `names(load_layer()) == ["Zorbexin", "Quillavex"]` (the layer is still in recency order).
- [ ] **Step 3: Change `load_layer`** in `api/formulary.py`. Re-find the line with `grep -n "ClinicLayer(tuple" doctor_dictation/api/formulary.py`. If I1-h3 shaped it differently, keep its error handling and replace only the expression that builds the layer.

```diff
+from datetime import datetime, timezone
```
```diff
-            return formulary.ClinicLayer(tuple((r["name"], r["generic"] or "") for r in fdb.list_active(conn)))
+            return formulary.ranked_layer(fdb.list_active(conn), datetime.now(timezone.utc).date())   # most used first (I1-r1)
```

- [ ] **Step 4: Run.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py tests/test_formulary_routes.py tests/test_isolation_formulary.py -q`. Expected: all pass (`test_formulary_usage.py`: 4 passed). The I1-h3 and I1-h4 tests use one name, so order does not affect them.
- [ ] **Step 5: Leave uncommitted.**

---

### Task 3: The near-tie rule in Spell it (needs the owner's yes on Decision 3)

**Files:** Modify `doctor_dictation/core/candidates.py`, `core/formulary.py`, `core/rowcheck.py`; append to `tests/test_formulary_usage.py`.

**Interfaces:** Produces `candidates.scored_candidates(name, k=3) -> list[(canonical, score)]` (same rules and order as `suggest_candidates`), `candidates.similarity(name, spelling) -> float`, `formulary.BAND = 0.03`, `formulary.POOL = 3`, `formulary.tie_break(scored, usage_of) -> list[str]`, `formulary.sound_alikes(name, k=POOL) -> list[str]`. `rowcheck.suggestions(row)` keeps its signature and its limit of 5.

- [ ] **Step 1: Append the failing tests.**

```python


def test_usage_reorders_only_the_clinic_names_inside_the_band():
    use = {"Cl-hi": 50.0, "Cl-mid": 5.0, "Cl-lo": 0.5, "Cl-far": 99.0}
    scored = [("Cl-lo", 1.0, True), ("Lexa", 0.99, False), ("Cl-mid", 0.98, True), ("Cl-hi", 0.971, True),
              ("Cl-far", 0.969, True), ("Lexb", 0.90, False)]
    assert F.BAND == 0.03
    assert F.tie_break(scored, lambda n: use.get(n, 0.0)) == ["Cl-hi", "Lexa", "Cl-mid", "Cl-lo", "Cl-far", "Lexb"]
    assert F.tie_break(scored, lambda n: 0.0) == [n for n, _s, _c in scored]          # no usage: today's order exactly
    assert F.tie_break([], lambda n: 1.0) == []


def test_spell_it_offers_the_clinic_names_and_usage_only_breaks_near_ties():
    unknown = {"name": "Dolvex", "lexicon_match": ""}
    assert suggest_candidates("Dolvex") == [] and rowcheck.suggestions(unknown) == []        # cold clinic: as today
    rows = [row("Dolvexa", 2, "2026-10-17T00:00:00Z"), row("Dolvexi", 30, "2026-10-15T00:00:00Z"),
            row("Dolmexa", 500, "2026-10-17T00:00:00Z")]
    F.activate(F.ClinicLayer(tuple((r["name"], "") for r in rows)))                          # no usage: score, then name
    assert rowcheck.suggestions(unknown) == ["Dolvexa", "Dolvexi", "Dolmexa"]
    F.activate(F.ranked_layer(rows, TODAY))
    assert rowcheck.suggestions(unknown) == ["Dolvexi", "Dolvexa", "Dolmexa"]    # 1.0 twins: more used first; 0.785 stays 3rd
    assert rowcheck.suggestions({"name": "Dolvexa", "lexicon_match": ""})[0] == "Dolvexa"    # a clinic row's own name leads
    F.activate(F.ranked_layer([row("Zorbexin", 200, "2026-10-17T00:00:00Z"),
                               row("Zorbexim", 2, "2026-10-17T00:00:00Z")], TODAY))
    assert rowcheck.suggestions({"name": "Zorbexem", "lexicon_match": ""}) == ["Zorbexim", "Zorbexin"]   # 1.0 vs 0.79
    today = rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"})
    F.activate(F.ranked_layer([row("Prednisome", 900, "2026-10-17T00:00:00Z")], TODAY))
    assert rowcheck.suggestions({"name": "Prednisone", "lexicon_match": "Prednisone"}) == today   # a lexicon row: unchanged
    assert rowcheck.suggestions({"name": "Crocin", "lexicon_match": "Paracetamol"})[0] == "Paracetamol"  # did you mean


def test_check_row_returns_the_ranked_list_and_keeps_the_dictated_name(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from doctor_dictation import db as dbmod
    from doctor_dictation.api.app import create_app
    monkeypatch.setenv("DB_PATH", str(tmp_path / "f.db"))
    seen = datetime.now(timezone.utc).date().isoformat() + "T08:00:00Z"
    with TestClient(create_app()) as client:                          # start-up migrates the temp database
        conn = dbmod.get_conn()
        for name, count in (("Dolvexa", 2), ("Dolvexi", 30), ("Dolmexa", 500)):
            conn.execute("INSERT INTO clinic_formulary(name_key, name, confirm_count, first_seen_at, last_seen_at)"
                         " VALUES (?, ?, ?, ?, ?)", (F.key(name), name, count, seen, seen))
        conn.commit()
        conn.close()
        r = client.post("/api/v1/rx/check-row", json={"row": {"name": "Dolvex"}, "transcript": "tablet dolvex daily"})
    got = r.json()
    assert r.status_code == 200 and got["suggestions"] == ["Dolvexi", "Dolvexa", "Dolmexa"]
    assert (got["row"]["name"], got["row"]["status"]) == ("Dolvex", "unknown-medicine")   # offered, never applied


def test_the_page_shows_the_suggestions_in_the_order_the_server_sends():
    js = (Path(__file__).resolve().parents[1] / "frontend" / "rxview.js").read_text(encoding="utf-8")
    line = next(t for t in js.splitlines() if "res.suggestions" in t)
    assert ".slice(0, 6)" in line and ".sort(" not in line and ".reverse(" not in line
    assert 'list.forEach((s) => { const b = btn("sug", "sug", s)' in js and '"Did you mean"' in js
```

- [ ] **Step 2: Run them.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py -q`. Expected: 3 FAIL (`AttributeError: ... 'BAND'`, then `assert [] == ['Dolvexa', 'Dolvexi', 'Dolmexa']` twice). The page test passes from the start: it is a pin. To see it guard, add `.sort()` after `.map(String)` in `rxview.js:149`, see it fail, and restore the line.
- [ ] **Step 3: `core/candidates.py`.** Move the body of `suggest_candidates` (`:97-107`) into `scored_candidates`, which returns `ranked[:k]` with the scores. Then `suggest_candidates` keeps its docstring and becomes one line. Add `similarity` after it.

```python
def scored_candidates(name: str, k: int = 3) -> list:
    """[(canonical, score)] behind suggest_candidates: the same rules, the same order."""
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    key = phonetic_key(low)
    if k <= 0 or len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3:
        return []
    best = {}
    for text, tkey, canon in _rows():
        sc = _score(low, key, text, tkey)
        if sc >= MIN_SCORE and sc > best.get(canon, 0.0):
            best[canon] = sc
    return sorted(best.items(), key=lambda kv: (-round(kv[1], 6), kv[0].lower(), kv[0]))[:k]


def suggest_candidates(name: str, k: int = 3) -> list:
    """(docstring unchanged)"""
    return [c for c, _ in scored_candidates(name, k)]


def similarity(name: str, spelling: str) -> float:
    """The score suggest_candidates would give one more single-word ``spelling`` for ``name``; 0.0 outside its rules."""
    low = re.sub(r"[^a-z]", "", (name or "").lower())
    text = " ".join(str(spelling or "").split()).lower()
    key = phonetic_key(low)
    if len(low) < 4 or len(low) > MAX_NAME_LETTERS or len(key) < 3 or len(text) < MIN_LEN or " " in text:
        return 0.0
    return _score(low, key, text, phonetic_key(text))
```

- [ ] **Step 4: `core/formulary.py`.** Change the import, add two constants, and append the two functions.

```diff
-from .candidates import suggest_candidates
+from .candidates import MIN_SCORE, scored_candidates, similarity, suggest_candidates
```
```diff
 HALF_LIFE_DAYS = 30                            # usage halves for every 30 days a name goes unconfirmed (plan I1-r1)
+BAND, POOL = 0.03, 3                           # near-equal: within 0.03 of the top sound-alike; sound-alikes per row
```
```python


def tie_break(scored, usage_of) -> list[str]:
    """Names of ``scored`` ([(name, score, from_clinic)], best first) after the near-tie rule (plan I1-r1).

    Inside the band (within BAND of the TOP score) the clinic's names trade places by usage, more used first; a
    lexicon name keeps its exact slot, and nothing enters or leaves the band. With no usage nothing moves."""
    if not scored:
        return []
    top = scored[0][1]
    slots = [i for i, (_n, s, clinic) in enumerate(scored) if clinic and round(top - s, 6) <= BAND]
    moved = sorted((scored[i] for i in slots), key=lambda c: (-usage_of(c[0]), -round(c[1], 6), c[0].lower(), c[0]))
    out = list(scored)
    for i, cand in zip(slots, moved):
        out[i] = cand
    return [n for n, _s, _c in out]


def sound_alikes(name, k: int = POOL) -> list[str]:
    """Up to k names that sound like ``name``: the lexicon's and this clinic's single-word names by one score, then
    the near-tie rule. With an empty layer this is exactly suggest_candidates(name, k)."""
    layer = active_layer()
    clinic = [c for c in ((n, similarity(name, n), True) for n, _generic in layer.items) if c[1] >= MIN_SCORE]
    lexicon = [(n, s, False) for n, s in scored_candidates(name, k + len(clinic))]
    merged = sorted(lexicon + clinic, key=lambda c: (-round(c[1], 6), c[0].lower(), c[0]))
    return tie_break(merged, layer.usage_of)[:k]
```

- [ ] **Step 5: `core/rowcheck.py` `suggestions`** (`:77-89`). Keep the `suggest_candidates` import: `tests/test_rx_check_row.py:137` reads `rowcheck.suggest_candidates`. Lexicon rows keep today's list exactly. Unmatched rows get the clinic's names and the row's own clinic name first.

```diff
     match = [row["lexicon_match"]] if row.get("lexicon_match") else []
-    for name in match + suggest_candidates(row.get("name", "")) + list(twins):
+    own = [] if match else [hit[0] for hit in [formulary.active_layer().get(row.get("name", ""))] if hit]
+    alikes = suggest_candidates(row.get("name", "")) if match else formulary.sound_alikes(row.get("name", ""))
+    for name in match + own + alikes + list(twins):
```

Also add one sentence to the docstring: `A row with no lexicon match also gets this clinic's names (its own name first); usage breaks only near-ties among them (I1-r1).`

- [ ] **Step 6: Run.** Run: `.venv/bin/python -m pytest tests/test_formulary_usage.py tests/test_rowcheck.py tests/test_rx_check_row.py tests/test_candidates.py tests/test_formulary.py -q`. Expected: all pass (`test_formulary_usage.py`: 8 passed). `test_rx_check_row.py:137` still holds: the layer is empty there, so `sound_alikes == suggest_candidates`.
- [ ] **Step 7: Leave uncommitted.**

---

### Task 4: Mutations, whole suite, sizes and hand-over

- [ ] **Step 1: Run every mutation.** Apply each mutation alone. Run `.venv/bin/python -m pytest tests/test_formulary_usage.py -q`, see at least one failure, then revert. Report each result as "killed by test N" in the hand-over.

| # | Mutation | Must fail |
|---|---|---|
| M1 | `HALF_LIFE_DAYS = 60` | test 1 |
| M2 | `math.log2(1 + count)` → `count` | test 1 (Morvexa passes Quillavex) |
| M3 | drop `max(0, ...)` around the age | test 2 (`usage_of("Future")`) |
| M4 | delete the name-key sort pass in `ranked_layer` | test 2 (reversed input) |
| M5 | `version` hashes `self.items` in order or includes `self.usage` | test 3 |
| M6 | `load_layer` back to the I1-h3 recency expression | test 4 |
| M7 | `BAND = 0.05` | test 5 (`Cl-far` enters the band) |
| M8 | sort every band member by usage, lexicon ones too | test 5 (`Lexa` moves) |
| M9 | band measured from the previous candidate, not the top | test 5 |
| M10 | `rowcheck.suggestions` back to `suggest_candidates` for every row | tests 6, 7 |
| M11 | delete the `own` line | test 6 (`Dolvexa` row) |
| M12 | `sound_alikes` also for lexicon-matched rows | test 6 (Prednisone list) |
| M13 | `.sort()` added in `rxview.js:149` | test 8 |

- [ ] **Step 2: Whole suite.** Run: `.venv/bin/python -m pytest tests/ -q`. Expected: N + 8 passed (N = the count after I1-h4), same skip count, no failure.
- [ ] **Step 3: Sizes.** Run: `wc -l doctor_dictation/core/formulary.py doctor_dictation/core/candidates.py doctor_dictation/core/rowcheck.py doctor_dictation/core/determinism.py doctor_dictation/core/correction.py doctor_dictation/db/__init__.py doctor_dictation/api/persistence.py`. Expected: every file inside its budget in the File Structure table; the last four unchanged.
- [ ] **Step 4: Timing check (once).** Activate a layer of 1,000 single-word names and time `rowcheck.suggestions({"name": "Dolvex", "lexicon_match": ""})`. Expected: under 50 ms. If slower, report it. Do not add a cache in this plan.
- [ ] **Step 5: Leave uncommitted.** Changed files: the five in the File Structure table. Then hand over to the final whole-branch review.

## Self-Review

- Row 1: the blend, worked example and ties (Decisions 1-2, Task 1); the caps and the version (Decision 5, test 3); the load path (Task 2). Row 3: the band, slots, own name and lexicon rows (Decisions 3-4, Task 3); the page is pinned (Decision 7, test 8). Each Review Focus row maps to a test.
- Names match the I1-h1/I1-h2 code on disk and the I1-h3/I1-h4 plan text. Every I1-h3 dependency is listed as A1-A6. If A1 differs, Task 2 Step 3 says what to keep.
- Deliberately out of scope: the "top medicines" quick-pick on an empty row; per-doctor popularity; cross-clinic popularity; any boost for clinic names beyond the tie-break; multi-word clinic names in Spell it; clinic names in the LLM repair message (`core/repair.py:39` stays lexicon only); usage shown in the Team tab or the API; per-specialty or time-of-day hints; changing `hint_names`' stop-at-first-misfit rule (pinned by `tests/test_formulary.py:42-43`). These are cards in `docs/superpowers/plans/2026-10-17-i1-backlog-suggestion-ideas.md`.

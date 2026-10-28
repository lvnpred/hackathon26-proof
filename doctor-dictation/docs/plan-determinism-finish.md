# Plan: Finish the Determinism Track (P1.1, P1.3 hardening, P2.1, P2.3)

Status of this doc: execution-ready plan. It finishes the remaining open items of
`C:\Users\lvnar\.opencode\plan\determinism-plan.md`. Work already DONE and NOT
re-planned here: P0.1–P0.5, P1.2, P1.3 (build.py offline normalize + `--enrich`
RxNav cache), P2.2 (determinism test suite), agent-loop Part A, Part B Step 0.

> **Progress (2026-10-12, HEAD `d5301a8`):** D1, D2, D3 **DONE** (see the
> corrected §2 below). D4, D5, D6 **open**. Part B Step 1 (ONNX/Snapdragon)
> **DEFERRED — not needed**. Line references in this doc predate the
> implementation and have largely shifted.

---

## 1. Goal + acceptance criteria

**Goal.** Expand the offline drug lexicon from 41 → 300–500 entries via a
repeatable offline build path, harden remaining lexicon/versioning gaps, grow
the golden transcript set from 8 → 12–14 with noisy-STT / no-strength /
Hindi-English coverage, and add a merge gate + CI so determinism regressions
are caught automatically.

**Acceptance criteria (measurable).**
- `lexicon_size()` returns ≥ 300 and ≤ 500 (verified via `GET /api/health`
  `lexicon_entries`, and `pytest tests/ -q`).
- `backend/lexicon/build.py` run with **no network** is idempotent: two
  consecutive runs produce byte-identical `drugs.json`, and a new `--check`
  mode exits `0` when `drugs.json` is in sync and non-zero otherwise.
- All existing lexicon regression tests still pass at 300–500 entries
  (`crocin→Paracetamol`, `dolo→Paracetamol`, `tam sulosin→Tamsulosin`,
  file-order independence).
- `tests/golden.json` contains 12–14 cases, each with a deterministic
  expectation; `test_golden_deterministic_5x` and `test_golden_expected_fields`
  pass with zero LLM/network.
- CI (`.github/workflows/ci.yml`) runs `pytest tests/ -q` **and**
  `node --check frontend/app.js` and the lexicon `--check` gate; a merge that
  breaks determinism is blocked.

**Non-goals (unchanged behavior).** The runtime pipeline
`normalize → ground → repair → validate → cache` in `backend/determinism.py` is
preserved byte-for-byte in behavior. No new runtime network calls. No new
native (compiled) dependencies.

---

## 2. Current state (verified by reading code)

> **STALE (2026-10-12, HEAD `d5301a8`).** Pre-implementation snapshot; partly
> wrong now. Corrections are marked **[FIXED]**; unmarked bullets are still
> accurate. Line numbers here have shifted — treat them as approximate.

- **Lexicon** `backend/lexicon/drugs.json`: **[FIXED]** now `version` **1.1.0**
  with **444 entries** (was 1.0.0 / 41). JSON shape is
  `{"entries": [...], "version": "..."}`. Schema per entry: `canonical`,
  `aliases[]`, `brands[]`, `forms[]`, `strengths[]`.
- **Build tool** `backend/lexicon/build.py`: **[FIXED]** now has `--merge [SEED]`
  (adds entries, offline, deterministic) and `--check` (idempotency gate, exit
  0/1); a seed duplicate-`canonical` guard fails loudly (`build.py:88–100`).
  - `--enrich --terms …` still queries NIH RxNav and caches to `rxnav_cache.json`.
    Build-time only; runtime never calls it.
- **Runtime** `backend/determinism.py`:
  - `load_lexicon()` lines 50–61 (sets module-global `LEXICON_VERSION` from the
    JSON `version` field on load), `lexicon_size()` 64–65.
  - `_alias_map()` 68–93: rebuilt on **every** call (no memoization) from
    `_lexicon_cache`; sorted by canonical → deterministic but O(aliases) per call.
  - `correct_drugs()` 102–163, `normalize_transcript()` 166–172,
    `_canonical_lookup()` 204–218, `_ground_row()` 225–249, `ground_rx()` 252–279,
    `validate_structured()` 336–406, cache 409–416.
- **Gap A (version staleness). [MOSTLY FIXED]** `determinism.py` now exposes a
  live `lexicon_version()` accessor (`:68`) and `GET /api/health` calls it
  (`main.py:459`); `tests/test_determinism.py:138` asserts `== "1.1.0"`.
  **Residual:** the `engine` strings in `backend/main.py:643/735/747` still use
  the frozen by-value `LEXICON_VERSION`, so `/api/format` responses report
  `v1.0.0` while health reports `1.1.0`.
- **Gap B (perf).** `_alias_map()` rebuilds the full alias map on every
  `correct_drugs()` call (once per `/api/format`) **and** once per rx row inside
  `_ground_row()` via `_canonical_lookup()` — up to ~9 rebuilds/request. At 500
  entries × ~4 aliases ≈ 2000 keys this is minor but avoidable. Memoization must
  invalidate when `_lexicon_cache` changes (the order-independence test
  monkeypatches it — `tests/test_determinism.py:58–64`).
- **Tests** `tests/test_determinism.py` + `tests/golden.json` (**still 8
  entries** — D5 open). The suite has grown since this snapshot: `tests/test_db.py`
  (P0-4) and `tests/test_secrets.py` (P0-2) now exist, so re-measure the pass
  count. Golden assertion fields in use:
  `diagnosis_contains`, `advice_contains`, `review_contains`, `rx[].name`,
  `rx[].dose`, `patientName`, `ageSex`.
- **CI / git. [FIXED for git]** The repo **is** a git repo now (`git init`,
  commit `a706ce6`) with `.gitignore` (venvs, `.env`, `secrets.json`,
  `__pycache__`, `.pytest_cache`). **CI still absent** (no `.github/`) — D6 open.

---

## 3. Decisions needed

| # | Decision | Options | Proposed default | Blocks |
|---|---|---|---|---|
| D-1 | Lexicon scope & size target | (a) ~300 core, (b) ~400 WHO-EML + India-NLEM + top IN brands, (c) ~500 incl. niche | **(b) ~400** | D1, D3 |
| D-2 | Seed source & licensing | (a) manually curated committed seed (no license risk), (b) RxNorm full dump (US, free, needs net at build), (c) WHO EML + India NLEM CSVs | **(a) curated seed committed to repo**, optional `--enrich` RxNav stays build-time | D1 |
| D-3 | Lexicon versioning source of truth | (a) `drugs.json.version` read at load + accessor, (b) keep hardcoded const | **(a)** semver bump each change; add `lexicon_version()` accessor | D3 |
| D-4 | Golden determinism target path | (a) rules+lexicon fallback only (offline, CI-safe), (b) also live-LLM golden | **(a)** fallback-only for CI; LLM golden optional/separate, never in CI | D5, D6 |
| D-5 | Golden expectation strictness | (a) full-JSON byte-identical ×5 **and** field-subset asserts, (b) field-subset only | **(a)** keep existing 5× byte-identical test; add field-subset for new cases | D5 |
| D-6 | OP-number determinism | (a) keep OP numbers out of golden, (b) inject fixed OP via fixture if sheet-level tests appear | **(a)** `/api/format` schema has no OP number; OP stays out of golden | D5 |
| D-7 | CI runner | (a) GitHub Actions ubuntu-latest + Python 3.12 + Node 20, (b) self-hosted Windows | **(a)** ubuntu-latest (tests need only `backend/requirements.txt`) | D6 |
| D-8 | Seed data review (medical) | (a) doctor/clinical reviewer sign-off on the 400-drug list, (b) ship as-is | **(a)** one clinical review pass before merge | D1, D3 |

---

## 4. Task table

IDs: `D*` (determinism). "Effort" in hours (h) / days (d).

| ID | Task | Files | Depends on | Effort | Verify command |
|---|---|---|---|---|---|
| D1 ✅ | Author committed lexicon seed: `backend/lexicon/seed_extra.json` with ~360 additional IN-market generics (WHO EML 2023 + India NLEM 2022 + top IN brands), each with `canonical`, `aliases[]` (incl. phonetic STT-splits like `"pan to"`→Pantoprazole), `brands[]`, `forms[]`, `strengths[]`. No network. | `backend/lexicon/seed_extra.json` (new) | D-1, D-2, D-8 | 1.5 d | `python -c "import json;print(len(json.load(open('backend/lexicon/seed_extra.json','r',encoding='utf-8'))))"` ≥ 300 |
| D2 ✅ | Extend `build.py`: `--merge seed_extra.json` (offline default) + `--check`. Merge = dedupe by `canonical` (seed wins on conflict), deterministic sort, bump `version`; write `drugs.json`. `--check` regenerates to a temp string and diffs against on-disk `drugs.json` (exit 0/1) — the CI idempotency gate. | `backend/lexicon/build.py` | D1 | 0.5 d | `python backend/lexicon/build.py --merge backend/lexicon/seed_extra.json --check` (0 then 0 after regen) |
| D3 ✅ | Regenerate `drugs.json` to v1.1.0 (300–500 entries). Fix version source of truth: add `lexicon_version()` accessor in `determinism.py`; change `main.py` health to call it (drop the by-value import usage). Update `test_api_health_reports_lexicon` to assert `lexicon_version == "1.1.0"` and `lexicon_entries >= 300`. | `backend/lexicon/drugs.json`, `backend/determinism.py`, `backend/main.py`, `tests/test_determinism.py` | D2, D-3 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/ -q` |
| D4 | Lexicon hardening + regression tests: (1) memoize `_alias_map()` keyed on `id(_lexicon_cache)` (invalidate on change — preserves order-independence test); (2) `build.py` fails on duplicate alias/brand across different canonicals; (3) new tests: no alias collisions, every entry has canonical + ≥1 alias + ≥1 strength, brand→generic still resolves, file-order independence at full size, `--check` idempotency. | `backend/determinism.py`, `backend/lexicon/build.py`, `tests/test_lexicon.py` (new) | D3 | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/ -q` |
| D5 | Grow `tests/golden.json` 8 → 12–14 cases. Add: second noisy-STT (multiple splits in one line), multi-drug no-strength (2 drugs, no strengths), SOS no-strength, 2 more Hindi-English (Hinglish) mixes, a mixed verified+unknown-medicine case, a demographics-only-no-rx case. Each case adds deterministic expectations: `rx[].name/dose` plus NEW `rx[].status` and `rx[].strength` ("" for no-strength). Add a `test_golden_status_expectations` asserting per-row `status`/`strength`. | `tests/golden.json`, `tests/test_determinism.py` | D3 (needs new lexicon for some drugs) | 0.5 d | `.\.venv-arm64\Scripts\python -m pytest tests/ -q` |
| D6 | CI + merge gate: `git init`; add `.github/workflows/ci.yml` (ubuntu-latest: setup-python 3.12, `pip install -r backend/requirements.txt`, `python backend/lexicon/build.py --merge … --check`, `pytest tests/ -q`, setup-node, `node --check frontend/app.js`). | `.github/workflows/ci.yml` (new), `.gitignore` (new), `README.md` (CI badge note) | D4, D5, D-7 | 0.5 d | `node --check frontend/app.js` && `python -m pytest tests/ -q` (locally) |

**Total effort: ~4 days** (authoring D1 is the long pole).

**New dependency check.** None of D1–D6 adds a runtime or test dependency. CI
uses only `backend/requirements.txt` (already-installed: fastapi, uvicorn,
python-multipart, httpx, python-dotenv) + Node for `--check`. All Python is
3.12-compatible on ARM64 and x64; no compiled wheels.

---

## 5. Execution DAG

```
D1 ──► D2 ──► D3 ──┬──► D4 ──► D6
                   └──► D5 ─────────┘
```

- **Sequential chain:** D1 → D2 → D3 (seed → merge → regenerate). D3 must land
  before D4 (memoization should be tested against the full lexicon) and before
  D5 (new golden cases reference newly-added drugs).
- **PARALLEL after D3:** `D4` and `D5` can run concurrently. **File-conflict
  check:** D4 edits `backend/determinism.py` + `backend/lexicon/build.py` +
  new `tests/test_lexicon.py`; D5 edits `tests/golden.json` +
  `tests/test_determinism.py`. **No shared files** → safe to parallelize.
- **D6** is strictly after D4 and D5 (CI gate must run against the finalized
  lexicon + golden set). It creates `.github/workflows/ci.yml` and `.gitignore`
  (new files, no conflict).
- **`backend/main.py` is edited only by D3** (health version accessor). Keep it
  that way — do not let D4/D5 touch `main.py`.

**Cross-plan conflict note:** `backend/main.py`, `tests/test_determinism.py`, and
`.github/workflows/ci.yml` are also touched by Phase 0 hardening
(`docs/plan-phase0-hardening.md`, tasks P0-1 CI and P0-6 versioning). Do **not**
dispatch D6 and P0-1 concurrently — both create `.github/workflows/ci.yml`.
Serialize them; D6 owns the determinism gate, P0-1 owns Docker build/extra jobs.

---

## 6. Risks / rollback

- **Fuzzy false-positives at 400 entries.** `_canonical_lookup` uses
  `difflib.get_close_matches(cutoff=0.84)` (`determinism.py:217`); more keys ⇒
  higher chance a near-match maps a dictation to the wrong generic. Mitigation:
  D4 adds a "do-not-correct" regression list (e.g. `cortisol`≠`Cortisol`, and
  brand/generic pairs that must never cross-resolve). If a false-positive
  appears, revert the offending seed entry (single-line rollback) — the pipeline
  itself is untouched.
- **Version test breakage.** Bumping to 1.1.0 breaks
  `test_api_health_reports_lexicon:138`. D3 updates it in the same change;
  rollback = revert the version string + test together.
- **`_alias_map` memoization bug.** If the invalidation key is wrong, the
  order-independence test (`test_determinism.py:54–67`) fails loudly. Rollback:
  drop the memoization (behavior-neutral) — it is a perf-only hardening.
- **Seed data errors (clinical).** A wrong strength/form in the seed can turn a
  real prescription into an `unverified-strength` flag (safe) or silently
  normalize to the wrong drug (unsafe). Mitigation: D-8 clinical review + D4
  duplicate-alias guard. Rollback: revert `seed_extra.json`/`drugs.json` (pure
  data).
- **CI is net-new.** Requires git remote + Node on the runner. If the repo can't
  be pushed to GitHub yet, D6's CI file can land locally but the gate is inert
  until a remote exists — flag to user (D-7).

---

## 7. Definition of Done

- [x] `lexicon_size()` ∈ [300, 500] (444 ✔); `/api/health` reports
      `lexicon_version` via `lexicon_version()` (1.1.0). **DONE** (health) — a
      residual `engine`-string use of the frozen constant remains
      (`main.py:643/735/747`).
- [x] `python backend/lexicon/build.py --merge backend/lexicon/seed_extra.json`
      is offline + idempotent; `--check` passes (exit 0). **DONE (D2)**.
- [ ] `tests/golden.json` has 12–14 entries incl. noisy-STT, no-strength,
      Hindi-English, unknown-medicine, no-hallucination. **STILL 8 — D5 open.**
- [ ] `test_golden_deterministic_5x`, `test_golden_expected_fields`,
      `test_golden_status_expectations`, and all lexicon regression tests pass;
      `pytest tests/ -q` green.
- [ ] `.github/workflows/ci.yml` runs `--check` + `pytest` + `node --check` and
      blocks a determinism-breaking merge.
- [ ] `normalize → ground → repair → validate → cache` behavior unchanged
      (no diffs to `determinism.py` logic beyond memoization + version accessor).

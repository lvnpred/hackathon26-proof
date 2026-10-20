# 06 — Engineering standards for the product build

## 1. Summary

These standards apply to every product-phase change (`05`). Most already exist in this repo as tests or
habits; this file writes them down and adds what a regulated module needs (traceability, hazard links,
stricter typing). The hackathon follows only the "lite" subset in §10.

## 2. Architecture rules

| Rule | Enforced by |
|---|---|
| `core/` is pure: no `sqlite3`, `fastapi`, `httpx`, environment or clock reads | `tests/test_core_purity.py` (extend its banned list with `time.time`, `datetime.now`, `os.getenv`) |
| Every external system sits behind a `Protocol` port in `providers/<port>/base.py`, with a factory and a stub | Review checklist §8 |
| Rules take `now` as an argument; only adapters read clocks | Purity test |
| Modules talk through timeline events, never by importing each other's internals | New test: `core/<a>` may not import `core/<b>` except `core/timeline` |
| Decision-tier code lives in files named `*_decision.py`; routers mount them only through the tier gate | New test scanning routers |
| Files stay under 500 lines | `tests/test_file_sizes.py` |
| New logic goes in new modules; edits to large existing files stay hooks, not logic | Review |

## 3. Code style

- Python ≥ 3.11, `from __future__ import annotations`, type hints on every public function.
- New packages pass `mypy --strict` and `ruff check` (add both to `requirements-dev.txt`; existing code is
  exempt until touched).
- Dataclasses are `frozen=True` for values that cross a boundary (events, readings, detections).
- Errors: one exception type per port; `str(e)` is safe to show and ≤ 300 chars; keys are redacted from
  any upstream body (see `providers/stt/muse.py`).
- Names: one term per concept across code, UI and docs (`episode`, not "case"/"session"/"surgery").
- Comments say *why*. A comment that repeats the code is deleted in review.
- Frontend: vanilla ES modules, no build step; a new file per feature; cache-busting `?v=` bumped in
  `index.html`; tokens from `polish.css`, no raw colours.

## 4. Data and migrations

- Numbered SQL files in `db/migrations/`, applied once and recorded in `schema_migrations`; additive only
  (no dropping columns in the same release that stops using them).
- Every clinic has its own database; every new table gets an isolation test like `tests/test_isolation_*.py`.
- Timeline payloads carry `payload_v`; a reader handles every version still in any database.
- Append-only tables get `BEFORE UPDATE` / `BEFORE DELETE` triggers that raise.
- Shared files under the data root use a cross-process lock (`fcntl.flock`), because production runs two
  uvicorn workers.

## 5. Testing

| Level | What | Rule |
|---|---|---|
| Unit (core) | Every rule, every branch, every threshold edge | Test-first; offline; fake clock |
| Contract | Each adapter against the port protocol and recorded fixtures | One fixture per real response shape |
| API | Routes with auth, scope, tier gate on and off | Isolation tests for any per-clinic data |
| Frontend | DOM tests in the `tests/test_frontend_*.py` style | One per new screen state |
| Golden | End-to-end episode replay (`vision_replay` + `vitals_sim`) produces the expected event list | Run in CI |
| Accuracy bench | STT and vision accuracy on held-out recordings (`bench/`) | Run before each provider or model change |
| Red team | Prompt set that tries to make the card or narrative advise | Must stay at 0 failures |

- No test reaches a real network. A test that needs a key is a bench, not a test.
- Tests never touch the dev database: fixtures set `DB_PATH` to a temp file.
- Command: `.venv/bin/python -m pytest tests/ -q`; the full suite is green before review.

## 6. LLM and model use

- The LLM never decides. It rewords facts or structures dictated text; deterministic code validates every
  output against its inputs (the pattern of `core/rowcheck.py` and the wording check in `02` §5.3).
- Every call has a timeout and a deterministic fallback; the UI never waits on a model for a safety signal.
- Prompts are versioned constants; the version and model name are stored with the output
  (`documents.model_versions` today; `evidence` on timeline events).
- `seed` is set where the provider supports it (`Settings.llm_seed`).
- No patient identifiers to cloud models without a DPA; never a provider tier that trains on inputs.

## 7. Security and privacy

- Secrets only through `secret_loader.load_secret`; never in code, tests, logs or the repo.
- Logs carry ids, never names, transcripts, images or readings.
- Every route declares its role and clinic scope; default deny.
- Images and audio are deleted after use unless a clinic setting keeps them; retention is enforced by a
  job, not by convention.
- Dependencies pinned with a reason comment when capped (see `av<15` in `requirements-stt.txt`).

## 8. Traceability and review

- Every requirement ID in `05` §3 maps to at least one test (`# req: CG-2` comment on the test).
  A script lists requirements without tests; it must print nothing before a release.
- Every hazard in `05` §7 names its controls and the tests that prove them.
- Decisions with lasting effect get a short ADR in `docs/adr/` (context, decision, consequences).

Review checklist (reviewer subagent + human):

1. Does the change do what its plan says, and nothing more?
2. Purity, port, file-size and module-boundary rules hold.
3. Tests prove each acceptance bullet, including threshold edges and the "off" state of the tier switch.
4. Errors are safe to show; no secret or patient data in logs.
5. Migrations are additive and have isolation tests.
6. For decision-tier code: hazard log updated, banner present, banned-term test extended.

## 9. Workflow

- Spec → plan (`docs/superpowers/plans/`, index-and-contracts file first) → subagent-driven tasks →
  review → human approval → commit. Agents never commit; the owner approves each commit.
- One feature branch per phase; merge to `main` only with a green full suite and an updated
  `docs/deploy/vps-operations.md` when deployment changes.
- Definition of done: tests green, review passed, requirement and hazard links updated, docs updated,
  demo of the behaviour on a clean database.

## 10. Hackathon lite (what the hackathon keeps)

| Kept | Dropped for speed |
|---|---|
| Pure rule cores, test-first, offline tests | mypy/ruff, frontend tests, isolation tests |
| Frozen contracts (`02` §3–4) | Multi-clinic mode, auth on `/api/hx/*` (demo only, never deployed) |
| 500-line files, no secrets, temp `DB_PATH` | Traceability IDs, ADRs, retention jobs |
| Wording check and tier banner | Hazard log (the product starts it in P0) |

`/api/hx/*` routes have no auth. **Never deploy the `hackathon` branch to the VPS.**

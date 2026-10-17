# I1-h3 report (clinic formulary: API and cache)

Status: complete, uncommitted. Full suite 1484 passed, 1 skipped, 1 deselected (baseline 1459 + 25 new in tests/test_formulary_routes.py; the plan said +5).
Offline guard on tests/test_formulary_routes.py: 25 passed, NETGUARD attempts 0. Also green under the guard: test_formulary, test_formulary_db, test_api_app, test_isolation_routes.
`doctor_dictation/data/app.db` did not exist before the first run and does not exist after the full suite (R5).
Largest touched sources: persistence.py 421, format.py 220, core/formulary.py 167. Nothing near 500.

## What was built (real symbols)
- `api/formulary.py` (new): `router`, `load_layer()`, `async use_clinic_layer()`, `async request_scoped()`, `learn_from_save(conn, structured, confirmed_rows, document_id, user_id)`, `GET /api/v1/formulary`, `DELETE /api/v1/formulary/{entry_id}`.
- `core/formulary.py`: `_active` default is now `None` (sentinel); `active_layer()` returns an empty layer for that case and logs ONE warning per process when the read happens inside a request (`mark_request_scoped()`); CLI, bench and bare threads never warn. `activate()` unchanged.
- `db/formulary.py`: `patient_words(conn)` (casefolded words of 3+ letters from `patients.name`).
- `use_clinic_layer` (dependency) on: `/api/format`, `/api/v1/correct`, `/api/transcribe`, `/api/v1/rx/check-row`, `POST /api/v1/documents` (R1).
- `FastAPI(dependencies=[Depends(request_scoped)])` in `api/app.py`: marks every request so a route that forgot `use_clinic_layer` is reported.
- `policy.py`: action `formulary.manage`, admin only.
- Cache key: `clinic:LAYER_VERSION:key:rawhash` (`api/format.py` ckey).
- Save hook: `learn_from_save` after `log_audit` in `create_document`, called with the INCOMING `structured` (pre-validate indexes) and `req.confirmed_rows`; never raises.
- `tests/conftest.py`: autouse `_private_single_mode_db` sets DB_PATH to `tmp_path_factory.mktemp("single-db")/app.db`. Tests that set their own DB_PATH win (their setenv runs later); `multi` still deletes it.
- Tests/fixtures touched: `tests/test_api_app.py` (2 routes), `tests/isolation_fixtures.py` (TABLES + `clinic_formulary`, `clinic_formulary_docs`), `tests/test_isolation_routes.py` (`ADMIN_ONLY` skip in `id_routes`, 2 CLASSIFIED entries, check-row text updated).

## Adaptations vs the plan text
1. app.py anchors include `rx` (import line and module loop); ckey anchor is `# per clinic and raw wording`.
2. `use_clinic_layer` also on POST /documents (R1) and the pin test is stronger than the plan's textual count: it walks every APIRoute (inside FastAPI's lazy `_IncludedRouter` wrappers, found via `original_router`) and asserts exactly the five expected routes carry `use_clinic_layer`, no more and no fewer. A second test scans `api/*.py` for the grounding functions and fails if a new module uses them (a new grounding route must be reviewed).
3. Fail-loud: request marker via an app-wide async dependency; warn-once via `core.formulary._warned`. The plan had nothing here.
4. `known_patient_words`: `learn_from_save` first calls `learnable(...)` with no words; only if something is learnable does it read the patients table and call again. So the full patients scan runs only when a confirmed unknown name exists.
5. 503/401 handling: list and delete catch `sqlite3.Error` -> 503 `{"error": "try again"}`; delete with no identity in multi mode is 401 (single mode: allowed, no roles).
6. `TABLES` gets both new tables (plan: one).
7. Plan test 5 (the `rx.py` text count) replaced by the structural pin test above.
8. FastAPI here wraps included routers in `_IncludedRouter`, so `app.routes` is not a flat list; do not enumerate routes with `app.routes` directly in new tests (use `_api_routes` in the test file).

## ContextVar findings
- Async dependency sets the var in the request task's context. A sync `def` handler (POST /documents) and `asyncio.to_thread` copy that context: proven by `test_a_synchronous_handler_sees_the_layer_set_by_the_async_dependency` and the per-route tests (format, correct, documents, check-row, transcribe each show an effect that exists only if the layer was visible in the grounding or hint code).
- A bare `Thread` or `ThreadPoolExecutor` sees the empty default (pinned by a test).
- Test-only hazard: the test thread's own ContextVars are copied into TestClient requests (anyio portal). A test that calls `activate()` in the main thread leaks into later tests (this broke `tests/test_hints.py` once). New tests that activate must run inside `contextvars.Context().run(...)` (fixture `fresh_context`) or reset after.
- A load failure (`sqlite3.Error`, such as an unmigrated DB) yields an empty layer plus a logged warning (fails open to "unknown medicine", the safe direction). `NoScope` still propagates to a 401.

## Mutations (28 on scratch copies in scratchpad/h3mut, run against 5 test files)
Killed 25 (each by a named test): dependency missing on each of check-row, documents, transcribe, correct (pin test); layer never activated; sync dependency; version not in cache key; version constant; layer cached across clinics; admin check removed; admin check widened to doctors; known_patient_words not passed; patient_words filter changed; patient_words empty; 503 removed on list; 503 removed on delete; threshold 1; learning from unconfirmed rows; added_by lost; request marker dropped; warn every time; never warn; warn outside requests; no save hook; learn exception not swallowed (the last needed a new test `test_saving_never_fails_because_learning_failed`).
Survivors (2, both equivalent or unreachable):
- `activate(load_layer())` without `to_thread` inside the async dependency: same result, only blocks the event loop briefly. Not testable.
- Removing the route-level 401 for a signed-out DELETE in multi mode: the session middleware already answers 401 before the route runs (tested at middleware level in `test_signed_out_and_malformed_requests_are_rejected`); the branch is defence in depth.

## What h4 must know
- `GET /api/v1/formulary` returns `{"items": [{id, name, generic, confirm_count, first_seen_at, last_seen_at, added_by}]}`; `DELETE` returns `{"removed": id, "name": name}`; 403/404/422/503 shapes as above; any signed-in user may list, only admins delete.
- `ADMIN_ONLY = ("/api/v1/formulary/",)` already exists in `tests/test_isolation_routes.py`; its two routes are classified pointing at `test_formulary_routes.py`. h4's isolation sweep for the admin DELETE is additional and should reuse `ADMIN_ONLY`, not redefine it. TABLES already has both formulary tables.
- The team page needs `added_by` as a user id (join with the users list client-side).
- Tests that activate a layer must use a fresh context (see above).

## Concerns
- Owner-flag R4 unchanged: names within edit distance of a lexicon drug never reach the layer.
- `load_layer` runs one extra query per grounding request and POST /documents (one SELECT on a small table); `patient_words` scans the patients table, but only on a save that confirmed a learnable name.
- The "default layer" warning only fires in a request; a bare thread inside a request is silent by design (it cannot see the marker either).
- Learning failure on save is logged, not shown to the doctor.

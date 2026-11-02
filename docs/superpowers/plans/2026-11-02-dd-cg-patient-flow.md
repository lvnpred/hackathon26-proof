# DD → Count Guard Patient Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A patient saved with "Admit to ward" in Doctor Dictation flows into Count Guard and through ward → theatre → ward → discharge, with real Muse checks at every step, and every older Count Guard feature moved into the care app before the older screens are archived.

**Architecture:** Two servers stay separate. DD pushes an admission after its save commits (new `api/admit.py`, additive `admissions` table); CG takes it through one intake path (`journey/intake.py`, `intake_keys` table) that Sync and New patient also use. CG gains a server-owned ward list and demo clock, explicit live switches with labelled prepared fallbacks, per-item photo verdicts, and new theatre/discharge modules that wrap existing morning and camera-counter helpers. The older route and screen files are archived last, from the import graph.

**Tech Stack:** FastAPI + stdlib sqlite3 + vanilla JS (DD); FastAPI + React 19/Vite + `node --test` + Playwright demo harness (CG); httpx; Muse Voice Transcribe, Muse Spark 1.3, SAM 3.1.

**Spec:** `docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md` (v4; § numbers below refer to it). Code maps with file:line for every touch point: `docs/superpowers/plans/2026-11-02-dd-cg-flow-codemap-dd.md` and `…-codemap-cg.md`. Read the spec and the map for your app before each task.

## Global Constraints

- Run CG commands from `count-guard/`, DD commands from `doctor-dictation/`. CG backend `.venv/bin/pytest -q`; CG frontend `cd frontend && node --test $(find src -name "*.test.js") && node --test $(find scripts -name "*.test.mjs")` and `npm run build`; DD `.venv/bin/python -m pytest tests/ -q`.
- Ports: CG checks 8200/5273, DD checks 8300. **Never** 8100/5173/8000.
- Tests never call live models. Every file stays under 500 lines; the files listed as near the limit in the CG map get no new code — add modules.
- No secret values in code, docs, logs or test output. `CG_SYNC_TOKEN`, `COUNT_GUARD_URL`, `DD_BASE_URL` are read from env at call time (DD: no module-level `get_settings()` in `api/*.py`).
- Synthetic data only to Meta APIs (`03-hackathon-spec.md:42`). Demo-mode names end in "(synthetic)".
- `count_gate` (`backend/app/journey/states.py:95-110`) is not edited. Nothing a model, camera, rule or replay writes may carry a person's `by` on `count.closing`.
- Every prepared result carries `source: "prepared"` and shows the label "Prepared"; with a live switch on, nothing is looked up by uploaded file name (spec §4, §6.7).
- Staff copy: no event names, snake_case or model names outside the Inspector Model tab and `/ai` (existing scan, `frontend/scripts/demo/scan.mjs`).
- Branch `dd-cg-flow` from `main`. **Commits only after the user authorizes commits for this branch** (CLAUDE.md); then one commit per task with `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`, no Co-Authored-By, never push.
- Tier order (spec §9): Tasks 1–11 and 5b are tier V (video path), 12–14 tier F, 15 tier S, 16–18 close-out. At the freeze (3 Nov 18:00 IST, U11) unfinished F/S rows stay on their old screens, hidden from the menu, and Task 16 skips their files.
- **Checkpoint 3 Nov 12:00 IST:** if Tasks 1–11 (with 5b) are not all green, stop tier F/S work and finish the video path.
- Fixed copy (pin in tests): DD buttons "Save & send home" / "Save & admit to ward"; "Saved. Sending to Count Guard…"; "Saved and in Count Guard."; "Saved. Not yet in Count Guard — use Sync there."; "Not checked — model unavailable"; "Prepared"; "Research demo — not for clinical use"; on-screen "synthetic data" in both apps. The video patient is **"M. Fernandes, 52 F (synthetic)"** (not in the seed).
- Every task that changes a string asserted by `beats.mjs`, `steps.mjs`, `beats.test.mjs` or a src test updates those in the same task.

## Review Focus

1. **A DD push and a CG Sync for the same document arrive at the same moment.** Expected: exactly one patient, one `patient.registered`. Pinned in Task 2 (`test_push_and_sync_race_make_one_patient`).
2. **CG is down or hangs while the doctor saves in DD.** Expected: the save returns within 1 s and succeeds; `admissions.last_error` is set; Sync later brings the patient in. Pinned in Task 3 (`test_after_save_only_queues_push`, `test_push_to_blackholed_cg_is_fast_and_records_error`).
3. **The model fails mid-demo with a live switch on.** Expected: "Not checked — model unavailable", the item stays open, override works, no fixture chosen by file name. Pinned in Tasks 5 and 6.
4. **A stale browser tab sends `at_ms` from before a reset, or from the future.** Expected: the server clamps it (spec §8); event order on the episode never goes backwards. Pinned in Task 1.
5. **DD re-saves an admitted patient's document after the patient went to theatre, or switches it to Send home.** Expected: a superseding `rx.ordered` or a "Doctor Dictation now says: send home" notice; the patient's state never changes. Pinned in Task 2.

---

### Task 1: Server-owned ward list and demo clock (CG)

**Files:**
- Create: `backend/app/journey/clock.py`, `backend/app/journey/ward_api.py`
- Modify: `backend/app/journey/seed.py:45` (write `patient.registered`), `backend/app/main.py:50-67` (mount `ward_router`), `backend/app/journey/api.py:138-142` (`_at` delegates to `clock.stamp`)
- Modify: `frontend/src/care/ward.js` (roster from server; clock from server), `frontend/src/journey.js` (add `getWard`, `postClock`)
- Test: `backend/tests/test_ward_list.py`, `frontend/src/care/ward.test.js`

**Interfaces:**
- Produces: `clock.now_ms(store) -> int`; `clock.set_ms(store, ms: int) -> int`; `clock.stamp(store, episode_id: str, at_ms: int | None) -> int` (clamp rule below); `ward_api.register(store, episode_id, *, bed: str, source: str, document_id: int | None, ts_ms: int) -> dict` writes `patient.registered {bed, source, document_id}`; `ward_api.next_bed(store) -> str` (lowest free integer bed as text); routes `GET /journey/ward` → `{"now_ms": int, "patients": [{"id", "name", "bed", "state", "source"}]}` (staff board excluded), `POST /journey/clock {"ms": int}` → `{"now_ms"}`; frontend `getWard() -> Promise<{now_ms, patients}>`, `postClock(ms)`.
- Clock storage: a `clock(id INTEGER PRIMARY KEY CHECK (id=1), now_ms INTEGER)` table appended to `MorningStore.SCHEMA` (`morning/store.py:12-28`), read and written only through new `MorningStore.get_clock() -> int | None` and `MorningStore.set_clock(ms: int) -> int` (clock.py never touches `_conn`/`_lock`). Only `POST /journey/clock` sets the row; the seed leaves it unset; reset deletes it.
- **Clamp rule (keeps today's behaviour when the clock is unset):** `stamp(store, eid, at_ms)` — if `at_ms is None`: `max(latest_ts_on_episode, clock or 0) + 1000` when the episode has events, else `clock or 0`; if given: never below the episode's latest event; above the clock only clamped when the clock row is set. `now_ms(store)` returns the clock or 0.

- [ ] **Step 1: Write failing tests** in `test_ward_list.py`:
  - `test_seed_registers_three_patients_with_beds`: after `POST /journey/demo/seed`, `GET /journey/ward` lists beds `["4","7","9"]` with names from `seed.PATIENTS`, and no "Ward staff board" row.
  - `test_next_bed_is_lowest_free`: with beds 4, 7, 9 taken, `next_bed` is `"1"`; after registering 1, 2, 3 it is `"5"`.
  - `test_stamp_clamps_future_to_server_now`: server clock 600_000; `stamp(eid, 900_000) == 600_000`.
  - `test_stamp_clamps_behind_latest_event`: latest event on the episode at 500_000; `stamp(eid, 100_000) == 500_000`.
  - `test_stamp_none_on_empty_episode_uses_server_now`: clock 600_000, new episode → `stamp(eid, None) == 600_000`.
  - `test_seed_then_future_at_ms_unchanged`: seed, then a nurse action with `at_ms = 2*H + 5*M` keeps that time (as `test_care_story.py:91` relies on).
  - `test_existing_at_ms_unchanged_when_clock_unset`: no clock row; `stamp(eid, 120_000) == 120_000`; `stamp(eid, None) == 121_000` after that event (today's `_at`).
  - `test_clock_route_moves_time_for_all_patients`: `POST /journey/clock {"ms": 3_600_000}` then `GET /journey/ward` → `now_ms == 3_600_000`.
- [ ] **Step 2: Run** `.venv/bin/pytest -q backend/tests/test_ward_list.py` — expect FAIL (no module).
- [ ] **Step 3: Implement** `clock.py`, `ward_api.py`, the seed change and `_at` delegation. The Demo dock's tick/jump/reset call `POST /journey/clock`; reset also resets the clock to 0.
- [ ] **Step 4: Frontend.** `useWard()` (`care/ward.js:78`) loads `getWard()` on mount, after each action, and every `wardPollIntervalMs()` (= 1000 until Task 14 adds the stream, then 3000 as the fallback) while the page is visible; it no longer keeps a roster or `NOW` in sessionStorage (ROLE/PATIENT stay). Test in `ward.test.js`: `rosterFrom({now_ms: 5, patients:[{id:"a",bed:"4"}]})` returns `{nowMs: 5, patients:[…]}` sorted by bed number; `wardPollIntervalMs() === 1000` (Task 14 changes it to 3000 and updates this test).
- [ ] **Step 5: Run** the backend suite, the frontend tests, then `make demo-check` — all PASS (the existing 32 beats still pass).
- [ ] **Step 6: Commit** (when authorized): `Count Guard: server-owned ward list and demo clock`.

### Task 2: Intake — one path for push, Sync and New patient (CG)

**Files:**
- Create: `backend/app/journey/intake.py`, `backend/app/journey/intake_api.py`
- Modify: `backend/app/morning/store.py:12-28` (append `intake_keys` table), `backend/app/main.py` (mount), `backend/app/config.py` (add `sync_token` from `CG_SYNC_TOKEN`)
- Modify (UI): the chart header component under `frontend/src/care/` that shows the patient name — add bed (doctor can change it), age/sex, OP number, diagnosis, DD doctor and a "Doctor Dictation PDF" link
- Test: `backend/tests/test_intake.py`, fixture `backend/tests/fixtures/dd_admission.json` (shared with DD Task 3)

**Interfaces:**
- Consumes: Task 1 `clock.now_ms`, `ward_api.register`, `ward_api.next_bed`; `rx.from_document(document, *, source)` (`rx.py:82`); `states.move_payload(events, to, body)` (`states.py:159`); `api.settle(request, eid, ts)`.
- Produces:
  - `MorningStore.claim_intake(source: str, document_id: int, finalized_at: str, label: str) -> tuple[str, bool]` — **one** lock acquisition and one transaction: on a new key it inserts the `episodes` row (id from `new_id()`), the `intake_keys` row and the bed (lowest free, same rule as `next_bed`, stored in an `episode_beds(episode_id PRIMARY KEY, bed UNIQUE)` table also used by `register` and `bed.changed`) together and returns `(episode_id, True)`; on a duplicate it returns `(stored_episode_id, False)`. The episode id is never NULL. `MorningStore.update_intake(source, document_id, finalized_at) -> bool` (True when changed). No `bind_intake`.
  - `intake.take(store, payload: dict, *, now_ms: int) -> dict` → `{"episode_id", "bed", "created": bool, "updated": bool, "notice": str | None}`.
  - `intake.new_patient(store, *, name: str, age_sex: str, reason: str, now_ms: int) -> dict` (source `count-guard`, state `clinic`, no `rx.ordered`).
  - Routes: `POST /journey/intake` (DD payload, spec §7.1; 201 created / 200 existing; 401 when `CG_SYNC_TOKEN` is set and header `X-CG-Sync-Token` differs), `POST /journey/patients` `{name, age_sex, reason}` (422 unless the name ends "(synthetic)" while the demo seed is in use).
- Payload: `{"source", "document_id", "status": "admit"|"send_home", "admit_reason", "finalized_at", "document"}`. Name from `document.structured.patientName`; `ageSex`, `opNo`, diagnosis and the DD doctor (`document.author.doctor_name`) are stored in `patient.registered` and shown on the chart, with the DD PDF link `f"{settings.dd_base}/api/v1/documents/{document_id}/pdf"`.
- `intake.take` and `intake.new_patient` take no `Request`; the routes call `api.settle(request, eid, ts)` for each episode with `created` or `updated`.
- `POST /journey/episodes/{id}/bed {bed, by}` (doctor) → `bed.changed`; 409 when the bed is taken.

- [ ] **Step 1: Write failing tests** in `test_intake.py`:
  - `test_admit_creates_patient_in_admitting_with_rx`: posting the fixture → 201, ward lists the patient in `admitting`, events in order `patient.registered`, `rx.ordered` (rows from the fixture), `patient.state {to:"admitting", reason: fixture admit_reason}`.
  - `test_second_post_is_idempotent`: same payload twice → second is 200, `created == False`, one `patient.registered`.
  - `test_concurrent_different_documents_get_distinct_beds`: 8 threads, 8 different `document_id`s → 8 distinct beds.
  - `test_push_and_sync_race_make_one_patient`: 8 threads call `intake.take` with the same payload → exactly one episode in `GET /journey/ward` with that `document_id`.
  - `test_resave_with_new_finalized_at_supersedes_rx`: second payload with a later `finalized_at` and a changed row → 200, `updated == True`, the new `rx.ordered` has `supersedes_id` = the old one, notice `"Prescription updated in Doctor Dictation"`.
  - `test_resave_after_theatre_never_changes_state`: move the patient to `theatre`, re-post with a new `finalized_at` → state still `theatre`.
  - `test_send_home_resave_adds_notice_only`: re-post with `status:"send_home"` → a `notice.dd` event text `"Doctor Dictation now says: send home"`; state unchanged.
  - `test_unchanged_resave_appends_nothing`: same `finalized_at` → event count unchanged.
  - `test_token_required_when_set`: with `CG_SYNC_TOKEN=t`, no header → 401; header `t` → 201.
  - `test_new_patient_starts_in_clinic`: `POST /journey/patients` → state `clinic`, no `rx.ordered`; `/state {to:"admitting", reason:"x", by: seed.DOCTOR}` → 200.
  - `test_settle_runs_after_intake`: monkeypatch `ops_run.run` to record calls → called once for the new episode.
  - `test_intake_links_dd_pdf_via_dd_base_url`: with `dd_base="http://127.0.0.1:8300"` the chart view has `dd_pdf == "http://127.0.0.1:8300/api/v1/documents/42/pdf"`, plus `age_sex`, `op_no`, diagnosis and DD doctor.
  - `test_doctor_moves_bed`: bed 1 → 5 → ward shows 5; moving to a taken bed → 409.
- [ ] **Step 2: Run** — expect FAIL.
- [ ] **Step 3: Implement** `claim_intake` (catch `sqlite3.IntegrityError` → look up the stored episode), `intake.take`, `intake.new_patient`, routes. Event times come from `clock.now_ms`.
- [ ] **Step 4: Run** the backend suite — PASS.
- [ ] **Step 5: Commit** (when authorized): `Count Guard: patient intake for Doctor Dictation admissions, Sync and new patients`.

### Task 3: Save & admit to ward (DD)

**Files:**
- Create: `doctor_dictation/db/migrations/015_admissions.sql`, `doctor_dictation/api/admit.py`, `frontend/admit.js`
- Modify: `doctor_dictation/api/persistence.py:139-146` (add `admit: bool = False`, `admit_reason: str = ""`) and `:353` (one call into `admit.after_save`), `doctor_dictation/api/app.py:89-91` (register `admit`), `frontend/index.html:104` (second button, reason input, load `admit.js`), `tests/test_db.py:88-100` (version list, `n == 15`), `tests/test_api_app.py:13-40` (add `("GET","/api/v1/admissions")`)
- Test: `tests/test_admit.py` (uses `count-guard/backend/tests/fixtures/dd_admission.json` field list)

**Interfaces:**
- Produces:
  - Table `admissions(document_id INTEGER PRIMARY KEY, status TEXT NOT NULL, reason TEXT, admitted_at TEXT, pushed_at TEXT, last_error TEXT)`.
  - `admit.after_save(request, background_tasks, *, document_id: int, admit: bool, reason: str, resave: bool) -> None`: records `status='admit'` when `admit`; on a re-save of an admitted document without `admit`, sets `status='send_home'`; a never-admitted document is left alone (U12). Builds the payload in the request (scope rule, DD map) and queues `admit.push(payload, url, token, db)`.
  - `admit.push(payload: dict, url: str, token: str, db: Path) -> None`: `httpx.post(url + "/journey/intake", timeout=httpx.Timeout(3.0, connect=1.0))`; writes `pushed_at` or `last_error` to `db` (resolved with `db_path()` inside the request); never raises.
  - `after_save` is a no-op when `multi_clinic_enabled()` (intake is single-clinic only, spec §7.4).
  - `GET /api/v1/documents/{id}/admission` (same origin, no token) → `{"status", "pushed_at", "last_error"}` or 404; the browser polls only this.
  - `admit.payload_for(conn, document_id) -> dict` — the spec §7.1 body including `status` and `finalized_at`; used by push and by `GET /api/v1/admissions?since=<iso>` → `{"admissions": [payload…]}`; 404 when `multi_clinic_enabled()`; 401 when `CG_SYNC_TOKEN` is set and `X-CG-Sync-Token` differs.
  - Frontend: `admit.js` wires `#admitBtn` → shows the reason input (required) → calls the existing save with `admit: true, admit_reason`. Status after the save returns: `"Saved. Sending to Count Guard…"`; it polls `/api/v1/documents/{id}/admission` (1 s, up to 5 tries) and shows `"Saved and in Count Guard."` once `pushed_at` is set, or `"Saved. Not yet in Count Guard — use Sync there."` on `last_error` or timeout. Buttons read `"Save & send home"` (the existing `#saveBtn`) and `"Save & admit to ward"`.
- `create_document` gains `background_tasks: BackgroundTasks`; nothing else in it changes. Admit with an empty reason → 422 `{"error":"admission reason required"}` before the gate.

- [ ] **Step 1: Write failing tests** in `test_admit.py`:
  - `test_admit_save_records_admission_and_pushes`: monkeypatch `admit.push` to capture; save `SAVE` + `admit:true, admit_reason:"Hernia repair"` → 200; one captured payload with every key in the CG fixture and `status=="admit"`.
  - `test_send_home_save_records_nothing`: plain save → `admissions` empty, no push.
  - `test_admit_without_reason_is_422`.
  - `test_verify_gate_still_blocks_admit`: unverified row + admit → 409, no admission row, no push.
  - `test_after_save_only_queues_push`: call `after_save` with a real `BackgroundTasks` → `background_tasks.tasks[0].func is admit.push`; nothing sent yet.
  - `test_push_to_blackholed_cg_is_fast_and_records_error`: `admit.push(payload, "http://10.255.255.1:9", "", db)` returns in < 1.5 s, raises nothing, and `last_error` is set.
  - `test_admission_status_route`: `GET /api/v1/documents/{id}/admission` → `{"status":"admit","pushed_at":…,"last_error":None}`; no token needed.
  - `test_after_save_noop_in_multi_clinic` (the `multi` fixture).
  - `test_resave_admitted_as_send_home_sets_status`: admit, then re-save the same `document_id` without admit → `status=='send_home'`, pushed again.
  - `test_admissions_since_lists_payloads` and `test_admissions_404_in_multi_clinic` (use the `multi` fixture) and `test_admissions_token`.
- [ ] **Step 2: Run** `.venv/bin/python -m pytest tests/test_admit.py -q` — expect FAIL.
- [ ] **Step 3: Implement** the migration, `admit.py`, the two `persistence.py` touches, router registration, frontend. `app.js` is a classic script, so `saveDocument` is already global. Exactly two `app.js` edits: `if (window.ddAdmit) Object.assign(payload, window.ddAdmit)` at the end of the payload builder (~`:1133`), and `return j` before the success status (~`:1159`). `admit.js` sets `window.ddAdmit` and clears it in `try/finally`, and sets its own status when the call returns truthy. `#admitBtn` follows `saveBtn.hidden` (`app.js:1015,1339` — mirror it in `admit.js` with a `MutationObserver`). Bump `app.js?v=` in `index.html:346` and add `admit.js?v=1`.
- [ ] **Step 4: Run** the whole DD suite — PASS.
- [ ] **Step 5: Commit** (when authorized): `Doctor Dictation: Save and admit to ward pushes the patient to Count Guard`.

### Task 4: Sync and New patient in the care app (CG)

**Files:**
- Create: `backend/app/journey/sync.py`, `frontend/src/care/WardActions.jsx`
- Modify: `backend/app/journey/intake_api.py` (route), `frontend/src/care/CareShell.jsx` (render `WardActions` on the ward list), `frontend/src/journey.js` (`syncWard`, `newPatient`)
- Test: `backend/tests/test_sync.py`, `frontend/src/care/WardActions.test.js`

**Interfaces:**
- Consumes: Task 2 `intake.take`, `intake.new_patient`; `config.dd_base`; `config.sync_token`.
- Produces: `sync.pull(settings, store, *, since: str | None, now_ms: int, get=httpx.get) -> dict` → `{"new": int, "existing": int, "updated": int, "error": str | None}`; route `POST /journey/sync` (browser → CG → DD, token sent server-side only); `syncSummary({new, existing, updated}) -> str` e.g. `"2 new, 3 already here, 1 updated"`.

- [ ] **Step 1: Failing tests**: `test_sync_pulls_missed_admission` (fake `get` returns two payloads → `new == 2`), `test_sync_twice_is_idempotent` (`existing == 2`), `test_sync_reports_dd_down` (`get` raises → `error == "Doctor Dictation is not reachable"`, nothing written), `test_sync_sends_token_header` (captures header), `test_sync_settles_each_new_patient` (route test; `ops_run.run` called once per new or updated episode). JS: `syncSummary({new:2, existing:3, updated:1}) === "2 new, 3 already here, 1 updated"`; `newPatientError({name:"Kiran"}) === "Add \"(synthetic)\" to the name"`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement.** The ward list shows **Sync** and **New patient** (name, age/sex, reason) for staff roles only.
- [ ] **Step 4: Run** backend + frontend tests + `make demo-check` — PASS. **Step 5: Commit** (when authorized).

### Task 5: Live switches and labelled prepared fallbacks (CG)

**Files:**
- Create: `backend/app/journey/switches.py`
- Modify: `backend/app/config.py` (fields `voice_live`, `proof_live`, `spark_live` from `VOICE_LIVE`, `PROOF_LIVE`, `SPARK_LIVE`; default on when a key is set, off otherwise), `backend/app/journey/live.py:120-135,187-212` (no file-name fallback when the switch is on), `backend/app/journey/video_api.py:21-23`, `backend/app/journey/ask_api.py:32` (read from `switches`)
- Test: `backend/tests/test_switches.py`

**Interfaces:**
- Produces: `switches.is_live(settings, name: Literal["voice","proof","spark","tray","setup","swabs","medicines"]) -> bool`; `switches.unavailable(reason: str) -> dict` → `{"source": "unavailable", "why": reason}`. Every prepared result dict carries `"source": "prepared"`; every live one `"source": "live"`.

- [ ] **Step 1: Failing tests**: `test_live_transcribe_failure_never_uses_filename_fixture` (switch on, adapter raises, file named like a fixture stem → result `source == "unavailable"`); `test_switch_off_uses_prepared_and_labels_it`; `test_read_photo_failure_live_is_unavailable`; `test_all_switches_listed_in_models_route` (`GET /journey/models` reports each switch, `live` false with no key — `server.mjs` asserts this).
- [ ] **Step 2–4:** run FAIL → implement → run suite + `make demo-check` PASS. **Step 5: Commit** (when authorized).

### Task 5b: Sample media and sources (tier V)

**Files:**
- Create: `count-guard/eval/media/SOURCES.md`, files under `count-guard/eval/media/<kind>/` — wristband photo, a wrong photo (no wristband), consent form, monitor screen, medicine bag, discharge card, saline set-up, swab tray, a swab-count clip with one swab leaving the field, drug-phrase audio (macOS `say`), home-medicine strips
- Modify: `count-guard/.gitignore` (keep `eval/p3/real/` out)
- Test: `backend/tests/test_media_sources.py`

- [ ] Steps: failing test `test_every_media_file_has_a_source_row` (each file under `eval/media/` appears in `SOURCES.md` with URL, licence and author, or "recorded for this project" per U14) → download openly licensed files into their own empty folders (no faces, no real records) → PASS → commit (when authorized). Tasks 6, 8, 11 use these files.

### Task 6: Photo proof verdicts for every check (CG)

**Files:**
- Create: `backend/app/journey/verdict.py`, `backend/app/journey/verdict_api.py`, `backend/app/journey/expected.py` (expected-photo lines, spec §6.6), `frontend/src/care/ProofItem.jsx`
- Modify: `backend/app/adapters/spark.py` (add `check_photo(raw: bytes, content_type: str, expect: str) -> dict`), `backend/app/journey/tasks.py:262` (refuse `task.done` while `verdict.item_open(events, f"task:{task_id}")`), `frontend/src/care/Checklist.jsx`, `frontend/src/care/TaskProof.jsx`, `frontend/src/care/TheatreChecklist.jsx` (theatre-step proofs), `backend/app/journey/proof.py:1-3` (docstring: D9 now applies to strip/monitor reads only; proof verdicts follow U9)
- Test: `backend/tests/test_verdict.py`, `frontend/src/care/ProofItem.test.js`

**Interfaces:**
- Consumes: Task 5 `switches`.
- Produces:
  - `expected.EXPECT: dict[str, str]` keyed `"admission:band"`, `"admission:allergies"`, `"admission:baseline_obs"`, `"admission:consent"`, `"discharge:card_given"`, `"discharge:medicines_handed"`, `"discharge:reminders_set"`, `"theatre:<step>"`, `"task:<kind>"`.
  - `verdict.check(settings, *, item: str, raw: bytes, content_type: str) -> {"verdict": "accepted"|"not_accepted"|"not_checked", "why": str, "source": "live"|"prepared"|"unavailable"}`.
  - Events: `check.photo {item, photo_id, verdict, why, source}`, `check.override {item, reason, by}`.
  - `verdict.item_open(events, item: str) -> bool` — **rule (a), my call:** an item is open only when its latest `check.photo` is `not_accepted` or `not_checked` and no later `check.override` exists. An item with no photo is not open, so existing tests that move with a checklist only keep passing; the demo and the video always attach the photo. **An item with no photo shows "No photo" on the chart and in Evidence** (`verdict.photo_state(events, item) -> "accepted"|"not_accepted"|"not_checked"|"overridden"|"none"`), so a missing proof is visible, never silent.
  - Ward-task items are keyed `task:<task_id>` (not by kind); `expected.EXPECT` is looked up by `task:<kind>`.
  - Routes `POST /journey/episodes/{id}/checks/{item}/photo` (multipart) and `POST …/checks/{item}/override {reason, by}` (422 on empty reason).
  - Gating lives in a new `backend/app/journey/check_gate.py`: `missing_checks(events, to: str) -> list[str]` used by `flow_api` `/state` before `move_payload` for `admitting→ward` and `discharging→home` only; returns items still open. `flow_api` returns 409 `{"error":"photo checks open","items":[…]}` where items are readable labels from `states.CHECK_WORDS` (e.g. `"wristband"`), never snake_case.
- Theatre-step and ward-task proofs never feed `missing_checks`, and `/surgery` never calls it.

- [ ] **Step 1: Failing tests**:
  - `test_not_accepted_keeps_admission_open`: a `not_accepted` photo on `admission:band` only → `/state {to:"ward", checklist all true}` → 409 with `items == ["wristband"]`.
  - `test_move_without_photos_still_allowed` (rule (a)) and `test_item_without_photo_shows_no_photo`.
  - `test_unavailable_copy`: the view text for a `not_checked` item is exactly `"Not checked — model unavailable"`.
  - `test_override_with_reason_opens_the_move`; `test_override_without_reason_is_422`.
  - `test_unavailable_model_is_not_checked_and_open` (switch on, adapter raises).
  - `test_prepared_verdict_when_switch_off_is_labelled`.
  - `test_theatre_proof_never_blocks_surgery_end`: a `not_accepted` `theatre:swab_tray` item plus a valid person's closing → `/surgery {step:"ended"}` 200.
  - `test_task_done_refused_while_proof_not_accepted`, `test_task_done_refused_while_not_checked` and `..._allowed_after_override`.
  - JS `proofLabel({verdict:"not_accepted", source:"live", why:"No wristband visible"}) === "Not accepted — No wristband visible"`; prepared adds `" · Prepared"`.
- [ ] **Step 2–4:** FAIL → implement → suite + `make demo-check` PASS (the demo beats attach photos from Task 5b's `eval/media/` to admission and discharge items; update `steps.mjs` for the new photo steps). **Step 5: Commit** (when authorized).

### Task 7: Theatre — drug given by voice, vitals strip, context card (CG)

**Files:**
- Create: `backend/app/journey/theatre_api.py`, `frontend/src/care/TheatreDrugs.jsx`, `frontend/src/care/VitalsStrip.jsx`, `frontend/src/care/ContextCard.jsx`
- Modify: `backend/app/main.py` (mount), the theatre chart component that renders `TheatreChecklist` (add the three panels)
- Test: `backend/tests/test_theatre_api.py`, `frontend/src/care/theatre.test.js`

**Interfaces:**
- Consumes: `morning.druglog.parse_drug_phrase(text)`, `morning.vitals.demo_readings/evaluate/template_card/choose_wording`, `morning.sim.apply(...)`, `live.transcribe`, Task 5 `switches`.
- Produces: `POST …/theatre/drug` (audio or `{text}`) → `druglog.parsed` (grounded row), `POST …/theatre/drug/{id}/confirm` → `drug.given`; `POST …/theatre/vitals/step` → `vitals.reading` events labelled `"Simulated"`; `GET …/theatre/card` → the context card or 404 unless the tier toggle is on (`POST …/theatre/tier {on: bool}`), always with the research banner text `"Research demo — not for clinical use"`.
- Allowed only in state `theatre` (409 `{"error":"not in theatre"}` otherwise).
- **Hard stop:** nothing heard or seen writes `count.pack_opened` or `count.closing`. A heard pack phrase writes `count.pack_heard`; only a person's confirm tap writes `count.pack_opened` with their `by` (same pattern as drugs).

- [ ] **Step 1: Failing tests**: `test_drug_phrase_becomes_grounded_row` ("lignocaine two percent, five ml, local infiltration" → name lignocaine, 2%, 5 ml); `test_drug_needs_confirm_before_given`; `test_vitals_drop_raises_card_with_three_sources` (append `brownbag.med_found` metoprolol directly with `store.append`, so this task does not depend on Task 10; BP 120→86 after the drug; card text names the drug, the home medicine and the swab count); `test_spoken_pack_phrase_is_heard` ("opening twenty swabs" → a `count.pack_heard {n: 20}` draft only, the morning "hear" intent); `test_heard_pack_never_counts_until_confirmed` (the draft leaves `stay_opened` unchanged; `POST …/theatre/pack/{id}/confirm {by}` writes `count.pack_opened` with that person's `by`); `test_card_404_when_tier_off`; `test_theatre_routes_refuse_outside_theatre`. JS: `vitalsLabel(reading).includes("Simulated")`.
- [ ] **Step 2–4:** FAIL → implement → suite PASS. **Step 5: Commit** (when authorized).

### Task 8: Theatre swab camera, advisory rules, missing-swab frame (CG)

**Files:**
- Create: `backend/app/journey/camera_api.py`, `backend/app/journey/advice.py`, `frontend/src/care/CameraAdvice.jsx`
- Modify: `frontend/src/care/CountPanel.jsx` (render advice and frame), `backend/app/main.py`
- Test: `backend/tests/test_camera_advice.py`, `backend/tests/test_count_gate_paths.py` (A6)

**Interfaces:**
- Consumes: `media_pipeline.run_recorded_video(engine, case_id, source, concepts=None)`, `core.rules.closing_gate`, morning `count/from-case` and `count/frame` logic (move the bodies into `camera_api`, leaving the morning routes calling them until Task 16), `live.segment_clip`, `switches.is_live(settings,"swabs")`.
- Produces: `POST …/camera/case` (creates the camera case with the engine — create, zones, upload as in `api/routes.py:70-84` — and links it to the stay → `camera.linked {case_id}`); `WS /journey/episodes/{id}/camera/live` (the live detection socket moved from `api/ws.py`); `POST …/camera/clip` (SAM run) ; `GET …/camera/frame?item=` → JPEG of the last frame for a missing item; `advice.from_case(engine, case_id) -> list[{"rule": "R1".."R6", "item", "text", "frame_id"}]` written as `camera.advice` with `by: "Count Guard AI"`; `POST …/camera/advice/{id}/ack {by, reason?}` → `camera.ack`.
- Advice never writes `count.closing`; ending surgery never reads `camera.ack` (U10).

- [ ] **Step 1: Failing tests** (`test_count_gate_paths.py`, all through HTTP):
  - `test_camera_and_rules_never_close_the_count` — run a clip with one missing swab → `count_gate(events) == "none"`.
  - `test_unacknowledged_advice_with_valid_manual_closing_ends_surgery` → 200.
  - `test_ai_written_closing_never_ok_via_intake_patient`, `…via_sync_patient`, `…via_new_patient` (patients created by Tasks 2/4) → `/surgery ended` 409.
  - `test_short_manual_count_still_409_with_camera_agreeing`.
  - `test_camera_never_writes_pack_opened`.
  - `test_missing_swab_frame_is_returned` (JPEG bytes, `content-type: image/jpeg`).
  - `test_camera_case_created_and_linked` (the `count/from-case` row), `test_rules_produce_advice_rows` (a clip with an unannounced gauze → an R4 advice row), `test_manual_count_route_in_care` (the `count/manual` row), `test_camera_live_socket_streams_detections` (TestClient websocket receives at least one detection message).
- [ ] **Step 2–4:** FAIL → implement → suite + `make demo-check` PASS. **Step 5: Commit** (when authorized).

### Task 9: Discharge drafted from the timeline, PDF and .ics (CG)

**Files:**
- Create: `backend/app/journey/discharge_api.py`, `backend/app/journey/discharge_draft.py`
- Modify: `frontend/src/care/DoctorActions.jsx` (Draft discharge button opens the draft; existing Dictate discharge edits it), patient view shows the discharge card (move `/discharge-card` use here)
- Test: `backend/tests/test_discharge_draft.py`

**Interfaces:**
- Consumes: `morning.pdf.write_discharge(path, *, label, sheet)`, `morning.ics.follow_up_ics(label, start=None)`, `morning.discharge.visible_events`, `seed.card_payload`.
- Produces: `discharge_draft.build(events) -> dict` with keys `prescription` (latest `rx.ordered`), `drugs_given` (`drug.given`), `count` (latest person closing summary), `events` (key moves), `follow_up`; `POST …/discharge/draft` → `discharge.drafted`; `GET …/discharge.pdf`; `GET …/follow-up.ics`.

- [ ] **Step 1: Failing tests**: `test_draft_pulls_rx_drugs_and_count` (after Tasks 2, 7, 8 events, the draft has the DD rows, lignocaine 5 ml, and "opened 20 / returned 20"); `test_pdf_contains_drug_and_count` (use the `pdf_text` fixture); `test_ics_has_follow_up_date`; `test_draft_refused_before_ward` (state `admitting` → 409); `test_discharge_card_in_patient_view`; `test_discharge_wording_live_and_template_fallback` (Spark wording passes the wording check when live; with `SPARK_LIVE` off the template text shows with "Prepared").
- [ ] **Step 2–4:** FAIL → implement → suite PASS. **Step 5: Commit** (when authorized).

### Task 10: Photo of medicines from home (merges brown-bag and strips) (CG)

**Files:**
- Create: `frontend/src/care/HomeMedicines.jsx`
- Modify: `backend/app/journey/media_api.py:266` (`/strips/photo` also writes `brownbag.med_found` rows), `frontend/src/care/DoctorActions.jsx` (replace `StripPhoto` entry with `HomeMedicines`)
- Test: `backend/tests/test_home_medicines.py`

**Interfaces:**
- Consumes: `morning.brownbag`, `morning.strips`, `live.read_photo`, `switches.is_live(settings,"medicines")`.
- Produces: one doctor action "Photo of medicines from home" whose result lists each medicine with its match to the prescription; the theatre context card (Task 7) reads `brownbag.med_found`.

- [ ] **Step 1: Failing tests**: `test_home_medicine_photo_lists_metoprolol` (prepared, labelled); `test_live_failure_is_unavailable_not_fixture`; `test_context_card_reads_home_medicine`.
- [ ] **Step 2–4:** FAIL → implement → suite PASS. **Step 5: Commit** (when authorized).

### Task 11: Two-app demo-check and live-check

**Files:**
- Modify: `frontend/scripts/demo/server.mjs` (start DD on 8300 with `../doctor-dictation/.venv/bin/python -m uvicorn doctor_dictation.main:app`, a temp `DB_PATH`, stub providers as in `doctor-dictation/scripts/demo_browser.py:45-48` but with a stub form for "M. Fernandes, 52 F (synthetic)" whose rx rows carry `status: "verified"` so the gate passes — set `DD_BASE_URL=http://127.0.0.1:8300` for CG and `COUNT_GUARD_URL=http://127.0.0.1:8200` for DD; refuse 8000/8100/5173), `frontend/scripts/demo/beats.mjs`, `steps.mjs`, `beats.test.mjs` (new beat list for the §12 flow: DD dictate → Save & admit; ward arrival; photo Accepted and Not accepted; theatre drug, card, camera, missing frame, hard stop; discharge draft and PDF), `Makefile` (`live-check` target)
- Create: `backend/app/live_check.py`
- Test: `frontend/scripts/demo/beats.test.mjs`, `backend/tests/test_live_check.py`

**Interfaces:**
- Produces: `make demo-check` (no key) prints `DEMO CHECK PASSED: <n> beats; …`; `beats.test.mjs` pins the new beat count and per-scene seconds matching spec §12 (DD 30 s, ward 25 s, theatre 60 s, discharge 40 s, ±4 s each; total ≤ 180 s); `make live-check` → `live_check.run(settings, out_dir) -> list[{"model","ok","seconds","artifact"}]`, one real call per §6.7 model, saving artifacts to `count-guard/eval/live/<YYYY-MM-DD>/` and printing `make cost` estimates. `live_check` refuses to run without a key.

- [ ] **Step 1: Failing tests**: the updated `beats.test.mjs` (also asserts a beat expecting the patient on the CG ward within 3 s of the DD save, and that "synthetic data" and "Research demo" appear in both apps' beats); `test_live_check_refuses_without_key`; `test_live_check_writes_one_row_per_model` (adapters faked).
- [ ] **Step 2–4:** FAIL → implement → `make demo-check` PASS.
- [ ] **Step 5: Run `make live-check` by hand with the key** (U15: no spend limit until 4 Nov). Record the result rows in the task report; artifacts are not committed.
- [ ] **Step 6: Commit** (when authorized).

### Task 12: Tier F — nurse and patient features from journey v1 (CG)

**Files:**
- Move: `AuditTable` (`screens/Audit`), `CheckIn`, `MyCard`, `NeedHelp` (`screens/PatientCard`), `Nudges`, `Reminders`, `Strips` (`screens/TodayPanel`), `RxImport`, `RxTable` (`screens/ClinicPanel`) into `frontend/src/care/legacy/` and repoint `care/History.jsx:3`, `care/Today.jsx:10-11`, `care/DoctorActions.jsx:2`
- Create: `frontend/src/care/Handover.jsx`, `frontend/src/care/DoseGiven.jsx`
- Test: `frontend/src/care/legacy.test.js`, `backend/tests/test_care_paths.py`

**Interfaces:**
- Consumes existing routes `/handover`, `/handover/{id}/accept`, `/dose`, `/reminders(.ics)`, `/checkin`, `/help`, `/audit` (`journey/api.py`).
- Produces: a named care-path test per spec §9 row: `test_handover_from_nurse_chart`, `test_dose_given_from_nurse_chart`, `test_reminders_ics_from_patient_view`, `test_checkin_and_help_from_patient_view`, `test_audit_in_history`, `test_audit_rows_on_ai_page`; each calls the route the care component calls.

- [ ] Steps: failing tests → move/create → frontend tests, build, `make demo-check` PASS → commit (when authorized).

### Task 13: Tier F — count extras and camera-case close (CG)

**Files:**
- Modify: `backend/app/journey/camera_api.py` (add replay, bucket-dwell, resolve, close), `frontend/src/care/CountPanel.jsx` / `CameraAdvice.jsx`
- Test: `backend/tests/test_camera_extras.py`

**Interfaces:**
- Consumes: `count_rules.replay/observe/fresh_state`, `engine.resolve(id, reason, by)`, `agent.reconciler.explain_case(store, settings, case_id)` (Spark 1.3 via the Meta key; Spark Open when `BASETEN_API_KEY` is set), `report.count_sheet.write_count_sheet(...)`.
- Produces: `POST …/camera/replay` (labelled "Prepared"), `POST …/camera/advice/{id}/resolve {reason, by}`, `POST …/camera/close` → explanation + `GET …/count-sheet.pdf`.

- [ ] Steps: failing tests `test_replay_is_labelled_prepared`, `test_bucket_dwell_counts_returned`, `test_resolve_needs_reason`, `test_close_writes_count_sheet_pdf`, `test_explanation_never_writes_closing` → implement → suite PASS → commit (when authorized).

### Task 14: Tier F — correction and the live stream (CG)

**Files:**
- Create: `backend/app/journey/stream_api.py` (SSE moved from `morning/api.py:107-146`), `backend/app/journey/correct_api.py` (from `routes_extra.py:182`, same refusals), `frontend/src/care/Correct.jsx`
- Modify: `frontend/src/care/ward.js` (follow `GET /journey/ward/stream`; 3 s refresh fallback), Inspector History (Correct button)
- Test: `backend/tests/test_stream.py`, `backend/tests/test_correct.py`

**Interfaces:**
- Produces: `GET /journey/ward/stream` (SSE, `id:` = event id, resumes from `Last-Event-ID`), `GET /journey/episodes/{id}/stream`; `POST …/correct {event_id, payload, by}` → superseding event; refuses `count.*`, `surgery.*`, `patient.state` (409).

- [ ] Steps: failing tests `test_stream_emits_new_event_within_1s`, `test_stream_resumes_from_last_event_id`, `test_correct_supersedes`, `test_correct_refuses_count_and_state` → implement → suite + `make demo-check` PASS → commit (when authorized).

### Task 15: Tier S — evidence viewer, Help page, typed home-medicine list (CG)

**Files:**
- Modify: Inspector Evidence (frames, tracks, events of a linked camera case via `camera_api`), `frontend/src/care/Help.jsx` (content from `morning/guide.py`), `HomeMedicines.jsx` (typed fallback using `/brownbag/text` logic moved into `media_api`-adjacent new module `journey/home_meds_api.py`)
- Test: `backend/tests/test_evidence_case.py`, `frontend/src/care/help.test.js`

- [ ] Steps: failing tests `test_evidence_lists_case_frames_and_tracks`, `test_typed_home_medicines_grounded`, JS `helpSections().length > 0` → implement → PASS → commit (when authorized). Skip at the freeze if not done (U11).

### Task 16: Archive the older screens and routes

**Files:**
- Create: `count-guard/scripts/archive_set.py` (import-graph walk from `backend/app/main.py` and `frontend/src/main.jsx`), `backend/app/journey/episode_api.py` (`POST /journey/episodes {label}` replacing `POST /morning/episodes`)
- Move to `count-guard/archive/`: files the script lists as unreachable after the routes below are unmounted — expected: `frontend/src/screens/*` not imported by care, `backend/app/morning/api.py`, `backend/app/morning/routes_extra.py`, `backend/app/morning/script.py`, `backend/app/api/routes.py`, `backend/app/api/ws.py`, `backend/app/journey/play.py` (remove its import `journey/api.py:17` and route `:401-406`)
- Modify: `backend/app/main.py:50-67` (unmount), `frontend/src/App.jsx:170-194` (drop old routes and menu entries), tests that POST `/morning/episodes` → `/journey/episodes` (21 files use `/morning/` routes); tests of archived routes move to `archive/tests/`
- Test: `backend/tests/test_archive.py`

**Interfaces:**
- `archive_set.unreachable(root: Path) -> list[Path]`; only rows whose §9 test passes are archived — the script takes `--keep <path>` for freeze leftovers. A kept screen stays routed but leaves the menu (U11): `App.jsx` menu entries come from one `MENU` list; kept screens are removed from it.
- Tests: list each of the 21 files using `/morning/` routes in the task report as "repointed to `/journey/episodes`" or "moved to `archive/tests/` with its route".

- [ ] **Step 1: Failing tests**: `test_app_imports_without_archive` (subprocess `python -c "import app.main"` with `archive/` absent from `sys.path`); `test_no_care_file_imports_screens`; `test_old_routes_are_gone` (`/morning/episodes/x/play` → 404; `/journey/episodes/x/play` → 404); `test_kept_screens_not_in_menu`.
- [ ] **Step 2–4:** FAIL → move, unmount, repoint → backend suite, frontend tests, `npm run build`, `make demo-check` all PASS with `archive/` excluded (A7).
- [ ] **Step 5: Commit** (when authorized).

### Task 17: The video script (before the freeze)

**Files:**
- Create: `docs/demo/dd-cg-flow-video-script.md`

- [ ] Write the script from spec §12: scene, time, on-screen action, narration, the beat id that proves it, and the labels "synthetic data" and "research demo". Narration passes the `ADVICE` regex used by `beats.test.mjs`. Done by the 3 Nov 12:00 checkpoint; commit (when authorized).

### Task 18: Whole-branch review

- [ ] **Step 1:** Run every suite in both apps, `npm run build`, `make demo-check`, and the A10 scan `count-guard/scripts/scan_limits.py` (new; fails on any tracked file over 500 lines in both apps, excluding pre-existing ones listed in it such as DD `frontend/app.js`, and on any value matching a key pattern); paste the summary lines.
- [ ] **Step 2:** Dispatch one fresh reviewer on the most capable model over the whole branch diff, including an **adversarial probe of the swab hard stop**: try to end surgery through every new route (intake, Sync, New patient, camera, advice ack, replay, correction, theatre proofs, a heard pack phrase, a voice drug phrase) without a person's reconciled closing.
- [ ] **Step 3:** Fix findings task by task; re-run Step 1.
- [ ] **Step 4:** List changed files for the user. Do not push. Then record the video from the finished code (spec §12).

## Appendix: spec §9 row → named test (A5)

| §9 row | Test (task) |
|---|---|
| `/rx/import` → intake | `test_admit_creates_patient_in_admitting_with_rx` (2) |
| `/strips`, brown-bag photo | `test_home_medicine_photo_lists_metoprolol` (10) |
| `/discharge-card` | `test_discharge_card_in_patient_view` (9) |
| `/handover` | `test_handover_from_nurse_chart` (12) |
| reminders, `.ics`, check-in, help | `test_reminders_ics_from_patient_view`, `test_checkin_and_help_from_patient_view` (12) |
| `/dose` | `test_dose_given_from_nurse_chart` (12) |
| `/audit` | `test_audit_in_history`, `test_audit_rows_on_ai_page` (12) |
| journey and morning play | `test_old_routes_are_gone` (16) |
| `/brownbag/text` | `test_typed_home_medicines_grounded` (15) |
| drug log, "hear" | `test_drug_phrase_becomes_grounded_row`, `test_spoken_pack_phrase_is_heard` (7) |
| simulated vitals | `test_vitals_drop_raises_card_with_three_sources` (7) |
| `/card`, `/tier` | `test_card_404_when_tier_off` (7) |
| `/count/frame`, `/count/manual` | `test_missing_swab_frame_is_returned`, `test_manual_count_route_in_care` (8) |
| `/count/from-case` | `test_camera_case_created_and_linked` (8) |
| `/count/replay` | `test_replay_is_labelled_prepared` (13) |
| bucket dwell | `test_bucket_dwell_counts_returned` (13) |
| correction | `test_correct_supersedes` (14) |
| SSE stream | `test_stream_emits_new_event_within_1s` (14) |
| discharge PDF, `.ics` | `test_pdf_contains_drug_and_count`, `test_ics_has_follow_up_date` (9) |
| R1–R6 | `test_rules_produce_advice_rows` (8) |
| SAM pipeline, live socket | `test_camera_live_socket_streams_detections` (8) |
| manual resolve | `test_resolve_needs_reason` (13) |
| close, explanation, count sheet | `test_close_writes_count_sheet_pdf` (13) |
| frame, track, event viewer | `test_evidence_lists_case_frames_and_tracks` (15) |
| `/guide` | `help.test.js` (15) |

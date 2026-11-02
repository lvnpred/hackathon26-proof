# Code map: Count Guard (for the 2026-11-02 DD → CG flow plan)

Paths relative to `count-guard/`. Checked 2026-11-02; re-check line numbers before editing.
Near the 500-line limit: `journey/states.py` 462, `journey/api.py` 412, `engine.py` 399, `journey/ai_moments.py` 356,
`core/rules.py` 338, `journey/dictation.py` 336, `morning/api.py` 326, `store.py` 319, `journey/live.py` 314;
tests `test_flow_states.py` 438, `test_journey.py` 382. **Add new modules; do not grow these.**

## Store — `backend/app/morning/store.py` (134)
- `app.state.morning = MorningStore(data_dir/"morning.db")` (`main.py:39`). `SCHEMA` :12-28, `executescript` :38, `self._lock` :35.
- `create_episode(label)` :55, `get_episode` :65, `list_episodes` :48, `append(eid, event_type, payload, *, ts_ms, tier="documentation", supersedes_id=None)` :70, `events(eid, after_id=None)` :109, `get_event` :127.
- No lock spans several writes. `app/store.py`: `now_iso` :88, `new_id` :92 (camera-case `Store` is `app.state.store`).

## Journey API
- `journey/api.py`: `router` prefix `/journey/episodes/{episode_id}` :31; `demo_router` `/journey/demo` :32; `_store` :127, `_require` :131, `_at` :138-142 (no clamp), `settle(request, eid, ts)` :153-161, `view` :169, `_act` :208. Routes: `/rx/import` :224, `/rx/demo` :241, `/strips` :258, `/reminders(.ics)` :270/282, `/dose` :293, `/tick` :317, `/handover` :337/363, `/discharge-card` :373, `/help` :384, `/checkin` :389, `/audit` :395, `/play` :401 (import :17), `seed` :409.
- `journey/seed.py`: `DOCTOR/NURSE/NURSE_THEATRE/PATIENTS` :17-27, `card_payload` :30, `seed_ward` :45 (no `patient.registered` yet).
- `journey/flow_api.py` (202): `StateIn` :21 `{to, by, reason, procedure, checklist}`; `/state` :41-58 (`MoveRefused`→409); `/surgery` :61-77, count-gate 409 :72-76; `/orders/sign` :148, `/orders/{id}/ack` :158, `/tasks/{id}/begin|done` :163/168, `/discharge/sign` :181; `_write` :136.
- `journey/states.py`: `PROCEDURES` :20, `ADMISSION_CHECKS` :22, `DISCHARGE_CHECKS` :23, `MOVES` :26, `count_gate` :95-110, `_missing` :126, `check_move` :130, `MoveRefused` :155, `move_payload(events, to, body) -> dict` :159. Checklist ticks travel inside the move body (`checklist: {key: True}`), stored in the `patient.state` payload.
- `main.py:50-67` mounts: `api.routes`, `api.ws`, morning, morning_extra, site, journey, count, demo, flow, media, ask, staff, video, evidence, ai, models, ops, ops_site. CORS uses `CG_WEB_PORT` :41.

## Photos, tasks, live seam
- `journey/media_api.py` (293): `/dictate/orders` :93, `/dictate/discharge` :113, `/dictate/task` :132, `_check_photo` :169, `write_photo` :203, `POST /photos` :213 (writes `photo.added`, `proof.checked`), `/strips/photo` :266.
- `journey/proof.py`: `check_strip`, `check_monitor`, `photos_view`; D9 "flag, never block".
- `journey/tasks.py` (299): `task_list` :54, `sign_order` :142, `acknowledge_order` :163, `begin_task` :204, `_proof_match` :222, `complete_task(store, eid, task_id, by, ts, *, via, note, values, transcript, proof_id, heard_by, calls)` :262.
- `journey/live.py`: `prepared(filename)` :93-101; `transcribe` :120 (falls back by filename :132); `spark_text` :147; `read_photo(...)` :187 (falls back by filename :209); `segment_clip` :260; `segment_photos` :292.
- Switches: `journey/video_api.py:21-23` `SETUP_LIVE/TRAY_LIVE/SWABS_LIVE`; `journey/ask_api.py:32` `MEDICINES_LIVE`. `config.py:89` key; `:103-105` `dd_base`. No `VOICE_LIVE/PROOF_LIVE/SPARK_LIVE` yet.
- Adapters: `SparkAdapter` (`second_look` :55, `read_strips` :58, `read_monitor` :62, `write` :66, `watch` :70); `SamAdapter` (`segment_video` :125, `segment_images` :138); `VoiceAdapter.transcribe(path, offset_ms, content_type)` :46.

## Morning and camera counter (to move)
- `morning/api.py`: tier :73/78, SSE stream :107-146, play :148, druglog :180/193, card :257, discharge :272, discharge.pdf :292, follow-up.ics :302.
- `morning/routes_extra.py`: hear :89, count/replay :103, count/from-case :118, count/manual :150, count/frame :163, correct :182, vitals/sim :208, brownbag/text :227, brownbag/photo :239.
- Helpers: `pdf.write_discharge(path, *, label, sheet)`, `ics.follow_up_ics(label, start=None)`, `druglog.parse_drug_phrase(text)`, `vitals.demo_readings/evaluate/template_card/choose_wording`, `sim.apply(...)`, `count_rules.fresh_state/observe/demo_frames/replay`. Camera and replay closings carry no `by` → `count_gate` "none".
- `api/routes.py`: resolve :152, close :160, report.pdf :209, frames :220, tracks :228, events :247. `core/rules.py:73 closing_gate`; `report/count_sheet.py:25 write_count_sheet`; `agent/reconciler.py:26 explain_case`; `media_pipeline.py:37 run_recorded_video`.
- **20 test files POST `/morning/episodes`; 53 use `/morning/` routes.** Archiving `morning/api.py` needs a journey episode-create route and those tests moved first.

## Frontend
- Client `src/journey.js`: `call` :6, `getJourney` :25, `postJourney(id, path, body)` :29, `uploadJourney(id, path, file, fields)` :38.
- `care/ward.js` (228): sessionStorage keys :8-11, `savedRoster` :30, `seed()` :49, `loadWard` :59, `fetchWard` :65, `useWard()` :78 (used by `care/CareShell.jsx`); returns `{patients, board, nowMs, act, upload, ask, jump, reset, …}`. `care/clock.js`: `afterRun`, `STEP_MS`, `label`, `skipTargets`.
- `App.jsx:170-194` care routes `/ /queue /patients /chart/:episodeId /today /my-care /ask /ai`; old `/steps /older /guide /count /morning /opd /ot /ward /case/:caseId(/close) /journey /doctor /nurse /patient /audit`.
- Care imports from screens: `History.jsx:3` AuditTable; `Today.jsx:10-11` CheckIn, MyCard, NeedHelp, Nudges, Reminders, Strips; `DoctorActions.jsx:2` RxImport, RxTable.
- Components: `PhotoInput` (21), `TaskProof` (73), `StripPhoto` (34), `MedicinesFromHome` (51), `NurseActions` (64, `move(to, checklist)`), `Checklist` (28), `NurseTasks` (123), `CountPanel` (138), `TheatreChecklist` (105), `VideoCheck` (83), `DemoDock` (91), `DoctorActions` (222).

## Demo harness and tests
- `Makefile:40-48` demo-check. `frontend/scripts/demo/server.mjs` (126): ports 8200/5273, `startServers` :88 asserts `live === false`; no DD yet. `run.mjs` (114), `steps.mjs` (220), `beats.mjs` (299; `BEATS` :34), `beats.test.mjs` (100: 32 beats, role 54–62 s, film ≤ 200 s, pinned strings :67-99).
- Backend: `.venv/bin/pytest -q` (pytest.ini `pythonpath=backend`). Frontend: `cd frontend && node --test $(find src -name "*.test.js")` and `node --test $(find scripts -name "*.test.mjs")`.
- Helpers: `tests/test_care_demo.py:19 _client(tmp_path, *, dd_base=...)`; `test_flow_states.py` `_new` :14, `_move` :20, `_to_ward` :29, `_to_theatre` :34, `_surgery` :39, `_count` :43, `_saved_count` :48; `test_count_gate.py` :14-104.
- `rx.py`: `from_document(document, *, source)` :82 (no ageSex/opNo), `fetch_document` :105. `handover.draft(...)` :122.

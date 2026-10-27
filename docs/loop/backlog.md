# Backlog — reviewed 2026-10-27
Sources: the 27 Oct Count Guard build spec (Grok chat, hackathon26 session), `hackathon26/docs/hackathon/03-hackathon-spec.md` §3/§5/§8 (adapted to this standalone repo), and README/docs claims checked against code and a running TestClient/uvicorn.
Baseline: `PYTHONPATH=backend .venv/bin/pytest -q` → 41 passed; `eval/run_eval.py` exit 0; `npm run build` ok.

Rules for the fixer: one item per sitting; do not edit `backend/app/core/rules.py` thresholds; keep every file under 500 lines; run the full suite and `eval/run_eval.py` after each item; do not commit. Skip any item with `Needs human: yes`.

### B1 — PDF text checks are vacuous: fpdf2 compresses the page streams
- Status: done — 43 passed; `pdf_text` in conftest inflates streams; tier 0 and 1 PDFs list metoprolol, lignocaine, closing count, no card or advice text; grep -rn finds nothing
- Priority: P1
- Needs human: no
- Gap: UC1 and UC4 search the raw PDF bytes for advice words (`backend/tests/test_e2e_uc1.py:104-106`, `backend/tests/test_e2e_uc4.py:88-89`), but the content streams are FlateDecode, so `b"metoprolol" in pdf.content` is False even though the sheet lists it. Spec 03 §5.5 ("PDF lists OPD medicines, every confirmed druglog.given, closing count; no decision-tier event in either tier mode") is therefore not verified at all.
- Done when: a `pdf_text(raw: bytes) -> str` helper in `backend/tests/conftest.py` inflates every `stream…endstream` block with `zlib`; UC1/UC4 use it; new test `backend/tests/test_e2e_uc4.py::test_discharge_pdf_text_lists_facts_and_drops_card_in_both_tiers` asserts, for tier 0 and tier 1 after `/play`, that the text contains `metoprolol`, `lignocaine`, and the closing count (opened 20, unaccounted 1), and contains neither the `vitals.card` text (`BP 86/50, down`) nor any advice word. `grep -rn "in pdf.content" backend/tests` returns nothing.
- Files: `backend/tests/conftest.py` (new), `backend/tests/test_e2e_uc1.py`, `backend/tests/test_e2e_uc4.py`.

### B2 — The camera demo has no unannounced gauze add (spec demo 0:35–1:30, R4)
- Status: done — demo adds five unannounced gauze at 25 s (R4 fires); filing sums only opened rows, so the sheet stays opened 10 / returned 9 / unaccounted 1 with gauze kept in detail; UC3 unchanged and passing
- Priority: P1
- Needs human: no
- Gap: The spec's live scene says "An unannounced add of gauze is caught (R4)". The `demo` scenario is clip 2 with a changed closing line (`backend/app/scenarios.py:201-215`) and raises only R1, R2, R3, so the "Play the closing-count demo" button (`frontend/src/screens/Setup.jsx:22-34`) cannot show R4.
- Done when: `demo` adds five `gauze swab` detections on the tray at about 25 s with no spoken add, and its `expect.rules` includes `("R4", "gauze swab")`; new test `backend/tests/test_api.py::test_demo_shows_unannounced_gauze` posts `/cases/{id}/upload?scenario=demo` and finds an open R4 row for `gauze swab`, while the lap-sponge ledger row stays opened 10 / bucket 9 / unaccounted 1. `backend/tests/test_e2e_uc3.py` and `eval/run_eval.py` still pass (the eval clips are unchanged). If UC3 fails because the filed count now carries gauze, stop and record it in `docs/loop/questions.md` instead of changing UC3's assertions.
- Files: `backend/app/scenarios.py`, `backend/tests/test_api.py`, `backend/app/morning/camera_file.py` (Q2 a: file the counted type only).

### B3 — "Draw zones, then go live" is a dead end in the UI
- Status: done — Live empty state runs the scripted demo or uploads a file; curl on a temp backend: demo 200, .json 200, .mp4 400 with the SAM key message; build ok; not clicked in a browser
- Priority: P1
- Needs human: no
- Gap: After a blank session's zones are saved, Setup navigates to `/case/{id}` (`frontend/src/screens/Setup.jsx:70-71`). Live only plays a snapshot cached in sessionStorage (`frontend/src/screens/Live.jsx:13`), so it shows "This session has no playback yet" (`Live.jsx:63`). No screen offers the spec's "upload mode is the safety net", although `POST /cases/{id}/upload` accepts a file or `?scenario=` (`backend/app/api/routes.py:84-118`). The demo's "zones drawn" scene (spec 0:15–0:35) cannot lead into the live scene.
- Done when: the Live empty state offers (a) "Run the scripted demo on this case" (calls `uploadScenario(caseId, "demo")`, stores the snapshot under `cg:${caseId}`, and re-renders) and (b) a file input for `.mp4`/`.json` that posts multipart to `/cases/{id}/upload` and shows the 400 message, for example "SAM 3.1 needs MODEL_API_KEY…", in `.error`. The screen states that the scripted run replaces the drawn zones with the scenario's zones. `cd frontend && npm run build` succeeds. `grep -n "uploadFile" frontend/src/api.js` finds the new helper.
- Files: `frontend/src/screens/Live.jsx`, `frontend/src/api.js`.

### B4 — Real model runs: SAM 3.1 clip, Voice, Spark 1.3 strip photo (UC6)
- Status: open
- Priority: P1
- Needs human: yes (a `MODEL_API_KEY`, a spend limit set on the Meta billing page, and the five prop-tray clips plus the 10-swab live test shot by you)
- Gap: Every count shown so far is scripted (`eval/run_eval.py` prints "SAM 3.1 was not called"). The spec's eval table and the 03 §5.2 live check (10 swabs within ±1) need real footage. The OPD "photo → list" scene needs Spark (`backend/app/morning/routes_extra.py:242-247` returns `no_model`).
- Done when: README eval table is replaced by measured rows including misses, and `GET /health` shows `configured: true` for SAM and Voice.
- Files: `README.md`, `eval/`, `backend/app/scenarios.py` (only to add recorded clips).

### B5 — Upload routes: path traversal, write-before-check, and 500 on wrong-shape JSON
- Status: done — 47 passed; traversal reproduced then fixed (Path.name, ".." falls back); refused clip deleted before the 400; wrong-shape JSON is 400
- Priority: P2
- Needs human: no
- Gap: (1) `dest = … / (file.filename or "clip.mp4")` (`backend/app/api/routes.py:112`) is used as given. A filename of `../../evil.mp4` was written to `data/evil.mp4` during review, and it is written before the missing-key check (`routes.py:114` runs before the check in `media_pipeline.py:17`). The brown-bag photo has the same pattern (`backend/app/morning/routes_extra.py:239-240`). (2) Uploading `{"a":1}` or `[1,2]` as JSON returns 500 with `KeyError 'zones'` (`backend/app/engine.py:32`, reached from `routes.py:110`).
- Done when: new tests in `backend/tests/test_api.py`: `test_upload_filename_cannot_escape_the_case_folder` (filename `../../evil.mp4` → 400 with no key, and no file exists outside `data/uploads/<case_id>/`), `test_video_is_not_stored_without_a_key` (nothing under `uploads/` after a 400), `test_wrong_shape_scenario_json_is_400` (`{"a":1}` and `[1,2]` → 400 with a message naming `zones`/`steps`), and `test_strip_photo_filename_is_sanitised` in `backend/tests/test_rest.py`. Use `Path(name).name` or a fixed name, and check `zones`/`steps` before replay.
- Files: `backend/app/api/routes.py`, `backend/app/morning/routes_extra.py`, `backend/app/engine.py` (shape check only), `backend/tests/test_api.py`, `backend/tests/test_rest.py`.

### B6 — Video pipeline failures become 500s
- Status: done — 49 passed; missing ffmpeg/bad clip 400, SAM failure 502, one-line messages; key and zones checked before the clip is written
- Priority: P2
- Needs human: no
- Gap: `_ffmpeg` raises `FileNotFoundError` when ffmpeg is absent, `_video_size` uses `check=True` and raises `CalledProcessError` (`backend/app/media_pipeline.py:103-124`), and SAM HTTP errors propagate. The route only maps `RuntimeError` to 400 (`backend/app/api/routes.py:115-118`), so a bad clip or a missing binary returns a bare 500.
- Done when: new test `backend/tests/test_api.py::test_video_errors_are_clear_not_500` builds Settings with a fake `meta_api_key`, saves zones, and monkeypatches `subprocess.run` to raise `FileNotFoundError`, then `CalledProcessError`. It also monkeypatches `SamAdapter.segment_video` to raise. Each case returns 4xx/502 with a one-line message naming ffmpeg or SAM 3.1. No network call is made.
- Files: `backend/app/media_pipeline.py`, `backend/app/api/routes.py`, `backend/tests/test_api.py`.

### B7 — Close screen swallows a failed resolution
- Status: done — resolve() shows errors; 422 body formats to "reason: String should have at least 3 characters" (checked on a live temp backend); build ok
- Priority: P2
- Needs human: no
- Gap: `resolve()` awaits `resolveDiscrepancy` without try/catch (`frontend/src/screens/Close.jsx:29-34`). A reason under 3 characters (422 from `ResolveIn`, `backend/app/models.py:27-29`) makes "Record resolution" do nothing visible on camera. `api.js` builds the message from `detail.message || detail`, which for a 422 is an array and prints as `[object Object]` (`frontend/src/api.js:6`).
- Done when: `resolve()` catches and shows the error in `.error`; `send()` in `api.js` turns a 422 `detail` array into "reason: String should have at least 3 characters"; `npm run build` succeeds; `grep -n "catch" frontend/src/screens/Close.jsx` shows a catch inside `resolve`.
- Files: `frontend/src/screens/Close.jsx`, `frontend/src/api.js`.

### B8 — Human resolutions are not shown on the Close screen or the count sheet
- Status: done — 50 passed; rows carry resolution {reason, by, wall_clock}; PDF and Close print "Resolved by X: reason"
- Priority: P2
- Needs human: no
- Gap: The spec's Close screen and PDF show "human resolutions" ("Found under drape, placed in bucket"). `open_discrepancies` keeps only the status, not the reason, by, or time (`backend/app/core/ledger.py:214-237`). The PDF prints only status and detail (`backend/app/report/count_sheet.py:49-55`), and Close prints only status (`frontend/src/screens/Close.jsx:69-77`).
- Done when: rows carry `resolution: {reason, by, wall_clock}` when resolved; new test `backend/tests/test_api.py::test_resolution_reason_is_on_rows_and_sheet` resolves the demo, checks the row's `resolution.reason`, and finds the reason in the count-sheet text (use B1's `pdf_text` helper if it exists, otherwise inflate inline). The Close screen renders "Resolved by X: reason". Existing tests pass.
- Files: `backend/app/core/ledger.py` (the `open_discrepancies` function only), `backend/app/report/count_sheet.py`, `frontend/src/screens/Close.jsx`, `backend/tests/test_api.py`.

### B9 — Evidence drawer lacks "the transcript line around it"
- Status: done — drawer shows spoken lines within ±10 s or by transcript evidence id; all 3 demo alerts show a line; build ok; not clicked in a browser
- Priority: P2
- Needs human: no
- Gap: The spec's evidence drawer shows the last-seen frame, the path, and the transcript line around it. Live shows the frame, the path, and raw evidence ids only (`frontend/src/screens/Live.jsx:128-143`). R1 and R2 rows have no `last_media_ts_ms`, so they show nothing of the transcript.
- Done when: the drawer lists the snapshot transcript lines within ±10 s of `selected.last_media_ts_ms`, or the transcript ids named in `selected.evidence` when no time exists, each with its clock. `npm run build` succeeds. `grep -n "transcript" frontend/src/screens/Live.jsx` shows use inside the evidence section.
- Files: `frontend/src/screens/Live.jsx`.

### B10 — Muse Spark 1.3 "second look" is never called
- Status: done — R5 with a key calls SparkAdapter.second_look once per row (cropped PNG), appends second_look event, logs the call; no key calls nothing; eval unchanged; live call unverified (B4)
- Priority: P2
- Needs human: no (the live call itself needs a key, see B4)
- Gap: README, architecture, and `/health` say Spark 1.3 names a crop when R5 fires (`README.md` Models table, `docs/architecture.md:51`, `backend/app/api/routes.py:59-64`). `SparkAdapter.second_look` (`backend/app/adapters/spark.py:42`) has no caller: `grep -rn "SparkAdapter" backend/app` matches only its definition.
- Done when: after rules run in `Engine.apply_rules` (`backend/app/engine.py:124`), each new R5 row is handled when `settings.spark_configured` is true. The engine crops the row's last frame, calls `second_look`, appends a `second_look` event (label only, count unchanged), and logs the model call. Without a key, nothing is called. New test `backend/tests/test_models.py::test_r5_triggers_one_second_look_with_a_fake_adapter` monkeypatches `SparkAdapter.second_look` with a fake key. It asserts one call per R5 row and no change to the ledger, and asserts zero calls with no key. `rules.py` is untouched.
- Files: `backend/app/engine.py`, `backend/tests/test_models.py`.

### B11 — OT screen cannot show the fact card (spec 03 demo 1:40–2:10)
- Status: done — OT shows tier toggle and a Fact card panel with the banner, hidden while the tier is off; card written at the drop reading in < 500 ms (test); curl tier off 404, on 200
- Priority: P2
- Needs human: no
- Gap: The decision tier is off unless `DECISION_TIER=1` (`backend/app/main.py:33`). The only toggle is on `/morning` (`frontend/src/screens/Morning.jsx:50-57`), which no nav or guide link reaches (`frontend/src/App.jsx:66-70`; `backend/app/site.py` has no `/morning` href). The OT screen draws the BP sparkline but has no card panel (`frontend/src/screens/Ot.jsx`). There is also no test for spec 03 §5.4 "card visible < 500 ms after the reading".
- Done when: Ot shows the tier state with the same toggle and a "Fact card" panel with the banner when a `vitals.card` event exists. New test `backend/tests/test_morning.py::test_card_is_written_within_500ms_of_the_drop_reading` turns the tier on, seeks the sim past the drop, asserts the response contains a `vitals.card` event, and asserts the call took < 500 ms. `npm run build` succeeds.
- Files: `frontend/src/screens/Ot.jsx`, `backend/tests/test_morning.py`.

### B12 — Morning event stream does not follow new events (spec 03 §5.1)
- Status: done — ?follow=1&timeout_s=N polls every 250 ms, stops on timeout (cap 30) or disconnect; new event arrives < 1 s; plain stream unchanged
- Priority: P2
- Needs human: no
- Gap: `GET /morning/episodes/{id}/stream` sends the rows that exist and closes (`backend/app/morning/api.py:102-114`); measured 1 ms and closed. The spec wants each new event emitted within 1 s of the write. Resume-after-id is covered (`backend/tests/test_morning.py:147`); following is not.
- Done when: `?follow=1&timeout_s=N` (N capped at 30) polls the store every ≤ 250 ms and emits new rows in id order until timeout or disconnect. Without `follow`, the behaviour stays the same, so the existing test still passes. New test `test_stream_follows_a_new_event_within_one_second` starts the stream with `timeout_s=2` and appends an event from a thread after 200 ms. It asserts the event's id appears and the elapsed time from write to receipt is < 1 s.
- Files: `backend/app/morning/api.py`, `backend/tests/test_morning.py`.

### B13 — The camera WebSocket has no test
- Status: done — test_ws.py: ready+state ledger row, 4404 on unknown case, bad JSON gives error then 1011; mutation-checked; ws.py unchanged
- Priority: P2
- Needs human: no
- Gap: `WS /cases/{id}/stream` is one of the spec's endpoints (`backend/app/api/ws.py:20-91`), but `grep -rn websocket backend/tests` finds nothing. Unknown case closes with 4404; malformed JSON goes to the generic `except` (`ws.py:89-91`).
- Done when: new `backend/tests/test_ws.py` has three tests. `test_ws_ready_then_state` sends a ready message, saves zones, sends a `detections` message and an `utterance` "Adding 2 lap sponges", and gets a `state` message with a ledger row. `test_ws_unknown_case_is_refused` expects close code 4404. `test_ws_bad_json_sends_error` expects an `error` message and no server crash.
- Files: `backend/tests/test_ws.py` (new), `backend/app/api/ws.py` (only if a test exposes a bug).

### B14 — Muse Spark Open live run: tool calls and the "Running on Muse Spark Open" badge
- Status: open
- Priority: P2
- Needs human: yes (a `BASETEN_API_KEY` with credits, and a decision on `SPARK_OPEN_MODEL`: `meta-models/muse-spark-open-1026` vs Baseten's public `meta-models/muse-spark-open`, see `docs/architecture.md:32`)
- Gap: Without the key the reconciler returns `model: "template"` and an empty trace (`backend/app/agent/reconciler.py:39-40`), so the spec demo 2:15–2:40 ("agent's tool calls shown", open-weights bonus) cannot be filmed.
- Done when: with the key set, `POST /cases/{id}/close` on the resolved demo returns `model` starting with `meta-models/muse-spark-open` and a non-empty `trace`, and the Close screen shows the tool list.
- Files: `.env` (local only, never committed).

### B15 — Submission artefacts outside the code
- Status: open
- Priority: P2
- Needs human: yes (record the 3-minute video and the 30-second X clip, make the X post, claim Meta API credits before 4 Nov 9 PM ET, make the repo public, answer Q1 in `docs/loop/questions.md`)
- Gap: Spec "Before you submit" items and `README.md` "Before this is public" list are not code work.
- Done when: the README links the public video and X post.
- Files: `README.md`.
### B16 — Case and zone input accepts nonsense
- Status: done — item types from SAM_CONCEPTS, [x, y] points in 0–1, no repeated zone names (422); test_ws.py rescaled to the 0–1 contract
- Priority: P3
- Needs human: no
- Gap: `CaseIn.item_types` accepts any string; `{"item_types":["banana"]}` returned 200 (`backend/app/models.py:14-16`). `ZoneIn.polygon` accepts points outside 0–1 and points of any length. `ZonesIn` accepts three `tray` zones (`models.py:19-24`), although zones are normalised 0–1 (`docs/architecture.md:41`).
- Done when: new test `backend/tests/test_api.py::test_case_and_zone_input_is_validated` expects 422 for an unknown item type, a point `[5, 0]`, a 3-number point, and duplicate zone names. `[0.02, 0.05]` style points and all five `SAM_CONCEPTS` still pass. The full suite passes.
- Files: `backend/app/models.py`, `backend/tests/test_api.py`, `backend/tests/test_ws.py` (rescale to 0–1, added by the loop).

### B17 — README run section, broken curl, and missing submission notes
- Status: done — README run/curl/eval/submission notes updated; every command run in zsh on a temp backend
- Priority: P3
- Needs human: no
- Gap: (1) The README demo command `curl -s -X POST localhost:8000/cases/CASE_ID/upload?scenario=demo` (`README.md:104`) fails in zsh with "no matches found" because the URL is unquoted. This was checked against uvicorn on port 8799. (2) The Run section (`README.md:23-37`) never says `DECISION_TIER=1` is needed for the fact-card scene. (3) Spec 03 §8 asks for notes on what was live vs replayed, measured accuracy, and which LLM worded the card. No such section exists.
- Done when: the curl URLs are quoted; Run shows `DECISION_TIER=1 make dev` for the card scene; a "Submission notes" section says plainly that SAM 3.1, Voice, and both Spark models were not called, that every count shown is scripted replay (`make eval`, 3 of 3), and that the card wording is the template. `grep -n "upload?scenario=demo'" README.md` and `grep -n "Submission notes" README.md` both match. Copy-pasting the README curl lines in zsh against `make backend` returns 200.
- Files: `README.md`.

### B18 — "Built during the hackathon" list misses the morning modules
- Status: done — new-work.md lists every 27 Oct module (one commit, eb76d59) and the uncommitted overnight work by backlog id
- Priority: P3
- Needs human: no
- Gap: The spec wants the README to list every feature with its build date. `docs/new-work.md:5-17` lists only the camera-count pieces. It omits `backend/app/morning/*` (strips, drug log, vitals sim and card, discharge PDF/ICS, guide), `backend/app/site.py`, and the screens Home/Opd/Ot/Ward/Guide/Morning. The README feature table (`README.md:9-16`) has no date column.
- Done when: `docs/new-work.md` has one row per module above, with dates taken from `git log --format=%ad --date=short -- <path>`, and the README links to it from the feature table. `for f in backend/app/morning backend/app/site.py frontend/src/screens/Ot.jsx; do grep -q "$f" docs/new-work.md || echo MISSING $f; done` prints nothing.
- Files: `docs/new-work.md`, `README.md`.

### B19 — `make eval` bypasses the upload path and has no ground-truth files
- Status: done — eval posts each clip through /cases/{id}/upload, reads eval/ground_truth/clip1-5.json, adds ID switches/min; still 3 of 3, exit 0; writes only under data/eval/
- Priority: P3
- Needs human: no
- Gap: The spec says "make eval replays all five clips through the upload path", with `eval/clips.yaml` and `eval/ground_truth/`. `eval/run_eval.py:47-55` calls `Engine.replay` directly, and the expectations live inside `backend/app/scenarios.py`. The metric is ID switches, not ID switches per minute as the spec names it.
- Done when: `run_eval.py` drives each clip through `TestClient(create_app(settings)).post("/cases/{id}/upload?scenario=clipN")`; ground truth is read from `eval/ground_truth/clipN.json` (written from the current `expect` blocks); the table adds an "ID switches/min" column; `PYTHONPATH=backend .venv/bin/python eval/run_eval.py` exits 0 and still prints "3 of 3". Do not add a YAML dependency; JSON is fine.
- Files: `eval/run_eval.py`, `eval/ground_truth/*.json` (new).

### B20 — No guard that secrets or real media stay out of git
- Status: done — test_repo_hygiene.py flags tracked .env, media/db/pdf and key values via git ls-files; proven to fail on a throwaway repo; skips outside git
- Priority: P3
- Needs human: no
- Gap: The submission checklist says no `.env`, no keys, and no real images. This holds today: `git ls-files` has 0 media/db files, and `.env` is ignored (`.gitignore:1`). Nothing keeps it true.
- Done when: new test `backend/tests/test_repo_hygiene.py::test_no_env_keys_or_media_are_tracked` runs `git ls-files` (skips if git is absent). It asserts no `.env`, no `*.png|jpg|jpeg|mp4|mov|wav|db|pdf`, and no line matching `(MODEL_API_KEY|BASETEN_API_KEY)=\S` in tracked files other than `.env.example` with empty values.
- Files: `backend/tests/test_repo_hygiene.py` (new).


### B21 — A reason with an em dash or smart quote crashes the PDF
- Status: done — 52 passed; latin1() helper in count_sheet.py used by both PDF writers; em dash, smart quotes and emoji no longer crash
- Priority: P2
- Needs human: no
- Gap: Found by B8. fpdf2's built-in Helvetica only draws Latin-1. "Found under drape — bucket" raises `FPDFUnicodeEncodingException`, so a typed resolution reason, a strip name or a model sentence with an em dash, smart quotes or an emoji can turn closing or discharge into a 500 (`backend/app/report/count_sheet.py`, `backend/app/morning/pdf.py`).
- Done when: one small helper maps common characters to Latin-1 (em/en dash → "-", smart quotes → straight quotes, ellipsis → "...") and replaces anything else with "?"; both PDF writers pass every text through it. New test `backend/tests/test_api.py::test_count_sheet_survives_non_latin1_reason` resolves the demo with "Found under drape — “bucket” ✓" and gets 200 with `pdf_text` containing `Found under drape - "bucket"`. A similar test in `backend/tests/test_morning.py` covers the discharge PDF.
- Files: `backend/app/report/count_sheet.py`, `backend/app/morning/pdf.py`, `backend/tests/test_api.py`, `backend/tests/test_morning.py`.

### B22 — R1 and R2 alerts read "Last seen 0 min 0 sec"
- Status: done — clock() shows "No camera time (spoken count)" for null; evidence line reads "Rule R1. No camera time (spoken count)."; build ok
- Priority: P3
- Needs human: no
- Gap: Found by B9. R1 and R2 rows have `last_media_ts_ms: null`, and Live formats null as 0, so the drawer claims the item was last seen at the start of the clip (`frontend/src/screens/Live.jsx`).
- Done when: a null time shows "No camera time (spoken count)" instead of a clock; `npm run build` succeeds; `grep -n "No camera time" frontend/src/screens/Live.jsx` finds it.
- Files: `frontend/src/screens/Live.jsx`.

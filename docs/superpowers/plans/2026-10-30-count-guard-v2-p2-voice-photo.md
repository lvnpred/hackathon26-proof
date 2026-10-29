# Count Guard v2 · P2 Voice and Photo Proof Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The doctor dictates orders and the discharge, the nurse completes tasks by voice, and photos
are checked against tasks. Every model-made result is shown for one-tap confirm before it is saved, and
the whole path runs offline without a key.

**Architecture:** Every P2 model call goes through one seam, `journey/live.py`. With a key it calls Muse
Voice Transcribe or Muse Spark 1.3. Without a key it uses a prepared result, keyed by the uploaded file's
name, or the deterministic rules. New pure modules turn a transcript into order items or discharge
sections (`dictation.py`) or into a task match with values (`spoken.py`), and check a photo against its
task (`proof.py`). They are served by a new router, `journey/media_api.py`. Drafts (`order.drafted`,
`discharge.drafted`) and photos (`photo.added`, `proof.checked`) are ledger events. Signing an order,
signing a discharge and completing a task (P1 routes in `flow_api.py`) gain `draft_id`, `via: "voice"`,
`transcript` and `proof_id`. The frontend adds a `Dictate` control (MediaRecorder, an audio file, or
typed text), loads drafts into the order form and the discharge box, and adds a voice/photo completion
card for the nurse.

**Tech Stack:** FastAPI + pydantic v2 (multipart via python-multipart), SQLite ledger, pytest, ffmpeg (live
audio conversion only); React 18 + Vite, browser MediaRecorder, Node built-in test runner.

**Spec:** `docs/superpowers/specs/2026-10-29-count-guard-v2-patient-states-design.md` (P2 section, D9, D10,
D11, D13, Data table rows `order.drafted`, `task.done`, `photo.added`, `proof.checked`,
`discharge.drafted`, anti-goals, Constraints). P1 ledger rulings R1–R13:
`.superpowers/sdd/2026-10-29-count-guard-v2-p1-states/progress.md`. This plan closes R12.

## Global Constraints

- Branch `count-guard-v2` (P1 ends at 32c0b95). Commit after each task with
  `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Never push. No `Co-Authored-By` trailer.
- Keep every file under 500 lines. `journey/api.py` (466) gets no edits. `journey/flow_api.py` (164) gets
  only model-field and refactor edits. New routes go in `journey/media_api.py`.
- Validate input at system boundaries. JSON bodies use the `Strict` pydantic base with bounds. Multipart
  routes use `Form(...)`/`File(...)` parameters with bounds: text 1–2000, `by` 1–80, `at_ms` ≥ 0, audio
  ≤ 10 MB, photo ≤ 8 MB (`MAX_PHOTO_BYTES`).
- No advice wording in any new server or UI string, model prompt output shown to people, or
  `why`/refusal text: `\b(give|take|stop|increase|reduce|start|administer|consider)\b` (case-insensitive)
  must not match. Exemption: text the doctor or nurse said (transcripts, order item text). UI labels are
  "Record", "Finish recording", "Begin", "Mark done", "Confirm".
- Every model prompt contains the sentence `Do not give medical advice.`
- D10: nothing a model made becomes a record until a person taps Sign or Confirm. Drafts are stored as
  `*.drafted` events and are never read as orders, tasks or facts.
- D9: a photo that does not match is flagged (`match: "mismatch"`) and never blocks completion.
- D11: live calls only when `settings.spark_configured` / `voice_configured`. Each call has a prepared
  or rules fallback. **Tests never call a model.** Every new test file installs an autouse fixture that
  makes `httpx.Client.send` raise, and fakes adapters with `monkeypatch`.
- **Build agents never spend credits.** The workspace `.env` sets `META_API_KEY`. Any server a build agent
  starts runs as `MODEL_API_KEY= make backend` (an empty value wins over `.env`, `load_dotenv(override=False)`).
  Before using a running server, check `GET /journey/models` → `{"live": false}`; if `true`, stop it and
  restart it with the empty key.
- No dosing logic: a strip is matched to a dose task by medicine name only. The strength is shown, never compared.
- Synthetic data only. Names: `Dr. A. Rao (synthetic)`, `Nurse Meena (synthetic)`, `Nurse Asha (synthetic)`.
- One ward clock: every write is stamped with the client's `at_ms` (multipart sends it as a form field).
- Backend tests: `cd count-guard && make test`. Frontend: `cd count-guard/frontend && node --test 'src/care/*.test.js' && npm run build`.
- P1 tests (143 backend, 36 node) keep passing, or are updated in the task that changes the behaviour they pin.

## Out of scope (decided)

- A doctor "stop order" (R11 deferred). Duplicate obs tasks (Iyer's hourly and 15-minute ones) are
  handled by the nurse picking among candidates. Cost: one extra tap per Iyer reading after the saline order.
- Voice for Begin on the doctor side, healing/medicine photos (P4), video proof (P3), keeping raw audio.

## Review Focus

1. A file name that is not a safe stem (`../../etc/passwd.wav`, `Kumar Orders.WAV`, 200 characters)
   reaches the prepared lookup → no file outside `journey/prepared/` is read, and the name counts as "no
   prepared result". Test in Task 1.
2. A photo is uploaded for a `start_end` task that is running. The task stays `running`, because photo
   and proof events carry `task_id` but are not task progress (`task_list` today treats any event with
   `task_id` as progress). Test in Task 3.
3. The model's reply invents an item, a number or a medicine that the transcript does not contain, or is
   not JSON → the rules result is used and `source` says so. Nothing invented reaches the draft. Tests in Tasks 2 and 4.
4. A voice completion names a task that is closed or done, or a value that was not said → the task or
   value is dropped. Zero matches → the UI offers every open task. A `proof_id` from another episode → 404.
   A photo checked against another task → 409. Tests in Task 4.
5. The microphone is missing, permission is denied, or MediaRecorder is unsupported → the typed box and
   the audio-file input still work, and a plain message says so. Pure helper test in Task 5. Checked in Task 8.

---

### Task 1: Model seam, prepared results and demo media (backend)

**Files:**
- Create: `count-guard/backend/app/journey/live.py`
- Create: `count-guard/backend/app/journey/prepared/{kumar-orders,kumar-discharge,kumar-paracetamol,iyer-bp,iyer-saline,strip-paracetamol,monitor-88-54}.json`
- Create: `count-guard/eval/p2/make_media.py` and its output `count-guard/eval/p2/*.wav`, `*.png` (committed)
- Modify: `count-guard/backend/app/adapters/voice.py` (`transcribe(path, offset_ms=0, content_type="audio/wav")`), `count-guard/backend/app/adapters/spark.py` (`MONITOR_PROMPT`, `read_monitor`)
- Test: `count-guard/backend/tests/test_p2_live.py`

**Interfaces:**
- Produces (`spark.py`): `MONITOR_PROMPT` = `'Read the numbers on this blood pressure monitor screen. Reply with JSON only: {"sbp": 0, "dbp": 0, "hr": 0}. Use null for a number that cannot be read. Copy what is shown. Do not give medical advice.'`; `SparkAdapter.read_monitor(image_data_url) -> str` (raw text).
- Produces (`live.py`):
  - `class NotHeard(Exception)` with `.status` (409 or 502) and `.detail` (plain text).
  - `safe_stem(filename: str | None) -> str | None`: lowercased stem only if it matches `^[a-z0-9-]{1,60}$`, else `None`.
  - `prepared(filename) -> dict | None`: loads `prepared/<safe_stem>.json`, else `None`.
  - `transcribe(settings, raw: bytes, filename: str, content_type: str) -> dict` returns `{"text", "source"}`. With a voice key, `to_wav` then `VoiceAdapter.transcribe`, turns joined by spaces, `source "muse-voice-transcribe"`. An HTTP or ffmpeg error raises `NotHeard(502, "The transcriber did not answer. Type what was said in the box.")`. With no key: a prepared `transcript` gives `source "prepared"`. Otherwise it raises `NotHeard(409, "No model key, so recordings are not transcribed here. Type what was said in the box.")`.
  - `to_wav(raw, content_type) -> bytes`: passes `audio/wav` through; anything else goes through `ffmpeg -i pipe:0 -ac 1 -ar 16000 -f wav pipe:1`.
  - `spark_text(settings, prompt) -> str | None`: `None` with no key or on any adapter error.
  - `read_photo(settings, reader: Literal["strip","monitor"], raw, filename, content_type) -> dict` returns `{"text": str | None, "source"}`. With a key it uses the data URL and `read_strips`/`read_monitor` (`source "muse-spark-1.3"`). Otherwise it uses the prepared `text` (`source "prepared"`), else `{"text": None, "source": "none"}`. An adapter error gives `{"text": None, "source": "failed"}`.
- Prepared JSON (exact): audio files hold `{"transcript": ...}`:
  - `kumar-orders`: `"Admit for open hernia repair. Paracetamol 1 g every 6 hours, strip photo as proof. BP and pulse every 1 hour, lower systolic limit 90."`
  - `kumar-discharge`: `"Diagnosis: right inguinal hernia. Open mesh repair on day 0, swab count closed 20 of 20. Recovered well on the ward, wound clean and dry. Paracetamol 1 g every 6 hours for 3 days. Review in clinic on day 7."`
  - `kumar-paracetamol`: `"Paracetamol 1 g given to bed 4."`; `iyer-bp`: `"BP 82 over 54, pulse 112, bed 7."`; `iyer-saline`: `"Saline 1 litre over 2 hours. BP and pulse every 15 minutes."`
  - photos hold `{"text": ...}` in the model's reply format: `strip-paracetamol`: `{"strips": [{"name": "Paracetamol", "strength": "500 mg"}]}` (as a JSON string); `monitor-88-54`: `{"sbp": 88, "dbp": 54, "hr": 112}` (as a JSON string).
- `make_media.py` (run once by the implementer; it needs macOS `say`, ffmpeg and Pillow) writes `eval/p2/<stem>.wav` from each transcript (`say -o x.aiff`, then ffmpeg to 16 kHz mono WAV). It also draws `eval/p2/strip-paracetamol.png` (a strip-like box with "PARACETAMOL 500 mg") and `eval/p2/monitor-88-54.png` ("SYS 88 / DIA 54 / PUL 112").

- [ ] **Step 1: Write failing tests** (`test_p2_live.py`, settings built like `tests/test_care_demo.py::_client`, autouse `httpx.Client.send` guard):
  - `test_safe_stem_rejects_paths_and_odd_names`: `"../../etc/passwd.wav"`, `"Kumar Orders.WAV"`, `"a"*200 + ".wav"` → `None`; `"kumar-orders.wav"` → `"kumar-orders"`.
  - `test_no_key_uses_prepared_transcript`: `transcribe(no_key, b"x", "kumar-orders.wav", "audio/wav") == {"text": <kumar-orders transcript>, "source": "prepared"}`.
  - `test_no_key_unknown_audio_is_409_with_type_hint`: `"recording.webm"` raises `NotHeard`, `.status == 409`, and the detail contains `"Type what was said"`.
  - `test_key_calls_faked_voice_adapter`: key `"test-key"`, monkeypatch `live.to_wav` to identity and `VoiceAdapter.transcribe` to return two turns → text joined, `source "muse-voice-transcribe"`.
  - `test_read_photo_prepared_and_unknown`: no key, `strip-paracetamol.png` → prepared text; `IMG_0001.jpg` → `{"text": None, "source": "none"}`.
  - `test_prompts_forbid_advice`: `"Do not give medical advice."` is in `MONITOR_PROMPT` and `STRIP_PROMPT`.
  - `test_detail_strings_have_no_advice_words`: the two `NotHeard` details do not match the advice regex.
- [ ] **Step 2: Run** `cd count-guard && .venv/bin/pytest backend/tests/test_p2_live.py -q` → FAIL (import error).
- [ ] **Step 3: Implement** `live.py`, the adapter edits, the prepared JSON files, `make_media.py`. Run `make_media.py` once and commit its outputs.
- [ ] **Step 4: Run** the file → PASS; `make test` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2 P2: model seam with prepared fallbacks; demo audio and photos`.

---

### Task 2: Dictated orders and discharge become drafts (backend)

**Files:**
- Create: `count-guard/backend/app/journey/dictation.py`, `count-guard/backend/app/journey/media_api.py`
- Modify: `count-guard/backend/app/journey/flow_api.py` (`SignIn.draft_id`, `DischargeIn.draft_id`, `move()` and `sign_discharge` through `states.move_payload`), `count-guard/backend/app/journey/states.py` (`MoveRefused`, `move_payload`, `flow_view` adds `drafts`), `count-guard/backend/app/journey/tasks.py` (`sign_order(..., draft_id=None)`), `count-guard/backend/app/journey/stories.py` (`plain` lines), `count-guard/backend/app/main.py` (register routers)
- Test: `count-guard/backend/tests/test_p2_dictation.py`

**Interfaces:**
- Consumes: Task 1 `live.transcribe`, `live.spark_text`, `live.NotHeard`; P1 `OrderItem` (validate model items with `OrderItem.model_validate`), `tasks.ORDER_STATES`, `_store`, `_require`, `_at`, `view`, `raise_nudges`.
- Produces (`dictation.py`, pure):
  - `ORDER_PROMPT`, `DISCHARGE_PROMPT`: both end with `Do not give medical advice.` and ask for JSON only (`{"reason": "", "items": [...OrderItem fields]}` / `{"sections": [{"heading", "text"}]}`), with the transcript appended.
  - `digits(text) -> str`: turns number words into digits ("eighty two over fifty four" → "82 over 54", "one gram" → "1 gram"; units one–nineteen, tens twenty–ninety, tens followed by a unit are added).
  - `parse_order_text(text) -> {"reason": str, "items": list[dict]}` (rules). Split clauses on `[.;\n](?!\d)`. A clause matching `^admit(?:ted)?\s+(?:for\s+)?(.+)` sets `reason` (first letter capitalised). A clause naming a `lexicon.known_names()` drug becomes a dose: `name` = the generic, `amount` from `(\d+(?:\.\d+)?)\s*(mg|g|gram|grams|mcg|ml)` normalised to `"1 g"`. A clause with `bp|blood pressure|pulse|obs|observations` becomes obs: `limits.sbp_min` from `(?:lower|minimum|min|below|under)\D{0,25}(\d{2,3})` and `sbp_max` from `(?:upper|maximum|max|above)\D{0,25}(\d{2,3})`. A clause with `saline|drip|infusion` or `over \d+ (hours?|h)` becomes a procedure with `mode "start_end"`. Anything else is `other`. Every item: `text` = the clause as said, `every_h` from `every (\d+(?:\.\d+)?) (hours?|h|hrs?|minutes?|min)` or `every hour` (minutes ÷ 60; dropped unless 0 < x ≤ 72), `proof "photo"` when the clause says "photo", else `"none"`.
  - `HEADINGS = ("Diagnosis", "Procedure", "Course on the ward", "Medicines", "Follow-up")`.
  - `discharge_sections(text) -> list[{"heading","text"}]` (rules): each sentence goes to the first match in this order: Diagnosis (`diagnos`), Medicines (a known drug name or `\d+\s*(mg|g|ml)\b`), Follow-up (`review|follow|clinic|appointment|stitches`), Procedure (`repair|surgery|operation|procedure|count`), else Course on the ward. Sentences in one heading are joined. Headings keep `HEADINGS` order; an empty heading is left out.
  - `grounded(text, transcript) -> bool`: every number and every known drug name in `text` also appears in `digits(transcript)`, and no advice-regex word appears that the transcript lacks.
  - `items_from_reply(reply: str | None, transcript) -> dict | None` (import `OrderItem` inside the function: `flow_api` → `states` → `dictation` would cycle): a parsed `{"reason", "items"}` only if the JSON parses, there are 1–20 items, and each item passes `OrderItem` and `grounded`. Otherwise `None`.
  - `sections_from_reply(reply, transcript) -> list | None`: headings must be in `HEADINGS`, each text 1–600 characters and `grounded`. Otherwise `None`.
  - `open_drafts(events) -> {"order": dict | None, "discharge": dict | None}`: the latest `order.drafted` / `discharge.drafted` whose id no later `order.signed` / `discharge.signed` names as `draft_id`, as `{"id", "at_ms", **payload}`.
- Produces (`media_api.py`): `media_router = APIRouter(prefix="/journey/episodes/{episode_id}")` and `models_router` (`GET /journey/models` → `{"live": settings.spark_configured, "voice": settings.voice_configured}`). Shared helper `_heard(settings, file, text) -> dict` (`{"text","source"}`): exactly one of `file`/`text` (422 otherwise); audio ≤ 10 MB and `audio/*` or `video/webm` (400 otherwise); typed text gives `source "typed"`; `NotHeard` maps to its status.
  - `POST /dictate/orders` (multipart: `file?`, `text?`, `by`, `at_ms?`). Allowed only in `ORDER_STATES` (else 409). Model reply via `items_from_reply(spark_text(ORDER_PROMPT + digits(t)))`. If that is `None`, use `parse_order_text`; `source` is `"muse-spark-1.3"`, or `"rules"`, or `"rules (model reply not usable)"` when a key was set. Writes `order.drafted {transcript, heard_by: <transcript source>, reason, items, source, by}`. Returns `view()`. Zero items and no reason → 422 `"Nothing to draft was heard. Type the orders instead."`.
  - `POST /dictate/discharge`: same shape. Only in `ward`. Writes `discharge.drafted {transcript, heard_by, sections, source, by}`.
- Produces (`states.py`): `class MoveRefused(Exception)`; `move_payload(events, to, body) -> dict` runs `check_move` and raises `MoveRefused(reason)`, else returns the P1 payload (`from, to, by, reason` + `procedure`/`checklist` when given). `flow_view` adds `"drafts": open_drafts(events)`.
- Produces (`flow_api.py`): `SignIn.draft_id: str | None` (max 64). The id must be this episode's `order.drafted` (404 otherwise) and not already signed (409). It is stored in `order.signed`. `DischargeIn.draft_id` follows the same rule against `discharge.drafted`. `move()` and `sign_discharge` both build `patient.state` with `move_payload` (closes R12: no hand-built move). `sign_discharge` keeps its ward pre-check before it writes anything.
- `plain`: `order.drafted` → `"{by} dictated {n} orders (draft, not signed)."`; `discharge.drafted` → `"{by} dictated a discharge summary (draft, not signed)."`.

- [ ] **Step 1: Write failing tests** (`test_p2_dictation.py`, autouse send guard; helpers from `test_flow_states`/`test_flow_tasks`):
  - `test_parse_kumar_orders`: `parse_order_text(<kumar-orders transcript>)` → reason `"Open hernia repair"`. Items: dose `name "paracetamol"`, `amount "1 g"`, `every_h 6`, `proof "photo"`; obs `every_h 1`, `limits {"sbp_min": 90}`.
  - `test_parse_iyer_saline`: procedure `mode "start_end"`; obs `every_h 0.25`.
  - `test_digits`: `"eighty two over fifty four"` → `"82 over 54"`.
  - `test_discharge_sections_kumar`: headings in order Diagnosis, Procedure, Course on the ward, Medicines, Follow-up; Follow-up text `"Review in clinic on day 7."`.
  - `test_dictate_orders_prepared_no_key`: upload `kumar-orders.wav` (bytes `b"RIFF"`) in clinic → `view["drafts"]["order"]` has 2 items and `source "rules"`, `heard_by "prepared"`; `order_list` is still empty (D10).
  - `test_typed_text_and_exactly_one_input`: typed text gives a draft with `heard_by "typed"`; both file and text → 422; neither → 422.
  - `test_model_reply_used_when_grounded`: key set, `live.spark_text` faked to return grounded JSON → `source "muse-spark-1.3"`.
  - `test_model_reply_with_invented_item_falls_back` (Review Focus 3): fake reply adds `"Ondansetron 4 mg every 8 h"` → `source "rules (model reply not usable)"`, no ondansetron item. Same for the reply `"not json"`.
  - `test_sign_with_draft_id_closes_draft`: sign the draft's items with `draft_id` → `drafts.order is None`, `order.signed.payload.draft_id` set; a second sign with the same id → 409; an unknown id → 404.
  - `test_dictate_discharge_and_sign`: in `ward`, `kumar-discharge.wav` → five sections; `/discharge/sign` with `draft_id` → state `discharging`; dictate discharge in `clinic` → 409.
  - `test_models_endpoint_reports_no_key`: `GET /journey/models` → `{"live": False, "voice": False}`.
  - `test_new_plain_lines_have_no_advice_words`, and `"Do not give medical advice."` is in `ORDER_PROMPT` and `DISCHARGE_PROMPT`.
- [ ] **Step 2: Run** the file → FAIL.
- [ ] **Step 3: Implement.** Keep `media_api.py` under 300 lines after Tasks 3–4 add to it. If needed, put `_heard` and upload checks in `live.py`.
- [ ] **Step 4: Run** the file → PASS; `make test` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2 P2: dictated orders and discharge as drafts; sign by draft`.

---

### Task 3: Photos and proof checks (backend)

**Files:**
- Create: `count-guard/backend/app/journey/proof.py`
- Modify: `count-guard/backend/app/journey/media_api.py` (`POST /photos`, `GET /photos/{photo_id}`), `count-guard/backend/app/journey/tasks.py` (task progress = `task.began`/`task.done` only), `count-guard/backend/app/journey/states.py` (`flow_view` adds `photos`), `count-guard/backend/app/journey/stories.py`
- Test: `count-guard/backend/tests/test_p2_photos.py`

**Interfaces:**
- Consumes: Task 1 `live.read_photo`; `morning.strips.parse_strip_text`; `morning.lexicon.ground`; `journey.rx.key_of`; `tasks.task_list`.
- Produces (`proof.py`, pure):
  - `parse_monitor_text(text) -> dict`: `{sbp, dbp, hr}` for the ints that are present, from JSON (code fences stripped). Bad JSON → `{}`.
  - `check_strip(strips: list[dict], task: dict) -> {"read": str, "match", "why"}`: `match "ok"` when a strip's `generic`, or else its lowercased `name_as_read`, equals the generic of `ground(task name or title)`, or else `key_of(task name)`. `"mismatch"` when strips were read and none match. `"none"` when no strip was read. `read` = `"Paracetamol 500 mg"`-style, joined by `", "`. `why` examples: `"The strip reads Paracetamol 500 mg; the task is paracetamol."` and `"The strip reads Amlodipine 5 mg; the task is paracetamol."`. Strength is never compared.
  - `check_monitor(read: dict, stated: dict) -> {...}`: compares only the keys present in both. All equal → `"ok"`; any differ → `"mismatch"` with `why "The monitor reads 88/54, pulse 112; stated 82/54, pulse 112."`. Nothing read → `"none"` (`"The monitor could not be read; the photo is kept."`). Nothing stated → `"none"` (`"No stated value to compare; the photo is kept."`).
  - `photos_view(events) -> list[dict]`: `{"id", "purpose", "task_id", "by", "at_ms", "url": f"/journey/episodes/{e['episode_id']}/photos/{id}", "check": {"read","match","why","source"} | None}`, oldest first.
- Routes (`media_router`):
  - `POST /photos` (multipart: `file` image/* ≤ 8 MB, `purpose` Literal["reference","proof"], `by`, `at_ms?`, `task_id?` ≤ 64, `sbp?`/`dbp?`/`hr?` with P1 `Values` bounds). `proof` needs `task_id` of this episode (404) whose status is `open` or `running` (409 otherwise). `reference` takes no `task_id` (422). The file is saved to `data_dir/journey_media/<episode_id>/<uuid4hex><.jpg|.png|.webp>`. Writes `photo.added {purpose, path (relative to data_dir), task_id?, by}`. For `proof`: dose → `read_photo(..., "strip")` → `parse_strip_text` → `check_strip`; obs → `read_photo(..., "monitor")` → `parse_monitor_text` → `check_monitor` against the stated values; other kinds → `match "none"`, `why "Kept as proof; this kind of task has no reading."`. A reader that returned nothing gives `match "none"` and keeps the photo. Writes `proof.checked {photo_id, task_id, read, match, why, source}`. Returns `view()`. The new photo is the last in `view["photos"]`.
  - `GET /photos/{photo_id}`: a `FileResponse` of this episode's `photo.added`. 404 if the photo is unknown, or in another episode, or its resolved path is outside `data_dir/journey_media`.
- `tasks.task_list`: `mine` keeps only `task.began` and `task.done` events (Review Focus 2).
- `plain`: `photo.added` → `"{by} added a {purpose} photo."`; `proof.checked` → `"Photo check: {why}"`.

- [ ] **Step 1: Write failing tests** (`test_p2_photos.py`, autouse send guard):
  - `test_strip_photo_matches_dose_task`: Kumar in ward with an acknowledged paracetamol dose task → upload `strip-paracetamol.png` (proof, task_id) → the last photo's `check.match == "ok"`, `source "prepared"`.
  - `test_strip_of_other_medicine_is_flagged`: `check_strip([read_strip("Amlodipine","5 mg")], task)` → `"mismatch"`, and `why` names both.
  - `test_monitor_photo_flags_mismatch`: Iyer's obs task, `monitor-88-54.png` with stated 82/54/112 → `"mismatch"`, `why` contains `"88/54"` and `"82/54"`.
  - `test_unknown_photo_without_key_is_kept_not_checked`: `IMG_0001.jpg` → photo listed, `match "none"`.
  - `test_reference_photo_and_served_file`: purpose `reference` → `GET` its url returns the same bytes. Another episode's id → 404.
  - `test_proof_needs_open_task`: `task_id` of a done non-recurring task → 409; unknown → 404.
  - `test_photo_on_running_task_keeps_it_running` (Review Focus 2): a begun `start_end` task plus a proof photo → status still `running`, and `/done` succeeds.
  - `test_live_reader_faked`: key set, `SparkAdapter.read_strips` faked → `source "muse-spark-1.3"`; a faked raise → `match "none"`.
  - `test_why_strings_have_no_advice_words`.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** → PASS; `make test` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2 P2: photos on the chart; strip and BP-monitor proof checks, flagged never blocking`.

---

### Task 4: Spoken task completion and the P2 story test (backend)

**Files:**
- Create: `count-guard/backend/app/journey/spoken.py`
- Modify: `count-guard/backend/app/journey/media_api.py` (`POST /dictate/task`), `count-guard/backend/app/journey/flow_api.py` (`DoneIn`), `count-guard/backend/app/journey/tasks.py` (`complete_task` and `task_list` fields), `count-guard/backend/app/journey/stories.py`
- Test: `count-guard/backend/tests/test_p2_spoken.py`, `count-guard/backend/tests/test_p2_story.py`

**Interfaces:**
- Consumes: Task 1 seam; Task 2 `digits`, `_heard`; Task 3 `proof.checked` events.
- Produces (`spoken.py`, pure):
  - `TASK_PROMPT`: lists the open tasks as `id: title`, asks for `{"task_ids": [...], "values": {"sbp","dbp","hr","spo2","temp"}}`, and contains `Do not give medical advice.`
  - `parse_values(text) -> dict`. Reads `digits(text)` with: sbp/dbp `(\d{2,3})\s*(?:over|/)\s*(\d{2,3})`; hr `(?:pulse|heart rate|hr)\D{0,10}(\d{2,3})`; spo2 `(?:sats?|saturation|spo2|oxygen)\D{0,10}(\d{2,3})`; temp `temp(?:erature)?\D{0,10}(\d{2}(?:\.\d)?)`. Only found keys are returned.
  - `match_tasks(text, tasks) -> list[str]`: over tasks with status `open` or `running`, in `task_list` order. A dose matches when its name (or title) generic/key appears in the text. An obs matches when `parse_values` finds sbp, or the text says bp/pressure/pulse/obs. Other kinds match when a title word of 4+ letters (not a stopword) appears.
  - `completion_from_reply(reply, tasks, transcript) -> dict | None`: the ids must be open tasks, and every value must appear in `digits(transcript)` and pass the P1 `Values` field bounds (checked per field). Otherwise `None`.
- Produces: `POST /dictate/task` (multipart like Task 2). Only in `ward` (409). It writes **nothing** and returns `{"transcript", "heard_by", "source", "candidates": [{"id","title","kind","mode","status"}], "values": dict}`. Model first, rules fallback, `source` as in Task 2.
- Produces (`DoneIn`): `via: Literal["tap","voice"] = "tap"`; `transcript: str` 0–1000 (required non-empty when `via == "voice"`, else 422); `proof_id: str | None` (≤ 64).
- `complete_task(..., via, note, values, transcript="", proof_id=None)`. `proof_id` must be this episode's `photo.added` (404). If it has a different `task_id`, the result is 409 `"This photo was checked against another task."`. `match` is the `proof.checked.match` for that photo, or `"none"` when there is no photo. `task.done` payload: `{task_id, by, via, note, transcript, proof_id, match, values}` (the last three only when present). A mismatch never refuses (D9).
- `task_list` rows add `name`, `amount` (R12). `done[]` entries add `transcript`, `proof_id`, `match`. `plain(task.done)` → `"{by} finished a task by voice."` when `via == "voice"`, with `" Photo flagged."` added on a mismatch.

- [ ] **Step 1: Write failing tests** in `test_p2_spoken.py` (autouse send guard):
  - `test_parse_values_iyer`: `"BP 82 over 54, pulse 112, bed 7."` → `{"sbp": 82, "dbp": 54, "hr": 112}`.
  - `test_kumar_paracetamol_matches_one_task`: open dose and obs tasks → `/dictate/task` with `kumar-paracetamol.wav` → one candidate (the dose); the ledger event count is unchanged.
  - `test_two_obs_tasks_both_offered`: two open obs tasks → two candidates (the nurse picks).
  - `test_no_match_returns_empty_candidates`.
  - `test_model_ids_and_values_are_grounded` (Review Focus 4): the faked reply names a done task id and `hr 130` that was not said → falls back to rules.
  - `test_voice_done_needs_transcript`: `via "voice"` with an empty transcript → 422.
  - `test_done_with_proof_records_match`: a strip photo `ok` → `task.done.match == "ok"` and the dose is given. A monitor photo `mismatch` → done succeeds, `match "mismatch"`, the obs is recorded.
  - `test_proof_id_rules`: a photo from another episode → 404; a photo for another task → 409.
  - `test_task_view_has_name_amount_and_done_fields`.
  - `test_task_prompt_forbids_advice`: `"Do not give medical advice."` is in the `TASK_PROMPT` text.
- [ ] **Step 2: Write failing** `test_p2_story.py::test_p2_done_when_without_a_key` (no key, prepared files only, explicit `at_ms`, `H = 3_600_000`):
  - Kumar: `/dictate/orders` `kumar-orders.wav` at 0. Admit with the draft's `reason` at 10 min. Sign the draft (`draft_id`) at 12 min. Complete admission at 1 h. Ack at 1 h 05. `/dictate/task` `kumar-paracetamol.wav` at 4 h → one candidate. Photo `strip-paracetamol.png` → `ok`. Done `via voice` with `proof_id` → `match "ok"`. `/dictate/discharge` `kumar-discharge.wav` at 30 h. Sign with `draft_id` → `discharging`.
  - Iyer: `/dictate/task` `iyer-bp.wav` at 1 h → one obs candidate with values 82/54/112. Photo `monitor-88-54.png` with those stated values → `mismatch`. Done `via voice` → `match "mismatch"`, and an open `obs_past_limit` nudge exists.
  - Assert no `now_next`, `plain` or `why` text seen matches the advice regex.
- [ ] **Step 3: Run** both files → FAIL. **Step 4: Implement.** **Step 5: Run** → PASS; `make test` → all pass.
- [ ] **Step 6: Commit** `Count Guard v2 P2: tasks completed by voice with photo proof; done-when story test`.

---

### Task 5: Frontend plumbing and pure helpers

**Files:**
- Create: `count-guard/frontend/src/care/recorder.js`, `count-guard/frontend/src/care/recorder.test.js`, `count-guard/frontend/src/care/drafts.js`, `count-guard/frontend/src/care/drafts.test.js`
- Modify: `count-guard/frontend/src/journey.js` (`uploadJourney(id, path, file, fields = {})`), `count-guard/frontend/src/care/ward.js` (`upload(id, path, file, fields)` stamps `at_ms: nowMs`; new `ask(id, path, file, fields)` returns the JSON without swapping the view; shares `busy`/`error`)

**Interfaces:**
- Produces (`journey.js`): `uploadJourney` appends `file` only when given, and each field whose value is not `null`/`undefined`/`""`. The TodayPanel strip call stays unchanged.
- Produces (`recorder.js`):
  - `pickMime(isSupported: (t) => boolean) -> string`: first of `["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"]`, else `""`.
  - `audioName(mime) -> "recording.webm"|"recording.m4a"|"recording.ogg"`.
  - `micStatus({ hasMediaDevices, hasRecorder, mime }) -> {ok: boolean, message: string}`: when not ok, the message is `"Recording is not available in this browser. Choose an audio file or type what was said."`.
- Produces (`drafts.js`):
  - `itemsToRows(items) -> rows`: the inverse of `orderRowsToItems` (numbers become strings; `limits.sbp_min`/`sbp_max` become row fields; missing fields become `blankRow` defaults).
  - `sectionsToSummary(sections) -> string`: `"Heading: text"` lines joined by `"\n"`.
  - `MATCH_LABEL = {ok: "Photo matches the task", mismatch: "Flagged: the photo does not match. The nurse decides.", none: "Photo kept, not checked"}`.
  - `proposalChoices(proposal, tasks) -> {choices, pick: boolean}`: the candidates, or all `open`/`running` tasks when there are none. `pick` is true unless there is exactly one.
  - `newestPhoto(view, taskId) -> photo|null`: the last of `view.photos` with that `task_id` (any purpose when `taskId` is null).
  - `SOURCE_LABEL = {"muse-spark-1.3": "Muse Spark", rules: "Rules (no model)", "rules (model reply not usable)": "Rules (model reply not usable)", prepared: "Prepared demo result", typed: "Typed", "muse-voice-transcribe": "Muse Voice"}`.
- [ ] **Step 1: Write failing tests**:
  - Round-trip `orderRowsToItems(itemsToRows(items)).items` deep-equals the Task 2 Kumar items, `proof "photo"` included.
  - `sectionsToSummary` output.
  - `proposalChoices` for 0, 1 and 2 candidates.
  - `newestPhoto`.
  - `pickMime(() => false) === ""` and `micStatus` not ok with the message (Review Focus 5).
  - No label in `MATCH_LABEL`, `SOURCE_LABEL` or `micStatus` matches the advice regex.
- [ ] **Step 2: Run** `node --test 'src/care/*.test.js'` → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P2: upload with fields, recorder and draft helpers`.

---

### Task 6: Doctor dictation, drafts and reference photos (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/Dictate.jsx`, `count-guard/frontend/src/care/Photos.jsx`
- Modify: `count-guard/frontend/src/care/OrderForm.jsx`, `count-guard/frontend/src/care/DoctorActions.jsx`, `count-guard/frontend/src/care/Chart.jsx` (pass `upload`/`ask` to `StatePanel`; render `Photos`), `count-guard/frontend/src/care/StatePanel.jsx`, `count-guard/frontend/src/care/CareShell.jsx` (models chip from `GET /journey/models`: "Models: live" / "Models: prepared (no key)")

**Interfaces:**
- Consumes: Task 5 helpers; `view.drafts`, `view.photos`; routes from Tasks 2–3.
- Produces: `Dictate({ label, busy, onSend })`, where `onSend({ file } | { text })` returns a promise. It holds:
  - one **Record** button that toggles to **Finish recording**, using `getUserMedia({audio: true})` and `MediaRecorder` with `pickMime`. The blob becomes `new File([blob], audioName(mime), {type: mime})`.
  - an "Or choose an audio file" `<input type="file" accept="audio/*">`.
  - an "Or type what was said" textarea with a **Use this text** button.
  - On a mic error it shows `micStatus(...).message`, and the typed box stays usable.
- `OrderForm({ busy, onSign, draft })`: when `draft?.id` changes, `setRows(itemsToRows(draft.items))` and remember `draftId`. It shows "Draft from dictation · {SOURCE_LABEL[source]}. Check each row, then sign." and the transcript in quotes. `onSign(items, draftId)` sends `draft_id` only while the rows came from that draft. Each row gains a Proof select (None / Photo) (R12).
- `DoctorActions`:
  - `clinic`: `Dictate` "Dictate orders" → `upload("/dictate/orders", file, {text, by})`; `OrderForm draft={view.drafts?.order}`; the Admit reason is prefilled from `draft.reason` when the draft id changes.
  - `admitting` and `ward`: the same Dictate and OrderForm.
  - `ward`: `Dictate` "Dictate discharge" → `/dictate/discharge`. The Summary textarea is prefilled with `sectionsToSummary(draft.sections)` when the draft id changes. Sign sends `draft_id` while the text came from that draft.
  - `clinic` and `ward`: an "Add reference photo" file input (`accept="image/*" capture="environment"`) → `upload("/photos", file, {purpose: "reference", by})`.
- `Photos({ view })`: a card on the chart for every role. Each photo shows a thumbnail (`<img src={photo.url}>`), purpose, who, when (`label(at_ms)`) and, for proof, `MATCH_LABEL[check.match]` with `check.why`. A mismatch uses the `sun` pill.
- [ ] **Step 1: Write a failing node test** for any new pure helper this task extracts (at least `draftChanged(prevId, draft) -> boolean` if it is used for the prefill effects; add it to `drafts.js`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P2: doctor dictates orders and discharge; drafts load for checking; reference photos`.

---

### Task 7: Nurse voice completion with photo proof; patient sees proof (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/TaskProof.jsx`
- Modify: `count-guard/frontend/src/care/NurseActions.jsx` (ward branch hosts `TaskProof`; a `TaskRow` with `proof === "photo"` gets an **Add photo proof** button that opens `TaskProof` on that task with `via "tap"`), `count-guard/frontend/src/care/Chart.jsx` (task rows show the last done entry's via and match), `count-guard/frontend/src/care/MyCare.jsx` (done entries: who, when, "by voice", a photo link, flag)

**Interfaces:**
- Consumes: Task 5 `ask`, `upload`, `proposalChoices`, `newestPhoto`, `MATCH_LABEL`; `tasklist.js` `OBS_FIELDS`, `obsValues`; Task 4 routes.
- Produces: `TaskProof({ view, tasks, by, busy, act, upload, ask, preset })`, a card titled "Complete a task by voice":
  1. `Dictate` → `ask("/dictate/task", file, {text, by})` → the proposal. It shows the transcript in quotes and `SOURCE_LABEL`.
  2. `proposalChoices`: with `pick`, radio buttons list the choices; with exactly one choice, it is preselected.
  3. An obs task shows the obs inputs prefilled from `proposal.values` (validated with `obsValues`).
  4. Optional **Add photo** → `upload("/photos", file, {purpose: "proof", task_id, by, sbp, dbp, hr})` → `newestPhoto(view, task_id)` → the `MATCH_LABEL` pill and `why`. A mismatch is shown amber and **Confirm stays enabled** (D9).
  5. **Confirm**:
     - a `start_end` task that is not running → `act("/tasks/{id}/begin", {by})`;
     - otherwise → `act("/tasks/{id}/done", {by, via, transcript, note: "", values?, proof_id?})`.
     - On success the card clears.
  - **Cancel** clears without writing.
  - `preset` (from Add photo proof) skips steps 1–2 with `via "tap"` and an empty transcript.
- [ ] **Step 1: Write a failing node test** for the extracted helper `doneBody({task, via, transcript, form, photo}) -> {body} | {error}` in `drafts.js`:
  - obs without valid values → error;
  - `proof_id` only when there is a photo;
  - `via "voice"` with an empty transcript → error;
  - no advice words in the errors.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P2: nurse completes tasks by voice with photo proof; proof on the chart and My care`.

---

### Task 8: Browser walk of the P2 done-when, and fixes

**Files:**
- Create: `.superpowers/sdd/<this plan's workspace>/p2-walk.md` (git-ignored walk log), the walk script in the scratchpad (not committed)
- Modify: whatever the walk finds broken

**Interfaces:**
- Consumes: everything above, running via `make dev` with **`MODEL_API_KEY=`** in the environment. First run `curl -s localhost:8100/journey/models` and expect `{"live":false,...}`. If a server is already listening (`lsof -iTCP:8100 -sTCP:LISTEN`) and reports `live: true`, stop it and restart it with the empty key. Never walk with a key.
- The Playwright MCP browser may be locked. Headless `playwright-core` from the scratchpad (as in the P1 walk) is fine. The mic is faked by `setInputFiles` on the "choose an audio file" input with `count-guard/eval/p2/<stem>.wav`. The typed box covers the rest. Photos use `count-guard/eval/p2/*.png`.
- [ ] **Step 1:** Reset the ward. Walk the done-when, switching roles in the header as in P1. Log each step (role, control, Now/Next, pass/fail):
  1. Doctor on Kumar in clinic: upload `kumar-orders.wav`. Check that the draft rows load (paracetamol with proof Photo, BP and pulse) and that the Admit reason fills. Sign, then Admit.
  2. Nurse: complete admission and Acknowledge.
  3. Nurse on Kumar (ward), voice card: upload `kumar-paracetamol.wav`. One task is preselected. Add `strip-paracetamol.png` → "Photo matches the task". Confirm. The chart task row shows by voice and the match.
  4. Nurse on Iyer: upload `iyer-bp.wav`. The values fill 82/54/112. Add `monitor-88-54.png` → the Flagged pill. Confirm still works, and the limit nudge appears for nurse and doctor.
  5. Doctor on Kumar (ward): upload `kumar-discharge.wav`. The summary fills with five headings. Sign discharge → Being discharged.
  6. Doctor adds a reference photo on Kumar. It shows on the chart's Photos card for the patient role too.
- [ ] **Step 2:** Check Review Focus 5 by denying the microphone (the browser context has no `microphone` permission). The message shows, and the typed box drafts orders (`source` "Typed" heard, "Rules" structured).
- [ ] **Step 3:** For each failure: fix it, add a test where the fault is in pure logic, and re-walk that step.
- [ ] **Step 4:** `make test`, node tests and `npm run build` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2 P2: browser walk of voice and photo proof; fixes`.

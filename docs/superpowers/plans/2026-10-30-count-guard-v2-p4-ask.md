# Count Guard v2 · P4 Patient "Ask" Section and Doctor Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A patient (Das, Kumar or Iyer, picked in the patient view) has an **Ask** page with four actions:
a record bot that answers only from their own record and shows its source lines, a question to the doctor
answered by voice or text, a healing photo the doctor reviews with one of three fixed decisions, and a
medicine photo whose strips are matched to the prescription and named with their schedule. A doctor-status
chip on every screen reads "Dr. A. Rao: In theatre with R. Kumar, free about 11:45" while Kumar is in
theatre, and the doctor can set "Available" or "Busy until …" by hand. Everything runs offline without a key.

**Architecture:** Three pure backend modules: `journey/record.py` turns one episode's ledger into numbered
record lines and answers a question from them (model reply checked with `grounded()`, else a rules
retrieval that quotes the lines). `journey/medicines.py` matches strips read from a photo to the
prescription by exact medicine key. `journey/doctor_status.py` derives the chip from the patients' episodes
and a ward "staff board" episode that holds hand-set statuses. One new route module per area:
`journey/ask_api.py` (patient Ask actions and the doctor's answers) and `journey/staff_api.py` (doctor
status). `flow_view` gains `ask`. The frontend gains a patient picker, the Ask page, the doctor's Ask inbox
on the chart, doctor-queue rows, and the status chip.

**Tech Stack:** FastAPI + pydantic v2 (JSON and multipart), SQLite ledger, pytest; Muse Spark 1.3 through
`journey/live.py` (`spark_text`, `read_photo`), Muse Voice through `media_api._heard`; React 18 + Vite,
Node built-in test runner; Pillow for stand-in photos; headless `playwright-core` for the walk.

**Spec:** `docs/superpowers/specs/2026-10-29-count-guard-v2-patient-states-design.md`. Sections: P4, D7,
D8, D9, D10, D11, D3 (second cut), anti-goals, "Actors and what they see" (patient, header chip), the Data
table rows `question.*`, `review.*`, `photo.added` (healing, medicines), `doctor.status`, and demo script
items 1–3. Ledgers: P1 `.superpowers/sdd/2026-10-29-count-guard-v2-p1-states/progress.md`, P2
`.superpowers/sdd/2026-10-30-count-guard-v2-p2-voice-photo/progress.md`, P3
`.superpowers/sdd/2026-10-30-count-guard-v2-p3-video/progress.md`. Rulings P2-R1, R3, R4, R5, R15, R17,
R20, R21 and P3-R4 bind this plan.

## Global Constraints

- Branch `count-guard-v2` (P3 ends at f54f2f6 or later). Commit after each task with
  `git -c user.name=lvnpred -c user.email=lvnpred@gmail.com commit`. Never push. No `Co-Authored-By` trailer.
- Keep every file under 500 lines. `journey/api.py` (466 lines) gets only the two-line `demo_rx` and `seed`
  edits named in Tasks 1 and 4. `journey/media_api.py` gets no new routes; Task 2 extracts two helpers from it.
  New routes go in `journey/ask_api.py` and `journey/staff_api.py`.
- Validate input at system boundaries. JSON bodies use `api.Strict`/`api.At` with bounds: question 1–300,
  answer 1–1000, note 0–300, `by` 1–80, ids 1–64, `at_ms` ≥ 0. Multipart routes use `Form(...)`/`File(...)`
  with the same bounds. Photos reuse the P2 checks: JPEG/PNG/WebP, ≤ 8 MB, magic bytes.
- **Doctor decides; the app never advises.** The bot restates record lines only. A review decision is one of
  three fixed choices. No new server string, UI string, record-line wrapper, bot answer or `why` text may
  match `\b(give|take|stop|increase|reduce|start|administer|consider)\b` (case-insensitive). Exempt, as the
  spec says: the doctor's own words (prescription rows, dictated orders and summary, the doctor's answers
  and review notes) and the patient's own question text. Tests collect strings from produced output (P2-R17).
- The patient's question text is shown only on the Ask page and the doctor's Ask inbox. It never goes into
  `plain`, `now_next` or a queue row (Das's demo question contains "take").
- Bot anti-goal: every found answer lists ≥ 1 source line, and each source is a line built from this
  episode's own events (`event_id` in this episode). No source → `found: false` and the copy
  "I can't find that in your record." with an "Ask Dr. Rao" button.
- D11 and P2-R1/R21: live Muse only when `settings.spark_configured` / `voice_configured`. A live failure or
  an unusable reply falls back (bot → rules answer; photo read → prepared file by name). Every result stores
  and shows its `source` label (`drafts.js` `sourceLabel`). **Tests never call a model.** Every new test file
  installs the P2-R3 autouse guard on `httpx.HTTPTransport.handle_request` and
  `httpx.AsyncHTTPTransport.handle_async_request`. Live paths are tested by monkeypatching
  `SparkAdapter.write` / `SparkAdapter.read_strips` with `create_app(_keyed(tmp_path))` (`test_p2_live._keyed`).
- **Build agents never spend credits.** Any server an agent starts: `make dev MODEL_API_KEY= CG_API_PORT=8200
  CG_WEB_PORT=5273 COUNT_GUARD_DATA=<scratchpad>/walk-data`; check `curl -s 127.0.0.1:8200/journey/models`
  → `"live": false` first (P2-R15). Never use or stop the owner's 8100. No `--spend`, no `SPEND=1`.
  No task uses WebSearch/WebFetch.
- P2-R4: media is never committed. Stand-in photos come from `eval/p4/make_photos.py`; `eval/p4/*.png` is
  git-ignored. The doctor's spoken answer WAV comes from the existing `eval/p2/make_media.py` (it speaks every
  prepared JSON with a `transcript`). `tests/test_repo_hygiene.py` keeps passing.
- D9 style: a medicine not on the prescription, or a strength that differs, is flagged, never refused.
- Synthetic only: `Dr. A. Rao (synthetic)`, `Nurse Meena (synthetic)`, the three seeded patients.
- One ward clock: every write is stamped with the client's `at_ms`.
- Tests: `cd count-guard && make test`; `cd count-guard/frontend && node --test 'src/care/*.test.js' && npm run build`.
  Baseline: 278 backend, 64 node at f54f2f6 (re-count at dispatch). Earlier tests keep passing or are updated
  in the task that changes the behaviour they pin.

## Out of scope (decided)

- Free-text bot prose offline. Without a key the bot quotes the matching record lines under "Here is what
  your record says." Cost if wrong: offline answers read as quotes, not sentences.
- Healing-photo comparison by a model. The doctor sees the healing photo beside the reference photos and decides.
- Prescribed medicines missing from the photo. Only strips seen are listed. Cost if wrong: one line per gap.
- Several doctors. The status logic takes a `doctor` name, but only Dr. A. Rao is seeded and shown.
- Fixing `spoken.py`'s substring medicine match (P2 deferral). P4's own matching is exact-key; the spoken path
  is unchanged. Cost if wrong: a short spoken name can still pick a dose task (the nurse confirms, D10).
- Notifying the patient when an answer arrives. The Ask page shows it on the next look.

## Review Focus

1. A question that seeks advice ("Should I stop amlodipine?", "Can I take two?"). The answer never contains
   an advice word: the rules answer is the fixed lead plus quoted lines, and a model answer with an advice
   word is rejected and replaced by the rules answer. Test in Task 1.
2. A model reply that cites a line the record does not have (`"L99"`), or adds a number, medicine or
   "not/before/after" that its cited lines do not contain. It is rejected (`grounded()` against the cited
   lines only); the stored source is `"rules (model reply not usable)"`. Test in Task 1 (pure) and Task 2 (route).
3. A strip with a short or brand-like name (`"Amlo 5 mg"`, `"Pan 40 mg"`). It is never matched by substring:
   it is listed as not prescribed and flagged. Test in Task 3.
4. A second answer to one question or a second decision on one review (double tap, two tabs). 409, nothing
   written. A doctor answering a bot question is 409. Test in Task 2.
5. A hand-set status that expires: "Busy until 11:30" set at 11:00 reads busy at 11:29 and falls back to the
   automatic status at 11:30 (in theatre if Kumar is there, else available). `until_ms` in the past or more
   than 12 h ahead is 422. Test in Task 4.

---

### Task 1: Record lines and the grounded record bot (backend, pure) + the patients' prescriptions

**Files:**
- Create: `count-guard/backend/app/journey/record.py`
- Modify: `count-guard/backend/app/journey/schedule.py` (`schedule_text`), `count-guard/backend/app/journey/rx.py` (`IYER_DOCUMENT`, `document_for`), `count-guard/backend/app/journey/seed.py` (Iyer's prescription), `count-guard/backend/app/journey/api.py` (`demo_rx` uses `document_for(episode label)`)
- Test: `count-guard/backend/tests/test_p4_record.py`

**Interfaces:**
- Consumes: `dictation.grounded`, `dictation.ADVICE`, `dictation._WORD`, `dictation._STOP`, `dictation._DRUG`, `dictation.digits`, `dictation._json_of`; `rx.key_of`; `schedule.build`; `stories.clock`; `morning.discharge.visible_events`.
- Produces (`schedule.py`): `schedule_text(row: dict) -> str` for one `build()` row: the filled slots as
  `"{amount} {SLOT_WORDS[slot]}"` joined by `", "` (or `"as needed"` when `as_needed`), then `timing`, then
  `"for {days} days"` when `days`, then `note`, the non-empty parts joined by `"; "`.
  Amlodipine row → `"1 in the morning; After food; for 30 days"`.
- Produces (`rx.py`): `IYER_DOCUMENT` shaped like `DEMO_DOCUMENT`: patient `"S. Iyer (synthetic)"`, rows
  Tab. Pantoprazole 40 mg 1-0-0 Before food 14 days; Tab. Atorvastatin 10 mg 0-0-1 After food 30 days;
  Tab. Paracetamol 500 mg SOS "As needed for pain", instructions "Max 3 times daily". Every name grounds
  in the lexicon. `document_for(label: str) -> dict`: a copy of `DEMO_DOCUMENT` whose `patientName` is
  `label`. `demo_rx` calls `from_document(document_for(episode["label"]), source="demo")`, so Das's
  prescription no longer carries Kumar's name (anti-goal: patients see only their own record).
- Produces (`seed.py`): after Iyer's admission, `store.append(iyer, "rx.ordered", from_document(IYER_DOCUMENT, source="demo"), ts_ms=0)`.
  Her prescription is on file from the day before. `seed_ward`'s return value is unchanged in this task.
- Produces (`record.py`, pure):
  - `NOT_FOUND = "I can't find that in your record."`, `FOUND = "Here is what your record says."`, `BOT = "Record bot"`.
  - `BOT_PROMPT`: "A patient asks about their own hospital record. Answer only from the numbered lines below.
    Reply with JSON only: {\"answer\": \"...\", \"sources\": [\"L1\"]}. The answer restates the cited lines
    in plain words and adds nothing. If no line answers the question, reply {\"answer\": \"\", \"sources\": []}.
    Do not give medical advice.\nLines:\n" — then `bot_prompt(lines)` appends `"L{n}: {text}"` rows and `"\nQuestion: "`.
  - `WRAPPERS: dict[str, str]`: one `str.format` template per line variant below, so the wrapper copy is
    testable apart from the record content it wraps (the v1 card sign "Vomiting that does not stop" is the
    doctor's discharge list, exempt; the wrapper around it is not).
  - `record_lines(events: list[dict]) -> list[dict]`: `{"id": "L1"…, "kind", "text", "event_id"}` from
    `visible_events(events)`, in ledger order, each text ≤ 300 chars. Exact wrappers:
    - `rx.ordered` row (latest rx only): `"Prescription from {by}: {medicine} — {schedule_text(row)}."` (kind `prescription`);
      each `advice` item: `"Note on the prescription from {by}: {item}"`; `review`: `"Follow-up on the prescription: {review}"`.
    - `order.signed` item: `"Order signed by {by} at {clock}: {text}"` (kind `order`).
    - latest `task.done` per task: `"{title}: done by {by} at {clock}."` (kind `task`).
    - `discharge.signed`: one line per sentence of `summary`: `"Discharge summary from {by}: {sentence}"` (kind `discharge`).
    - latest `discharge.card`: `"Wound care on your discharge card: {wound_care}"`, one `"Warning sign on your discharge card: {sign}"` per sign, `"Review on your discharge card: {review}"`, `"Help line on your discharge card: {help_line}"` (kind `card`).
    - `patient.state` with a `from`: `"{by} {states.DID[to]} at {clock}."` (no raw state words); without: `"You were admitted to the ward the day before."` (kind `stay`).
    - `question.answered` with `source "doctor"` (Task 2): `"{by} answered your question: {answer}"` (kind `answer`).
    - `review.answered` (Task 2): `"{by} reviewed your healing photo at {clock}: {label}."` (kind `review`).
  - `ASK_STOP = dictation._STOP | {"when", "what", "which", "where", "should", "could", "would", "does", "take", "have", "about", "much", "many", "need", "your", "tell", "know", "please", "there", "their"}`.
  - `rules_answer(question: str, lines: list[dict]) -> dict`: question words = `_WORD` matches of
    `digits(question).lower()` with length ≥ 4 and not in `ASK_STOP`. A line scores 1 per question word it
    contains (plural `s` tolerated, as `_words_heard`) plus 2 per medicine key it shares with the question
    (`key_of` of `_DRUG` matches on each side). Best score ≥ 1 → `{"answer": FOUND, "sources": [the
    best-scoring lines, first 3 in line order], "found": True}`; else `{"answer": NOT_FOUND, "sources": [], "found": False}`.
    Sources are the full line dicts.
  - `answer_from_reply(reply: str | None, lines: list[dict]) -> dict | None`: `_json_of(reply)`; `sources` a
    non-empty list of 1–3 ids all in `lines`; `answer` a str of 1–400 chars; `grounded(answer, " ".join(cited
    texts))` true; `ADVICE.search(answer)` false. Otherwise None (the caller falls back to the rules).
    An empty-sources reply is None too. Returns `{"answer", "sources": [line dicts], "found": True}`.

- [ ] **Step 1: Write failing tests** (`test_p4_record.py`, P2-R3 guard). Build events with a fresh client
  (`test_flow_states._new`) and the routes, then read `store.events`:
  - `test_schedule_text`: amlodipine, metoprolol (`"1 in the morning, 1 at night; After food; for 30 days"`) and paracetamol SOS (`"as needed; As needed for pain; Max 3 times daily"`).
  - `test_demo_rx_names_the_episode`: `rx/demo` on an episode labelled `"A. Das, 47 M (synthetic)"` → `view["rx"]["patient"] == "A. Das, 47 M (synthetic)"`.
  - `test_seed_iyer_has_her_prescription`: seeded Iyer's `view["rx"]["rows"]` keys `["pantoprazole", "atorvastatin", "paracetamol"]`; Kumar and Das have `rx None`; `test_care_demo` seed tests still pass.
  - `test_record_lines_from_a_full_record`: clinic rx + signed order + task done + discharge signed + card + home → kinds present, ids `L1..Ln` in order, every `event_id` is an event of this episode, the amlodipine line equals `"Prescription from Dr. A. Rao (synthetic): Tab. Amlodipine 5 mg — 1 in the morning; After food; for 30 days."`.
  - `test_rules_answer_cites_the_prescription_line`: `"When do I take amlodipine?"` → `found`, one source, the amlodipine line, `answer == FOUND`.
  - `test_rules_answer_not_found`: `"What is the capital of France?"`, `"When?"` and `""` → `NOT_FOUND`, `sources == []`.
  - `test_advice_seeking_question_gets_no_advice` (Review Focus 1): `"Should I stop amlodipine?"` → only the amlodipine line (it outscores the card sign "…does not stop"); `ADVICE` does not match `answer`. `"Can I take two?"` → not found.
  - `test_model_reply_checked` (Review Focus 2): a good reply `{"answer": "Amlodipine 5 mg, 1 in the morning, after food, for 30 days.", "sources": ["L<amlodipine>"]}` is accepted; `"L99"`, `"10 mg"`, `"before food"`, a reply with "take", an empty-sources reply and non-JSON each → None.
  - `test_wrappers_have_no_advice`: every `WRAPPERS` template formatted with `"x"` for each field, every `stay` line of the full record, `NOT_FOUND` and `FOUND` → no `ADVICE` match.
- [ ] **Step 2: Run** `cd count-guard && .venv/bin/pytest backend/tests/test_p4_record.py -q` → FAIL (import error).
- [ ] **Step 3: Implement** `record.py`, `schedule_text`, `IYER_DOCUMENT`/`document_for`, the seed line and the `demo_rx` edit. `record.py` may import `states.DID` but never `journey.api` or `tasks` (cycle rule as P3-R7; `states` never imports `record`).
- [ ] **Step 4: Run** the file → PASS; `make test` → all pass.
- [ ] **Step 5: Commit** `Count Guard v2 P4: record lines and a grounded record bot; Iyer's prescription; demo prescription carries the patient's own name`.

---

### Task 2: Ask routes: record bot, question to the doctor, healing-photo review (backend)

**Files:**
- Create: `count-guard/backend/app/journey/ask.py` (pure view), `count-guard/backend/app/journey/ask_api.py`, `count-guard/backend/app/journey/prepared/rao-answer.json`
- Modify: `count-guard/backend/app/journey/media_api.py` (extract `read_upload_photo`, `write_photo`; `add_photo` uses them), `count-guard/backend/app/journey/states.py` (`flow_view["ask"]`; `now_next`; `_latest_happening`), `count-guard/backend/app/journey/stories.py` (`plain`), `count-guard/backend/app/main.py` (register `ask_router`)
- Test: `count-guard/backend/tests/test_p4_ask.py`

**Interfaces:**
- Consumes: Task 1 `record_lines`, `bot_prompt`, `rules_answer`, `answer_from_reply`, `BOT`; `media_api._structure`, `media_api._heard`; `api._act/_at/_require/_store/view/raise_nudges/Strict/At`; `states.current_state`.
- Produces (`media_api.py`): `read_upload_photo(file: UploadFile) -> tuple[bytes, str]` (type → 400, size → 400, magic → 400, the existing details) and `write_photo(settings, store, episode_id, raw, kind, added: dict, ts) -> dict` (saves under `journey_media/<eid>/`, appends `photo.added`). `add_photo` behaviour and tests are unchanged.
- Produces (`ask.py`, pure, imports nothing from `states`/`tasks`/`seed`):
  - `DECISIONS = {"no_visit": "No visit needed", "come_in": "Come in to the clinic", "call": "The doctor will call you"}`.
  - `PHOTO_STATES = ("clinic_done", "home")`.
  - `short_name(label) -> str`: text before the first comma, without `" (synthetic)"`. `"R. Kumar, 58 M (synthetic)"` → `"R. Kumar"`; `"Dr. A. Rao (synthetic)"` → `"Dr. A. Rao"`.
  - `ask_view(events) -> {"questions": [...], "reviews": [...], "medicines": []}`, oldest first.
    Question: `{"id", "to", "text", "by", "at_ms", "answer": None | {"text", "by", "at_ms", "via", "heard_by", "sources", "found", "source"}}`.
    Review: `{"id", "photo": {"id", "url"}, "note", "by", "at_ms", "answer": None | {"decision", "label", "note", "by", "at_ms"}}`.
    Photo urls use the P2 `/photos/{id}` route. Task 3 fills `medicines`.
  - `open_for_doctor(events) -> {"questions": int, "reviews": int}` (unanswered doctor questions and reviews).
- Produces (`ask_api.py`): `ask_router = APIRouter(prefix="/journey/episodes/{episode_id}")`. The patient's
  `by` is always the episode label, never a body field.
  - `POST /ask/bot` `BotIn(At){text 1–300}`: writes `question.asked {to: "bot", text, by}`, builds
    `record_lines`, runs `_structure(settings, bot_prompt(lines), text, lambda r, q: answer_from_reply(r, lines), lambda q: rules_answer(q, lines))`,
    writes `question.answered {question_id, answer, sources, found, source, by: BOT}` at the same ts. Any state.
  - `POST /ask/doctor` `BotIn`: writes `question.asked {to: "doctor", text, by}`. Any state.
  - `POST /ask/hear` multipart (`by` 1–80, `file`, optional `at_ms`): `{"text", "heard_by"}` from `_heard(settings, file, None)`. Writes nothing (D10: the doctor confirms the text).
  - `POST /questions/{question_id}/answer` `AnswerIn(At){text 1–1000, by, via: Literal["text","voice"]="text", heard_by: str ≤ 40 = ""}`:
    404 `"Question not found"` (unknown id or another episode's), 409 `"The record bot answers this question."` (to bot),
    409 `"This question is answered already."`; writes `question.answered {question_id, answer: text, by, via, heard_by, sources: [], found: True, source: "doctor"}`.
  - `POST /ask/review` multipart (`file`, `note` 0–300 = "", `at_ms`): state not in `PHOTO_STATES` → 409
    `"A healing photo is sent once the visit is closed or you are home."`; then `read_upload_photo`, `write_photo`
    with `{purpose: "healing", by}`, and `review.requested {photo_id, note, by}`.
  - `POST /reviews/{review_id}/answer` `DecisionIn(At){decision: Literal["no_visit","come_in","call"], note 0–300 = "", by}`:
    404 `"Review not found"`, 409 `"This photo is reviewed already."`; writes `review.answered {review_id, decision, label: DECISIONS[decision], note, by}`.
  - Every write route returns `view()` and raises nudges, like `_act`.
- Produces (`states.py`): `flow_view` adds `"ask": ask_view(events)`. `now_next`: when the state is
  `clinic_done` or `home` and `open_for_doctor` has a review → next `"The doctor reviews the healing photo."`;
  else a question → `"The doctor answers the question."`. `_latest_happening` adds, at rank 0:
  `question.asked` to doctor → `"{short} sent a question to the doctor at {clock}."`; doctor `question.answered`
  → `"{by} answered the question at {clock}."`; `review.requested` → `"{short} sent a healing photo at {clock}."`;
  `review.answered` → `"{by} reviewed the healing photo at {clock}: {label}."`.
- Produces (`plain`): `question.asked` → `"{short} asked the record bot a question."` / `"{short} sent a question to the doctor."`
  (never the question text); `question.answered` by the bot → `"The record bot answered from {n} lines of the record."`
  or `"The record bot found nothing in the record for this question."`; by a doctor → `"{by} answered the question ({via})."`;
  `review.requested` → `"{short} sent a healing photo for review."`; `review.answered` → `"{by} reviewed the healing photo: {label}."`;
  `photo.added` with purpose `healing` keeps the generic line.
- `prepared/rao-answer.json`: `{"transcript": "The wound looks as expected for day 3. Your clinic review stays on day 7."}`.

- [ ] **Step 1: Write failing tests** (`test_p4_ask.py`, P2-R3 guard; a seeded ward via `test_care_demo._seed`; a helper `_home(client, eid)` that walks Kumar clinic → `rx/demo` → admit → ward → discharge sign → home with `DISCHARGE_CHECKS`):
  - `test_bot_answers_from_the_record_offline`: Das after `rx/demo` and Close visit, `"When do I take amlodipine?"` → `view["ask"]["questions"][-1]["answer"]` has `found`, `source "rules"`, one source whose text contains `"Amlodipine 5 mg"` and whose `event_id` is Das's `rx.ordered`.
  - `test_bot_not_found_offers_the_doctor`: `"Can I drive?"` → `found False`, `answer == NOT_FOUND`, `sources == []`.
  - `test_bot_reads_only_this_patient`: Kumar at home (card says "Wound"), Das asks `"How is the wound?"` → not found; every stored source `event_id` belongs to the asking episode.
  - `test_bot_live_reply_used_and_rejected` (Review Focus 2): keyed app, `SparkAdapter.write` faked with the good reply → `source "muse-spark-1.3"`; faked with `"L99"` → `source "rules (model reply not usable)"`; faked to raise `httpx.ConnectError` → `"rules (model reply not usable)"`.
  - `test_question_to_doctor_answered_by_text`: Kumar at home asks → `open_for_doctor` 1, `now_next.next == "The doctor answers the question."` → answer by text → `answer.via "text"`, the record now has an `answer` line.
  - `test_hear_writes_nothing`: `rao-answer.wav` (bytes `b"RIFF"`, `audio/wav`) → `{"text": <rao-answer transcript>, "heard_by": "prepared"}`; event count unchanged; `IMG_0001.webm` → 409 (P2 no-key detail).
  - `test_answer_refusals` (Review Focus 4): second answer → 409; answering a bot question → 409; unknown id → 404; another episode's question id → 404; each leaves the event count unchanged; empty text → 422.
  - `test_healing_review_no_visit_needed`: Kumar at home uploads a PNG with note "Day 3" → `review.requested`; `photos` lists it with purpose `healing`; `now_next.next == "The doctor reviews the healing photo."`; decision `no_visit` → `answer.label == "No visit needed"`; a second decision → 409.
  - `test_healing_review_refusals`: in ward → 409 with the exact detail; a GIF → 400; `decision "maybe"` → 422.
  - `test_ask_strings_have_no_advice`: collect every `plain`, `now_next`, bot `answer`, `DECISIONS` label and refusal detail produced above.
- [ ] **Step 2: Run** the file → FAIL.
- [ ] **Step 3: Implement.** Keep `ask_api.py` under 250 lines (Task 3 adds one route).
- [ ] **Step 4: Run** the file → PASS; `make test` → all pass (including the P2 photo tests after the extraction).
- [ ] **Step 5: Commit** `Count Guard v2 P4: Ask routes: grounded record bot, question to the doctor, healing photo reviewed by the doctor`.

---

### Task 3: Medicine photo: strips read, matched to the prescription, named with their schedule (backend)

D3 second cut: `ask_api.MEDICINES_LIVE = True` is the switch. The route calls `read_photo(..., live_ok=MEDICINES_LIVE)`.
The cut sets it to `False`, so the medicine photo always uses the prepared result. Record the cut in the ledger.

**Files:**
- Create: `count-guard/backend/app/journey/medicines.py`, `count-guard/backend/app/journey/prepared/meds-kumar.json`, `count-guard/backend/app/journey/prepared/meds-iyer.json`, `count-guard/eval/p4/make_photos.py`
- Modify: `count-guard/backend/app/journey/ask_api.py` (`POST /ask/medicines`), `count-guard/backend/app/journey/live.py` (`read_photo(..., live_ok=True)`), `count-guard/backend/app/journey/media_api.py` (extract `strips_from(text) -> list[dict]`, used by `_check_photo`), `count-guard/backend/app/journey/ask.py` (`medicines` in `ask_view`), `count-guard/backend/app/journey/stories.py` (`plain`), `count-guard/.gitignore` (`eval/p4/*.png`)
- Test: `count-guard/backend/tests/test_p4_medicines.py`

**Interfaces:**
- Consumes: Task 1 `schedule_text`; `schedule.build`; `rx.key_of`; `nudges._norm`; `live.read_photo`; `parse_strip_text` (through `strips_from`); Task 2 `read_upload_photo`, `write_photo`, `PHOTO_STATES`, `short_name`.
- Produces (`medicines.py`, pure): `match_medicines(strips: list[dict], rx: dict) -> {"rows", "match", "why"}`.
  - One row per strip, in read order: `{"read": "{name_as_read} {strength}".strip(), "prescribed": bool, "medicine": str | None, "schedule": str | None, "flag": None | "not_prescribed" | "strength_differs", "why": str}`.
  - A strip matches the rx row whose `key == key_of(name_as_read)`: **exact key equality, never a substring** (Review Focus 3).
  - Matched: `medicine` = the `build()` row's `medicine`, `schedule` = `schedule_text(row)`, `why` = `"On your prescription: {medicine}, {schedule}."`.
    If both strengths are present and `_norm` differs: `flag "strength_differs"`, `why` = `"The strip reads {read}. The prescription says {medicine}."`.
  - Not matched: `flag "not_prescribed"`, `why` = `"{read} is not on your prescription from {rx by}. Ask Dr. Rao about it."`.
  - `match`: `"none"` when no strips; `"mismatch"` when any flag; else `"ok"`. Whole `why`:
    none → `proof.NO_STRIP`; else `"{k} of {n} medicines in the photo are on your prescription."`, plus `" Flagged: {reads joined by ', '}."` when any flag.
- Produces (`live.py`): `read_photo(settings, reader, raw, filename, content_type, live_ok: bool = True)`; with `live_ok False` it skips the live branch even with a key.
- Produces (`POST /ask/medicines` multipart: `file`, `at_ms`): state not in `PHOTO_STATES` → 409
  `"A medicines photo is checked once the visit is closed or you are home."`; no `rx.ordered` → 409
  `"There is no prescription on your record yet, so the medicines cannot be matched."`; then photo checks,
  `write_photo` with `{purpose: "medicines", by}`, `read_photo(settings, "strip", raw, name, kind, live_ok=MEDICINES_LIVE)`,
  `strips_from(read["text"] or "")`, `match_medicines(...)`, and `medicines.read {photo_id, rows, match, why, source, by}`.
- `ask_view["medicines"]`: `{"id", "photo": {"id", "url"}, "rows", "match", "why", "source", "at_ms"}`, oldest first.
- `plain`: `medicines.read` → `"Medicines photo: {why}"`.
- Prepared (`{"text": "{\"strips\": [...]}"}` as `strip-paracetamol.json`):
  - `meds-kumar`: Metoprolol 25 mg, Amlodipine 5 mg, Pantoprazole 40 mg, Cetirizine 10 mg (the last not prescribed).
  - `meds-iyer`: Pantoprazole 40 mg, Atorvastatin 10 mg, Paracetamol 500 mg, Ibuprofen 400 mg (the last not prescribed).
- `make_photos.py` (Pillow, output git-ignored, docstring: stand-ins until the owner photographs real
  strips, as P2-R2): `meds-kumar.png`, `meds-iyer.png` (one drawn strip per prepared row, its name and
  strength), and `wound-day3.png` (a plain skin-tone panel with a drawn dressing line).

- [ ] **Step 1: Write failing tests** (`test_p4_medicines.py`, P2-R3 guard):
  - `test_match_names_each_with_its_schedule`: Kumar's demo rx and the `meds-kumar` strips → three rows `prescribed` with schedules (`amlodipine` → `"1 in the morning; After food; for 30 days"`), Cetirizine `not_prescribed`, `match "mismatch"`, whole `why` `"3 of 4 medicines in the photo are on your prescription. Flagged: Cetirizine 10 mg."`.
  - `test_short_names_never_match` (Review Focus 3): `"Amlo 5 mg"`, `"Pan 40 mg"`, `"Para 500 mg"` → all `not_prescribed`.
  - `test_strength_differs_is_flagged`: `Amlodipine 10 mg` → `strength_differs`, the why names both.
  - `test_no_strips_is_none`: `[]` → `match "none"`, `why == proof.NO_STRIP`.
  - `test_route_offline_kumar_and_iyer`: Kumar at home (Task 2 `_home`) uploads `meds-kumar.png` → `ask.medicines[-1]` with `source "prepared"`, 4 rows; seeded Iyer taken to home uploads `meds-iyer.png` → Ibuprofen flagged, three named with schedules.
  - `test_route_refusals`: in ward → 409; Das closed with no rx → 409 with the exact detail; `IMG_0001.png` with no key → `match "none"`, `source "none"`, 200 (photo kept).
  - `test_live_read_and_cut_switch`: keyed app, `SparkAdapter.read_strips` faked → `source "muse-spark-1.3"`; faked raise → `"prepared (live call failed)"` for `meds-kumar.png`; `ask_api.MEDICINES_LIVE` monkeypatched `False` → `"prepared"` and the fake is not called.
  - `test_medicine_strings_have_no_advice`: every row `why`, whole `why` and refusal detail produced above.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** Run `make_photos.py` once; do not commit the PNGs.
- [ ] **Step 4: Run** → PASS; `make test` → all pass (P2 photo tests after the `strips_from` extraction).
- [ ] **Step 5: Commit** `Count Guard v2 P4: medicine photo read and matched to the prescription by exact name, each named with its schedule`.

---

### Task 4: Doctor status (auto from theatre, hand-set wins until it expires) and the P4 story test (backend)

**Files:**
- Create: `count-guard/backend/app/journey/doctor_status.py`, `count-guard/backend/app/journey/staff_api.py`
- Modify: `count-guard/backend/app/journey/flow_api.py` (`move` writes the auto `doctor.status`), `count-guard/backend/app/journey/seed.py` (`seed_ward` creates the staff board), `count-guard/backend/app/journey/api.py` (`seed` returns the board), `count-guard/backend/app/journey/stories.py` (`plain`), `count-guard/backend/app/main.py` (register `staff_router`)
- Test: `count-guard/backend/tests/test_p4_status.py`, `count-guard/backend/tests/test_p4_story.py`

**Interfaces:**
- Consumes: Task 2 `short_name`; `procedures.tray_plan` (`expected_minutes`); `states.current_state`; `stories.clock`; `seed.DOCTOR`.
- Produces (`seed.py`): `BOARD_LABEL = "Ward staff board (synthetic)"`. `seed_ward(store, raise_nudges) -> {"patients": [...], "board": board_id}`; the board episode is created after the three patients. The `/journey/demo/seed` route returns that dict (its `patients` key is unchanged).
- Produces (`doctor_status.py`, pure):
  - `QUARTER = 15 * 60_000`; `free_about(ts_ms, minutes) -> int`: `ts + minutes·60 000`, rounded **up** to the next quarter hour. Theatre at Day 0 11:00 with 31 min → 11:45.
  - `theatre_payload(doctor, patient_label, ts_ms, minutes) -> {"doctor", "status": "in_theatre", "patient": short_name(label), "until_ms", "source": "auto"}`.
  - `current(doctor, episodes: list[list[dict]], board: list[dict], now_ms) -> {"doctor", "status", "text", "until_ms", "source", "patient"}`:
    1. Manual: the latest board `doctor.status` for `doctor` with `ts_ms ≤ now_ms`. If its status is `available` or `busy` and `now_ms < until_ms`, it wins. A manual `auto` clears it.
    2. Auto: among episodes in state `theatre`, the latest auto `doctor.status` for `doctor` written at or after the last move into theatre → `in_theatre`.
    3. Else `available`, source `auto`, `until_ms None`.
    - `text` (`hhmm` = `clock(ts)[-5:]`, doctor = `short_name(doctor)`):
      `"{doctor}: In theatre with {patient}, free about {hhmm}"`, `"{doctor}: Busy until {hhmm}"`, `"{doctor}: Available"`.
- Produces (`flow_api.move`): after `tray.planned` on a move to theatre, it appends
  `doctor.status theatre_payload(body.by, episode["label"], ts, tray_plan(procedure)["expected_minutes"])` at the same ts.
- Produces (`staff_api.py`): `staff_router = APIRouter(prefix="/journey/staff")`.
  - `GET /doctor?board=&ids=&at_ms=&doctor=`: `board` 1–64, `ids` comma-separated (1–10 ids, each 1–64; else 422),
    `at_ms` ≥ 0, `doctor` defaults to `seed.DOCTOR`. Unknown episode → 404. Returns `current(...)`.
  - `POST /doctor` `StatusIn(Strict){board, ids: list[str] 1–10, doctor = seed.DOCTOR, status: Literal["available","busy","auto"], until_ms: int | None, at_ms: int ≥ 0}`.
    `available`/`busy` need `at_ms < until_ms ≤ at_ms + 12 h`; `auto` needs `until_ms None`. Otherwise 422 (Review Focus 5).
    Writes `doctor.status {doctor, status, until_ms, source: "manual"}` on the board episode. Returns `current(...)` at `at_ms`.
- `plain`: `doctor.status` auto → `"{doctor short} is in theatre with {patient}, free about {hhmm}."`;
  manual → `"{doctor short} set the status: {Available | Busy until hhmm | automatic}."`.

- [ ] **Step 1: Write failing tests** in `test_p4_status.py` (P2-R3 guard; seeded ward):
  - `test_free_about_rounds_up`: 2 h + 31 min → Day 0 11:45; exactly 11:45 stays.
  - `test_chip_flips_when_kumar_enters_theatre`: before → `"Dr. A. Rao: Available"`; Kumar to theatre at 2 h → `"Dr. A. Rao: In theatre with R. Kumar, free about 11:45"`, `source "auto"`; back to ward → available.
  - `test_manual_busy_wins_until_it_expires` (Review Focus 5): Kumar in theatre at 2 h; busy until 2.5 h set at 2 h → `"Dr. A. Rao: Busy until 11:30"` at 2 h 29 min; at 2.5 h → in theatre again. `auto` clears a manual setting at once.
  - `test_status_refusals` (Review Focus 5): `until_ms` ≤ `at_ms`, > 12 h ahead, `auto` with `until_ms`, 11 ids, unknown board id → 422/404; nothing written.
  - `test_seed_returns_board`: three patients unchanged, a `board` id, the board's view state `clinic` with no events; `test_care_demo` seed tests still pass.
  - `test_status_strings_have_no_advice`: every `text` and `plain` produced above.
- [ ] **Step 2: Write failing** `test_p4_story.py::test_p4_done_when_without_a_key` (no key, prepared files only, explicit `at_ms`, `H = 3_600_000`, seeded ward):
  - Kumar: `rx/demo` in clinic → admit → ward → chip `Available` → Send to theatre (`hernia-repair`) at 2 h → chip `"…In theatre with R. Kumar, free about 11:45"` → surgery began and ended → Back to ward → discharge signed → home (`DISCHARGE_CHECKS`) at 1 day.
  - Kumar's four Ask actions at home: bot `"How do I care for the dressing?"` → found, sources include the wound-care line; a question to the doctor → answered by text; `wound-day3.png` review → `no_visit` → `"No visit needed"`; `meds-kumar.png` → three named with schedules and Cetirizine flagged.
  - Das: `rx/demo` → Close visit → bot `"When do I take amlodipine?"` → the amlodipine prescription line is the only source.
  - Iyer: discharge signed → home → `meds-iyer.png` → Ibuprofen flagged, the others named with schedules.
  - No `now_next`, `plain`, bot `answer`, medicine `why`, decision label or status `text` matches the advice regex.
- [ ] **Step 3: Run** both → FAIL. **Step 4: Implement.** **Step 5: Run** → PASS; `make test` → all pass.
- [ ] **Step 6: Commit** `Count Guard v2 P4: doctor status from theatre with hand-set override; P4 done-when story test`.

---

### Task 5: Patient view for any patient, the Ask page, My care fixes (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/ask.js`, `count-guard/frontend/src/care/ask.test.js`, `count-guard/frontend/src/care/Ask.jsx`, `count-guard/frontend/src/care/AskCards.jsx`
- Modify: `count-guard/frontend/src/care/ward.js` (`patientBed`, `setPatientBed`, key `cg-patient`), `count-guard/frontend/src/care/Patients.jsx` (`findPatient` replaces `findKumar`/`KUMAR_BED`), `count-guard/frontend/src/care/CareShell.jsx` (patient picker; `/ask` tab), `count-guard/frontend/src/App.jsx` (`/ask` route), `count-guard/frontend/src/care/Today.jsx`, `count-guard/frontend/src/care/MyCare.jsx`, `count-guard/frontend/src/care/Photos.jsx`, `count-guard/frontend/src/care/drafts.js` (+ `drafts.test.js`), `count-guard/frontend/src/care/tasklist.js` (+ `tasklist.test.js`)

**Interfaces:**
- Consumes: `view.ask` (Tasks 2–3), `view.photos`, `view.state`; `ward.act(id, path, body)`, `ward.upload(id, path, file, fields)`; `sourceLabel`.
- Produces (`ward.js`): `patientBed` (default `"4"`), `setPatientBed(bed)` stored in sessionStorage `cg-patient`.
- Produces (`Patients.jsx`): `findPatient(patients, bed) -> patient | undefined`. Today, My care and Ask use `findPatient(ward.patients, ward.patientBed)`.
- Produces (`CareShell.jsx`): for role patient, a `<select aria-label="Patient">` of the three patients by name (a demo lens, like the role switch). `PATIENT_TABS = [["/today","Today"],["/my-care","My care"],["/ask","Ask"]]`.
- Produces (`ask.js`):
  - `NOT_FOUND = "I can't find that in your record."` (same copy as the server), `ASK_DOCTOR = "Ask Dr. Rao"`, `PHOTO_STATES = ["clinic_done", "home"]`, `photoAskOpen(state) -> bool`.
  - `PHOTO_CLOSED = "Photos for the doctor open once the visit is closed or you are home."`
  - `botQuestions(view)`, `doctorQuestions(view)`: newest first. `latestReview(view)`, `latestMedicines(view)`.
  - `answerByLine(answer) -> string`: bot → `"Record bot · " + sourceLabel(answer.source)`; doctor → `"{by}, {via === "voice" ? "by voice" : "typed"}"`.
  - `medicineLine(row) -> string`: prescribed → `"{medicine}: {schedule}"`; else `row.why`.
  - `questionProblem(text) -> string`: `""`, `"Type a question."` or `"Keep the question under 300 characters."`.
- Produces (`drafts.js`): `photoPurposeLabel(purpose)`: proof "Proof", reference "Reference", healing "Healing photo", medicines "Medicines photo", other → "Photo". `Photos.jsx` uses it.
- Produces (`tasklist.js`): `TASK_STATUS_LABEL = {open: "To do", running: "Running", done: "Done", closed: "Stay ended"}`, `taskStatusLabel(status)` (unknown → the raw word).
- `Ask.jsx` (page, `PageLead` + `StateHeader`) renders from `AskCards.jsx`:
  - `BotCard`: textarea + "Ask the record". Shows each bot answer: the `answer`, the cited lines as a quoted list, `answerByLine`. When not found: `NOT_FOUND` and an `ASK_DOCTOR` button that copies the question into the doctor card (state lifted to `Ask.jsx`).
  - `DoctorCard`: textarea + "Send to Dr. Rao"; lists questions with "Waiting for Dr. Rao" or the answer and `answerByLine`.
  - `ReviewCard`: when `photoAskOpen`, a photo input "Send a healing photo" with an optional note; shows the latest review with its photo, "Waiting for Dr. Rao" or the decision label and note. Else `PHOTO_CLOSED`.
  - `MedicinesCard`: when `photoAskOpen`, a photo input "Photograph your medicines"; shows `medicineLine` per row (flagged rows amber `sun`), the whole `why` and `sourceLabel(source)`. Else `PHOTO_CLOSED`.
- `MyCare.jsx`: task pill uses `taskStatusLabel`; done-line key `${task.id}:${index}`; renders `<Photos view={view} />` (the patient now reaches reference and healing photos without a chart URL).

- [ ] **Step 1: Write failing node tests**: `ask.test.js` (`photoAskOpen` for each state; `botQuestions` order and filter; `answerByLine` for bot/doctor voice/typed; `medicineLine` both ways; `questionProblem` three cases; no string in the exported constants or helper outputs matches the advice regex); `drafts.test.js` `photoPurposeLabel`; `tasklist.test.js` `taskStatusLabel` including `closed` and an unknown word.
- [ ] **Step 2: Run** `node --test 'src/care/*.test.js'` → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P4: patient view for any patient; Ask page with the bot, the doctor, healing and medicine photos; My care fixes`.

---

### Task 6: Doctor side: Ask inbox on the chart, queue rows, status chip and "My status" (frontend)

**Files:**
- Create: `count-guard/frontend/src/care/AskInbox.jsx`, `count-guard/frontend/src/care/status.js`, `count-guard/frontend/src/care/status.test.js`
- Modify: `count-guard/frontend/src/care/derive.js` (+ `derive.test.js`), `count-guard/frontend/src/care/ward.js` (`board`, `doctorStatus`, `setDoctorStatus`; a saved roster without `board` reseeds), `count-guard/frontend/src/care/CareShell.jsx` (`DoctorChip` in the nav bar for every role), `count-guard/frontend/src/care/Queue.jsx` (doctor's "My status" buttons), `count-guard/frontend/src/care/Chart.jsx` (renders `AskInbox`), `count-guard/frontend/vite.config.js` (`/journey/staff` in `journeyApi`, as P2-R13)

**Interfaces:**
- Consumes: Task 4 `GET`/`POST /journey/staff/doctor`, `seed` `board`; Task 2 routes `/ask/hear`, `/questions/{id}/answer`, `/reviews/{id}/answer`; `view.ask`; `Dictate`; `ward.ask`.
- Produces (`status.js`):
  - `STATUS_CHOICES = [{id: "free1h", label: "Available for 1 h", status: "available", forMs: H}, {id: "busy30", label: "Busy for 30 min", status: "busy", forMs: 30 * M}, {id: "busy1h", label: "Busy for 1 h", status: "busy", forMs: H}, {id: "auto", label: "Back to automatic", status: "auto", forMs: null}]`.
  - `statusBody(choice, nowMs, board, ids) -> {board, ids, status, until_ms, at_ms}` (`until_ms` null for auto).
  - `statusQuery(board, ids, nowMs) -> string` (`/journey/staff/doctor?board=…&ids=a,b,c&at_ms=…`, URL-encoded).
  - `chipClass(status) -> "sun" | "info" | "ready"` (in_theatre/busy → sun, available → ready).
- Produces (`ward.js`): `board` from the roster; `doctorStatus` refreshed by `call(statusQuery(...))` whenever `patients` or `nowMs` change (errors leave the last status); `setDoctorStatus(choice)` posts `statusBody` and stores the reply.
- Produces (`derive.js`): `RANK.ask = 2`. Doctor rows per patient: each unanswered doctor question →
  `row(patient, "question:{id}", "ask", "Question from the patient", {...timed(nowMs, at_ms), lineId: id, owner: DOCTOR, role: "doctor", rank: RANK.ask})`;
  each unanswered review → the same with `"review:{id}"` and `"Healing photo to review"`. The question text never goes into a row.
  `rowsFor(..., "doctor")` drops a row whose `key` was already emitted (the P1 duplicate deferral).
- Produces (`AskInbox.jsx`): `AskInbox({ view, role, busy, act, ask })`, a chart card returning null when there are no questions or reviews.
  For role doctor, each open question (`data-line={id}`) shows its text, a textarea, and `Dictate` labelled "Answer by voice".
  Dictate's file → `ask("/ask/hear", file, {by: DOCTOR})` fills the textarea with the heard text and remembers `via "voice"`, `heard_by`; typed text fills it with `via "text"`.
  "Send answer" posts `/questions/{id}/answer` (D10: the doctor sees and can edit the text before it is saved).
  Each open review (`data-line={id}`) shows the healing photo beside the chart's reference photos (96 px), the note, an optional note field and three buttons "No visit needed", "Come in to the clinic", "The doctor will call you" posting `/reviews/{id}/answer`.
  Answered items show read-only for every role. Bot questions are not listed.
- `DoctorChip`: `<span className={`pill ${chipClass(status)}`}>{doctorStatus.text}</span>` in the nav bar; nothing until the first reply.
- `Queue.jsx`, role doctor: a "My status" row of `STATUS_CHOICES` buttons calling `ward.setDoctorStatus`.

- [ ] **Step 1: Write failing node tests**: `status.test.js` (`statusBody` for busy30 at 2 h → `until_ms` 2.5 h, auto → null; `statusQuery` encodes three ids; `chipClass` three cases; labels have no advice words); `derive.test.js` (an open doctor question and an open review give two doctor rows with rank `ask` and the fixed says texts; answered ones give none; bot questions give none; the question text is not in `JSON.stringify` of the rows; a nudge `{to: "doctor", kind: "obs_past_limit"}` yields exactly one doctor row; `waitingPills` shows `"Dr. A. Rao → Question from the patient"`).
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4:** node tests PASS, `npm run build` succeeds.
- [ ] **Step 5: Commit** `Count Guard v2 P4: doctor answers questions and reviews healing photos on the chart; doctor status chip and My status`.

---

### Task 7: Offline browser walk of the P4 done-when and the three patient beats, and fixes

**Files:**
- Create: `.superpowers/sdd/2026-10-30-count-guard-v2-p4-ask/p4-walk.md` (walk log, git-ignored), the walk script in the scratchpad (not committed)
- Modify: whatever the walk finds broken

**Interfaces:**
- Consumes: everything above on a separate offline server (P2-R15):
  `make dev MODEL_API_KEY= CG_API_PORT=8200 CG_WEB_PORT=5273 COUNT_GUARD_DATA=<scratchpad>/walk-data`.
  Check `curl -s 127.0.0.1:8200/journey/models` → `"live": false` before any step. Never touch 8100.
- First run `.venv/bin/python eval/p4/make_photos.py` and `.venv/bin/python eval/p2/make_media.py` (it now also speaks `rao-answer.wav`).
- Headless `playwright-core` from the scratchpad (the Playwright MCP browser may be locked). Files go in through `setInputFiles`.

- [ ] **Step 1:** Reset the ward. Walk the steps below, switching role and patient in the header. Log each step (role, patient, control, Now/Next, chip text, pass or fail):
  1. Doctor on Das: Use the demo prescription; check strips `Amlodipine 10 mg` (flag); Close visit. Patient role, pick A. Das, Ask: "When do I take amlodipine?" → "Here is what your record says." with the amlodipine prescription line quoted and "Rules (no model)". Ask "Can I drive?" → "I can't find that in your record." and the "Ask Dr. Rao" button fills the doctor card.
  2. Doctor on Kumar: demo prescription, admit, nurse completes admission. Chip reads "Dr. A. Rao: Available" on doctor, nurse and patient screens. Send to theatre → the chip reads "Dr. A. Rao: In theatre with R. Kumar, free about …" on every role. Doctor sets "Busy for 30 min" → "Busy until …"; skip ahead 30 min → back to "In theatre…". Surgery began, ended, Back to ward → "Available".
  3. Doctor signs Kumar's discharge; nurse completes it. Patient role, R. Kumar, Ask: bot "How do I care for the dressing?" → wound-care line; send a question to Dr. Rao; send `wound-day3.png` with note "Day 3"; photograph `meds-kumar.png` → three named with schedules, Cetirizine flagged amber.
  4. Doctor's queue: "Question from the patient" and "Healing photo to review", each once. Open → Ask inbox. Answer the question with `rao-answer.wav` through "Answer by voice" → the heard text appears editable → Send answer. Review: the healing photo shows beside any reference photo → "No visit needed". Patient: the answer and "No visit needed" show on Ask; My care shows the photos, status words "To do/Done/Stay ended" and no raw words.
  5. Iyer: doctor signs discharge, nurse completes it. Patient role, S. Iyer, Ask: `meds-iyer.png` → Ibuprofen flagged, three named with schedules.
- [ ] **Step 2:** Edge checks: Kumar on the ward (reset, or Das in clinic) → the photo cards show the closed note and no inputs; a GIF as a healing photo → the 400 detail; a second "No visit needed" from a stale tab → the 409 detail.
- [ ] **Step 3:** For each failure: fix it, add a test where the fault is in pure logic, and re-walk that step.
- [ ] **Step 4:** `make test`, the node tests and `npm run build` → all pass. Stop the walk servers.
- [ ] **Step 5: Commit** `Count Guard v2 P4: browser walk of the Ask section and doctor status; fixes`.

---

### Task 8 (owner request, 30 Oct; runs after Task 6 and BEFORE Task 7): Photos wherever a video check is offered

The owner asked: wherever video is needed, the user can also upload photos against the same action, so the demo continues when video is slow or unavailable. This also closes P3-R19 (photo at Begin of a start_end task) for set-up checks.

**Files:**
- Modify: `count-guard/backend/app/journey/video_api.py` (accept images on `POST /video`), `count-guard/backend/app/journey/live.py` (image seam), `count-guard/backend/app/adapters/sam.py` (only if an image helper is missing — `concept_request` already takes `image_data_url`), `count-guard/backend/app/journey/video.py` (summarize detections over photos), `count-guard/backend/app/journey/stories.py` (plain line wording "photo check" vs "video check")
- Modify: `count-guard/frontend/src/care/VideoCheck.jsx` (accept photos too), `count-guard/frontend/src/care/video.js` (`videoProblem` → accepts images; label text)
- Test: `count-guard/backend/tests/test_p4_photo_checks.py`, `count-guard/frontend/src/care/video.test.js`

**Interfaces:**
- `POST /journey/episodes/{id}/video` keeps its form (`check` tray|setup, `task_id` for setup, `by`, `at_ms`) and now takes either one video `file` (as today) or 1–6 image files (`files`, image/jpeg|png|webp, each ≤ 8 MB, magic bytes checked with the existing `media_api.MAGIC`/`read_upload_photo` rules). Exactly one of the two; else 422 "Send one video or 1 to 6 photos.". All existing refusals and their order are unchanged.
- Live (key set and `TRAY_LIVE`/`SETUP_LIVE` true): `live.segment_photos(settings, paths, concepts, filename, live_ok)` sends each image to SAM 3.1 via `concept_request(concept, image_data_url=...)` per concept; per concept the seen count is the max over photos (same rule as frames). Keyed failure → prepared fallback with source "prepared (live call failed)"; no prepared → "failed". No key or switch off → prepared by the first photo's file stem (`tray-hernia.jpg` → `tray-hernia` prepared result) via `live.prepared`, else source "none".
- The photos themselves are stored as the check's frames (`photo.added{purpose:"frame", task_id?}`) — no ffmpeg; `frame_ids` = the stored photo ids. The written `tray.checked` / `setup.checked` gains `media: "video" | "photos"`; everything else (rows, missing, match, why, source, clip) unchanged (`clip` = the first photo's safe stem).
- `plain()` says "Tray check by photos: …" / "Set-up check by photos: …" when `media == "photos"`.
- Frontend `VideoCheck`: the file input accepts `video/*,image/*` with `multiple`; `videoProblem(files)` returns null for one video or 1–6 images, else a plain message. Card label reads "Upload tray video or photos" / "Add video or photo check". Results show the same way (frames grid).
- Generated stand-in photos: extend `eval/p3/make_clips.py` (or a sibling script) to also write `tray-hernia.png`, `tray-hernia-full.png`, `saline-setup.png` (gitignored); prepared results already exist for those stems.

- [ ] **Step 1: Failing tests** in `test_p4_photo_checks.py` (network guard on): tray check with 2 photos offline → 200, `media "photos"`, `source "prepared"`, 2 frame ids served by `/photos/{id}`; setup check with 1 photo on Iyer's running/open saline task → `setup.checked` with `media "photos"`; video + photos together → 422; 7 photos → 422; a PNG with JPEG content type → 400; keyed live path with `concept_request` faked: per-concept max over photos; keyed failure → "prepared (live call failed)"; `TRAY_LIVE=False` with a key → prepared; existing P3 video tests stay green; plain lines have no advice words. Node: `videoProblem` accepts 1 video or 1–6 images, rejects mixes and 7 images.
- [ ] **Step 2: Run** → FAIL. **Step 3: Implement.** **Step 4: Run** `make test`, node tests, `npm run build` → PASS.
- [ ] **Step 5: Commit** `Count Guard v2 P4: photos accepted wherever a video check is offered`.

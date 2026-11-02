# One patient, two apps: Doctor Dictation → Count Guard flow (design)

Date: 2026-11-02 · Status: draft v4 (builder, product-owner, architect and judge reviews and the person asking's answers folded in) · Scope:
`doctor-dictation/` and `count-guard/`

## 1. Summary

A doctor dictates a clinic visit in **Doctor Dictation (DD)** and saves it. On Save, the doctor chooses
**Send home** or **Admit to ward**. An admitted patient appears in **Count Guard (CG)** with the
prescription already on the chart. From there the patient moves ward → theatre → ward → discharge. At
each step the nurse records vitals and checklists and adds photo proofs, which a real Muse model checks.
Every dictation goes through real Muse speech-to-text and structuring. The discharge ends in a real PDF.

At the same time, every feature that lives only in Count Guard's older screens moves into this one flow.
Then those screens are archived. **Nothing is lost.** Only then is the 3-minute hackathon video
recorded, so the video and the submitted code match.

```
DD clinic ──Save & admit──▶ CG intake ──▶ admitting ──▶ ward ⇄ theatre ──▶ discharging ──▶ home
   │                           ▲                                                    │
   └─Save & send home (§6.1)   CG "Sync" (backup pull) / CG "New patient"         discharge PDF + .ics
```

## 2. Why

- The judges must see one patient flow across two apps, not five generations of screens.
- The person asking said: "move all features into the new flow, nothing lost".
- They also said: "use real Muse calls with the key — create real artifacts — everything real".
- They chose to record **after** the features move, so the video and the submitted code cannot disagree.

## 3. Decisions made by the person asking (not open)

| # | Decision |
|---|---|
| U1 | The two apps stay separate: their own servers and their own databases. |
| U2 | Count Guard's older generations (camera counter, morning, journey v1) are archived. Every feature they hold moves into the care app first. |
| U3 | Admission starts in DD **on Save**. |
| U4 | Muse calls are real, using the key that is set. Artifacts (PDFs, transcripts, photo verdicts) are real. |
| U5 | Media are samples downloaded from the internet for now. |
| U6 | CG gets a **Sync** button as a backup pull from DD. CG can also **create a patient** directly. |
| U7 | The video is for hackathon judges and is 3 minutes long (`docs/hackathon/03-hackathon-spec.md:5`). |
| U8 | Order: move all features first, then record the video. |
| U9 | A photo proof that is **Not accepted** keeps the item open until a retake or an override with a typed, logged reason. This deliberately reverses the "flag, never block" rule (D9) in `journey/proof.py:1-3`, for proof photos only. |
| U10 | A camera or rules discrepancy is **advice only**. It must be acknowledged, but it never blocks ending surgery. The manual count through `count_gate` stays the only hard stop. Acknowledgement is UI only: ending surgery never checks it. |
| U11 | **Freeze on 3 Nov at 18:00 IST**, then record. A feature not moved by then stays reachable on its old screen, hidden from the menu, flagged in the plan. Nothing is deleted. U11 refines U8: the video is recorded at the freeze even if some "may slip" rows (§9) have not moved. |
| U12 | **Send home** produces only what DD does today: the prescription PDF and the share QR. Nothing goes to CG. |
| U13 | The three-act scripted play (CG-22) is retired to `archive/`, with `journey/play.py`. |
| U14 | Where no openly licensed clip exists, a prop clip recorded for the project is allowed and noted in `SOURCES.md`. |
| U15 | **No spend limit until 4 Nov**: use live models as much as needed for the best results. After 4 Nov a cap applies (figure to be set then). |
| U16 | The CG discharge report does **not** go back to DD now; after the hackathon. |

## 4. Goals, non-goals, anti-goals

**Goals** (each has a numbered acceptance check in §11)

1. A patient saved with **Admit to ward** in DD is on the CG ward list within 3 s, in `admitting`, with
   the DD prescription as `rx.ordered`.
2. CG **Sync** pulls every admitted DD patient the push missed. Two Syncs, or a push and a Sync racing,
   create exactly one patient.
3. CG **New patient** creates a patient in `clinic`, for walk-ins that never went through DD.
4. Every step from ward to home works in the care app ("Ward 4", `count-guard/frontend/src/care/`), with
   a real Muse call behind each AI step (§6.7).
5. Every row in the feature map (§9) has a named test that drives it from the care app.
6. `make demo-check` covers the whole flow across both apps and passes with no key.
7. A 3-minute video is recorded from the finished code.

**Non-goals.** Merging the apps or their databases. Production auth. Multi-clinic intake (§7.4). HL7 or
monitor integration. Mobile layout. New clinical rules beyond what the older generations already had.

**Anti-goals** (a failure even if it "works")

- Real patient data, or anything patient-like, sent to Meta APIs (`03-hackathon-spec.md:42`).
- A weaker swab hard stop. `count_gate` (`count-guard/backend/app/journey/states.py:95-110`, the 409 at
  `flow_api.py:73-75`) stays the only authority on ending surgery, with its code unchanged (§6.5).
- An AI verdict that silently blocks care. Every AI verdict can be overridden by a person with a logged reason.
- A prepared (fixture) result shown as if it were live. Every fallback is labelled "Prepared" on screen.
- A real upload that quietly receives a prepared answer. Today the live/prepared seam picks fixtures by
  file name (`journey/live.py:87-100`, overlap O8). With a live switch on, a real upload always goes to the model.
- A feature dropped without the person asking agreeing to it.

## 5. Current state (evidence)

- CG states and moves: `clinic → admitting | clinic_done`, `admitting → ward` (nurse, admission checks),
  `ward → theatre | discharging`, `theatre → ward`, `discharging → home` (`states.py:19-38`). Admit needs a
  reason (`states.py:142`). Send to theatre needs a procedure.
- **CG has no server-side ward list.** The care app keeps its roster in sessionStorage, filled from the seed
  response (`frontend/src/care/ward.js:30-52`). Beds exist only in that response (`journey/seed.py:43-46`).
  The `episodes` table holds only id, label and created_at (`morning/store.py:12-16`).
- **The demo clock lives in the browser** and is sent as `at_ms` on every action (`ward.js:147-150`).
  A new episode starts at 0 (`journey/api.py:138-142`).
- Every write goes through `settle()`, which runs nudges and the ops agent (`journey/api.py:153-161`).
- CG already reads a DD document: `fetch_document` and `from_document` (`journey/rx.py:83-113`). Only the
  older clinic panel calls it (`frontend/src/screens/ClinicPanel.jsx:51`).
- DD Save is `POST /api/v1/documents`, with the verify gate (409) (`doctor-dictation/doctor_dictation/api/persistence.py:198`,
  about 130 lines). A re-save keeps the same `document_id` and refreshes `finalized_at` (`persistence.py:305-312`).
  `persistence.py` is already 476 lines. DD stores `ageSex` and `opNo` as strings (`persistence.py:269-273`).
- DD single-clinic mode has no sign-in. `MULTI_CLINIC=1` gives each clinic its own database (`scope.py:48,57-60`).
- **"Morning" is mostly shared code, not dead code.** The care app and the ops agent import `morning.store`,
  `discharge`, `brownbag`, `druglog`, `lexicon`, `vitals`, `guide` and `strips`. Ops plans import
  `agent/verifier.py`. `morning/store.py:10` imports `app.store`. The camera rules need `core/ledger.py`,
  `engine.py` and `app/store.py`.
- Muse access: `META_API_KEY` is set. `MODEL_API_KEY` and `BASETEN_API_KEY` are empty, so Spark Open is
  unavailable. CG reads `MODEL_API_KEY`, then `META_API_KEY` (`count-guard/backend/app/config.py:89`).
- `make demo-check` starts only CG, on 8200/5273 (`count-guard/Makefile:44-49`).

## 6. The flow, by role

Roles in CG stay as they are: `doctor`, `nurse`, `patient`. Ward and theatre work are both done by the
`nurse` role, under the names on the seed (`NURSE`, `NURSE_THEATRE`, `journey/seed.py`). The chart shows
the name of whoever acted.

### 6.1 Clinic (DD, doctor)

1. The doctor dictates. The DD pipeline is unchanged: Muse STT (`STT_ENGINE=muse`), Muse Spark structuring
   (`LLM_PROVIDER=meta`), grounding, the verify gate.
2. Save offers **Save & send home** and **Save & admit to ward**. Admit asks for a one-line reason, which is required.
3. The save runs exactly as today, including the 409 gate. Only after the commit does DD push the admission (§7.1).
   A failed push never undoes or slows the save. DD shows "Saved. Not yet in Count Guard — use Sync there".
4. **Send home:** DD produces its prescription PDF and share QR as today. Nothing goes to CG (U12).

### 6.2 Arrival (CG, nurse)

- The patient appears on the ward list in `admitting`, with the DD prescription, diagnosis, admission reason,
  DD doctor, and a link to the DD PDF.
- The nurse completes admission. Each `ADMISSION_CHECKS` item has an expected photo (§6.6).
- The patient gets the lowest free bed number. The doctor can change it on the chart.

### 6.3 Ward (nurse, doctor, patient)

- **Nurse:** vitals against limits raise named alerts (CG-07). Tasks carry values and photo proofs (CG-06).
  The handover draft is a chart action (from journey v1). The dose record is a chart action (from journey v1 `/dose`).
- **Doctor:** dictates orders (CG-03) through Muse Voice Transcribe → Spark; signs. The ops agent acknowledges
  and assigns as today. "Photo of medicines from home" merges the brown-bag and strip-photo checks (CG-11, CG-23).
  **Send to theatre** asks for the procedure.
- **Patient:** Today, My care, Ask (record bot, ask the doctor, photo review, CG-13), medicines-from-home photo
  (CG-12), reminders and check-in (from journey v1), and the doctor-status chip (CG-15).
- The tray and saline set-up video checks (CG-09) run live with SAM 3.1.

### 6.4 Theatre (doctor, theatre nurse)

- Surgery steps, as today. Each step can carry a photo proof (§6.6).
- **Drug given** by push-to-talk: Muse STT → `druglog` parse → grounded row, confirm tap (from morning).
- **Vitals strip** from a scenario file, labelled "Simulated", and the **context card** behind the research
  banner and the tier toggle (from morning, CG-24).
- **Swab count:** the manual count, plus the camera assist (SAM 3.1 live) and the rules R1–R6 on its detections.
  A missing swab shows its **last frame as proof** (from morning `/count/frame`). A discrepancy gets a drafted
  explanation (the reconciler, CG-26). See §6.5 for what decides.
- **Count-sheet PDF** download (CG-27). The theatre nurse moves the patient **Back to ward**.

### 6.5 The hard stop (unchanged)

- `count_gate` decides, with its code unchanged. Only a person's closing counts. AI-written closings are
  ignored (`states.py:104`).
- Camera, rules R1–R6 and the reconciler write their own events with an AI `by`. They never write a
  `count.closing` that a person did not save.
- A camera or rules discrepancy is advice only (U10). It shows as an alert on the count panel that a person must acknowledge (with a reason if they disagree). It never blocks ending surgery.
- `states.py` is 462 lines, so new count logic goes in a new module.

### 6.6 Photo proofs at every step

Each check gets an expected-content line. Muse Spark 1.3 (vision) returns **Accepted** or **Not accepted**,
with a one-line reason. The verdict shows on the item and in the Inspector's Evidence tab.

| Step | Item | Expected photo |
|---|---|---|
| Admission | band, allergies, baseline_obs, consent | wristband with name; allergy label or "none known" card; monitor screen with readings; signed consent form |
| Ward tasks | per task template | e.g. "saline set-up with label visible" |
| Theatre | each surgery step | e.g. "swab tray before incision" |
| Discharge | card_given, medicines_handed, reminders_set | discharge card in hand; medicine bag with labels; phone showing the reminder |

**Not accepted** keeps the item open (U9). The nurse retakes the photo, or overrides with a typed reason. The override, the reason and the verdict are logged on the timeline. An admission or discharge move cannot complete while one of its items is open. **Ward-task and theatre proofs never block a move or `surgery.ended`**: they keep only their own task open, so U9 cannot reach the swab hard stop.

### 6.7 What counts as "real"

| Step | Model | Live switch | Switch off (demo-check) | Switch on, call fails |
|---|---|---|---|---|
| Dictation in DD and CG (orders, discharge) | Muse Voice Transcribe → Spark 1.3 | DD: `STT_ENGINE`/`LLM_PROVIDER`; CG: `VOICE_LIVE` (new) | prepared transcript, labelled | error, retry |
| Drug given (voice) | Muse Voice Transcribe | `VOICE_LIVE` | prepared, labelled | error, retry |
| Photo proof | Spark 1.3 vision | `PROOF_LIVE` (new) | prepared verdict, labelled | "Not checked — model unavailable": the item stays open; retake or override with a reason |
| Tray / set-up video | SAM 3.1 | `TRAY_LIVE`, `SETUP_LIVE` | prepared, labelled | prepared, labelled |
| Swab camera | SAM 3.1 | `SWABS_LIVE` | prepared, labelled | prepared, labelled; the manual count stands |
| Strip / home-medicine photo | Spark 1.3 vision | `MEDICINES_LIVE` | prepared, labelled | error |
| Handover wording, context card, discharge wording | Spark 1.3, with the wording check | `SPARK_LIVE` (new) | template text | template text, labelled |
| Patient Ask bot and photo review | Spark 1.3 | `SPARK_LIVE` | prepared, labelled | error |
| Discrepancy explanation | Spark 1.3 (Spark Open if `BASETEN_API_KEY` is set) | `SPARK_LIVE` | none | none; the rule rows still show |
| AI page "Try sample" | the model named | per model | prepared, labelled | error |

With a switch on, fixtures are never picked by file name (§4).

### 6.8 Discharge (doctor, nurse, patient)

- The doctor presses **Draft discharge**. The draft is assembled from the timeline: DD prescription, drugs
  given, count result, key events. This is the hackathon's success criterion (c) (`03-hackathon-spec.md:9`).
  The doctor may dictate changes (Muse STT → Spark), then signs (CG-14).
- The nurse completes `DISCHARGE_CHECKS`, with photo proofs.
- **Real artifacts:** the discharge PDF and an `.ics` follow-up file (from morning). The discharge card
  (journey v1 `/discharge-card`) goes to the patient view.

## 7. How the two apps talk

### 7.1 Push on admit (DD → CG)

- New DD module `doctor_dictation/api/admit.py`, because `persistence.py` is near the line limit. It runs
  after the commit, in a background task, with a 1 s connect and 3 s total timeout.
- New additive DD table, created with `CREATE TABLE IF NOT EXISTS`:
  `admissions(document_id PRIMARY KEY, status, reason, admitted_at, pushed_at, last_error)`, where `status` is `admit` or `send_home`. It feeds Sync and records failures.
- `POST {COUNT_GUARD_URL}/journey/intake`:

```json
{
  "source": "doctor-dictation",
  "document_id": 42,
  "admit_reason": "Inguinal hernia repair",
  "finalized_at": "2026-11-03T10:14:05",
  "document": { "...": "the same body as GET /api/v1/documents/42" }
}
```

- CG reads the name, `ageSex` and `opNo` from `document.structured`. It maps the prescription with the
  existing `from_document` (`rx.py:82`). It builds the PDF link from its own `DD_BASE_URL` (`config.py:103`),
  so the link follows whatever port DD is on.

### 7.2 Intake in CG (one code path for push, Sync and New patient)

- New CG module `journey/intake.py` and a new table `intake_keys(source, document_id, episode_id, finalized_at,
  PRIMARY KEY(source, document_id))`. The insert into it happens first, under the store lock. A duplicate key
  means "already here".
- A new patient gets a `patient.registered` event (bed, source, document_id), then `rx.ordered`, then the
  `clinic → admitting` move built by `states.move_payload` with `admit_reason` as the reason. Then `settle()`
  runs, so nudges and the ops agent see it.
- **Re-save:** if `finalized_at` changed, CG appends an `rx.ordered` that supersedes the old one, in any
  state before `home`, and the chart says "Prescription updated in Doctor Dictation". If nothing changed, Sync
  appends nothing.
- *(My call)* A re-save of an already admitted document as Send home sets `admissions.status='send_home'`,
  pushes, and Sync returns it. CG does not remove the patient. The chart shows "Doctor Dictation now says:
  send home", and the CG doctor decides. A document that was never admitted still sends nothing (U12).
- Event times use the server demo clock (§8).

### 7.3 Sync (CG pulls from DD)

- New DD route `GET /api/v1/admissions?since=<iso>` returns the same payloads as the push.
- The flow is CG browser → CG backend → DD, so the token never reaches a browser. Both hops are
  server-to-server, so CORS does not apply.
- The **Sync** button reports, for example, "2 new, 3 already here, 1 updated".

### 7.4 Configuration and auth

- DD: `COUNT_GUARD_URL` (new). CG: `DD_BASE_URL` (exists).
- A shared `CG_SYNC_TOKEN` header, checked by both sides when it is set. No secret values go into code, docs or logs.
- **Intake is single-clinic only** for now. With `MULTI_CLINIC=1`, the admissions route answers 404.

### 7.5 New patient in CG

A **New patient** form on the ward list takes name, age/sex and reason. The patient starts in `clinic` with no
prescription, through the same intake path (source `count-guard`). The CG doctor admits them with **Admit**.
In demo mode the name must end in "(synthetic)".

## 8. The ward list and the clock

- New `GET /journey/ward` lists patient episodes (not the staff board), with bed, state and source. It is built
  from `patient.registered` events. The seed writes the same event for its three patients.
- The care app loads its roster from this route, replacing the sessionStorage roster. It follows the kept SSE
  stream (§9) for changes, falls back to a 3 s refresh, and refreshes right after Sync.
- The demo clock moves to the server (`journey/clock.py`). The Demo dock's tick and reset call it. Actions still
  send `at_ms`. The server clamps it to its own clock: a value ahead of the server time is set to the server time, and a value behind the latest event on that episode is set to that event's time.
- The three seeded patients stay as the background ward. The video patient has a new synthetic name, so it does
  not clash with "R. Kumar" in bed 4.

## 9. Feature map: nothing lost

Built from the router and screen inventory (`frontend/src/App.jsx:177-194` and every backend router), not
from the feature IDs alone. Each row needs a named test that drives it from the care app.

Tier: **V** = on the video path, done first; **F** = before the freeze; **S** = may slip past the freeze
(stays on its old screen, hidden from the menu, per U11).

| Old place | Feature | New home in the care app | Tier |
|---|---|---|---|
| journey v1 `/rx/import` (CG-05) | Import a DD prescription | Intake (§7) | V |
| journey v1 `/strips` | Strip photo read | Doctor → Photo of medicines from home | V |
| journey v1 `/discharge-card` | Discharge card | Discharge step → patient view | V |
| journey v1 `/handover` (CG-20) | Nurse handover draft | Nurse chart → Handover | F |
| journey v1 `/reminders`, `.ics`, `/checkin`, `/help` (CG-21) | Reminders, check-in, help | Patient view | F |
| journey v1 `/dose` | Dose record | Nurse chart → Dose given | F |
| journey v1 `/audit` | Audit list | Inspector → History, plus the AI page | F |
| journey v1 `/play` (CG-22) | Three-act scripted play | Retired to `archive/` (U13) | — |
| morning `/episodes/{id}/play` (`morning/api.py:148`, `script.py`) | Morning scripted play | Retired with CG-22 *(my call, extending U13; same kind of scripted player)* | — |
| morning OPD (CG-23), `/brownbag/text` | Brown-bag photo and typed list | Doctor → Photo of medicines from home, with a typed fallback | V (photo), S (typed) |
| morning OT (CG-23) | Voice drug log, intent "hear" | Theatre → Drug given | V |
| morning OT (CG-23) | Simulated vitals | Theatre → vitals strip | V |
| morning `/card` (`morning/api.py:257`), `/tier` (CG-24) | Context card, decision tier | Theatre context card | V |
| morning `/count/frame`, `/count/manual` | Missing-swab frame as proof | Theatre count panel | V |
| morning `/count/from-case` | Link a camera case to the stay | Theatre swab camera | V |
| morning `/count/replay` | Replay of recorded detections | Theatre camera assist, labelled "Prepared" | F |
| morning `count_rules.py` | Bucket-dwell counter | Theatre camera assist | F |
| morning correction route | Event correction | Inspector → Correct (supersedes) | F |
| morning SSE stream (`morning/api.py:107`) | Live updates | Kept: the ward list and chart follow it in place of polling *(my call, so nothing is dropped)* | F |
| morning discharge PDF and `.ics` (CG-23) | Discharge artifacts | Discharge step | V |
| camera counter (CG-25) | Zones, rules R1–R6 | Theatre camera assist | V |
| camera counter (CG-28) | Real-video SAM pipeline and live socket | Theatre swab camera | V |
| camera counter `routes.py:152` | Manual resolve of a discrepancy | Theatre count panel → Resolve with reason | F |
| camera counter `/cases/{id}/close` (`routes.py:160`), CG-26, CG-27 | Close, discrepancy explanation, count-sheet PDF | Theatre count panel and download | F |
| camera counter `routes.py:220,228`, `/cases/{id}/events` (`:247`) | Frame, track and event viewer | Inspector → Evidence | S |
| `/guide` (CG-34) | Feature guide | Care app Help page | S |

Features already in the care app (CG-01 to CG-19) and the tools (CG-29 to CG-33) stay.

**Archiving.**
- A screen or route is archived only after every §9 row it serves has a passing test. Until then it stays
  mounted, unlinked from the menu, and the plan flags it (U11).
- Components the care app imports from `src/screens/` move into `src/care/` first: `AuditTable`
  (`care/History.jsx:3`), `CheckIn`, `MyCard`, `NeedHelp`, `Nudges`, `Reminders`, `Strips` (`care/Today.jsx:10-11`),
  `RxImport`, `RxTable` (`care/DoctorActions.jsx:2`).
- Then only screens and route files move to `count-guard/archive/`: the old React screens and the `/journey`,
  `/steps`, `/opd`, `/ot`, `/ward`, `/morning`, `/count`, `/case` routes; the route parts of `morning/api.py`
  (the SSE stream is kept, §9) and `morning/routes_extra.py`; `api/routes.py`, `api/ws.py`; and
  `journey/play.py` with its import and route (`journey/api.py:17`, `:401`).
- Everything imported by the care app or the ops agent stays in place: all of `morning/` except the route
  files, `core/`, `engine.py`, `app/store.py`, `agent/`, `adapters/`, `media_pipeline.py`, `report/`.
- The set to archive, backend and frontend, is computed from the import graph, not by hand. A7 proves it.

## 10. Sample media

- Downloaded from openly licensed sources (Wikimedia Commons, Pexels, Pixabay). Each file is listed in
  `count-guard/eval/media/SOURCES.md` with its URL, licence and author.
- No real faces, no real patients, no identifiable records.
- Where no openly licensed clip exists, a prop clip recorded for the project is allowed (U14).
- No spend limit until 4 Nov (U15): use clip lengths and repeat runs that give the best results. `make cost CLIP=…` still prints the cost of each run, so the spend is known when the cap comes in after 4 Nov.
- The untracked real clip in `count-guard/eval/p3/real/` is not committed.

## 11. Acceptance checks

| # | Check | How |
|---|---|---|
| A1 | DD admit → CG ward list within 3 s, in `admitting`, with `rx.ordered` | API test with both apps; demo-check beat |
| A2 | Push plus two Syncs → one patient; a changed `finalized_at` → one superseding `rx.ordered` | API test |
| A3 | With CG unreachable (a black-holed port), a DD save returns within 1 s and succeeds; Sync later brings the patient in | API test |
| A4 | New patient → `clinic`; Admit → `admitting` | API test |
| A5 | Every §9 row has a passing named test that drives it from the care app | test list in the plan |
| A6 | An AI-written, camera-written or rules-written closing never makes `count_gate` return `"ok"`, through intake, Sync, New patient and the theatre panel. An unacknowledged camera discrepancy plus a valid manual closing ends surgery with 200. An open theatre proof never blocks `surgery.ended` | adversarial tests |
| A7 | With `archive/` excluded: `app.main` imports, the backend suite passes, `vite build` succeeds and the frontend tests pass | test |
| A8 | `make demo-check` passes with no key. CG runs on 8200/5273 and DD on 8300, never 8100/5173/8000 | make target |
| A9 | `make live-check` makes one real call per model in §6.7 and saves its artifacts in `count-guard/eval/live/<date>/` | make target, run by hand |
| A10 | No file over 500 lines; no secret in code, docs or logs | scan |

`demo-check` changes: it starts DD on 8300 with prepared STT and language-model results, sets `DD_BASE_URL`
and `COUNT_GUARD_URL`, and runs the new beats. The beat count and timings change, and the plan updates
`beats.test.mjs` to the new numbers.

## 12. The video (after §9 is done)

3 minutes, for hackathon judges, recorded from the finished code with every live switch on. Scenes are
recorded separately and spliced. The screen shows "synthetic data" and "research demo" throughout
(`03-hackathon-spec.md:109`). It hits the three judging criteria (`03-hackathon-spec.md:8-9`).

| Time | Scene |
|---|---|
| 0:00–0:10 | Title: one synthetic patient, two apps |
| 0:10–0:40 | DD: dictate → Save & admit to ward |
| 0:40–1:05 | Ward: the patient arrives; the wristband photo is Accepted, then a wrong photo is Not accepted |
| 1:05–2:05 | Theatre: drug by voice; the BP falls and the **context card** appears; the swab camera; one swab is missing, shown with its **last frame**; the hard stop |
| 2:05–2:45 | Discharge: **Draft discharge** fills itself from the timeline; sign; the PDF opens with the drug log and the count |
| 2:45–3:00 | Close: "The system formats. The doctor decides." |

The script goes in `docs/demo/`, next to the current one.

## 13. Risks

| Risk | Mitigation |
|---|---|
| The submission is due on 4 Nov, and the Meta credits must be claimed before 4 Nov 9 PM ET (`count-guard/docs/loop/backlog.md:122`) | Freeze on 3 Nov 18:00 IST (U11); the plan does tier V, then F, then S (§9); the person asking claims the credits |
| Live models are slow or fail on camera | Re-shoot the scene; labelled fallbacks |
| Moving camera and rules code next to `count_gate` | `count_gate` unchanged, A6, the whole-branch review |
| Archiving breaks imports | Import-graph archive set, A7 |
| Licence of downloaded media | `SOURCES.md`; open licences only |

## 14. Left to the builder

The exact DD Save UI, bed renumbering, the layout of new chart actions, the vitals scenario file format,
the PDF layout and the expected-photo wording. All of these must stay within the constraints above, with
files under 500 lines.

## 15. Open questions

None. Q1–Q8 were answered as U9–U16 (§3).

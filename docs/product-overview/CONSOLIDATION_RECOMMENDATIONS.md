# Consolidation Recommendations

> Snapshot of `main` @ `90e0f56`, generated 2026-11-02. Companion to [index.html](index.html) — same data, same numbers.

## Summary

13 findings, first assessed at e40d8c7 and re-checked at 90e0f56 after the 2 Nov consolidation: **3 resolved, 3 partly resolved, 7 open.** This overview changed no code.

- **Resolved:** the five-generation app is now one care app plus `count-guard/archive/` (O1); only `count_gate` can end surgery, the other counters are advice (O4); old and new UIs no longer share records (O9).
- **Biggest open issue:** the platform kernel still hides under legacy names — `morning/` (event store, intake keys, clock) and the camera counter's `core/`, `engine.py`, `report/`, now imported by the theatre (O2, O10).
- **Second:** the ops agent still runs inside every write, now including DD intake (O3).
- **Cross-app duplication:** medicine knowledge, PDF rendering and voice capture (O5–O7); one discharge path now, two PDF engines.

### Recommended product boundaries

| Boundary | Contents | Today |
| --- | --- | --- |
| Doctor Dictation | OPD dictation → prescription, records, tenancy, clinic learning, admit | doctor-dictation/ (already separate) |
| Count Guard Care | Intake/Sync, ward, theatre, swab hard stop, photo verdicts, discharge, Ask, Inspector, AI admin | count-guard/backend/app/journey + ops, frontend/src/care (the only UI) |
| Care platform | Ledger (episodes, events, supersede, intake keys, clock), perception (adapters, switches, camera libs), advice verifier, async ops runner | Spread across morning/, journey/, adapters/, agent/, core/ |
| Showcase | Demo dock, seed, prepared fixtures, demo-check, live-check, eval | Mixed into journey/ and care/ |
| Archive | Camera swab counter, morning timeline, journey v1 screens and routes | Done 2 Nov: count-guard/archive/ |

**Decision needed:** after the submission, approve *extract the ledger and perception kernel (O2, O10) → move the ops agent off the request path (O3)*, or keep everything as-is.

## Findings at a glance

| # | Finding | Severity | Recommendation | State at 90e0f56 |
| --- | --- | --- | --- | --- |
| O1 | Five product generations in one Count Guard app | High | Archive | Resolved |
| O2 | One store and one 'morning' package serve as the platform kernel | High | Extract shared | Open |
| O3 | journey/api.py is a hub, and every write runs the ops agent | High | Separate | Open |
| O4 | Swab count implemented three times | Medium | Archive | Resolved |
| O5 | Medicine knowledge duplicated across apps | Medium | Extract shared | Open |
| O6 | Three PDF engines and three discharge paths | Medium | Extract shared | Partly resolved |
| O7 | Voice dictation in both apps | Medium | Keep together | Open |
| O8 | Demo code inside product paths | Medium | Separate | Partly resolved |
| O9 | Old and new UIs write to the same patient records | Medium | Archive | Resolved |
| O10 | Advice verifier and reconciler live in the legacy agent/ folder | Low | Extract shared | Open |
| O11 | Doctor Dictation's Save is a hub for side effects | Low | Separate | Partly resolved |
| O12 | Doctor Dictation: three learning stores, two modes forked per route | Low | Separate | Open |
| O13 | Docs describe things that are no longer true | Low | Archive | Open |

## O1 · Five product generations in one Count Guard app

**Severity:** High · **Recommendation:** Archive · **State:** Resolved

1. **What is combined:** Was: camera counter (A), morning timeline (B), journey v1 (C), care app (D), ops agent (E) in one app with 24 React routes. Now: every feature of A–C moved into the care app (spec §9, each row with a named test) and 44 screen/route/test files sit in count-guard/archive/, unmounted. main.py mounts 26 care routers; App.jsx has care routes only.
2. **Where:** `count-guard/backend/app/main.py:58-84`, `count-guard/frontend/src/App.jsx:34-44`, `count-guard/archive/`, `count-guard/scripts/archive_set.py`
3. **Why it confuses:** Resolved for viewers: there is one product on screen. What remains is that the legacy camera libraries (core/, engine.py, report/, scenarios.py) are now dependencies of the theatre camera, not archive.
4. **Logical separation:** Done: archive moved with git mv, computed from the import graph (archive_set.py), pinned by test_archive.py. Next: treat core/, engine.py and report/ as platform code (see O2).
5. **Keep together or separate:** Archive
6. **Target shape:** `count-guard/ (care) · count-guard/archive/ (A, B, C screens and routes)`

## O2 · One store and one 'morning' package serve as the platform kernel

**Severity:** High · **Recommendation:** Extract shared · **State:** Open

1. **What is combined:** MorningStore (morning.db) is the persistence for journey and ops and now also holds episode_beds, intake_keys and the server clock. The theatre reuses morning/ druglog, intents, vitals, pdf, ics and count_rules; the camera reuses core/, engine.py, scenarios.py and report/.
2. **Where:** `count-guard/backend/app/morning/store.py:13-39`, `count-guard/backend/app/journey/theatre.py:1-4`, `count-guard/backend/app/journey/camera_api.py:20-27`
3. **Why it confuses:** The legacy names ('morning', the camera counter's core/) hide the platform kernel. Archiving them would break the current product, which is why the consolidation kept them in place.
4. **Logical separation:** Extract a 'ledger' kernel (episodes, events, supersede, visibility, intake keys, clock) and a 'perception' package (adapters, switches, tracker, rules). Give non-patient records (staff board, ops site) their own kind.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `count-guard/backend/app/ledger/ · perception/`

## O3 · journey/api.py is a hub, and every write runs the ops agent

**Severity:** High · **Recommendation:** Separate · **State:** Open

1. **What is combined:** journey/api.py exports _store, _act, _require, _at, settle and view to every other router — now 20+ modules, including intake, camera and theatre. settle() raises nudges and runs the ops agent synchronously inside the user's request; errors are logged and swallowed.
2. **Where:** `count-guard/backend/app/journey/api.py:153-161`, `count-guard/backend/app/journey/camera_api.py:23`
3. **Why it confuses:** Agent latency and bugs sit on the clinician's request path, and now also on the DD push path (intake runs settle()).
4. **Logical separation:** Split into a write service, an event-driven side-effect runner (outbox or background task for ops) and a read-model module.
5. **Keep together or separate:** Separate
6. **Target shape:** `journey/write.py · journey/view.py · ops runs after commit`

## O4 · Swab count implemented three times

**Severity:** Medium · **Recommendation:** Archive · **State:** Resolved

1. **What is combined:** core/rules.py R1–R6 and morning/count_rules.py bucket-dwell still exist, but both now feed advice rows only (camera.* events). journey count_gate is the single rule that can end surgery.
2. **Where:** `count-guard/backend/app/journey/advice.py:1-5`, `count-guard/backend/app/journey/camera_extras.py:1-6`, `count-guard/backend/app/journey/states.py:95-109`
3. **Why it confuses:** Resolved by role, not by deletion: the semantics no longer compete. test_count_gate_paths.py and test_route_sweep.py prove camera, rules, replay and close never make the gate 'ok'.
4. **Logical separation:** Keep count_gate as the only gate; keep the two counters as advice inside perception.
5. **Keep together or separate:** Archive
6. **Target shape:** `journey/count (gate) · perception (advice)`

## O5 · Medicine knowledge duplicated across apps

**Severity:** Medium · **Recommendation:** Extract shared · **State:** Open

1. **What is combined:** Doctor Dictation ships a 448-entry lexicon with LASA and grounding. Count Guard keeps its own map (morning/lexicon.py) and now uses it for theatre drug lines and medicines from home.
2. **Where:** `doctor-dictation/doctor_dictation/core/lexicon/`, `count-guard/backend/app/morning/lexicon.py`, `count-guard/backend/app/journey/home_medicines.py`, `count-guard/backend/app/morning/druglog.py`
3. **Why it confuses:** The DD prescription now flows into CG, so two sources of drug truth sit on one chart.
4. **Logical separation:** Expose DD's lexicon as a read-only medicines service or package; CG consumes it.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `shared 'medicines' package or DD API`

## O6 · Three PDF engines and three discharge paths

**Severity:** Medium · **Recommendation:** Extract shared · **State:** Partly resolved

1. **What is combined:** Discharge paths are now one: Draft discharge → sign → discharge PDF + .ics (the v1 discharge card shows in the patient view). PDF engines are still two: DD pooled Chromium; CG fpdf (morning/pdf.py for discharge, report/count_sheet.py for the camera).
2. **Where:** `count-guard/backend/app/journey/discharge_api.py:13-17`, `doctor-dictation/doctor_dictation/pdf/renderer.py`, `count-guard/backend/app/report/count_sheet.py`
3. **Why it confuses:** A patient now receives a DD prescription PDF and a CG discharge PDF with a different look and script support.
4. **Logical separation:** One document renderer.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `shared renderer`

## O7 · Voice dictation in both apps

**Severity:** Medium · **Recommendation:** Keep together · **State:** Open

1. **What is combined:** DD is a whole dictation product (STT chain, hints, corrections). CG has journey/dictation.py + live.transcribe for orders, discharge, tasks and theatre drugs (Muse Voice only, VOICE_LIVE).
2. **Where:** `doctor-dictation/doctor_dictation/api/stt.py`, `count-guard/backend/app/journey/dictation.py`, `count-guard/backend/app/journey/live.py:121`
3. **Why it confuses:** Same capability, two implementations, different models.
4. **Logical separation:** Acceptable for a hackathon. For a product, CG should call a shared speech service; keep the domain parsers separate.
5. **Keep together or separate:** Keep together
6. **Target shape:** `shared speech service (later)`

## O8 · Demo code inside product paths

**Severity:** Medium · **Recommendation:** Separate · **State:** Partly resolved

1. **What is combined:** Improved: every AI step has a live switch; prepared results are labelled; photo verdicts and medicine photos are chosen by bytes, not file name; with a switch on, file names never pick a fixture. Still: tray, set-up and swab fixtures are picked by uploaded file name when the switch is off; DemoDock, rx/demo and ai/try stay in the product; DD keeps seed-demo and stub providers in production code.
2. **Where:** `count-guard/backend/app/journey/live.py:94-98`, `count-guard/backend/app/journey/switches.py:1-6`, `doctor-dictation/doctor_dictation/admin.py:234`
3. **Why it confuses:** A real upload named like a fixture (e.g. tray-hernia.mp4) still gets a hand-made answer when the switch is off — though now labelled 'Prepared'.
4. **Logical separation:** One explicit DEMO flag per app; mount demo routers only when on; match the remaining fixtures by content hash.
5. **Keep together or separate:** Separate
6. **Target shape:** `demo/ package + flag`

## O9 · Old and new UIs write to the same patient records

**Severity:** Medium · **Recommendation:** Archive · **State:** Resolved

1. **What is combined:** The old screens and their routes are archived; the remaining v1 write routes (dose, handover, reminders, check-in) are called from the care app itself.
2. **Where:** `count-guard/archive/frontend/src/screens/`, `count-guard/backend/tests/test_count_gate_paths.py:163`
3. **Why it confuses:** Resolved: test_archived_morning_count_routes_cannot_touch_a_care_theatre_stay pins it.
4. **Logical separation:** Done.
5. **Keep together or separate:** Archive
6. **Target shape:** `archive`

## O10 · Advice verifier and reconciler live in the legacy agent/ folder

**Severity:** Low · **Recommendation:** Extract shared · **State:** Open

1. **What is combined:** agent/verifier.py is used by ops/plan.py and journey/handover.py; agent/reconciler.py (the camera counter's narrative) is now used by the theatre camera close.
2. **Where:** `count-guard/backend/app/agent/verifier.py`, `count-guard/backend/app/journey/handover.py:15`, `count-guard/backend/app/journey/camera_explain.py:18`
3. **Why it confuses:** agent/ is now wholly current code under a legacy-looking name.
4. **Logical separation:** Move both to the platform kernel.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `platform/verifier · perception/explain`

## O11 · Doctor Dictation's Save is a hub for side effects

**Severity:** Low · **Recommendation:** Separate · **State:** Partly resolved

1. **What is combined:** The admit side effect went into its own module (api/admit.py, called after the commit). persistence.py is still 484 lines with legacy CRUD, Today, Save (verify gate, PDF, share, formulary/investigation/spoken learning) and PDF serving.
2. **Where:** `doctor-dictation/doctor_dictation/api/persistence.py:360-361`, `doctor-dictation/doctor_dictation/api/admit.py:101`
3. **Why it confuses:** Any learning change still touches the Save path, which is 16 lines from the repo's 500-line limit.
4. **Logical separation:** Save → document service + post-save hooks (admit is the first such hook); move the prompt to core/.
5. **Keep together or separate:** Separate
6. **Target shape:** `services/ layer`

## O12 · Doctor Dictation: three learning stores, two modes forked per route

**Severity:** Low · **Recommendation:** Separate · **State:** Open

1. **What is combined:** clinic_formulary, clinic_overlay and spoken_terms all learn on Save. Single vs multi-clinic is checked per route — the new admissions routes add two more forks (404 in multi-clinic).
2. **Where:** `doctor-dictation/doctor_dictation/db/migrations/`, `doctor-dictation/doctor_dictation/api/admit.py:147,163`
3. **Why it confuses:** Hard to explain which store made a name 'verified'. Mode forks are easy to miss in new routes.
4. **Logical separation:** One 'clinic knowledge' module with a documented precedence. Decide the mode at one seam.
5. **Keep together or separate:** Separate
6. **Target shape:** `core/knowledge`

## O13 · Docs describe things that are no longer true

**Severity:** Low · **Recommendation:** Archive · **State:** Open

1. **What is combined:** docs/hackathon/README.md still says 'Nothing is built yet'. (count-guard/README.md 'Submission notes' are now correct: they report the 2 Nov live-check, line 239.)
2. **Where:** `docs/hackathon/README.md:3`, `count-guard/README.md:239`
3. **Why it confuses:** New readers and judges start from the most stale document.
4. **Logical separation:** Mark docs/hackathon 01–06 superseded.
5. **Keep together or separate:** Archive
6. **Target shape:** `docs/hackathon/ARCHIVE`

## Gaps found during the assessment

| Priority | Type | Gap | Evidence |
| --- | --- | --- | --- |
| P1 | Validation | No Count Guard model output has been measured on real media. Live calls work (live-check 2 Nov: voice, Spark text, Spark vision, SAM all answered), but live SAM found 0 swabs on the drawn demo media, and the demo default is prepared results. | `count-guard/backend/app/live_check.py:1-6; docs/demo/dd-cg-flow-video-script.md (The swab camera)` |
| P1 | Missing | DD safety data is absent or unreviewed: dosing.json is empty, investigations.json is missing, and the 8 LASA pairs and 448-entry lexicon are not clinician-reviewed. | `doctor-dictation/doctor_dictation/core/lexicon/` |
| P1 | Security | Count Guard has no user authentication; actor and role are client-supplied. POST …/theatre/tier toggles decision content without auth. Resolved 2 Nov: with CG_SYNC_TOKEN unset, POST /journey/intake now accepts loopback callers only (403 otherwise). | `count-guard/backend/app/journey/intake_api.py:66-80; theatre_api.py:164` |
| P1 | Security | DD single-clinic mode (the default) has no auth and CORS '*'. Safe on localhost only. Resolved 2 Nov: with CG_SYNC_TOKEN unset, GET /api/v1/admissions now answers loopback callers only (403 otherwise). | `doctor-dictation/doctor_dictation/api/admit.py:182-191; api/app.py:81-87` |
| P2 | Architecture | The CG discharge does not go back to DD (deferred, U16). Resolved 2 Nov: the DD → CG push now retries a connection error or 5xx up to 3 attempts (0.5 s, 1.5 s backoff); after that, Sync recovers it. | `doctor-dictation/doctor_dictation/api/admit.py:127-162` |
| P2 | Security | DD verify gate trusts the client-supplied row status on Save; rows are not re-grounded server-side. | `doctor-dictation/doctor_dictation/api/persistence.py:223-245` |
| P2 | Architecture | Ops agent runs synchronously in every care write, including intake; failures are swallowed. No queue, no retry, no metrics. | `count-guard/backend/app/journey/api.py:153-161` |
| P2 | Architecture | Process-local state breaks with >1 worker: DD format cache, share-link rate limiter, login semaphore. | `doctor-dictation/doctor_dictation/core/determinism.py:61; api/share_public.py:29-30` |
| P2 | Incomplete | Browser Web Speech fallback is promised in an error message but not implemented. | `doctor-dictation/doctor_dictation/providers/stt/factory.py:116` |
| P2 | Incomplete | Spark baseline scoring raises NotImplementedError (the only TODO in the repo). | `count-guard/backend/app/baseline.py:66-67` |
| P2 | Missing | Consent capture and data retention are not implemented (encounters.consent_at column only), yet a live pilot is claimed. | `doctor-dictation/doctor_dictation/db/__init__.py:208` |
| P3 | Docs | docs/hackathon/README.md still says 'Nothing is built yet'. Resolved 2 Nov: count-guard/README.md 'Submission notes' now report the 2 Nov live-check timings and the DD → CG video script. | `count-guard/README.md:235-243; docs/hackathon/README.md:3` |
| P3 | Docs | count-guard/docs/architecture.md covers only the camera counter; the care app, intake/Sync and ops agent have no architecture doc (the 2 Nov spec is the nearest). | `count-guard/docs/architecture.md` |
| P3 | Docs | Resolved 2 Nov: .env.example now lists COUNT_GUARD_URL, DD_BASE_URL, CG_SYNC_TOKEN, DEMO_BANNER, VOICE_LIVE, PROOF_LIVE, SPARK_LIVE and CG_OPS_AGENT (MODEL_API_KEY was already described); doctor-dictation/.env.production.example lists COUNT_GUARD_URL and CG_SYNC_TOKEN. | `.env.example; count-guard/backend/app/journey/switches.py:1-6; doctor-dictation/doctor_dictation/api/admit.py:7` |
| P3 | Architecture | Count Guard has no deployment assets; the DD → CG link assumes both apps on one machine (COUNT_GUARD_URL default 127.0.0.1:8100). | `doctor-dictation/doctor_dictation/api/admit.py:30` |
| P3 | Validation | No DOM/component tests for the Count Guard UI; end-to-end coverage is the two-app demo-check only. | `count-guard/frontend/scripts/demo/` |
| P3 | Architecture | doctor-dictation/frontend/app.js is 1,406 lines, breaking the repo's 500-line rule; persistence.py is at 484. | `doctor-dictation/frontend/app.js` |

## Areas requiring human validation

- Is the live camera good enough to film? Live SAM found 0 swabs on drawn media; the video script recommends a filmed prop tray (spec U14). Confirm before recording.
- Should CG_SYNC_TOKEN be set for every demo? /journey/intake and /api/v1/admissions accept loopback only when no token is set (any process on the machine) and refuse other hosts with 403.
- Is the Doctor Dictation pilot at the documented domain live with real patients? If so, consent, retention and the default-mode exposure need review — and Save & admit must stay off there (it is single-clinic only).
- Which repo is canonical for Doctor Dictation deploys: this monorepo or the upstream that 02-deploy.sh clones?
- Do the default model names resolve with live vendors for DD (default 'gpt-6-luna')? The CG Meta models answered on 2 Nov.
- Is the clinician-review status of the lexicon and LASA pairs acceptable for showing 'safety checks' to customers?
- Freeze rule U11 (3 Nov 18:00 IST): confirm that no §9 row slipped — every row has a named test, but slip status at the freeze is not recorded in the repo.
- eval/p3/real/ holds an untracked real surgical clip — confirm source and licence before any public push.
- Is the 'assistant' role in Doctor Dictation meant to have fewer rights than a doctor?

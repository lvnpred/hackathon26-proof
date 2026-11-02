# Consolidation Recommendations

> Snapshot of `main` @ `e40d8c7`, generated 2026-11-01. Companion to [index.html](index.html) — same data, same numbers.

## Summary

13 findings. This is an assessment only: **nothing was moved, renamed or refactored.**

- **Biggest issue:** `count-guard/` bundles five product generations in one backend and one frontend (O1). The current product depends on the "legacy" `morning` package for its event store (O2), so the first move must be to extract that store, before anything is archived.
- **Second issue:** the ops agent runs inside every clinician write (O3).
- **Cross-app duplication:** the two apps duplicate medicine knowledge, PDF rendering and voice capture (O5–O7).

### Recommended product boundaries

| Boundary | Contents | Today |
| --- | --- | --- |
| Doctor Dictation | OPD dictation → prescription, records, tenancy, clinic learning | doctor-dictation/ (already separate) |
| Count Guard Care | Patient flow, orders/tasks, swab hard stop, checks, alerts, Ask, discharge, Inspector, AI admin | count-guard/backend/app/journey + ops, frontend/src/care |
| Care platform | Ledger (episodes, events, supersede), perception seam + adapters, advice verifier, async ops runner | Spread across morning/, journey/, adapters/, agent/ |
| Showcase | Demo dock, seed, prepared fixtures, demo-check, eval | Mixed into journey/ and care/ |
| Archive | Camera swab counter, morning timeline, journey v1 screens and routes | Mounted and routed today |

**Decision needed:** approve the order *extract the ledger kernel (O2) → move the ops agent off the request path (O3) → flag-gate the archive (O1)*, or keep everything as-is for the hackathon submission.

## Findings at a glance

| # | Finding | Severity | Recommendation |
| --- | --- | --- | --- |
| O1 | Five product generations in one Count Guard app | High | Archive |
| O2 | One store and one 'morning' package serve three generations | High | Extract shared |
| O3 | journey/api.py is a hub, and every write runs the ops agent | High | Separate |
| O4 | Swab count implemented three times | Medium | Archive |
| O5 | Medicine knowledge duplicated across apps | Medium | Extract shared |
| O6 | Three PDF engines and three discharge paths | Medium | Extract shared |
| O7 | Voice dictation in both apps | Medium | Keep together |
| O8 | Demo code inside product paths | Medium | Separate |
| O9 | Old and new UIs write to the same patient records | Medium | Archive |
| O10 | Advice verifier born in the legacy counter, used by the current product | Low | Extract shared |
| O11 | Doctor Dictation's Save is a hub for side effects | Low | Separate |
| O12 | Doctor Dictation: three learning stores, two modes forked per route | Low | Separate |
| O13 | Docs describe a product that was never built | Low | Archive |

## O1 · Five product generations in one Count Guard app

**Severity:** High · **Recommendation:** Archive

1. **What is combined:** Camera swab counter (A), morning timeline (B), care journey v1 (C), care app (D), ops agent (E), plus a demo layer — one FastAPI app with 18 routers and one React router with 24 routes.
2. **Where:** `count-guard/backend/app/main.py:31-69`, `count-guard/frontend/src/App.jsx:170-195`, `count-guard/frontend/src/care/older.js`
3. **Why it confuses:** A viewer cannot tell which screen is 'the product'. The README still presents the camera rules and models of A as current.
4. **Logical separation:** Care app D + ops agent E are the product. A, B and C are archive: move them behind a feature flag or into a separate 'count-guard-archive' app.
5. **Keep together or separate:** Archive
6. **Target shape:** `count-guard/ (care) · count-guard-archive/ (A, B, C)`

## O2 · One store and one 'morning' package serve three generations

**Severity:** High · **Recommendation:** Extract shared

1. **What is combined:** MorningStore (morning.db) is the persistence for morning, journey and ops. Its episodes table holds patients, the staff board and the ops 'site' episode. morning.discharge.visible_events is imported by journey and ops in about 13 places.
2. **Where:** `count-guard/backend/app/morning/store.py:12-41`, `count-guard/backend/app/morning/discharge.py`, `count-guard/backend/app/ops/site.py`
3. **Why it confuses:** The legacy package name hides the platform kernel. Archiving 'morning' would break the current product.
4. **Logical separation:** Extract a 'ledger' kernel (episodes, events, supersede, visibility, clock text). Give non-patient records (staff board, ops site) their own table or kind.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `count-guard/backend/app/ledger/`

## O3 · journey/api.py is a hub, and every write runs the ops agent

**Severity:** High · **Recommendation:** Separate

1. **What is combined:** journey/api.py exports _store, _act, _require, settle and view to every other router. settle() raises nudges and runs the ops agent synchronously inside the user's request. view() recomputes the whole patient on every call.
2. **Where:** `count-guard/backend/app/journey/api.py:137-206`
3. **Why it confuses:** Agent latency and bugs sit on the clinician's request path (errors are swallowed and logged). One module owns writes, side effects and the read model.
4. **Logical separation:** Split into a write service, an event-driven side-effect runner (outbox or background task for ops) and a read-model module.
5. **Keep together or separate:** Separate
6. **Target shape:** `journey/write.py · journey/view.py · ops runs after commit`

## O4 · Swab count implemented three times

**Severity:** Medium · **Recommendation:** Archive

1. **What is combined:** core/rules.py R1–R6 on tracked detections; morning/count_rules.py bucket-dwell count; journey count_api + states.count_gate typed closing gate (+ swab camera read).
2. **Where:** `count-guard/backend/app/core/rules.py`, `count-guard/backend/app/morning/count_rules.py`, `count-guard/backend/app/journey/count_api.py`
3. **Why it confuses:** Three counting semantics; only the third is the safety gate shown in the product.
4. **Logical separation:** Keep count_gate as the single rule. Archive the other two with their generations.
5. **Keep together or separate:** Archive
6. **Target shape:** `journey/count (only)`

## O5 · Medicine knowledge duplicated across apps

**Severity:** Medium · **Recommendation:** Extract shared

1. **What is combined:** Doctor Dictation ships a 448-entry lexicon with LASA and grounding. Count Guard has its own hand-written ~20-drug map plus strip, brown-bag, drug-log and medicines modules (some duplicated inside CG).
2. **Where:** `doctor-dictation/doctor_dictation/core/lexicon/`, `count-guard/backend/app/morning/lexicon.py`, `count-guard/backend/app/morning/brownbag.py`, `count-guard/backend/app/journey/medicines.py`
3. **Why it confuses:** The original plan (docs/hackathon/01 §3.2) was to reuse DD's lexicon. Two sources of drug truth will disagree.
4. **Logical separation:** Expose DD's lexicon as a read-only medicines service or package; CG consumes it.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `shared 'medicines' package or DD API`

## O6 · Three PDF engines and three discharge paths

**Severity:** Medium · **Recommendation:** Extract shared

1. **What is combined:** DD renders with pooled headless Chromium; CG uses fpdf twice (morning/pdf.py, report/count_sheet.py). Discharge exists as morning/discharge.py, v1 discharge-card and v2 dictate/sign.
2. **Where:** `doctor-dictation/doctor_dictation/pdf/renderer.py`, `count-guard/backend/app/morning/pdf.py`, `count-guard/backend/app/report/count_sheet.py`
3. **Why it confuses:** Different look, fonts and Indic script support across documents a patient receives.
4. **Logical separation:** One document renderer. Keep only the v2 discharge flow in the care app.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `shared renderer`

## O7 · Voice dictation in both apps

**Severity:** Medium · **Recommendation:** Keep together

1. **What is combined:** DD is a whole dictation product (STT chain, hints, corrections). CG has journey/dictation.py + live.transcribe for orders, discharge and tasks.
2. **Where:** `doctor-dictation/doctor_dictation/api/stt.py`, `count-guard/backend/app/journey/dictation.py`, `count-guard/backend/app/journey/live.py:122`
3. **Why it confuses:** Same capability, two implementations, different models (DD: OpenAI/Groq/AssemblyAI/Muse; CG: Muse only).
4. **Logical separation:** Acceptable for a hackathon. For a product, CG should call a shared speech service; keep the domain parsers separate.
5. **Keep together or separate:** Keep together
6. **Target shape:** `shared speech service (later)`

## O8 · Demo code inside product paths

**Severity:** Medium · **Recommendation:** Separate

1. **What is combined:** CG: DemoDock in the care shell, rx/demo and ai/try routes, and the live/prepared seam choosing fixtures by uploaded file name. DD: seed-demo in the production CLI, stub providers in the production registry, a demo-phrase detector in the rules fallback.
2. **Where:** `count-guard/backend/app/journey/live.py:87-100`, `count-guard/backend/app/journey/ai_api.py:96`, `doctor-dictation/doctor_dictation/admin.py:234`, `doctor-dictation/doctor_dictation/core/fallback.py:54`
3. **Why it confuses:** In CG, a real upload whose name matches a fixture (e.g. tray-hernia.mp4) silently gets a hand-made answer. All are env-gated, but the gates differ per app.
4. **Logical separation:** One explicit DEMO flag per app; mount demo routers only when on; match fixtures by content hash, not file name.
5. **Keep together or separate:** Separate
6. **Target shape:** `demo/ package + flag`

## O9 · Old and new UIs write to the same patient records

**Severity:** Medium · **Recommendation:** Archive

1. **What is combined:** src/screens (v1 Doctor/Nurse/Patient/Audit) and src/care (v2) both act on the same episodes; v1 routes (/dose, /obs, /orders) write event kinds the v2 flow may not expect.
2. **Where:** `count-guard/frontend/src/screens/`, `count-guard/backend/app/journey/api.py:247-401`
3. **Why it confuses:** Using an old screen during a demo can put a patient in a state the care app does not show correctly (unverified).
4. **Logical separation:** Make legacy screens read-only or point them at a separate episode set.
5. **Keep together or separate:** Archive
6. **Target shape:** `archive`

## O10 · Advice verifier born in the legacy counter, used by the current product

**Severity:** Low · **Recommendation:** Extract shared

1. **What is combined:** agent/verifier.py was written for the camera counter's narrative; ops/plan.py and journey/handover.py now depend on it.
2. **Where:** `count-guard/backend/app/agent/verifier.py`, `count-guard/backend/app/ops/plan.py:8`, `count-guard/backend/app/journey/handover.py:15`
3. **Why it confuses:** Archiving agent/ would break the ops agent.
4. **Logical separation:** Move the verifier to the platform kernel.
5. **Keep together or separate:** Extract shared
6. **Target shape:** `platform/verifier`

## O11 · Doctor Dictation's Save is a hub for side effects

**Severity:** Low · **Recommendation:** Separate

1. **What is combined:** api/persistence.py (476 lines) holds legacy CRUD, the Today query, Save (verify gate, PDF, share link, formulary learning, investigation memory, spoken-term learning) and PDF serving. api/format.py holds the system prompt, the agent loop, caching and correction.
2. **Where:** `doctor-dictation/doctor_dictation/api/persistence.py`, `doctor-dictation/doctor_dictation/api/format.py:49-75`
3. **Why it confuses:** Any learning change touches the Save path. Prompt text lives inside HTTP code.
4. **Logical separation:** Save → document service + post-save learning hooks; move the prompt to core/.
5. **Keep together or separate:** Separate
6. **Target shape:** `services/ layer`

## O12 · Doctor Dictation: three learning stores, two modes forked per route

**Severity:** Low · **Recommendation:** Separate

1. **What is combined:** clinic_formulary, clinic_overlay (source learned) and spoken_terms all learn on Save. Single vs multi-clinic behaviour is checked in about 15 routes.
2. **Where:** `doctor-dictation/doctor_dictation/db/migrations/`, `doctor-dictation/doctor_dictation/scope.py:47-48`
3. **Why it confuses:** Hard to explain which store made a name 'verified'. Mode forks are easy to miss in new routes.
4. **Logical separation:** One 'clinic knowledge' module with a documented precedence. Decide the mode at one seam (dependency), not per route.
5. **Keep together or separate:** Separate
6. **Target shape:** `core/knowledge`

## O13 · Docs describe a product that was never built

**Severity:** Low · **Recommendation:** Archive

1. **What is combined:** docs/hackathon/01–06 describe a doctor_dictation/hx/ timeline with ports, SSE and timeline_events inside DD; the code went another way (decisions D1, J1).
2. **Where:** `docs/hackathon/02-architecture.md`, `docs/hackathon/README.md:3,60`
3. **Why it confuses:** New readers start from the most stale document.
4. **Logical separation:** Mark 01–06 superseded; point to this overview and the Count Guard README.
5. **Keep together or separate:** Archive
6. **Target shape:** `docs/hackathon/ARCHIVE`

## Gaps found during the assessment

| Priority | Type | Gap | Evidence |
| --- | --- | --- | --- |
| P1 | Validation | No Count Guard model output is real: every SAM, Voice and Spark result in the demo is a hand-made fixture. No real tray or theatre clip has been measured. | `count-guard/README.md:281-288` |
| P1 | Missing | DD safety data is absent or unreviewed: dosing.json is empty, investigations.json is missing, and the 8 LASA pairs and 448-entry lexicon are not clinician-reviewed. | `doctor-dictation/doctor_dictation/core/lexicon/` |
| P1 | Security | Count Guard has no authentication; actor and role are client-supplied. POST /morning/tier toggles decision content without auth. | `count-guard/backend/app/morning/api.py:78-81` |
| P1 | Security | DD single-clinic mode (the default) has no auth and CORS '*'; /docs and /api/health are public. Safe on localhost only. | `doctor-dictation/doctor_dictation/api/app.py:81-87` |
| P2 | Security | DD verify gate trusts the client-supplied row status on Save; rows are not re-grounded server-side. | `doctor-dictation/doctor_dictation/api/persistence.py:223-245` |
| P2 | Architecture | Ops agent runs synchronously in every care write; failures are swallowed. No queue, no retry, no metrics. | `count-guard/backend/app/journey/api.py:153-163` |
| P2 | Architecture | Process-local state breaks with >1 worker: DD format cache, share-link rate limiter, login semaphore. | `doctor-dictation/doctor_dictation/core/determinism.py:61; api/share_public.py:29-30` |
| P2 | Incomplete | Browser Web Speech fallback is promised in an error message but not implemented. | `doctor-dictation/doctor_dictation/providers/stt/factory.py:116` |
| P2 | Incomplete | Spark baseline scoring raises NotImplementedError (the only TODO in the repo). | `count-guard/backend/app/baseline.py:66-67` |
| P2 | Missing | Consent capture and data retention are not implemented (encounters.consent_at column only), yet a live pilot is claimed. | `doctor-dictation/doctor_dictation/db/__init__.py:208` |
| P3 | Docs | docs/hackathon/01–06 describe an unbuilt hx/ architecture with no 'superseded' marker; README says 'Nothing is built yet'. | `docs/hackathon/README.md:3` |
| P3 | Docs | count-guard/docs/architecture.md covers only the legacy camera counter; the care app and ops agent have no architecture doc. | `count-guard/docs/architecture.md` |
| P3 | Docs | doctor-dictation/README.md references moved files (pdf.py, stt_onnx.py), lexicon v1.1.0/444 (actual v1.4.0/448) and Windows ARM paths. | `doctor-dictation/README.md` |
| P3 | Docs | .env.example misses names the code reads: CG_OPS_AGENT, DD_BASE_URL, MODEL_API_KEY, PUBLIC_BASE_URL, DATE_LOCALE, META_BASE_URL/META_MODEL, GROQ_LLM_MODEL, LLM_SEED, TEMPLATE_*. | `.env.example; count-guard/backend/app/config.py:89,103,106` |
| P3 | Architecture | Count Guard has no deployment assets (container, proxy, env template for production). | `count-guard/` |
| P3 | Validation | No DOM/component tests for the Count Guard UI; end-to-end coverage is the demo-check only. | `count-guard/frontend/src/care/*.test.js` |
| P3 | Architecture | doctor-dictation/frontend/app.js is 1,404 lines, breaking the repo's 500-line rule. | `doctor-dictation/frontend/app.js` |

## Areas requiring human validation

- Were any Count Guard models ever called live? README:281 says never; docs/hackathon/07-care-journey.md:35 records a live Spark 1.3 check on 28 Oct, and some commits mention live Voice fixes.
- Is the Doctor Dictation pilot at the documented domain live with real patients? If so, consent, retention and the default-mode exposure need review.
- Which repo is canonical for Doctor Dictation deploys: this monorepo or the upstream that 02-deploy.sh clones? DD history in this repo starts at the 28 Oct import.
- Should the camera counter (A) still be part of the pitch? The Count Guard README 'Models' and 'Camera-count rules' sections present it as current.
- Do the default model names resolve with live vendors (DD default 'gpt-6-luna'; Meta endpoint marked 'not yet verified')?
- Is the clinician-review status of the lexicon and LASA pairs acceptable for showing 'safety checks' to customers?
- Is it safe to keep v1 journey endpoints writing to the same episodes as the v2 care app?
- eval/p3/real/ holds an untracked real surgical clip — confirm source and licence before any public push.
- Is the 'assistant' role in Doctor Dictation meant to have fewer rights than a doctor?

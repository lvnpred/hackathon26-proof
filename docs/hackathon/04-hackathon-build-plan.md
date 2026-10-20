# 04 — Hackathon build plan (subagent-driven, 7 days)

## 1. Summary

One human orchestrator plus subagents. Day 1 freezes the contracts (`02` §3–4) and builds the skeleton.
Days 2–6 run **parallel lanes** whose files never overlap. Day 7 films. Pure rule cores are test-first and
get a reviewer subagent; adapters and UI get only a smoke check by the orchestrator.

Total effort: about **65 task-hours** (§4: Day 1 8 h, Days 2–3 23 h, Days 4–5 18.5 h, Day 6 9 h,
Day 7 6.5 h). Days 2–5 run up to three lanes at once, so wall-clock fits 7 days at ~8–9 h; the orchestrator's
own time goes on gates, smoke tests and the demo.

## 2. How the orchestration works

```
           ┌─────────────── orchestrator (you + main Claude session) ───────────────┐
           │ owns: contracts, hooks outside hx/, day gates, demo                     │
           └───┬──────────────┬──────────────┬──────────────┬──────────────┬─────────┘
   task card → │ implementer  │ implementer  │ implementer  │ implementer  │  (one subagent per task)
               │ L1 count     │ L2 druglog   │ L3 vitals    │ L4 UI        │
               └──────┬───────┴──────┬───────┴──────┬───────┴──────┬───────┘
                      ▼              ▼              ▼              ▼
              reviewer subagent (rule cores only): spec match → test quality → code
                      ▼
              orchestrator smoke test → tick the task card → next card
```

Rules for every lane:

1. **Disjoint files.** Each task card lists the only files it may create or edit. A lane never edits
   another lane's file. `hx/api.py` only includes per-lane routers (`hx/api_count.py`, …), created empty
   on Day 1, so no two agents edit one router.
2. **Same working tree, no commits by agents.** `CLAUDE.md` forbids commits without explicit approval.
   Lanes therefore share the `hackathon` working tree and stay out of each other's files. If you approve
   commits for this branch (decision D6 below), switch to one git worktree per lane and merge at day gates.
3. **Tests offline.** No test calls Meta, OpenAI or Groq. Tests use the `replay` and `sim` adapters and the
   existing stub LLM (`providers/llm/stub.py`).
4. **Never the real DB.** Every agent runs with `DB_PATH=$(mktemp -d)/hx.db`. Single mode otherwise
   writes the dev database.
5. **Test command:** `DB_PATH=$(mktemp -d)/hx.db .venv/bin/python -m pytest tests/hx -q`, then the full
   suite `tests/ -q` once per day gate to prove the hooks broke nothing.

## 3. Day 0 spikes (21–25 Oct, before the build window)

Throwaway experiments. If the rules forbid pre-window code, keep only the findings, not the code.

| # | Spike | Pass when | If it fails |
|---|---|---|---|
| S1 | SAM 3.1 tracking on 60 s of tray footage with hands passing over | ≥ 90% of swabs keep one track ID through a 1–2 s occlusion; measure s/frame via API | Use replay only; record footage now and run SAM offline (Colab GPU, open weights) |
| S2 | `LLM_PROVIDER=meta` with Muse Spark | One `complete_json` call returns valid JSON through `OpenAICompatLlm` | Word the card with `groq`; note it |
| S3 | Muse STT on the five drug-log phrases + "opening twenty swabs" | Drug names grounded after `correct_drugs` in ≥ 4/5 | Add lexicon hints; else `openai` STT |
| S4 | Read the hackathon rules | Pre-existing code, video length, API-use rules, deadline time zone known | Re-scope per README D1 |
| S5 | Buy props, record demo footage drafts (tray, bucket, strips) | Top-down shot with even light | — |

## 4. Task cards

Estimate = focused hours including review. Review: **R** = reviewer subagent; **S** = orchestrator smoke.

### Day 1 — Foundation (sequential, orchestrator-led)

| ID | Task | Files | Est | Review |
|---|---|---|---|---|
| T1 | Ports and dataclasses: `Detection`, `Frame`, `VitalReading`, `Clock`, `VisionPort`, `VitalsPort` | `hx/ports.py`, `tests/hx/test_ports.py` | 1.5 | R |
| T2 | Migration + store: append, supersede, list by episode, fold helper, in-process bus | `db/migrations/011_timeline.sql`, `hx/store.py`, `tests/hx/test_store.py` | 3 | R |
| T3 | API skeleton: mount behind `HACKATHON=1`, empty per-lane routers, episode create, SSE stream | `api/app.py` (hook), `hx/api.py`, `hx/api_*.py`, `tests/hx/test_stream.py` | 2.5 | S |
| T4 | Fixture formats: `one_morning.json` scenario, `detections_demo.jsonl`, demo patient seed | `hx/scenarios/*`, `hx/seed.py` | 1 | S |

**Gate 1:** full suite green; `curl` an SSE stream and see a test event.

### Days 2–3 — Lanes L1, L2, L4 in parallel

| ID | Lane | Task | Files | Est | Review |
|---|---|---|---|---|---|
| T5 | L1 | Count ledger: zones, `DWELL`, pack opened, closing reconcile, last-seen (test-first) | `hx/rules/count.py`, `tests/hx/test_count.py` | 3 | R |
| T6 | L1 | `vision_replay` adapter, time-synced to the episode clock | `hx/vision_replay.py`, test | 1.5 | S |
| T7 | L1 | `vision_sam` adapter (only if S1 passed) | `hx/vision_sam.py` | 2.5 | S |
| T8 | L1 | Routes: `POST /api/hx/count/frames`, `/count/pack`, `/count/manual`, `/count/close` | `hx/api_count.py`, test | 2 | S |
| T10 | L2 | Drug-log parser: amount, unit, strength, route; grounding via `core/drugnames.py` (test-first) | `hx/rules/druglog.py`, `tests/hx/test_druglog.py`, `tests/hx/druglog_phrases.json` | 3 | R |
| T11 | L2 | Route: audio → existing STT factory → parse → `druglog.given`; confirm route | `hx/api_druglog.py`, test | 2 | S |
| T13 | L2 | Voice intent "opening N swabs" → `count.pack_opened` (reuses T10 number parsing) | `hx/rules/intents.py`, test | 1 | R |
| T19 | L4 | `ot.html` 3-panel layout, SSE client, timeline feed, research banner slot | `frontend/hx/ot.html`, `ot.css`, `timeline.js` | 3 | S |
| T9 | L4 | Count panel: camera capture at 2 fps, IN/OUT counters, closing card with frame | `frontend/hx/count.js` | 3 | S |
| T12 | L4 | Push-to-talk button + drug rows with confirm tap | `frontend/hx/druglog.js` | 2 | S |

**Gate 2 (end Day 3):** demo scenes 2 and 3 (setup, drug) and the count close run end to end in replay.

### Days 4–5 — Lane L3 (vitals) and L5 (discharge)

| ID | Lane | Task | Files | Est | Review |
|---|---|---|---|---|---|
| T14 | L3 | `vitals_sim` adapter: plays the scenario on the clock; start/pause/seek control route | `hx/vitals_sim.py`, `hx/api_vitals.py` | 2 | S |
| T15 | L3 | Trend rules + cooldown (test-first, fake clock) | `hx/rules/trend.py`, `tests/hx/test_trend.py` | 2.5 | R |
| T16 | L3 | Context collector + template card + wording check (test-first) | `hx/rules/context.py`, `tests/hx/test_context.py` | 3 | R |
| T17 | L3 | Card pipeline: rule fires → template card event → LLM reword with timeout → replace if check passes; mounted only with `DECISION_TIER=1` | `hx/api_vitals.py`, test | 2 | R |
| T18 | L4 | Vitals strip (SVG sparkline), card component, banner | `frontend/hx/vitals.js`, `card.js` | 3 | S |
| T20 | L5 | Discharge fold (test-first; decision events excluded) | `hx/rules/discharge.py`, test | 2 | R |
| T21 | L5 | Discharge HTML via `pdf/sections.py` + renderer; route + button | `hx/discharge_render.py`, `hx/api_discharge.py`, `frontend/hx/discharge.js` | 3 | S |
| T22 | L5 | `.ics` export of follow-up dates (stdlib only) | `hx/ics.py`, test | 1 | S |

**Gate 3 (end Day 5):** the full OT scene and discharge run end to end; card visible < 500 ms.

### Day 6 — Could-have, hardening, rehearsal

| ID | Task | Files | Est | Review |
|---|---|---|---|---|
| T23 | Brown-bag: photo → `make_llm(vision=True)` reads strips → ground → class map → events | `hx/rules/brownbag.py`, `hx/classes.json`, `hx/api_brownbag.py` | 3 | R |
| T24 | Brown-bag page | `frontend/hx/brownbag.html`, `brownbag.js` | 2 | S |
| T25 | Duplicate flag (decision tier, gated) | `hx/rules/brownbag.py` | 1 | R |
| T26 | Rehearse the demo script 3× from a clean DB; fix only what breaks the script | any `hx/` file | 3 | S |

Cut order if Day 6 is short: T25 → T24/T23 → LLM wording (template only).

### Day 7 — Film and submit

| ID | Task | Est |
|---|---|---|
| T27 | Film the scenes; edit to ≤ 3:00; captions; banners visible | 5 |
| T28 | Submission notes (`03` §8), run instructions, live-vs-replay statement | 1.5 |

Buffer: 2–4 Nov for re-shoots and the submission form.

## 5. Implementer prompt template

Paste one task card into this template. Keep each prompt self-contained: the subagent has no chat history.

```text
You implement task {ID} of the hackathon build on branch `hackathon` in
/Users/narenlingala/Documents/workspace/work/Zebra/doctor-dic/doctor-dictation-main.

Read first: docs/hackathon/02-architecture.md sections {§}, and docs/hackathon/03-hackathon-spec.md §5.{n}.
Contracts in 02 §3–4 are frozen. If the task needs a contract change, stop and report it; do not change it.

Task: {one paragraph from the card}
You may create or edit ONLY: {file list}. Do not touch any other file.
Done when: {acceptance bullets from 03 §5}.

Rules:
- Test-first for anything under hx/rules/: write the failing test, run it, then the code.
- hx/rules/ is pure: no sqlite3, fastapi, httpx, os.getenv, time.time(); take `now` as an argument.
- Files stay under 500 lines. Match the style of doctor_dictation/core/vitals.py.
- Tests are offline. Run: DB_PATH=$(mktemp -d)/hx.db .venv/bin/python -m pytest tests/hx -q
- Do not commit. Do not edit .env.
Report: files changed, test output (last 5 lines), anything you were unsure about.
```

## 6. Reviewer prompt template (rule cores only)

```text
Review task {ID}. Files: {list}. Spec: docs/hackathon/02-architecture.md §{n}, 03-hackathon-spec.md §5.{n}.
Check in order: (1) does it do what the spec says, nothing more; (2) do the tests prove the acceptance
bullets, including the edge case {named edge case}; (3) purity and file-size rules; (4) obvious bugs.
Report only real problems, each with file:line and a failing input. No style nits.
```

## 7. Orchestrator daily loop

1. Morning: pick today's cards; dispatch independent lanes in one message so they run in parallel.
2. On each report: run the lane's tests yourself; for **R** cards dispatch the reviewer; fix-forward once,
   then cut scope rather than loop.
3. Evening gate: full suite, run today's demo scenes, update the checklist in this file.

## 8. Decision D6

Agents may not commit (`CLAUDE.md`). Option A (default): shared tree, disjoint files, you commit once per
gate. Option B: you authorise commits on `hackathon` for the build week; lanes then use worktrees.

# OPD → OT → Discharge: one patient timeline (hackathon extension)

**Status:** draft spec, 2026-10-21. Branch `hackathon` (cut from `main` at 7aeec9b). Nothing is built yet.

## One-page summary

Doctor Dictation already turns a spoken visit into a checked prescription (`README.md`). This extension grows
it into **one patient timeline** that runs from the outpatient clinic (OPD), through the operating theatre
(OT), to discharge. Each new feature is a **module that writes events onto that timeline**. No fork.

```
              ONE PATIENT TIMELINE  (OPD visit → procedure → discharge)
  ┌──────────┬─────────────┬─────────────┬──────────┬───────────┬────────────┐
  │ Rx       │ Brown-bag   │ Count Guard │ Drug log │ Vitals    │ Discharge  │
  │ dictation│ med list    │ swab ledger │ (voice)  │ context   │ draft      │
  │ (exists) │ (OPD)       │ (OT)        │ (OT)     │ card (OT) │            │
  └──────────┴─────────────┴─────────────┴──────────┴───────────┴────────────┘
inputs   mic ────► speech port  (existing SttProvider: muse | openai | groq | …)
         camera ─► vision port  (NEW: SAM 3.1 API | replay file | local weights later)
         monitor ► vitals port  (NEW: simulated scenario | HL7 feed later)
core     rules decide what happened ─► LLM phrases it ─► existing Chromium PDF prints it
```

The value is that modules feed each other. Example: the OPD medicine review finds metoprolol (a
beta-blocker). In the OT the blood pressure falls but the heart rate does not rise. The context card shows
"on metoprolol (OPD medicine review)" beside the drop. No single module can make that connection.

**The line we hold:** *the system formats; it never decides.* Most modules stay on the documentation side.
The vitals context card and the "same drug twice" flag cross into the **decision tier**. Those ship behind a
switch that is off by default and carry a "Research demo — not for clinical use" banner.

## Two specs, two speeds

| | Hackathon build | Product build |
|---|---|---|
| Goal | A 3-minute demo video, "One patient, one morning" | A safe, maintainable product for real clinics |
| Time | 7 build days (26 Oct – 1 Nov) + 3 buffer days to the 4 Nov deadline | ~6–9 months for all modules; documentation tier first |
| Data | Synthetic patient and props only | Real patient data, local-first, audited |
| Standards | "Hackathon lite": contracts frozen, core rules tested, UI untested | Full standards in `06-engineering-standards.md` |
| Code home | `doctor_dictation/hx/`, `frontend/hx/` (isolated, mounted only when `HACKATHON=1`) | Ported module by module into `core/`, `api/`, `providers/` |

## Documents in this folder

| File | Read it for | Applies to |
|---|---|---|
| `01-product-and-modules.md` | What each module does, the timeline idea, regulation tiers, corrections to the original brief | Both |
| `02-architecture.md` | Ports and adapters, the timeline event contract, data flow, real-time path, tier switch | Both (deltas marked) |
| `03-hackathon-spec.md` | Hackathon scope, demo script, shortcuts allowed, acceptance checks | Hackathon |
| `04-hackathon-build-plan.md` | Day-by-day plan, subagent lanes, task cards, agent prompt template | Hackathon |
| `05-product-spec.md` | Product scope, phases, time to build, what to keep or rewrite from the hackathon | Product |
| `06-engineering-standards.md` | Coding, testing, safety, security and review standards for the product build | Product |
| `07-care-journey.md` | **Current demo.** Doctor, nurse and patient stories; the nudge rule; option A; build-now cut; three-act script | Hackathon |

## Decisions needed before Day 1 (26 Oct)

Closed on 27 Oct 2026 by Vignan: D1 and D4. The rest are still open.

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| D1 | Do the hackathon rules allow pre-existing code? | **Closed.** Count Guard is the new repo at `../count-guard`. Do not put it under `hx/` and do not reuse Doctor Dictation code. The 27 Oct build spec governs. | The submission history has to start in that repo. |
| D2 | Is SAM 3.1 reachable through the Meta Model API, and at what frame rate? | Day 0 spike (`04` task S1). Fall back to a recorded-detections replay | Count Guard is the "Must" module and depends on it |
| D3 | Whose screen is the OT view? | Anaesthetist for the vitals card; circulating nurse for Count Guard; one shared timeline screen for the demo | Sets what the card shows and how loud it is |
| D4 | Commit the uncommitted provider work (Muse, Groq, AssemblyAI STT) first? | **Closed.** Do not commit or port that provider work into Count Guard. The new repo has its own adapters. | The old speech stack stays in Doctor Dictation. |
| D5 | Hackathon solo or with teammates? | Plan assumes one human plus subagents | Changes lane count in `04` |
| D6 | May agents commit on `hackathon` during the build week? | No (default): shared tree, disjoint files, you commit at each day gate | `CLAUDE.md` forbids unapproved commits; worktree-per-lane needs commits (`04` §8) |

Out of scope for both specs: GxP (separate product, see `01` §7), a real monitor connection in the
hackathon, Tamil speech, and any drug or dose recommendation.

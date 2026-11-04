# Lightday — the count can't be lost.

**Meta Global AI Developer Hackathon submission.** One patient, two apps, three
Muse heroes — built with Muse Spark 1.3, SAM 3.1, and Muse Voice.

> 🎬 **Demo video (3:00):** <https://youtu.be/Kdornth-47M>

## The problem

In surgery, the most dangerous moment isn't the incision — it's the count.
Tired eyes, wrong pills, and lost discharges send patients back under for
problems a machine could have caught. A tray that must add up, a strip that's
hard to read, a discharge written from memory: each is a place where a tired
count costs a real person.

## The product

Lightday is one care engine for three people:

- **Doctor (Dr. Rao):** dictates the visit, spells the drug, sends the patient
  to theatre, dictates the discharge, signs. The record writes itself; he
  decides.
- **Nurse (Asha/Meena):** proves every step with a photo — wristband, allergy,
  vitals, consent — counts the tray and every swab by camera, and won't let
  surgery end until the count is saved.
- **Patient (Vani):** checks in from home, checks her strips against her
  prescription, asks her record (answered instantly) and her doctor (answered
  next).

Three plain roles carry it, each backed by a Muse model:

| Role | Model | Job |
| --- | --- | --- |
| The Watcher | SAM 3.1 | counts every tool, every swab, tray to bucket |
| The Listener | Muse Voice | hears every order, every drug, every dictation |
| The Reader | Spark 1.3 | checks every photo, strip, monitor, and draft |

One rule binds them, on screen and in code: **the AI never decides — a person
confirms.** Every AI result opens an Expand view: what was captured, what the
model returned, how the app used it, and what a person did.

## Why it matters (Impact · 30%)

- **Who benefits:** the surgical patient, the ward nurse doing the count at
  midnight, the doctor signing a discharge from a complete timeline — and any
  clinic that runs on paper today.
- **How much it matters:** a retained swab means a second surgery; a wrong pill
  at home undoes a good operation; a lost discharge loses the follow-up. The
  demo proves all three closed: 15/15/0 saved by the nurse, strips matched at
  home, discharge unlocked only when the evidence matches.
- **Beyond the hackathon:** two deployable apps (clinic dictation + ward care)
  sharing one patient timeline, one Model API key, and an audit trail a real
  hospital could inspect.

## Use of Meta AI tooling (25%)

Not a chatbot wrapper — the models are the senses of the product:

- **SAM 3.1 (vision):** instrument-tray counting against the planned list
  (flags "needle holder 0 of 3"), swab-camera before/after counts with
  last-frame proof of a missing swab.
- **Spark 1.3 (vision + drafting):** wristband/allergy/vitals/consent photo
  verdicts with timings on screen (9.7/8.2/5.9/6.4s), medicine-strip reads,
  discharge and handover drafts, ask-your-record answers.
- **Muse Voice (speech):** visit and discharge dictation, ward tasks by voice,
  theatre drugs by voice — always transcribed, structured, then confirmed by
  a tap.

Every model call in the UI shows its own step line, its timing, and its failure
state; a step never claims a model call that didn't happen, and rules-only
results are labeled as such.

## Technical depth & execution (20%)

- Two apps, one repo, one shared `.env` (`META_API_KEY`): Doctor Dictation
  (`doctor-dictation/`, port 8000) and Count Guard (`count-guard/`, web 5173,
  API 8100).
- Provenance everywhere: model name, input, returned output, how-used, and the
  person's action are saved per result and expandable in the UI.
- Honest failure design: wrong-photo refusal with reason, flagged counts that
  gate surgery end, split pass/fail checklists, correct-a-line without
  rewriting history.
- Test suites: Count Guard backend (pytest), Count Guard frontend (node:test),
  Doctor Dictation suite — run with `make test`.
- Verification loop for the demo itself: `make demo-check` drives the
  scripted beats end to end.

## Demo (25%)

- **Video:** the 3-minute film above — problem, heroes, save-the-day — cut from
  18 live-API captures, voiced, scored with a generated MusicGen bed.
  Sources: [`demo-video/`](demo-video/ENGINE-DRAFT.md).
- **Live:** both apps run locally; the demo dock switches doctor/nurse/patient
  roles, and the scripted beats (`make demo-check` in `count-guard/`) replay
  the story on a real backend.

## Run it

```bash
cp .env.example .env   # once; fill in META_API_KEY only for live model calls
make setup             # both virtualenvs and the Count Guard frontend
make dev               # all three servers
make test              # both test suites
```

`make dd` or `make cg` runs one app. Change a port in `.env`, not in code.
Each app keeps its own README: [`doctor-dictation/`](doctor-dictation/README.md),
[`count-guard/`](count-guard/README.md). Cross-app plans: [`docs/hackathon/`](docs/hackathon/README.md).

## Submission

- **Track:** Indie Developer — Representative: lvnpred
- **Submitted to:** <https://cerebralvalley.ai/e/meta-ai-developer-hackathon/hackathon/submit>
- **Proof of work:** full history at <https://github.com/lvnpred/hackathon26-proof>
- Per the Official Rules, the entrant retains ownership of the submission and
  grants the organizers a license to use it; nothing here is confidential.

*Synthetic demo data throughout. Research demo — not for clinical use.*

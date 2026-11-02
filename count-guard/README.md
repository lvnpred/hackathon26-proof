# Count Guard

**Research demo. Not for clinical use.**

Count Guard keeps one morning for one patient. It records the medicine strips they brought, the swabs that were opened and counted back, the drugs that were confirmed in the room, and a blood-pressure log. A discharge sheet is then a view of that timeline. The product does not give medical advice.

## The care app

The care app is the main product: one ward (Ward 4) seen by a doctor, a nurse and a patient. All data is synthetic. Every screen carries the strip "Research demo · Synthetic data · Not for clinical use".

### Start it

```bash
make setup     # once
make dev       # backend on 8100, frontend on 5173
```

Open http://127.0.0.1:5173. The page lands on the first tab of the current role.

### Switch role, patient and time

The **Demo** dock at the bottom of the screen (dashed edge, dark) holds the controls that are not part of the product:

| Control | What it does |
| --- | --- |
| Role | Doctor (Dr. A. Rao), Nurse (Nurse Meena) or Patient |
| Patient | Which bed the patient role is |
| Demo clock | Moves the ward clock forward; the dock shows "Day N", product screens show clock times only |
| Reset | Starts the ward again from the seeded data |
| Use the demo prescription | Loads the prepared prescription |
| Pause AI / Resume AI (demo shortcut) | Same switch as Pause in the product header |
| Guide | The Help page: what each part of the care app does |

### What each role sees

| Role | Tabs | Routes |
| --- | --- | --- |
| Doctor | My patients, AI activity | `/patients`, `/chart/:episodeId`, `/ai` |
| Nurse | My queue, Patients, AI activity | `/queue`, `/patients`, `/chart/:episodeId`, `/ai` |
| Patient | Today, My care, Ask | `/today`, `/my-care`, `/ask` |

The header shows who is signed in, the alerts bell and "AI admin: on" with **Pause**.

### How a chart reads

Top to bottom:

1. **Patient band and stage rail.** Six stages (clinic, ward, theatre, …). A skipped stage says "Skipped"; after surgery the ward reads "Ward · back from theatre".
2. **Now.** One card: the single most important thing for the signed-in person, with its action as the only main button. Below it, "Next after this" (two rows) and "N more".
3. **Alerts.** One card per alert: the reading ("Systolic BP 82"), the limit and who set it, "What did you do?" and **Save response**.
4. **Patient questions**, then **AI admin for this patient**.
5. **Orders and evidence** and **History**, folded closed with a count.

The Now card is picked by a fixed rank, the same on every screen (`frontend/src/care/rank.js`, `now.js`):

| Rank | Kind | Example |
| --- | --- | --- |
| 1 | Danger | BP below the limit; swab unaccounted |
| 2 | Blocked on you | Count not saved; orders to acknowledge |
| 3 | Late | Observations overdue, oldest first |
| 4 | Due now | Task due at this time |
| 5 | Review (staff only) | AI work still inside its Undo window |
| 6 | Nothing | "Nothing needs you." and who acts next |

The patient sees a simpler "What happens next" line and never sees late items, AI bookkeeping or model names.

### Status words

Every status pill uses one of five roles: fine, wait, check, danger, done. The pill states the clinical finding ("Below limit", "Swab unaccounted", "Count complete", "Late"), not who touched the record.

### The swab count is a hard stop

Surgery cannot end until a person saves the closing swab count, and the count must add up or say what the team did.

```text
Surgery began → Pack opened 20 → closing count: Back ___
   Back 20                     → saved, "Count complete"
   Back 19, no reason          → refused: "Say what the team did: the count does not match."
   Back 19 + "Found under the drape" → saved
Surgery ended → refused unless a person's closing, saved after surgery began, adds up or has a reason
```

- Back starts empty. The camera read is shown beside it ("Camera read 14") but never fills it in.
- After surgery begins, the opened count can only go up: **Add pack** records an extra pack. Lowering it is refused.
- Count events, surgery steps and patient moves cannot be corrected in place.
- Server rule: `count_gate` in `backend/app/journey/states.py`. Screen: `frontend/src/care/CountPanel.jsx`.

### AI admin and Undo

The AI does small admin work on behalf of Ward 4: acknowledging signed orders, assigning tasks, routing questions, drafting answers. Each row shows the time, **Undo · N min** while the window is open, and **Why**. Once every Undo window has closed, the block folds into one line, "AI did N admin tasks · Review". **Pause** in the header stops it; paused work shows as "Waiting for a person".

Record rows say how a reading was made in plain words ("Read by camera", "Read from photo", "Drafted from voice", "From voice", "Checked against the order"). Model names appear only in the Inspector's Model tab and on the AI activity page.

### The Inspector

**Why** or **Details** on any AI row opens the Inspector, on the Why tab:

| Tab | Shows |
| --- | --- |
| Why | What it did, Because, How it chose, Made by |
| Evidence | The photo, video frame or text that was read |
| History | Plain audit lines, "09:14 · Nurse Asha · Tray check by photos: all seen." "Copy event IDs" copies the raw ids |
| Model | The models used (staff only) |

The patient gets Why and Evidence only.

### Test it

```bash
make test                       # backend
cd frontend && node --test $(find src -name "*.test.js")          # screen logic
cd frontend && node --test $(find scripts -name "*.test.mjs")     # demo harness
cd frontend && npm run build
make demo-check                 # the filmed demo, headless, on ports 8200/5273
```

`make demo-check` plays the 32-beat demo (doctor, nurse and patient, 58 seconds each) and checks the text each beat expects. It also fails a beat whose screen shows "Recorded" as a status, "Day N" times outside the dock, internal names such as `task.assigned`, or model names outside the AI page and the Model tab (`frontend/scripts/demo/scan.mjs`). The script and its narration are in `docs/demo/count-guard-v2-video-script.md` at the workspace root; the steps are in `frontend/scripts/demo/steps.mjs` and `beats.mjs`.

The design behind this section is `docs/superpowers/specs/2026-11-01-count-guard-product-design-design.md` at the workspace root.

## Archived screens

The screens and routes built before the care app (the camera counter, the morning screens and the first journey screens) are in `archive/`, moved with `git mv` and not deleted. Every feature they held now lives in the care app (spec §9 in `docs/superpowers/specs/2026-11-02-dd-to-count-guard-patient-flow-design.md` at the workspace root), and the scripted plays are retired. Nothing in the app imports `archive/`, and pytest does not collect `archive/tests/`. `scripts/archive_set.py` lists any file under `backend/app` or `frontend/src` that the app no longer reaches.

This repository was started on 27 Oct 2026. It does not reuse Doctor Dictation or OPD Companion code.
The prescription comes from a running Doctor Dictation over HTTP (`GET /api/v1/documents/{id}`), so the two apps stay separate. The plan is `docs/hackathon/07-care-journey.md` at the workspace root.

## Run

```bash
make setup
cp ../.env.example ../.env   # once, at the workspace root; optional, only for live model calls
make dev
```

Open http://127.0.0.1:5173. The API is http://127.0.0.1:8100. `GET /product` is the feature map. `GET /health` names the four models and whether a key is set.

The fact card is off by default. To start with it on, for the card in the theatre view:

```bash
DECISION_TIER=1 make dev
```

`POST /journey/episodes/{id}/theatre/tier` sets the same switch until the backend restarts.

```bash
make test
make eval
make day1    # prints the API reading and does not spend credits
```

## How a morning is stored

One episode is one patient label. Events are append-only. A correction writes a new event that points at the old one, and the sheet shows only the new line.

```text
strips, speech, frames
        │
        ▼
  timeline events
        │
        ├── six fixed count rules, for the camera
        ├── dwell count, for the theatre replay
        └── fold → discharge PDF
```

The fact card, which restates recorded facts, is off until it is turned on. Its route is 404 while it is off. Decision events are left off the discharge PDF.

`GET /journey/episodes/{id}/stream` sends the timeline as server-sent events and keeps the stream open for new events. It stops after `timeout_s` seconds or when the client leaves.

## Models

Each model has one adapter. A missing key means that model is not called. The screen says so.

| Model | Job | Code |
| --- | --- | --- |
| SAM 3.1 `sam-3.1` | Detect and track. One id per object inside a single response. | `backend/app/adapters/sam.py` |
| Muse Voice Transcribe `muse-voice-transcribe-1.0` | Spoken counts with turn-level times. | `backend/app/adapters/voice.py` |
| Muse Spark Open | Explain discrepancies. Tool loop, then a verifier. | `backend/app/adapters/spark_open.py` |
| Muse Spark 1.3 `muse-spark-1.3` | Name a crop when rule R5 fires. It does not change the count. | `backend/app/adapters/spark.py` |

SAM 3.1 accepts an uploaded video or a still image. A live frame socket is not in the docs. Voice Transcribe returns turn times, not word times. Muse Spark Open on Baseten documents tool calling. `SPARK_OPEN_MODEL` defaults to `meta-models/muse-spark-open-1026`.

Muse Spark 1.3 runs only on an R5 row, and only when `MODEL_API_KEY` is set. It gets a crop of the last frame. Its answer is saved as a `second_look` event next to the alert. Without a key, nothing is called (`backend/app/engine.py`).

## Camera-count rules

Rules decide. The model only explains.

| Rule | Raises | Blocks closing |
| --- | --- | --- |
| R1 Opened vs returned | `count_mismatch` | yes |
| R2 Spoken vs camera | `spoken_vs_camera` | yes |
| R3 Last seen in the field | `unaccounted_item` | yes |
| R4 Tray appearance with no spoken add within 30 seconds | `unannounced_add` | yes |
| R5 Low score or identity re-link | `needs_human_look` | no |
| R6 Closing gate | reconciled only when R1–R4 are clear or a person resolved each one | — |

A recorded line may say "Unaccounted: 1 lap sponge." It may not say "A sponge is probably inside the patient." The checker replaces advice wording with a fixed sentence.

When a person resolves an alert, the Close screen and the count sheet print "Resolved by X: reason" under it.

On the theatre replay, a swab counts as back only after it stays in the bucket for 3 frames. A shorter wave does not count.

## What the scripted clips measured

`make eval` sends each scripted clip through the engine's replay (`Engine.replay`, which the archived `POST /cases/{id}/upload?scenario=clipN` route called). The expected results are in `eval/ground_truth/clip1.json` to `clip5.json`. SAM 3.1 was not called. There is no tray video yet, so this table measures the rule engine.

| Clip | What was planted | What the rules raised | Missed | False alarms | Ledger exact | ID switches | ID switches/min | Gate | Pipeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 Clean run | No discrepancies | none | none | 0 | yes | 0 | 0.0 | reconciled | 26.2 ms |
| 2 Sponge left out | 1 unaccounted item | R1 and R3, lap sponge | none | 0 | yes | 0 | 0.0 | blocked | 33.6 ms |
| 3 Said ten, nine in the bucket | 1 spoken vs camera | R2, lap sponge | none | 0 | yes | 0 | 0.0 | blocked | 22.1 ms |
| 4 Five gauze, nothing said | 1 unannounced add | R4, gauze swab | none | 0 | yes | 0 | 0.0 | blocked | 8.1 ms |
| 5 Two instruments swap places | No discrepancies, no ID switches | none | none | 0 | yes | 0 | 0.0 | reconciled | 11.1 ms |

All 3 planted discrepancies were caught. The clip 1 count sheet was ready in 3.4 ms. Clip 2 also raises R1 because 10 were opened and 9 came back. That matches the worked example.

The Pipeline column and the count-sheet time change from run to run. The other columns do not.

## Try it with curl

Start the backend with `make backend`. Then paste these lines into the shell. The URLs with `?` or `&` are quoted, so zsh does not read them as file patterns.

```bash
curl -s localhost:8100/health
EPISODE_ID=$(curl -s -X POST localhost:8100/journey/episodes -H 'content-type: application/json' \
  -d '{"label":"Synthetic demo, R. Kumar"}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -s localhost:8100/journey/episodes/$EPISODE_ID
curl -sN localhost:8100/journey/episodes/$EPISODE_ID'/stream?timeout_s=5'
```

The last line prints the timeline, waits 5 seconds for new events, then stops. The older camera-case (`/cases`) and morning (`/morning`) routes are archived; the theatre count panel and the swab camera in the care app do that work now.

## Submission notes

What was live and what was replayed:

- `make live-check` on 2 Nov 2026 made one real call per model, and each answered: Voice Transcribe 2.80 s, Spark 1.3 text 7.16 s, Spark 1.3 vision 4.80 s, SAM 3.1 2.18 s. SAM 3.1 found 0 swabs on the drawn swab-tray image. live-check does not call Muse Spark Open. Without a key, `GET /health` shows `"configured": false` and no adapter makes a call.
- The patient flow from Doctor Dictation (Save & admit) into the ward, theatre and discharge is filmed from `docs/demo/dd-cg-flow-video-script.md` at the workspace root.
- Every count shown is scripted replay. The detections come from `backend/app/scenarios.py`, not from a camera.
- Spoken lines in the demo are typed or scripted text. Voice Transcribe did not hear them.

Measured accuracy:

- `make eval`: 3 of 3 planted discrepancies caught, 0 false alarms, 0 ID switches, on 5 scripted clips. This measures the rules, not SAM 3.1.
- No real tray video has been measured.

Which model worded the text:

- The fact card is the fixed template in `backend/app/morning/vitals.py`. Each card is saved with `"wording": "template"`. No LLM wrote it.
- The count-sheet narrative is also the template, because Muse Spark Open has no key. The sheet prints "Narrative model: template".

## Before this is public

- Covasant IP check: not applicable. Closed by you on this project.
- Do not commit `.env`. `backend/tests/test_repo_hygiene.py` fails if `.env`, a key, or a media file is tracked.
- Record the five prop-tray clips, then replace this table with the measured one, including misses.
- Set a spend limit on the Meta billing page before the first SAM video call.
- The 3-minute video (script: `docs/demo/dd-cg-flow-video-script.md`) and the X post are still to be made.

The build list is [docs/new-work.md](docs/new-work.md).

## Licence

MIT. See [LICENSE](LICENSE).

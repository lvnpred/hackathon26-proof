# Count Guard

**Research demo. Not for clinical use.**

Count Guard keeps one morning for one patient. It records the medicine strips they brought, the swabs that were opened and counted back, the drugs that were confirmed in the room, and a blood-pressure log. A discharge sheet is then a view of that timeline. The product does not give medical advice.

The running map is the guide. With the app open, start at [the guide](http://127.0.0.1:5173/guide). The same list is `GET /product`, defined in `backend/app/site.py`. Change a feature there and the page follows.

| Feature | Where you use it | Where a developer edits it | Built |
| --- | --- | --- | --- |
| One patient, six steps | [Home](http://127.0.0.1:5173/) | `frontend/src/screens/Home.jsx` | [2026-10-27](docs/new-work.md) |
| Medicine strips | [Before the operation](http://127.0.0.1:5173/opd) | `backend/app/morning/lexicon.py` | [2026-10-27](docs/new-work.md) |
| Swab count and drug line | [In the room](http://127.0.0.1:5173/ot) | `backend/app/morning/count_rules.py` | [2026-10-27](docs/new-work.md) |
| Discharge sheet | [After the room](http://127.0.0.1:5173/ward) | `backend/app/morning/discharge.py` | [2026-10-27](docs/new-work.md) |
| Camera count | [Video check](http://127.0.0.1:5173/count) | `backend/app/core/rules.py` | [2026-10-27](docs/new-work.md) |
| One patient, three people | [Journey](http://127.0.0.1:5173/journey) | `backend/app/journey/nudges.py` | [2026-10-28](docs/new-work.md) |
| Prescription, orders, discharge card | [Doctor](http://127.0.0.1:5173/doctor) | `backend/app/journey/rx.py` | [2026-10-28](docs/new-work.md) |
| Doses, observations, nudge inbox | [Nurse](http://127.0.0.1:5173/nurse) | `backend/app/journey/api.py` | [2026-10-28](docs/new-work.md) |
| Schedule, strips, check-in | [Patient](http://127.0.0.1:5173/patient) | `backend/app/journey/schedule.py` | [2026-10-28](docs/new-work.md) |
| Audit trail | [Audit](http://127.0.0.1:5173/audit) | `backend/app/journey/stories.py` | [2026-10-28](docs/new-work.md) |
| This map | [Guide](http://127.0.0.1:5173/guide) | `backend/app/site.py` | [2026-10-27](docs/new-work.md) |

Every module and its date is in [docs/new-work.md](docs/new-work.md). That list also names the changes made overnight on 27–28 Oct, committed as e36cd87.

These six steps are for this patient only. The next patient starts a new morning. Records are not mixed.

This repository was started on 27 Oct 2026. It does not reuse Doctor Dictation or OPD Companion code.
The prescription comes from a running Doctor Dictation over HTTP (`GET /api/v1/documents/{id}`), so the two apps stay separate. The plan is `docs/hackathon/07-care-journey.md` at the workspace root.

## Run

```bash
make setup
cp ../.env.example ../.env   # once, at the workspace root; optional, only for live model calls
make dev
```

Open http://127.0.0.1:5173. The API is http://127.0.0.1:8100. `GET /product` is the feature map. `GET /health` names the four models and whether a key is set.

The fact card is off by default. To start with it on, for the card scene on the OT screen:

```bash
DECISION_TIER=1 make dev
```

The OT screen also has a "Fact card on/off" button. It sets the same switch until the backend restarts.

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

`GET /morning/episodes/{id}/stream` sends the timeline as server-sent events and stops. Add `?follow=1` to keep the stream open and send new events as they arrive. It stops after `timeout_s` seconds (at most 30) or when the client leaves.

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

`make eval` sends each scripted clip through the same upload route the app uses (`POST /cases/{id}/upload?scenario=clipN`). The expected results are in `eval/ground_truth/clip1.json` to `clip5.json`. SAM 3.1 was not called. There is no tray video yet, so this table measures the rule engine.

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

Camera path, on scripted perception:

```bash
curl -s localhost:8100/health
CASE_ID=$(curl -s -X POST localhost:8100/cases -H 'content-type: application/json' \
  -d '{"label":"Prop tray demo","item_types":["lap sponge"]}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -s -X POST localhost:8100/cases/$CASE_ID'/upload?scenario=demo'
curl -s localhost:8100/cases/$CASE_ID/discrepancies
```

The Live screen does the same. On a case with no playback, it offers "Run the scripted demo on this case" or a file upload. The demo replaces the drawn zones with its own.

A video upload uses the same route, with `-F file=@clip.mp4`. Without `MODEL_API_KEY` it returns 400 and names SAM 3.1. It does not invent detections. Other upload errors are short too:

| Case | Status |
| --- | --- |
| Unknown scenario, unreadable JSON, no file | 400 |
| No key, or zones not saved, before a video | 400, and the clip is not kept |
| ffmpeg missing, or a clip it cannot read | 400, and the clip is not kept |
| SAM 3.1 call fails | 502, and the clip is not kept |

One morning, with the fact card on:

```bash
curl -s -X POST localhost:8100/morning/tier -H 'content-type: application/json' -d '{"enabled":true}'
EPISODE_ID=$(curl -s -X POST localhost:8100/morning/episodes -H 'content-type: application/json' \
  -d '{}' | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
curl -s -X POST localhost:8100/morning/episodes/$EPISODE_ID/play -o /dev/null -w '%{http_code}\n'
curl -s localhost:8100/morning/episodes/$EPISODE_ID/card
curl -sN localhost:8100/morning/episodes/$EPISODE_ID'/stream?follow=1&timeout_s=5'
```

The last line prints the timeline, waits 5 seconds for new events, then stops.

## Submission notes

What was live and what was replayed:

- SAM 3.1, Muse Voice Transcribe, Muse Spark Open and Muse Spark 1.3 were never called with a real key. Without a key, `GET /health` shows `"configured": false` for all four and no adapter makes a call.
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
- The 3-minute video and the X post are still to be made.

The build list is [docs/new-work.md](docs/new-work.md).

## Licence

MIT. See [LICENSE](LICENSE).

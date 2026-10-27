# Count Guard

**Research demo. Not for clinical use.**

Count Guard keeps one morning for one patient. It records the medicine strips they brought, the swabs that were opened and counted back, the drugs that were confirmed in the room, and a blood-pressure log. A discharge sheet is then a view of that timeline. The product does not give medical advice.

The running map is the guide. With the app open, start at [the guide](http://127.0.0.1:5173/guide). The same list is `GET /product`, defined in `backend/app/site.py`. Change a feature there and the page follows.

| Feature | Where you use it | Where a developer edits it |
| --- | --- | --- |
| One patient, six steps | [Home](http://127.0.0.1:5173/) | `frontend/src/screens/Home.jsx` |
| Medicine strips | [Before the operation](http://127.0.0.1:5173/opd) | `backend/app/morning/lexicon.py` |
| Swab count and drug line | [In the room](http://127.0.0.1:5173/ot) | `backend/app/morning/count_rules.py` |
| Discharge sheet | [After the room](http://127.0.0.1:5173/ward) | `backend/app/morning/discharge.py` |
| Camera count | [Video check](http://127.0.0.1:5173/count) | `backend/app/core/rules.py` |
| This map | [Guide](http://127.0.0.1:5173/guide) | `backend/app/site.py` |

These six steps are for this patient only. The next patient starts a new morning. Records are not mixed.

This repository was started on 27 Oct 2026. It does not reuse Doctor Dictation or OPD Companion code.

## Run

```bash
make setup
cp .env.example .env   # optional, only for live model calls
make dev
```

Open http://127.0.0.1:5173. The API is http://127.0.0.1:8000. `GET /product` is the feature map. `GET /health` names the four models and whether a key is set.

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

## Models

Each model has one adapter. A missing key means that model is not called. The screen says so.

| Model | Job | Code |
| --- | --- | --- |
| SAM 3.1 `sam-3.1` | Detect and track. One id per object inside a single response. | `backend/app/adapters/sam.py` |
| Muse Voice Transcribe `muse-voice-transcribe-1.0` | Spoken counts with turn-level times. | `backend/app/adapters/voice.py` |
| Muse Spark Open | Explain discrepancies. Tool loop, then a verifier. | `backend/app/adapters/spark_open.py` |
| Muse Spark 1.3 `muse-spark-1.3` | Name a crop when rule R5 fires. It does not change the count. | `backend/app/adapters/spark.py` |

SAM 3.1 accepts an uploaded video or a still image. A live frame socket is not in the docs. Voice Transcribe returns turn times, not word times. Muse Spark Open on Baseten documents tool calling. `SPARK_OPEN_MODEL` defaults to `meta-models/muse-spark-open-1026`.

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

On the theatre replay, a swab counts as back only after it stays in the bucket for 3 frames. A shorter wave does not count.

## What the scripted clips measured

`make eval` replays scripted detections. SAM 3.1 was not called. There is no tray video yet, so this table is the rule engine.

| Clip | What was planted | What the rules raised | Missed | False alarms | Ledger exact | ID switches | Gate | Pipeline |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 Clean run | No discrepancies | none | none | 0 | yes | 0 | reconciled | 29.4 ms |
| 2 Sponge left out | 1 unaccounted item | R1 and R3, lap sponge | none | 0 | yes | 0 | blocked | 66.7 ms |
| 3 Said ten, nine in the bucket | 1 spoken vs camera | R2, lap sponge | none | 0 | yes | 0 | blocked | 52.0 ms |
| 4 Five gauze, nothing said | 1 unannounced add | R4, gauze swab | none | 0 | yes | 0 | blocked | 6.8 ms |
| 5 Two instruments swap places | No discrepancies, no ID switches | none | none | 0 | yes | 0 | reconciled | 9.6 ms |

All 3 planted discrepancies were caught. The clip 1 count sheet was ready in 6.6 ms. Clip 2 also raises R1 because 10 were opened and 9 came back. That matches the worked example.

Try the camera path with:

```bash
curl -s -X POST localhost:8000/cases -H 'content-type: application/json' \
  -d '{"label":"Prop tray demo","item_types":["lap sponge"]}'
curl -s -X POST localhost:8000/cases/CASE_ID/upload?scenario=demo
```

A video upload uses the same route after zones are saved. Without `MODEL_API_KEY` it returns 400 and names SAM 3.1. It does not invent detections.

## Before this is public

- Covasant IP check: not applicable. Closed by you on this project.
- Do not commit `.env`.
- Record the five prop-tray clips, then replace this table with the measured one, including misses.
- Set a spend limit on the Meta billing page before the first SAM video call.
- The 3-minute video and the X post are still to be made.

The build list is [docs/new-work.md](docs/new-work.md).

## Licence

MIT. See [LICENSE](LICENSE).

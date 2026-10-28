# Count Guard architecture

Research demo. Not for clinical use.

Count Guard counts objects and records what was said. It does not read vitals, name a drug, or tell anyone what to do.

```text
video frames ── SAM 3.1 adapter ── detections ──┐
                                                 ├── event ledger ── six rules ── alerts
audio ── Voice Transcribe adapter ── parser ────┘                      │
                                                                       └── Muse Spark Open explains
                                                                           a verifier checks the sentence
```

The ledger is append-only. The track table is a cache. Every alert is a `discrepancy` event, so a number on screen comes from a frame or a transcript line.

## Decisions made while building

- The repo is new. It does not import Doctor Dictation or OPD Companion.
- Rules R1 to R6 are ordinary code. A model never sets a count to right or wrong.
- R1 runs only for item types with a spoken add, and only after a closing or final checkpoint. Unannounced items are R4's job.
- R3 runs at that same checkpoint. An item whose zone is still `field` is unaccounted.
- R5 (low score or identity re-link) does not block closing.
- Two extra event types record facts the rules need: `identity_relink` and `low_confidence`. They are not alerts by themselves.
- SAM ids from the API are stable only inside one response. The tracker mints its own id and, on a later chunk, re-links by label and position. That re-link is low confidence.
- Scripted clips keep the id they were given. `make eval` uses that path and says so.
- Voice timestamps are turn-level. The 30 second R4 window uses those turns.
- If Muse Spark Open is not configured, or a sentence fails the check, the sentence is a fixed template. The check rejects advice words such as recommend, should, X-ray, and re-explore.

## Day-1 API reading (27 Oct 2026)

Checked against dev.meta.ai and Baseten's Muse Spark Open pages. Not confirmed with a paid call.

| Question | Reading |
| --- | --- |
| Does SAM 3.1 take a live frame stream? | No socket is documented. It takes an uploaded video or a still image on `POST /v1/responses`, model `sam-3.1`, one noun phrase per call. |
| Does Voice Transcribe return word times? | No. `turns[].startMs` and `endMs` only. Model `muse-voice-transcribe-1.0`. |
| Does Muse Spark Open on Baseten support tools? | The docs say yes, via `POST https://inference.baseten.co/v1/chat/completions`. The spec's model id is `meta-models/muse-spark-open-1026`. Baseten's public id on 15 Oct 2026 was `meta-models/muse-spark-open`. `SPARK_OPEN_MODEL` selects one. |

Until a key is present, the demo plays scripted detections through the same rules as a video upload. The screen says SAM was not called.

## Zones

Polygons are normalized 0 to 1 on the first frame: tray, field, bucket. The center of a box picks the smallest containing polygon.

## Where each model is called

| Model | File |
| --- | --- |
| SAM 3.1 | `backend/app/adapters/sam.py` |
| Muse Voice Transcribe | `backend/app/adapters/voice.py` |
| Muse Spark Open | `backend/app/adapters/spark_open.py`, called by `backend/app/agent/reconciler.py` |
| Muse Spark 1.3 | `backend/app/adapters/spark.py`, only for a second look when R5 fires |

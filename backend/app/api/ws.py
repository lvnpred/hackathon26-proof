"""Live socket. Frames and audio in. Events, ledger, and alerts out.

SAM 3.1 does not accept a live frame socket. When a key is set, frames are
grouped into a short mp4 and sent as one video call. Without a key, the
socket still accepts detections so a scripted feed can drive the screen.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ledger import ledger_rows, open_discrepancies
from app.core.tracker import Tracker

router = APIRouter()


@router.websocket("/cases/{case_id}/stream")
async def stream(websocket: WebSocket, case_id: str) -> None:
    engine = websocket.app.state.engine
    store = websocket.app.state.store
    if store.get_case(case_id) is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    tracker = Tracker(
        lost_after_frames=engine.settings.lost_after_frames,
        low_confidence=engine.settings.low_confidence,
    )
    await websocket.send_json(
        {
            "type": "ready",
            "banner": "Research demo. Not for clinical use.",
            "sam": engine.settings.sam_model,
            "voice": engine.settings.voice_model,
            "perception": "scripted" if not engine.settings.sam_configured else "sam-3.1",
        }
    )
    try:
        while True:
            message = json.loads(await websocket.receive_text())
            kind = message.get("type")
            media_ts = int(message.get("media_ts_ms") or 0)
            if kind == "utterance":
                engine.add_utterance(
                    case_id,
                    message.get("text") or "",
                    t0_ms=int(message.get("t0_ms") or media_ts),
                    t1_ms=int(message.get("t1_ms") or media_ts),
                    source=message.get("source") or "websocket",
                )
            elif kind == "detections":
                zones = store.zones(case_id)
                engine._ingest_detections(
                    case_id,
                    tracker,
                    zones,
                    message.get("detections") or [],
                    media_ts_ms=media_ts,
                    width=int(message.get("width") or 640),
                    height=int(message.get("height") or 360),
                    source=message.get("source") or "websocket",
                    chunk_id=str(message.get("chunk_id") or "live"),
                    relink=bool(message.get("relink")),
                    external_ids=bool(message.get("external_ids")),
                )
            elif kind == "checkpoint":
                engine.add_utterance(
                    case_id,
                    message.get("text") or f"{message.get('phase', 'closing')} count",
                    t0_ms=media_ts,
                    t1_ms=media_ts,
                    source="websocket",
                )
            engine.apply_rules(case_id, now_ms=media_ts, finalize=bool(message.get("finalize")))
            events = store.events(case_id)
            await websocket.send_json(
                {
                    "type": "state",
                    "ledger": ledger_rows(events),
                    "discrepancies": open_discrepancies(events),
                    "transcript": store.transcripts(case_id),
                }
            )
    except WebSocketDisconnect:
        engine._cache_tracks(case_id, tracker)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1011)

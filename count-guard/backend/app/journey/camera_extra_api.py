"""The swab camera's live socket (moved from `api/ws.py`). Frames and speech in; ledger, findings and advice out.

SAM 3.1 does not accept a live frame socket. Without a key the socket still takes detections, so a scripted feed
can drive the screen. Advice written here carries CAMERA_BY and is never a swab count (U10).
"""

from __future__ import annotations

import json
from typing import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ledger import ledger_rows, open_discrepancies
from app.core.tracker import Tracker
from app.journey import advice
from app.journey.clock import stamp

camera_live_router = APIRouter(prefix="/journey/episodes/{episode_id}/camera")


def _apply(engine, store, case_id: str, tracker: Tracker, message: dict) -> None:
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
        engine._ingest_detections(
            case_id,
            tracker,
            store.zones(case_id),
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


async def stream_case(websocket: WebSocket, case_id: str, after: Callable[[], dict] | None = None) -> None:
    """Run the live socket for one camera case. `after` adds fields to each state message (the care advice)."""
    engine = websocket.app.state.engine
    store = websocket.app.state.store
    if store.get_case(case_id) is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    tracker = Tracker(lost_after_frames=engine.settings.lost_after_frames, low_confidence=engine.settings.low_confidence)
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
            _apply(engine, store, case_id, tracker, json.loads(await websocket.receive_text()))
            events = store.events(case_id)
            await websocket.send_json(
                {
                    "type": "state",
                    "ledger": ledger_rows(events),
                    "discrepancies": open_discrepancies(events),
                    "transcript": store.transcripts(case_id),
                    **(after() if after else {}),
                }
            )
    except WebSocketDisconnect:
        engine._cache_tracks(case_id, tracker)
    except Exception as exc:
        await websocket.send_json({"type": "error", "message": str(exc)})
        await websocket.close(code=1011)


@camera_live_router.websocket("/live")
async def camera_live(websocket: WebSocket, episode_id: str) -> None:
    """The live socket on this stay's camera case. Each state message carries the stay's advice."""
    morning = websocket.app.state.morning
    case_id = advice.linked_case(morning.events(episode_id)) if morning.get_episode(episode_id) else None
    if case_id is None:
        await websocket.close(code=4404)
        return

    def after() -> dict:
        rows = advice.from_case(websocket.app.state.engine, case_id)
        source = "sam-3.1" if websocket.app.state.settings.sam_configured else "scripted"
        advice.write(morning, episode_id, case_id, rows, stamp(morning, episode_id, None), source)
        return {"advice": advice.advice_view(episode_id, morning.events(episode_id))}

    await stream_case(websocket, case_id, after)

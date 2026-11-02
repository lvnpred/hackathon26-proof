"""Live socket. Frames and audio in. Events, ledger, and alerts out.

SAM 3.1 does not accept a live frame socket. When a key is set, frames are
grouped into a short mp4 and sent as one video call. Without a key, the
socket still accepts detections so a scripted feed can drive the screen.
"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket

from app.journey.camera_extra_api import stream_case

router = APIRouter()


@router.websocket("/cases/{case_id}/stream")
async def stream(websocket: WebSocket, case_id: str) -> None:
    """The socket body moved to the care swab camera; this route calls it until Task 16 archives it."""
    await stream_case(websocket, case_id)

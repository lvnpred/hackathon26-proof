"""Server-sent events: one frame format and one follow loop.

The care app's streams (`journey/stream_api.py`) and the morning stream (`morning/api.py`, until Task 16 archives
its routes) both use these, so the two never drift apart.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable

from fastapi import Request
from fastapi.responses import StreamingResponse

FOLLOW_POLL_S = 0.25
FOLLOW_MAX_S = 30.0  # a stream ends after this; EventSource reconnects with Last-Event-ID
RETRY_MS = 1000  # how soon the browser reconnects after a stream ends
# No cache, and no buffering in a proxy in front of the API, so each frame reaches the page as it is written.
HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


def frame(event_id: str | None, data: dict, *, name: str | None = None) -> str:
    """One SSE frame. `id:` is the event id, so a reconnect resumes after it."""
    lines = [f"event: {name}"] if name else []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


def event_frame(event: dict) -> str:
    return frame(event["id"], event)


def retry() -> str:
    return f"retry: {RETRY_MS}\n\n"


async def follow(request: Request, read: Callable[[], list[str]], timeout_s: float) -> AsyncIterator[str]:
    """Every poll, send the frames `read()` returns, until the timeout (at most FOLLOW_MAX_S) or a disconnect."""
    deadline = time.monotonic() + min(timeout_s, FOLLOW_MAX_S)
    while time.monotonic() < deadline:
        await asyncio.sleep(FOLLOW_POLL_S)
        if await request.is_disconnected():
            return
        for text in read():
            yield text


def response(body) -> StreamingResponse:
    return StreamingResponse(body, media_type="text/event-stream", headers=HEADERS)

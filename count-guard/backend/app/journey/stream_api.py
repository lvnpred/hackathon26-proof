"""The live stream, kept and moved into the care app (spec §8, §9 "morning SSE stream").

`GET /journey/ward/stream` tells the ward list something changed: any event on a patient episode (one with a
bed; the staff board has none), registrations included, and the demo clock. `GET /journey/episodes/{id}/stream`
sends one chart's events. Both use the event id as the SSE `id:` and resume after `Last-Event-ID`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.journey import sse

stream_router = APIRouter(prefix="/journey")
Timeout = Query(default=sse.FOLLOW_MAX_S, gt=0, le=sse.FOLLOW_MAX_S)


def _store(request: Request):
    return request.app.state.morning


def _known(store, event_id: str | None, episode_id: str | None = None) -> str | None:
    """The Last-Event-ID when this store wrote it (on this episode, when given), else None."""
    event = store.get_event(event_id) if event_id else None
    if event is None or (episode_id and event["episode_id"] != episode_id):
        return None
    return event_id


def _summary(event: dict) -> dict:
    """What the ward list needs to know: which patient changed. The chart reads the record itself."""
    return {key: event[key] for key in ("id", "episode_id", "event_type", "ts_ms")}


@stream_router.get("/ward/stream")
def ward_stream(request: Request, timeout_s: float = Timeout):
    store = _store(request)
    after = _known(store, request.headers.get("last-event-id"))
    tail = store.tail_id()
    seen = {"last": after or tail, "clock": store.get_clock()}

    def read() -> list[str]:
        rows = store.timeline_after(seen["last"]) if seen["last"] else store.timeline_after(None)
        beds = store.beds()
        out = []
        for event in rows:
            seen["last"] = event["id"]
            if event["episode_id"] in beds:
                out.append(sse.frame(event["id"], _summary(event)))
        clock = store.get_clock()
        if clock != seen["clock"]:
            seen["clock"] = clock
            out.append(sse.frame(None, {"now_ms": clock or 0}, name="clock"))
        return out

    async def body():
        yield sse.retry()
        if after:
            for text in read():
                yield text
        else:
            # A fresh stream sends no history, only where it stands, so a reconnect resumes from here.
            yield sse.frame(tail, {}, name="ready")
        async for text in sse.follow(request, read, timeout_s):
            yield text

    return sse.response(body())


@stream_router.get("/episodes/{episode_id}/stream")
def episode_stream(episode_id: str, request: Request, timeout_s: float = Timeout):
    store = _store(request)
    if store.get_episode(episode_id) is None:
        raise HTTPException(status_code=404, detail="Episode not found")
    after = _known(store, request.headers.get("last-event-id"), episode_id)
    rows = store.events(episode_id, after_id=after)
    seen = {"last": rows[-1]["id"] if rows else after}

    def read() -> list[str]:
        new = store.events(episode_id, after_id=seen["last"])
        if new:
            seen["last"] = new[-1]["id"]
        return [sse.event_frame(event) for event in new]

    async def body():
        yield sse.retry()
        for event in rows:
            yield sse.event_frame(event)
        async for text in sse.follow(request, read, timeout_s):
            yield text

    return sse.response(body())

"""Ops routes: undo, approve and reject an AI item, the kill switch, and the AI feed (C5)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import Field

from app.journey.ai_api import _ids
from app.journey.api import At, _at, _require, _store, settle, view
from app.journey.ask import short_name
from app.ops import gate, site
from app.ops.items import ops_view
from app.ops.run import _LOCK

router = APIRouter(prefix="/journey/episodes/{episode_id}/ops/work/{work_id}")
ops_site_router = APIRouter(prefix="/journey/ops")
FEED_MAX = 30
AI_ACTOR = "A person must do this, not the AI."


class ByIn(At):
    by: str = Field(min_length=1, max_length=80)


class ApproveIn(ByIn):
    text: str | None = Field(default=None, min_length=1, max_length=1000)


class RejectIn(ByIn):
    note: str = Field(default="", max_length=300)


def _person(by: str) -> None:
    if by.startswith("AI"):
        raise HTTPException(status_code=422, detail=AI_ACTOR)


def _run(request: Request, episode_id: str, at_ms: int | None, act) -> dict:
    """One gate call under the agent's lock (so it never overlaps a run), then settle and return the view."""
    _require(request, episode_id)
    store = _store(request)
    ts = _at(store, episode_id, at_ms)
    try:
        with _LOCK:
            act(store, ts)
    except gate.OpsError as exc:
        raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
    settle(request, episode_id, ts)
    return view(request, episode_id)


@router.post("/undo")
def undo(episode_id: str, work_id: str, body: ByIn, request: Request) -> dict:
    _person(body.by)
    return _run(request, episode_id, body.at_ms,
                lambda store, ts: gate.undo(store, episode_id, work_id, body.by, ts))


@router.post("/approve")
def approve(episode_id: str, work_id: str, body: ApproveIn, request: Request) -> dict:
    _person(body.by)
    return _run(request, episode_id, body.at_ms,
                lambda store, ts: gate.approve(store, episode_id, work_id, body.by, body.text, ts))


@router.post("/reject")
def reject(episode_id: str, work_id: str, body: RejectIn, request: Request) -> dict:
    _person(body.by)
    return _run(request, episode_id, body.at_ms,
                lambda store, ts: gate.reject(store, episode_id, work_id, body.by, body.note, ts))


def _state(store) -> dict:
    paused, by = site.paused(store)
    return {"paused": paused, "by": by}


@ops_site_router.get("")
def get_state(request: Request) -> dict:
    return _state(_store(request))


def _switch(request: Request, body: ByIn, paused: bool) -> dict:
    _person(body.by)
    store = _store(request)
    site.set_paused(store, paused, body.by, body.at_ms or 0)
    return _state(store)


@ops_site_router.post("/pause")
def pause(body: ByIn, request: Request) -> dict:
    return _switch(request, body, True)


@ops_site_router.post("/resume")
def resume(body: ByIn, request: Request) -> dict:
    return _switch(request, body, False)


@ops_site_router.get("/feed")
def feed(request: Request, ids: str = Query(...)) -> dict:
    """What the AI handled across these patients, newest first."""
    store = _store(request)
    items = []
    for episode_id in _ids(ids):
        episode = _require(request, episode_id)
        patient = short_name(episode.get("label"))
        items += [{**row, "episode_id": episode_id, "patient": patient}
                  for row in ops_view(store.events(episode_id))["handling"]]
    items.sort(key=lambda row: row["at_ms"], reverse=True)
    return {"items": items[:FEED_MAX]}

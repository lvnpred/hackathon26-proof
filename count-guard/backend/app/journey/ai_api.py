"""Routes for the AI evidence (Task 7 adds the dashboard routes here)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.journey import evidence
from app.journey.api import _require, _store

evidence_router = APIRouter(prefix="/journey/episodes/{episode_id}")
NOT_FOUND = "Evidence not found"


@evidence_router.get("/evidence/{evidence_id}")
def get_evidence(episode_id: str, evidence_id: str, request: Request) -> dict:
    """The sidecar of one check, if an event of this episode cites it."""
    _require(request, episode_id)
    if not evidence.EVIDENCE_ID.match(evidence_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    holders = evidence.held_by(_store(request).events(episode_id), evidence_id)
    body = evidence.load(request.app.state.settings, episode_id, evidence_id) if holders else None
    if body is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {
        **body,
        "images": [{**i, "url": f"/journey/episodes/{episode_id}/photos/{i['photo_id']}"} for i in body["images"]],
        "cited_by": [
            {"event_id": e["id"], "type": e["event_type"], "when": e["ts_ms"], "by": e["payload"].get("by")}
            for e in holders
        ],
    }

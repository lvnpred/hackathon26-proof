"""Routes for the AI evidence and the "AI at work" dashboard."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from app.config import REPO_ROOT
from app.journey import evidence, live
from app.journey.ai_summary import summary
from app.journey.api import _require, _store
from app.journey.procedures import tray_plan
from app.journey.video import compare, expected_for_tray
from app.journey.video_api import TRAY_LIVE

evidence_router = APIRouter(prefix="/journey/episodes/{episode_id}")
ai_router = APIRouter(prefix="/journey/ai")
IDS_BAD = "Send 1 to 10 patient ids, each 1 to 64 characters."
MISSING_SAMPLE = "The sample file is missing. Run make demo-check once to make it."
# The only files "Try sample" and the samples route serve: name -> folder under the repo root.
SAMPLES = {"tray-hernia.png": "eval/p3", "monitor-88-54.png": "eval/p2", "kumar-orders.wav": "eval/p2"}
SHOWN = ("tray-hernia.png", "monitor-88-54.png")  # the images the samples route may serve
NOT_FOUND = "Evidence not found"


@evidence_router.get("/evidence/{evidence_id}")
def get_evidence(episode_id: str, evidence_id: str, request: Request) -> dict:
    """The sidecar of one check, if an event of this episode cites it."""
    _require(request, episode_id)
    if not evidence.EVIDENCE_ID.fullmatch(evidence_id):
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    holders = evidence.held_by(_store(request).events(episode_id), evidence_id)
    body = evidence.load(request.app.state.settings, episode_id, evidence_id) if holders else None
    if body is None:
        raise HTTPException(status_code=404, detail=NOT_FOUND)
    return {
        **body,
        "images": [{**i, "url": f"/journey/episodes/{episode_id}/photos/{i['photo_id']}"} for i in body["images"]],
        "cited_by": [
            {"event_id": e["id"], "type": e["event_type"], "when": e["ts_ms"], "by": e["payload"].get("by"),
             **{k: e["payload"][k] for k in ("read", "saved") if e["payload"].get(k)}}
            for e in holders
        ],
    }


def _ids(raw: str) -> list[str]:
    ids = [i.strip() for i in raw.split(",")]
    if not 1 <= len(ids) <= 10 or any(not 1 <= len(i) <= 64 for i in ids):
        raise HTTPException(status_code=422, detail=IDS_BAD)
    return list(dict.fromkeys(ids))


@ai_router.get("/summary")
def ai_summary(request: Request, ids: str = Query(...)) -> dict:
    """Model calls in the records of these patients (R7), plus whether a key is set."""
    store, settings = _store(request), request.app.state.settings
    roster = [(_require(request, i), store.events(i)) for i in _ids(ids)]
    configured = {"voice": settings.voice_configured, "spark": settings.spark_configured,
                  "sam": settings.sam_configured, "spark-open": settings.spark_open_configured}
    return {**summary(roster, configured), "live": settings.spark_configured}


def _sample_path(name: str):
    return REPO_ROOT / SAMPLES[name] / name


def _sample_bytes(settings, name: str) -> bytes:
    """The bytes of an allow-listed sample. With a key the file must exist; without one the fixture is enough."""
    path = _sample_path(name)
    if path.is_file():
        return path.read_bytes()
    if settings.spark_configured:
        raise HTTPException(status_code=409, detail=MISSING_SAMPLE)
    return b""


def _sample_evidence(kind: str, name: str, found: dict, result: dict | None) -> dict:
    return {
        "kind": kind, "media": "photos",
        "images": [{"url": f"/journey/ai/samples/{name}", "t": None, "index": 0}],
        "frames": found.get("frames"), "regions": found.get("regions"),
        "expected": [{"concept": r["concept"], "planned": r["planned"]} for r in (result or {}).get("rows", [])],
        "rows": (result or {}).get("rows", []),
        "min_score": None, "fps": None,
        "calls": found["calls"], "raw": found.get("raw"), "handmade": found["handmade"],
    }


def _mode(source: str) -> str:
    return live.mode_of(source) or "failed"


@ai_router.post("/try/{model}")
def try_sample(model: Literal["voice", "spark", "sam", "spark-open"], request: Request) -> dict:
    """Run one model on a bundled sample. Writes nothing to any record (R9)."""
    settings = request.app.state.settings
    if model == "spark-open":
        return {"model": model, "mode": "Sample", "text": live.prepared("spark-open-sample.json")["text"]}
    if model == "voice":
        raw = _sample_bytes(settings, "kumar-orders.wav")
        try:
            heard = live.transcribe(settings, raw, "kumar-orders.wav", "audio/wav")
        except live.NotHeard as exc:
            raise HTTPException(status_code=exc.status, detail=exc.detail) from exc
        return {"model": model, "mode": _mode(heard["source"]), "text": heard["text"]}
    if model == "spark":
        raw = _sample_bytes(settings, "monitor-88-54.png")
        found = live.read_photo(settings, "monitor", raw, "monitor-88-54.png", "image/png")
        evidence_body = _sample_evidence("monitor", "monitor-88-54.png", {**found, "frames": None}, None)
        return {"model": model, "mode": _mode(found["source"]), "evidence": evidence_body}
    _sample_bytes(settings, "tray-hernia.png")  # 409 when a key is set and the file is missing
    plan = tray_plan("hernia-repair")
    rows = expected_for_tray(plan)
    found = live.segment_photos(settings, [_sample_path("tray-hernia.png")], [r["concept"] for r in rows],
                                "tray-hernia.png", live_ok=TRAY_LIVE)
    result = compare(rows, found["detections"], found["source"], "photos")
    return {"model": model, "mode": _mode(found["source"]),
            "evidence": _sample_evidence("tray", "tray-hernia.png", found, result)}


@ai_router.get("/samples/{name}")
def get_sample(name: str) -> FileResponse:
    """An allow-listed sample image, nothing else."""
    path = _sample_path(name) if name in SHOWN else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Sample not found")
    return FileResponse(path, headers={"X-Content-Type-Options": "nosniff"})

"""The ten endpoints from the build spec, plus /health."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from app.agent.reconciler import explain_case
from app.config import BANNER
from app.core.ledger import ledger_rows, open_discrepancies
from app.engine import track_path
from app.media_pipeline import SamCallFailed, check_video_ready, run_recorded_video
from app.models import CaseIn, ResolveIn, ZonesIn
from app.report.count_sheet import write_count_sheet
from app.scenarios import get_scenario

router = APIRouter()


def _engine(request: Request):
    return request.app.state.engine


def _store(request: Request):
    return request.app.state.store


def _missing(exc: KeyError) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Not found: {exc}")


@router.get("/health")
def health(request: Request) -> dict:
    settings = request.app.state.settings
    return {
        "ok": True,
        "banner": BANNER,
        "adapters": {
            "sam-3.1": {
                "file": "backend/app/adapters/sam.py",
                "configured": settings.sam_configured,
                "model": settings.sam_model,
                "note": "Uploaded video or still image. No live frame socket.",
            },
            "muse-voice-transcribe": {
                "file": "backend/app/adapters/voice.py",
                "configured": settings.voice_configured,
                "model": settings.voice_model,
                "note": "Turn-level timestamps. Word-level timestamps are not provided.",
            },
            "muse-spark-open": {
                "file": "backend/app/adapters/spark_open.py",
                "configured": settings.spark_open_configured,
                "model": settings.spark_open_model,
                "note": "Baseten chat completions. Tool calling is documented, not yet called from this machine.",
            },
            "muse-spark-1.3": {
                "file": "backend/app/adapters/spark.py",
                "configured": settings.spark_configured,
                "model": settings.spark_model,
                "note": "Second look only, and only when R5 fires.",
            },
        },
    }


@router.post("/cases")
def create_case(body: CaseIn, request: Request) -> dict:
    return _engine(request).create_case(body.label, body.item_types)


@router.post("/cases/{case_id}/zones")
def save_zones(case_id: str, body: ZonesIn, request: Request) -> dict:
    try:
        zones = _engine(request).set_zones(case_id, [zone.model_dump() for zone in body.zones])
    except KeyError as exc:
        raise _missing(exc) from exc
    return {"case_id": case_id, "zones": zones}


@router.post("/cases/{case_id}/upload")
async def upload_case(
    case_id: str,
    request: Request,
    scenario: str | None = None,
    file: UploadFile | None = File(default=None),
) -> dict:
    engine = _engine(request)
    try:
        engine._require_case(case_id)
    except KeyError as exc:
        raise _missing(exc) from exc
    if scenario:
        try:
            return engine.replay(case_id, get_scenario(scenario))
        except KeyError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if file is None:
        raise HTTPException(status_code=400, detail="Send a scenario name or a file.")
    raw = await file.read()
    name = (file.filename or "").lower()
    if name.endswith(".json") or (raw[:1] in (b"{", b"[")):
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail="Scenario JSON could not be read.") from exc
        try:
            return engine.replay(case_id, payload)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        check_video_ready(engine, case_id)
    except RuntimeError as exc:
        # A refused clip (no key, no zones) is never written to disk.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings = request.app.state.settings
    # Path(...).name drops any folder part, so "../../x.mp4" stays in this case's folder.
    name = Path(file.filename or "").name
    dest = settings.data_dir / "uploads" / case_id / (name if name not in ("", "..") else "clip.mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(raw)
    try:
        return run_recorded_video(engine, case_id, dest)
    except SamCallFailed as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except RuntimeError as exc:
        # A clip ffmpeg cannot read, or a missing ffmpeg, is not kept on disk.
        dest.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/cases/{case_id}/ledger")
def get_ledger(case_id: str, request: Request) -> dict:
    store = _store(request)
    if store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case_id, "items": ledger_rows(store.events(case_id))}


@router.get("/cases/{case_id}/discrepancies")
def get_discrepancies(case_id: str, request: Request) -> dict:
    store = _store(request)
    if store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"case_id": case_id, "discrepancies": open_discrepancies(store.events(case_id))}


@router.post("/discrepancies/{discrepancy_id}/resolve")
def resolve(discrepancy_id: str, body: ResolveIn, request: Request) -> dict:
    try:
        return _engine(request).resolve(discrepancy_id, body.reason, body.by)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discrepancy not found") from exc


@router.post("/cases/{case_id}/close")
def close_case(case_id: str, request: Request) -> dict:
    engine = _engine(request)
    store = _store(request)
    if store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    decision = engine.gate(case_id)
    if not decision["ok"]:
        raise HTTPException(
            status_code=409,
            detail={
                "ok": False,
                "status": "blocked",
                "banner": BANNER,
                "blockers": decision["blockers"],
                "message": "Open count discrepancies remain. A human can record a reason for each one.",
            },
        )
    explained = explain_case(store, request.app.state.settings, case_id)
    case = store.get_case(case_id)
    pdf_path = request.app.state.settings.report_dir / case_id / "count-sheet.pdf"
    write_count_sheet(
        pdf_path,
        case=case,
        ledger=decision["ledger"],
        discrepancies=open_discrepancies(store.events(case_id)),
        narrative=explained["narrative"],
        model=explained["model"],
        trace=explained["trace"],
    )
    store.save_report(case_id, explained["narrative"], str(pdf_path), explained["model"])
    if explained["model"] != "template":
        store.log_model_call(
            explained["model"],
            "app/adapters/spark_open.py",
            "reconciler narrative",
            case_id,
        )
    return {
        "ok": True,
        "status": "reconciled",
        "banner": BANNER,
        "narrative": explained["narrative"],
        "model": explained["model"],
        "trace": explained["trace"],
        "report_url": f"/cases/{case_id}/report.pdf",
    }


@router.get("/cases/{case_id}/report.pdf")
def report_pdf(case_id: str, request: Request):
    report = _store(request).get_report(case_id)
    if report is None:
        raise HTTPException(status_code=409, detail="The count sheet is written when the case is reconciled.")
    path = Path(report["path"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Count sheet file is missing")
    return FileResponse(path, media_type="application/pdf", filename="count-sheet.pdf")


@router.get("/frames/{frame_id}")
def frame_image(frame_id: str, request: Request):
    frame = _store(request).get_frame(frame_id)
    if frame is None:
        raise HTTPException(status_code=404, detail="Frame not found")
    return FileResponse(frame["path"], media_type="image/png")


@router.get("/tracks/{track_id}")
def track_detail(track_id: str, request: Request, case_id: str | None = None) -> dict:
    store = _store(request)
    if case_id is None:
        cached = store.find_track(track_id)
        if cached is None:
            raise HTTPException(status_code=404, detail="Track not found. Pass case_id if the id is shared.")
        case_id = cached["case_id"]
    if store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    events = store.events(case_id)
    return {
        "case_id": case_id,
        "track_id": track_id,
        "cached": store.track(case_id, track_id),
        "path": track_path(events, track_id),
    }


@router.get("/cases/{case_id}/events")
def list_events(case_id: str, request: Request) -> dict:
    """Playback support for the live screen. The spec's ledger is still the record."""
    store = _store(request)
    if store.get_case(case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return {"events": store.events(case_id), "transcript": store.transcripts(case_id)}

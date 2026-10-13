"""Letterhead template routes (contract 4.6)."""
from __future__ import annotations

import sys
import uuid
from typing import Any

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from doctor_dictation import db as dbmod
from doctor_dictation.config import get_settings
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import PdfUnavailable, render_prescription, validate_layout
from doctor_dictation.templates import TemplateError, service

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])

SAMPLE = {
    "patientName": "Sample Patient", "ageSex": "34 / F", "opNo": "OP-0001", "review": "Review after 5 days",
    "rx": [
        {"form": "Tab.", "name": "Paracetamol", "strength": "500 mg", "dose": "1-0-1", "timing": "After food",
         "duration": "3 days", "instructions": "", "status": "verified"},
        {"form": "Syr.", "name": "Ascoril", "strength": "", "dose": "5 ml 1-0-1", "timing": "",
         "duration": "5 days", "instructions": "", "status": "verified"},
    ],
}


class EditBody(BaseModel):
    # Shape is validated by service.edit so a malformed body answers 400, not FastAPI's 422/500.
    profile: Any = Field(default_factory=dict)
    lines: Any = Field(default_factory=list)


def _open():
    """New connection; lazily purge expired drafts (and their files). A failed purge is logged, never fatal."""
    conn = dbmod.get_conn()
    try:
        service.purge_expired(conn, get_settings())
    except Exception as exc:  # noqa: BLE001 - housekeeping must not fail the request
        print(f"warning: template draft purge failed: {exc}", file=sys.stderr)
    return conn


def _actor(request: Request):
    return getattr(request.state, "username", None)


def _err(exc: TemplateError) -> JSONResponse:
    return JSONResponse(status_code=exc.status, content={"error": str(exc)})


def purge_on_startup() -> None:
    try:
        _open().close()
    except Exception as exc:  # noqa: BLE001 - a purge problem must not stop the app booting
        print(f"warning: template startup purge failed: {exc}", file=sys.stderr)


@router.post("", status_code=201)
async def upload_template(request: Request, image: UploadFile | None = File(None)):
    if image is None:
        return JSONResponse(status_code=400, content={"error": "image file is required"})
    settings = get_settings()
    raw = await image.read(settings.template_max_image_bytes + 1)
    conn = _open()
    try:
        return JSONResponse(status_code=201, content=await service.upload(conn, raw, settings, actor=_actor(request)))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.get("/active")
def get_active():
    conn = _open()
    try:
        active = service.get_active(conn)
        return active if active else JSONResponse(status_code=404, content={"error": "no active template"})
    finally:
        conn.close()


@router.post("/deactivate")
def deactivate(request: Request):
    conn = _open()
    try:
        return {"deactivated": service.deactivate(conn, actor=_actor(request))}
    finally:
        conn.close()


@router.get("/{template_id}/preview.pdf")
def preview(template_id: int):
    conn = _open()
    try:
        row = tdb.get_template(conn, template_id)
        if row is None or row["status"] == "archived":
            return JSONResponse(status_code=404, content={"error": "template not found"})
        v = service.view(row)
        out = service.templates_dir() / f"preview_{template_id}_{uuid.uuid4().hex}.pdf"
        out.parent.mkdir(parents=True, exist_ok=True)
        meta = {"date": dbmod._utcnow()[:10], "opNo": SAMPLE["opNo"], "patientName": SAMPLE["patientName"],
                "profile": v["profile"], "logo": service.logo_data_uri(row["logo_path"])}
        try:
            layout = validate_layout({**v["layout"], "profile": v["profile"]})
            render_prescription(SAMPLE, meta, out, layout=layout)
        except PdfUnavailable:
            return JSONResponse(status_code=503, content={"error": "PDF renderer unavailable"})
        return FileResponse(out, media_type="application/pdf", background=BackgroundTask(out.unlink, missing_ok=True))
    finally:
        conn.close()


@router.put("/{template_id}")
def edit_template(template_id: int, body: EditBody, request: Request):
    conn = _open()
    try:
        return service.edit(conn, template_id, body.profile, body.lines, actor=_actor(request))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.post("/{template_id}/accept")
def accept_template(template_id: int, request: Request):
    conn = _open()
    try:
        return service.accept(conn, template_id, actor=_actor(request))
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()


@router.delete("/{template_id}")
def discard_template(template_id: int, request: Request):
    conn = _open()
    try:
        service.discard(conn, template_id, actor=_actor(request))
        return Response(status_code=204)
    except TemplateError as exc:
        return _err(exc)
    finally:
        conn.close()

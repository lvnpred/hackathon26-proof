"""Patients, encounters, today list and documents (verify gate + fail-soft PDF)."""
import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation.api.profile import profile_dict
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.safety import screen_unverified
from doctor_dictation.db.opno import create_patient_with_new_op
from doctor_dictation.pdf import PdfUnavailable, render_prescription
from doctor_dictation.templates import service as template_service

router = APIRouter()
log = logging.getLogger(__name__)


class PatientCreate(BaseModel):
    name: str
    age_sex: str = ""
    op_no: str | None = None


class EncounterCreate(BaseModel):
    patient_id: int
    doctor_id: int | None = None
    op_no: str | None = None
    status: str = "draft"
    consent_at: str | None = None


@router.get("/api/v1/patients")
def list_patients(limit: int = 100, offset: int = 0):
    conn = dbmod.get_conn()
    try:
        return [dict(r) for r in dbmod.list_patients(conn, limit=limit, offset=offset)]
    finally:
        conn.close()


@router.post("/api/v1/patients", status_code=201)
def create_patient(req: PatientCreate):
    conn = dbmod.get_conn()
    try:
        pid = dbmod.create_patient(conn, req.name, req.age_sex, req.op_no)
        return dict(dbmod.get_patient(conn, pid))
    finally:
        conn.close()


@router.get("/api/v1/encounters")
def list_encounters(patient_id: int | None = None, limit: int = 100, offset: int = 0):
    conn = dbmod.get_conn()
    try:
        rows = dbmod.list_encounters(conn, patient_id=patient_id, limit=limit, offset=offset)
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.post("/api/v1/encounters", status_code=201)
def create_encounter(req: EncounterCreate):
    conn = dbmod.get_conn()
    try:
        try:
            eid = dbmod.create_encounter(
                conn,
                req.patient_id,
                doctor_id=req.doctor_id,
                op_no=req.op_no,
                status=req.status,
                consent_at=req.consent_at,
            )
        except sqlite3.IntegrityError:
            return JSONResponse(
                status_code=404,
                content={"error": f"patient_id {req.patient_id} not found"},
            )
        return dict(dbmod.get_encounter(conn, eid))
    finally:
        conn.close()


@router.get("/api/v1/encounters/today")
def list_today_encounters():
    """Saved documents for the server-local calendar day (the "Today" sidebar)."""
    conn = dbmod.get_conn()
    try:
        start, end = dbmod.local_day_bounds_utc()
        rows = dbmod.list_documents_between(conn, start, end)
        return [dict(r) for r in rows]
    finally:
        conn.close()


class DocumentCreate(BaseModel):
    structured: dict = {}
    confirmed_rows: list[int] = []
    engine: str = ""
    transcript_sha256: str = ""
    document_id: int | None = None


def _pdf_inputs(conn, structured, day):
    """Render meta + layout for a document: the ONE place save and re-print share.

    The clinic's active letterhead template supplies layout and logo; any
    template problem (corrupt row, missing logo, bad layout) drops to the plain
    profile header (``layout`` None, no logo).
    """
    meta = {
        "date": day.isoformat(),
        "opNo": structured.get("opNo") or "",
        "patientName": structured.get("patientName") or "",
        "profile": profile_dict(dbmod.get_profile(conn)),
    }
    layout = None
    try:
        layout, logo_path = template_service.active_layout_for_save(conn)
        if layout is not None and logo_path:
            logo = template_service.logo_data_uri(logo_path)
            if logo:
                meta["logo"] = logo
    except Exception:
        log.warning("active template unusable; saving with the plain header", exc_info=True)
        layout = None
        meta.pop("logo", None)
    return meta, layout


def _render_with_fallback(structured, meta, layout, out_path):
    """Render; a failing template layout retries once with the plain header."""
    try:
        return render_prescription(structured, meta, out_path, layout=layout)
    except PdfUnavailable:
        raise
    except Exception:
        if layout is None:
            raise
        log.warning("layout render failed; retrying with the plain header", exc_info=True)
        meta.pop("logo", None)
        return render_prescription(structured, meta, out_path, layout=None)


@router.post("/api/v1/documents")
def create_document(req: DocumentCreate):
    """Save & Print: enforce the verify gate, then persist encounter/document/audit.

    The gate blocks while any Rx row is not ``verified`` and the doctor did not
    confirm it. Once clear, the form is validated and the patient (matched by OP
    number), a finalized encounter, the document, and an audit entry are
    recorded.

    Saving a *reopened* "today" document passes ``document_id``: the gate still
    runs first, then that existing document row is updated in place (no
    duplicate), reusing its encounter and that encounter's patient. The patient
    is not upserted from the payload on this path.
    """
    structured = req.structured if isinstance(req.structured, dict) else {}
    block = screen_unverified(structured, req.confirmed_rows)
    if block:
        return JSONResponse(
            status_code=409,
            content={"error": "unverified medicines", "block": block},
        )
    validated, _warnings = validate_structured(structured, "")
    # The incoming form is already doctor-verified. Re-grounding against a form
    # with no transcript would flip every row to `unverified-name`, so restore
    # the verification state the doctor finalized (rows dropped/recomputed with
    # no prior match are left as `validate_structured` produced them).
    preserve_untouched_rx_status(structured, {}, validated)
    conn = dbmod.get_conn()
    try:
        resave = req.document_id is not None
        if resave:
            existing = dbmod.get_document(conn, req.document_id)
            if existing is None:
                return JSONResponse(
                    status_code=404,
                    content={"error": f"document_id {req.document_id} not found"},
                )
            # Re-save touches the DOCUMENT only: keep its encounter and that
            # encounter's patient. Never upsert a patient from the payload, so a
            # payload naming another patient cannot rebind/rename a row, and a
            # blank OP cannot leak a fresh patient on every re-save.
            encounter_id = existing["encounter_id"]
            enc = dbmod.get_encounter(conn, encounter_id)
            patient_id = enc["patient_id"]
            # A blank OP on re-save keeps the number already on the record (and
            # shows it on the PDF); a typed one is left in the document only.
            if not (validated.get("opNo") or "").strip() and enc["op_no"]:
                validated["opNo"] = enc["op_no"]
        else:
            name = validated.get("patientName") or ""
            age_sex = validated.get("ageSex") or ""
            if (validated.get("opNo") or "").strip():
                patient_id = dbmod.upsert_patient(
                    conn, name, age_sex, validated.get("opNo") or None
                )
            else:
                # No OP dictated: generate one. A fresh patient row, never an
                # upsert, so a generated number cannot merge into/rename anyone.
                patient_id, validated["opNo"] = create_patient_with_new_op(
                    conn, name, age_sex
                )
            encounter_id = dbmod.create_encounter(
                conn,
                patient_id,
                op_no=validated.get("opNo") or None,
                status="finalized",
            )
        # Render the prescription PDF, but fail soft: a renderer or storage
        # problem must never block Save. On any failure (no Playwright/Chromium,
        # unwritable path, ...) pdf_path stays None and the doctor falls back to
        # browser print-to-PDF.
        pdf_path = None
        out_path = dbmod.pdf_dir() / f"encounter_{encounter_id}.pdf"
        meta, layout = _pdf_inputs(conn, validated, datetime.now().astimezone().date())  # server-local day, same as the OP number
        try:
            pdf_path = str(_render_with_fallback(validated, meta, layout, out_path))
        except Exception:
            pdf_path = None
        if resave:
            changed = dbmod.update_document(
                conn,
                req.document_id,
                validated,
                engine=req.engine or None,
                finalized_at=dbmod._utcnow(),
                transcript_sha=req.transcript_sha256 or None,
                pdf_path=pdf_path,
            )
            if not changed:  # row vanished between the lookup and the update
                return JSONResponse(
                    status_code=404,
                    content={"error": f"document_id {req.document_id} not found"},
                )
            document_id = req.document_id
            action = "resave"
        else:
            document_id = dbmod.save_document(
                conn,
                encounter_id,
                req.transcript_sha256,
                validated,
                engine=req.engine or None,
                finalized_at=dbmod._utcnow(),
                pdf_path=pdf_path,
            )
            action = "finalize"
        dbmod.log_audit(
            conn,
            action=action,
            entity="encounter",
            entity_id=str(encounter_id),
            detail={
                "document_id": document_id,
                "engine": req.engine,
                "confirmed_rows": list(req.confirmed_rows),
            },
        )
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "document_id": document_id,
            "op_no": _record_op_no(conn, encounter_id),
        }
    finally:
        conn.close()


def _record_op_no(conn, encounter_id) -> str:
    """The OP number now on the encounter ("" when none)."""
    return (dbmod.get_encounter(conn, encounter_id)["op_no"]) or ""


@router.get("/api/v1/documents/{document_id}")
def get_document(document_id: int):
    """Load a saved document back onto the sheet (re-open / re-print)."""
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        return {
            "document_id": row["id"],
            "structured": json.loads(row["structured_json"])
            if row["structured_json"]
            else {},
            "engine": row["engine"] or "",
            "transcript_sha256": row["transcript_sha"],
            "created_at": row["created_at"],
        }
    finally:
        conn.close()


def _stored_pdf(row):
    """The document's stored PDF, only if it exists inside the pdf dir."""
    raw = row["pdf_path"]
    if not raw:
        return None
    try:
        p = Path(raw).resolve()
        if p.is_file() and p.is_relative_to(dbmod.pdf_dir().resolve()):
            return p
    except (OSError, ValueError):
        pass
    return None


def _pdf_response(path, document_id):
    return FileResponse(
        path,
        media_type="application/pdf",
        content_disposition_type="inline",
        filename=f"prescription-{document_id}.pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.get("/api/v1/documents/{document_id}/pdf")
def get_document_pdf(document_id: int):
    """The saved document as a PDF: the stored file, else rendered on demand."""
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        stored = _stored_pdf(row)
        if stored is not None:
            return _pdf_response(stored, document_id)
        try:
            structured = json.loads(row["structured_json"]) if row["structured_json"] else {}
            created = datetime.fromisoformat(row["created_at"].replace("Z", "+00:00"))
            meta, layout = _pdf_inputs(conn, structured, created.astimezone().date())
            encounter_id = row["encounter_id"]
        except Exception:
            log.warning("cannot prepare on-demand PDF", exc_info=True)
            return _pdf_unavailable()
    finally:
        conn.close()  # no DB handle is open while Chromium runs
    try:
        out_path = dbmod.pdf_dir() / f"encounter_{encounter_id}.pdf"
        rendered = _render_with_fallback(structured, meta, layout, out_path)
    except Exception:
        log.warning("on-demand PDF render failed", exc_info=True)
        return _pdf_unavailable()
    conn = dbmod.get_conn()
    try:
        dbmod.set_document_pdf_path(conn, document_id, str(rendered))
    finally:
        conn.close()
    return _pdf_response(rendered, document_id)


def _pdf_unavailable():
    return JSONResponse(
        status_code=503,
        content={"error": "PDF rendering is not available on this server", "fallback": "browser"},
    )

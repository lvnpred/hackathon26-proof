"""Patients, encounters, today list and documents (verify gate + fail-soft PDF)."""
import json
import logging
import sqlite3
from pathlib import Path

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from doctor_dictation import db as dbmod
from doctor_dictation.api import authorship, visit
from doctor_dictation.api.pastday import is_past, past_refusal, visit_day, visit_day_iso
from doctor_dictation.api.formulary import learn_doctor_generics, learn_from_save, use_clinic_layer
from doctor_dictation.api.investigations import remember_from_save, use_investigations
from doctor_dictation.config import get_settings
from doctor_dictation.core import followup, investigations
from doctor_dictation.core.correction import preserve_untouched_rx_status
from doctor_dictation.core.determinism import validate_structured
from doctor_dictation.core.doctor_generic import settle
from doctor_dictation.core.safety import mark_confirmed, screen_unverified, strip_grounding_markers
from doctor_dictation.db import authorship as adb
from doctor_dictation.db.opno import create_patient_with_new_op
from doctor_dictation.pdf import PdfUnavailable, render_prescription
from doctor_dictation.providers.stt.factory import make_stt
from doctor_dictation.templates import service as template_service

router = APIRouter()
log = logging.getLogger(__name__)


def speech_settings() -> dict:
    """The speech settings a first save records in documents.model_versions, so edit rates can be compared with
    hints and silence trimming on and off. Read at save time: they change only when the server restarts."""
    s = get_settings()
    try:
        engine = make_stt(s).active_name()
    except ValueError:  # bad STT_CHAIN, or stub without ALLOW_STUB_PROVIDERS (as /api/health reports it)
        engine = "misconfigured"
    return {"stt": {"engine": engine, "hints": s.stt_use_hints, "trim": s.stt_trim_silence}}


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
def create_encounter(req: EncounterCreate, request: Request):
    """Signed in, the encounter is the signed-in doctor's: a body ``doctor_id`` is ignored."""
    ident = authorship.identity(request)
    conn = dbmod.get_conn()
    try:
        try:
            eid = dbmod.create_encounter(
                conn,
                req.patient_id,
                doctor_id=ident.user_id if ident else req.doctor_id,
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
def list_today_encounters(request: Request, scope: str = "mine", day: str | None = Query(None, alias="date")):
    """Saved documents for one clinic-zone calendar day (the "Today" sidebar): ``date=YYYY-MM-DD``, default today.

    A malformed or future ``date`` is a 400. Signed in: ``scope=mine`` (default) keeps the signed-in doctor's prescriptions, ``scope=clinic`` the whole
    clinic; rows gain ``author_id`` and ``doctor_name``. Single-database mode: every row, in the old shape (``scope`` is ignored).
    """
    ident = authorship.identity(request)
    if ident is not None and scope not in ("mine", "clinic"):
        return JSONResponse(status_code=400, content={"error": "scope must be mine or clinic"})
    listed = visit.today() if day is None else visit.parse_day(day)
    if listed is None:
        return JSONResponse(status_code=400, content={"error": "date must be YYYY-MM-DD"})
    if listed > visit.today():
        return JSONResponse(status_code=400, content={"error": "date is in the future"})
    conn = dbmod.get_conn()
    try:
        start, end = visit.day_bounds_utc(listed)
        if ident is None:
            return [dict(r) for r in dbmod.list_documents_between(conn, start, end)]
        return adb.list_today(conn, start, end, ident.user_id if scope == "mine" else None)
    finally:
        conn.close()


class DocumentCreate(BaseModel):
    structured: dict = {}
    confirmed_rows: list[int] = []
    remember_generics: list[int] = []     # rows whose doctor generic may replace a listed one for the clinic (Q20)
    remember_investigations: list = []    # indexes into the SAVED investigations; a bad one is ignored, never a 422
    engine: str = ""
    transcript_sha256: str = ""
    document_id: int | None = None


def _pdf_inputs(conn, structured, day, encounter_id):
    """Render meta + layout for a document: the ONE place save and re-print share.

    ``meta["profile"]`` carries the clinic's fields and the AUTHOR's doctor fields (never the viewer's).
    The author's own active letterhead, else the clinic's, supplies layout, logo and the doctors list; any
    template problem (corrupt row, missing logo, bad layout) drops to the plain
    profile header (``layout`` None, no logo).
    """
    meta = {
        "date": visit.date_text(day),         # "17 Oct 2026", the same locale as the page
        "opNo": structured.get("opNo") or "",
        "patientName": structured.get("patientName") or "",
        "profile": adb.print_profile(conn, encounter_id),
    }
    layout = None
    try:
        author_id = adb.encounter_author_id(conn, encounter_id)                          # never the viewer
        meta["authored"] = author_id is not None        # an author's blank doctor field stays blank, never the pad's
        row = template_service.active_row_for(conn, author_id)        # ONE lookup: layout and doctors from the same row
        layout, logo_path = template_service.active_layout_for_save(conn, author_id, row)   # the author's own, else the clinic's
        if layout is not None:
            meta["doctors"] = template_service.print_doctors(conn, author_id, row)          # None = the author
        if layout is not None and logo_path:
            logo = template_service.logo_data_uri(logo_path)
            if logo:
                meta["logo"] = logo
    except Exception:
        log.warning("active template unusable; saving with the plain header", exc_info=True)
        layout = None
        meta.pop("logo", None)
        meta.pop("doctors", None)
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


@router.post("/api/v1/documents", dependencies=[Depends(use_clinic_layer)])
def create_document(req: DocumentCreate, request: Request, _ix: None = Depends(use_investigations)):
    """Save & Print: enforce the verify gate, then persist encounter/document/audit.

    The gate blocks while any Rx row is not ``verified`` and the doctor did not
    confirm it. Once clear, the form is validated and the patient (matched by OP
    number), a finalized encounter, the document, and an audit entry are
    recorded.

    Saving a *reopened* "today" document passes ``document_id``: the gate still
    runs first, then that existing document row is updated in place (no
    duplicate), reusing its encounter and that encounter's patient. The patient
    is not upserted from the payload on this path.

    Signed in: the first save records the saver as author (``encounters.doctor_id``) and saver
    (``documents.finalized_by``); a re-save needs ``document.edit`` (only the author; 403 otherwise),
    keeps the author and records the new saver.
    """
    ident = authorship.identity(request)
    if req.document_id is not None:
        denied = authorship.check_document(request, "document.edit", req.document_id)
        if denied is not None:
            return denied
        past = past_refusal(req.document_id)          # before the verify gate: a past day is never re-saved
        if past is not None:
            return past
    structured = req.structured if isinstance(req.structured, dict) else {}
    block = screen_unverified(structured, req.confirmed_rows)
    ix_block = investigations.screen(structured)
    if block and not ix_block:
        return JSONResponse(
            status_code=409,
            content={"error": "unverified medicines", "block": block},
        )
    if ix_block:
        return JSONResponse(status_code=409, content={
            "error": "unverified medicines" if block else "investigations not dictated",
            "block": block, "investigations_block": ix_block})
    validated, _warnings = validate_structured(structured, "", vitals_typed=True)
    validated["investigations"] = investigations.regrade(validated.get("investigations"))
    # The incoming form is already doctor-verified. Re-grounding against a form
    # with no transcript would flip every row to `unverified-name`, so restore
    # the verification state the doctor finalized (rows dropped/recomputed with
    # no prior match are left as `validate_structured` produced them).
    preserve_untouched_rx_status(structured, {}, validated)
    strip_grounding_markers(validated)  # the gate passed: each row is verified or confirmed, so no "confirm with doctor" text prints
    settle(validated)  # the gate passed: no doctor generic is pending any more
    mark_confirmed(structured, req.confirmed_rows, validated)  # a reopen shows the doctor's confirmations, not Confirm again
    day = visit.today()  # a NEW document's visit day; a re-save keeps the day fixed at first save (below)
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
            day = visit_day(existing) or day  # fixed at first save: the screen, the PDF and the review date share it
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
                doctor_id=ident.user_id if ident else None,
                op_no=validated.get("opNo") or None,
                status="finalized",
            )
        # Render the prescription PDF, but fail soft: a renderer or storage
        # problem must never block Save. On any failure (no Playwright/Chromium,
        # unwritable path, ...) pdf_path stays None and the doctor falls back to
        # browser print-to-PDF.
        followup.stamp(validated, day)  # one visit day for the review date and the PDF
        pdf_path = None
        out_path = dbmod.pdf_dir() / f"encounter_{encounter_id}.pdf"
        meta, layout = _pdf_inputs(conn, validated, day, encounter_id)  # the visit day: today for a first save, the stored day for a re-save
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
            if ident is not None:
                adb.set_finalized_by(conn, document_id, ident.user_id)
            action = "resave"
        else:
            document_id = dbmod.save_document(
                conn,
                encounter_id,
                req.transcript_sha256,
                validated,
                engine=req.engine or None,
                model_versions=speech_settings(),   # a re-save keeps the first save's: the draft came from those
                finalized_by=ident.user_id if ident else None,
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
        learn_from_save(conn, structured, req.confirmed_rows, document_id, ident.user_id if ident else None)
        learn_doctor_generics(conn, structured, req.confirmed_rows, req.remember_generics, document_id,
                              ident.user_id if ident else None)  # commits: after the document's own commit
        remember_from_save(conn, validated["investigations"], req.remember_investigations, document_id,
                           ident.user_id if ident else None)       # commits too; never raises
        return {
            "patient_id": patient_id,
            "encounter_id": encounter_id,
            "document_id": document_id,
            "op_no": _record_op_no(conn, encounter_id),
            "visit_date": day.isoformat(),             # the day the PDF and the review date used (fixed at first save)
        }
    finally:
        conn.close()


def _record_op_no(conn, encounter_id) -> str:
    """The OP number now on the encounter ("" when none)."""
    return (dbmod.get_encounter(conn, encounter_id)["op_no"]) or ""


@router.get("/api/v1/documents/{document_id}")
def get_document(document_id: int, request: Request):
    """Load a saved document back onto the sheet (re-open / re-print).

    Any user of the clinic may view (``document.view``). Signed in, the answer adds ``author`` (who wrote it,
    with the doctor fields it prints) and ``can_edit``, so the sheet opens read-only for a colleague's.
    """
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        denied = authorship.check(conn, request, "document.view", document_id)
        if denied is not None:
            return denied
        return {
            "document_id": row["id"],
            "structured": json.loads(row["structured_json"])
            if row["structured_json"]
            else {},
            "engine": row["engine"] or "",
            "transcript_sha256": row["transcript_sha"],
            "created_at": row["created_at"],
            "visit_date": visit_day_iso(row),          # the clinic-zone day the sheet shows (I3)
            "past": is_past(row),                      # an earlier day: the page opens it view and reprint only
            **authorship.author_view(conn, request, document_id),
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
def get_document_pdf(document_id: int, request: Request):
    """The saved document as a PDF: the stored file, else rendered on demand.

    Any user of the clinic may reprint (``document.reprint``); the doctor fields are the author's.
    """
    conn = dbmod.get_conn()
    try:
        row = dbmod.get_document(conn, document_id)
        if row is None:
            return JSONResponse(
                status_code=404,
                content={"error": f"document_id {document_id} not found"},
            )
        denied = authorship.check(conn, request, "document.reprint", document_id)
        if denied is not None:
            return denied
        stored = _stored_pdf(row)
        if stored is not None:
            return _pdf_response(stored, document_id)
        try:
            structured = json.loads(row["structured_json"]) if row["structured_json"] else {}
            encounter_id = row["encounter_id"]
            meta, layout = _pdf_inputs(conn, structured, visit_day(row) or visit.today(), encounter_id)
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

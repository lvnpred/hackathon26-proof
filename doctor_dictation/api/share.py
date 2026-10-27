"""Private download links, doctor side (plan FB-D, C2): attach the link to a saved prescription, show it, revoke it.

The public route that serves the stored PDF is separate. A link or QR problem never blocks Save.
"""
import logging
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from doctor_dictation import db as dbmod
from doctor_dictation import policy
from doctor_dictation.api import authorship, visit
from doctor_dictation.api.pastday import is_past
from doctor_dictation.config import get_settings
from doctor_dictation.db import authorship as adb
from doctor_dictation.db import share as sdb
from doctor_dictation.pdf.qr import qr_data_uri
from doctor_dictation.scope import current_scope, multi_clinic_enabled

log = logging.getLogger(__name__)
router = APIRouter()
SINGLE_SLUG = "local"            # single-database mode has no clinic slug
NO_LINK = {"error": "no share link for this prescription"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def clinic_slug() -> str:
    scope = current_scope() if multi_clinic_enabled() else None
    return scope.clinic_slug if scope is not None else SINGLE_SLUG


def public_base(request: Request) -> str:
    return get_settings().public_base_url or str(request.base_url).rstrip("/")


def link_url(base: str, slug: str, token: str) -> str:
    return f"{base}/s/{slug}/{token}"


def until_text(expires_at: str) -> str:
    return visit.date_text(visit.to_clinic(sdb.parse(expires_at)).date())


def attach(conn, meta: dict, encounter_id: int, request: Request, issue: bool) -> None:
    """Put ``meta["share"] = {"url", "until"}`` on the PDF inputs. ``issue`` (a save) creates or renews the link;
    a reprint only prints a link that is still live. Any store problem leaves ``meta`` without a QR."""
    try:
        now = _now()
        row = sdb.ensure_link(conn, encounter_id, now) if issue else sdb.link_for_encounter(conn, encounter_id)
        if sdb.is_live(row, now):
            meta["share"] = {"url": link_url(public_base(request), clinic_slug(), row["token"]),
                             "until": until_text(row["expires_at"])}
    except Exception as exc:             # nothing about a link may turn Save into a 500
        log.warning("share link not attached: %s", type(exc).__name__)


def _not_found(document_id):
    return JSONResponse(status_code=404, content={"error": f"document_id {document_id} not found"})


@router.get("/api/v1/documents/{document_id}/share")
def get_share(document_id: int, request: Request):
    with closing(dbmod.get_conn()) as conn:
        author = adb.document_author(conn, document_id)
        if author is None:
            return _not_found(document_id)
        denied = authorship.check(conn, request, "document.reprint", document_id)
        if denied is not None:
            return denied
        row = sdb.link_for_encounter(conn, author["encounter_id"])
        if row is None:
            return JSONResponse(status_code=404, content=NO_LINK)
        ident = authorship.identity(request)
        doc = dbmod.get_document(conn, document_id)
        url = link_url(public_base(request), clinic_slug(), row["token"])
        until = until_text(row["expires_at"])
        return {
            "url": url, "expires_at": row["expires_at"], "valid_until": until,
            "active": sdb.is_live(row, _now()), "revoked": row["revoked_at"] is not None,
            "renewable": doc is not None and not is_past(doc),    # a re-save issues a new link only on the visit day
            "can_revoke": ident is None or policy.can(ident, "share.revoke", author),
            "qr": qr_data_uri(url), "subject": "Your prescription",
            "message": f"Your prescription is ready to download (valid until {until}): {url}",
        }


@router.post("/api/v1/documents/{document_id}/share/revoke")
def revoke_share(document_id: int, request: Request):
    with closing(dbmod.get_conn()) as conn:
        author = adb.document_author(conn, document_id)
        if author is None:
            return _not_found(document_id)
        denied = authorship.check(conn, request, "share.revoke", document_id)
        if denied is not None:
            return denied
        ident = authorship.identity(request)
        if not sdb.revoke(conn, author["encounter_id"], getattr(ident, "user_id", None), _now()):
            return JSONResponse(status_code=404, content=NO_LINK)
        # the stored PDF carries the dead QR: drop it so the next Print renders without one
        dbmod.set_document_pdf_path(conn, document_id, None)
        dbmod.log_audit(conn, action="share.revoke", entity="share_link", entity_id=str(author["encounter_id"]))
        return {"revoked": True}


def stored_pdf_ok(conn, document_id, encounter_id, stored: Path) -> bool:
    """False when the stored PDF carries a QR whose link has expired or been revoked; its path is then cleared.

    No link row (saved before share links), a file written at or after the link died (the QR-free
    reprint), or a failed lookup or stat keeps the stored PDF.
    """
    try:
        row = sdb.link_for_encounter(conn, encounter_id)
        if row is None or sdb.is_live(row, _now()):
            return True
        dead_since = sdb.parse(row["revoked_at"] or row["expires_at"])
        written = datetime.fromtimestamp(stored.stat().st_mtime, timezone.utc)
        if written >= dead_since:
            return True
        dbmod.set_document_pdf_path(conn, document_id, None)
        return False
    except Exception as exc:    # never block a reprint; the type only, no token or name
        log.warning("share link check failed before reprint: %s", type(exc).__name__)
        return True

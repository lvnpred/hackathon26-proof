"""Private download links, patient side (plan FB-D, C2): ``GET /s/{slug}/{token}``, no login.

Serves only the stored PDF of a live link and never renders. Every miss (bad format, unknown clinic, unknown,
expired or revoked token, no stored PDF) gets the same 404 page, so the route is no oracle. The limiter answers
before any database is opened. Tokens never reach a log line: the app logs the link id, and ``MASK`` hides the
token in the uvicorn access log.
"""
import logging
import re
import sqlite3
import threading
from collections import OrderedDict, deque
from contextlib import closing
from pathlib import Path
from time import monotonic

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse

from doctor_dictation import db as dbmod
from doctor_dictation.api import persistence
from doctor_dictation.api import share as share_api
from doctor_dictation.db import share as sdb
from doctor_dictation.directory import get_clinic, open_directory
from doctor_dictation.scope import Scope, clinic_dir, multi_clinic_enabled, use_scope, valid_slug

log = logging.getLogger(__name__)
router = APIRouter()
LIMIT = 30                       # requests per client address per window (per worker)
WINDOW_S = 600
MAX_ADDRESSES = 10_000
_hits: "OrderedDict[str, deque]" = OrderedDict()
_lock = threading.Lock()

EXPIRED_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex"><title>Link expired</title>
<style>body{font-family:system-ui,sans-serif;margin:0;display:flex;min-height:100vh;align-items:center;
justify-content:center;background:#f6f7f9;color:#1d2733}main{max-width:26rem;margin:1rem;padding:1.5rem;
background:#fff;border-radius:10px;text-align:center}h1{font-size:1.25rem;margin:0 0 .75rem}p{margin:0;line-height:1.5}</style>
</head><body><main><h1>This link has expired</h1>
<p>Please ask the clinic for a new copy of your prescription.</p></main></body></html>"""
BUSY_HTML = "<!doctype html><meta charset=\"utf-8\"><meta name=\"robots\" content=\"noindex\"><p>Too many requests. Try again in a few minutes.</p>"
HEADERS = {"Cache-Control": "no-store", "X-Robots-Tag": "noindex", "Referrer-Policy": "no-referrer",
           "X-Content-Type-Options": "nosniff"}


def allow(ip: str, now: float) -> bool:
    """Sliding window: at most ``LIMIT`` requests per ``WINDOW_S`` for one address. Counts refused ones too."""
    # The address is the leftmost X-Forwarded-For entry, trustworthy only because Caddy replaces that header;
    # a CDN or trusted_proxies in front would make it spoofable.
    with _lock:
        hits = _hits.pop(ip, None) or deque()
        while hits and now - hits[0] >= WINDOW_S:
            hits.popleft()
        ok = len(hits) < LIMIT
        if ok:
            hits.append(now)
        _hits[ip] = hits
        while len(_hits) > MAX_ADDRESSES:
            _hits.popitem(last=False)
        return ok


class MaskShareTokens(logging.Filter):
    """Rewrite ``/s/<slug>/<token>`` in an access-log record to ``/s/<slug>/-``."""
    _PATH = re.compile(r"(/s/[^/\s?\"]+/)[^\s\"]+")

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple):
            record.args = tuple(self._PATH.sub(r"\1-", a) if isinstance(a, str) else a for a in record.args)
        return True


MASK = MaskShareTokens()


def _expired() -> HTMLResponse:
    return HTMLResponse(EXPIRED_HTML, status_code=404, headers=HEADERS)


def _clinic_open(request: Request, slug: str) -> bool:
    """True only for an existing, active, healthy clinic. Never creates a folder or a database."""
    if not multi_clinic_enabled():
        return slug == share_api.SINGLE_SLUG
    if not valid_slug(slug) or slug in getattr(request.app.state, "failed_clinics", frozenset()):
        return False
    with closing(open_directory()) as d:
        row = get_clinic(d, slug)
    return row is not None and row["status"] == "active" and (clinic_dir(slug) / "app.db").is_file()


def _find_pdf(token: str):
    """(link id, stored PDF path) of a live link, else None."""
    with closing(dbmod.get_conn()) as conn:
        link = sdb.find_by_token(conn, token)
        if not sdb.is_live(link, share_api._now()):
            return None
        doc = sdb.document_for_encounter(conn, link["encounter_id"])
        pdf = persistence._stored_pdf(doc) if doc is not None else None
        if pdf is None:
            return None
        dbmod.log_audit(conn, actor="public", role="public", action="share.open", entity="share_link",
                        entity_id=str(link["id"]))
        return link["id"], pdf


@router.get("/s/{slug}/{token}", include_in_schema=False)
def open_link(slug: str, token: str, request: Request):
    ip = request.client.host if request.client else "unknown"
    if not allow(ip, monotonic()):
        return HTMLResponse(BUSY_HTML, status_code=429, headers={**HEADERS, "Retry-After": str(WINDOW_S)})
    if not sdb.TOKEN_RE.fullmatch(token):
        return _expired()
    try:
        if not _clinic_open(request, slug):
            return _expired()
        with use_scope(Scope(slug)):
            found = _find_pdf(token)
    except (sqlite3.Error, OSError, ValueError):     # a locked database or unreadable file is a miss, never a 500
        return _expired()
    if found is None:
        return _expired()
    link_id, pdf = found
    log.info("share link opened: clinic %s, link %s", slug, link_id)
    return FileResponse(Path(pdf), media_type="application/pdf", filename="prescription.pdf",
                        content_disposition_type="inline", headers=HEADERS)

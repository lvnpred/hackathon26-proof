"""Template rules: quota, TTL, edit, accept, discard. Callers own the connection."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.db import templates as tdb
from doctor_dictation.pdf import LayoutError, validate_layout
from doctor_dictation.templates import TemplateError
from doctor_dictation.templates.builder import PROFILE_FIELDS as FIELDS, build_draft
from doctor_dictation.templates.images import clean_image

CLINIC = "default"
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def templates_dir() -> Path:
    """Private folder next to the DB; never under frontend/ or any static mount."""
    return dbmod.db_path().parent / "templates"


def original_path(template_id: int) -> Path:
    return templates_dir() / f"{template_id}_original.jpg"


def _unlink(*paths) -> None:
    for p in paths:
        if p:
            Path(p).unlink(missing_ok=True)


def view(row) -> dict:
    lay = json.loads(row["layout_json"])
    return {"id": row["id"], "status": row["status"],
            "layout": {k: v for k, v in lay.items() if k != "profile"}, "profile": lay.get("profile", {})}


def purge_expired(conn, settings, now=None) -> int:
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(hours=settings.template_draft_ttl_hours)).strftime(_FMT)
    rows = tdb.purge_expired_drafts(conn, cutoff)
    for r in rows:
        _unlink(r["logo_path"], original_path(r["id"]))
    return len(rows)


_DECODE_SLOTS = 2                    # a 40 MP decode costs seconds of CPU and hundreds of MB
_decode_gates: dict = {}             # one semaphore per event loop: a module-level one binds to the wrong loop


def _decode_gate() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    for dead in [k for k in _decode_gates if k.is_closed()]:
        del _decode_gates[dead]
    return _decode_gates.setdefault(loop, asyncio.Semaphore(_DECODE_SLOTS))


def _over_quota(conn, settings, now) -> bool:
    since = now.replace(hour=0, minute=0, second=0, microsecond=0).strftime(_FMT)
    return tdb.count_uploads_since(conn, CLINIC, since) >= settings.template_uploads_per_day


async def upload(conn, raw: bytes, settings, actor=None, now=None) -> dict:
    now = now or datetime.now(timezone.utc)
    purge_expired(conn, settings, now)
    if _over_quota(conn, settings, now):         # read-only and before the costly decode; a bad image still uses no quota
        raise TemplateError(429, "daily template upload limit reached")
    async with _decode_gate():
        jpeg = await asyncio.to_thread(clean_image, raw, max_bytes=settings.template_max_image_bytes,
                                       max_pixels=settings.template_max_pixels)
    if _over_quota(conn, settings, now):         # re-check: other uploads may have been logged while this one decoded
        raise TemplateError(429, "daily template upload limit reached")
    # Logged before the LLM call: each attempt costs a call, so a failure still counts.
    dbmod.log_audit(conn, actor=actor, action="template_upload", entity="template",
                    detail={"clinic": CLINIC, "bytes": len(raw)}, at=now.strftime(_FMT))
    draft = await build_draft(jpeg, settings)
    tid = tdb.create_template_draft(conn, draft.layout, CLINIC, created_at=now.strftime(_FMT))
    templates_dir().mkdir(parents=True, exist_ok=True)
    original_path(tid).write_bytes(jpeg)
    if draft.logo_jpeg:
        logo = templates_dir() / f"{tid}_logo.jpg"
        logo.write_bytes(draft.logo_jpeg)
        tdb.set_template_logo(conn, tid, str(logo))
    return view(tdb.get_template(conn, tid))


def _draft(conn, template_id):
    row = tdb.get_template(conn, template_id)
    if row is None:
        raise TemplateError(404, "template not found")
    if row["status"] != "draft":
        raise TemplateError(409, "only a draft can be changed")
    return row


def edit(conn, template_id: int, profile: dict, lines: list, actor=None) -> dict:
    row = _draft(conn, template_id)
    lay = json.loads(row["layout_json"])
    profile = {} if profile is None else profile
    lines = [] if lines is None else lines
    if not isinstance(profile, dict) or not isinstance(lines, list):
        raise TemplateError(400, "profile must be an object and lines a list")
    for key, value in profile.items():
        if key not in FIELDS or not isinstance(value, str):
            raise TemplateError(400, f"unknown or non-text profile field: {key}")
        lay["profile"][key] = value.strip()
    for ln in lines:
        if not isinstance(ln, dict) or not isinstance(ln.get("text"), str):
            raise TemplateError(400, "each line needs section, index and text")
        section, index = ln.get("section"), ln.get("index")
        if (section not in ("header", "footer") or isinstance(index, bool) or not isinstance(index, int)
                or not 0 <= index < len(lay[section])):
            raise TemplateError(400, "no such line")
        block = lay[section][index]
        if block.get("type") != "text" or "text" not in block:
            raise TemplateError(400, "only literal text lines can be edited")
        block["text"] = ln["text"].strip()
    try:
        validate_layout(lay)
    except LayoutError as exc:
        raise TemplateError(400, f"edit rejected: {exc}") from None
    tdb.update_template_layout(conn, template_id, lay)
    return view(tdb.get_template(conn, template_id))


def _merge_profile(existing: dict, details: dict) -> dict:
    """Letterhead value wins when non-blank; a blank one keeps the existing Profile value."""
    out = {}
    for k in FIELDS:
        new = details.get(k)
        new = new.strip() if isinstance(new, str) else ""
        out[k] = new or (existing.get(k) or "")
    return out


def _save_details(conn, layout_json: str) -> dict:
    """Merge the draft's clinic details into the Profile (all six fields written); return what was saved."""
    row = dbmod.get_profile(conn)
    existing = {k: row[k] for k in FIELDS} if row is not None else {}
    merged = _merge_profile(existing, json.loads(layout_json).get("profile", {}))
    dbmod.save_profile(conn, **merged)
    return merged


def accept(conn, template_id: int, actor=None) -> dict:
    row = _draft(conn, template_id)
    tdb.set_template_active(conn, template_id)
    _save_details(conn, row["layout_json"])
    _unlink(original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_accept", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})
    return view(tdb.get_template(conn, template_id))


def discard(conn, template_id: int, actor=None) -> None:
    row = _draft(conn, template_id)
    tdb.delete_template(conn, template_id)
    _unlink(row["logo_path"], original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_discard", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})


def use_details(conn, template_id: int, actor=None) -> dict:
    """Keep the built-in layout: save this draft's clinic details to the Profile, then discard the draft."""
    row = _draft(conn, template_id)
    saved = _save_details(conn, row["layout_json"])
    tdb.delete_template(conn, template_id)
    _unlink(row["logo_path"], original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_use_details", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})
    return {"profile": saved, "discarded": True}


def get_active(conn) -> dict | None:
    row = tdb.get_active_template(conn, CLINIC)
    return view(row) if row else None


def active_layout_for_save(conn):
    """(Layout, logo_path) of the active template, or (None, None) so saves use the built-in layout."""
    row = tdb.get_active_template(conn, CLINIC)
    if row is None:
        return None, None
    try:
        return validate_layout(json.loads(row["layout_json"])), row["logo_path"]
    except (LayoutError, ValueError):
        return None, None


def logo_data_uri(path) -> str | None:
    """The stored logo crop as a data URI for the PDF builder, or None when missing."""
    try:
        return "data:image/jpeg;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")
    except (OSError, TypeError):
        return None


def deactivate(conn, actor=None) -> bool:
    """Stop using the accepted letterhead: saves print on the built-in layout again."""
    row = tdb.get_active_template(conn, CLINIC)
    if row is None:
        return False
    tdb.deactivate_templates(conn, CLINIC)
    dbmod.log_audit(conn, actor=actor, action="template_deactivate", entity="template",
                    entity_id=str(row["id"]), detail={"clinic": CLINIC})
    return True

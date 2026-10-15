"""Template rules: quota, TTL, edit, accept, discard. Callers own the connection."""
from __future__ import annotations

import asyncio
import base64
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from doctor_dictation import db as dbmod
from doctor_dictation.db import details
from doctor_dictation.db import templates as tdb
from doctor_dictation.policy import can
from doctor_dictation.pdf import LayoutError, validate_layout
from doctor_dictation.textclean import clean_text
from doctor_dictation.templates import TemplateError, doctors
from doctor_dictation.templates.builder import PROFILE_FIELDS as FIELDS, build_draft
from doctor_dictation.templates.images import clean_image

CLINIC = "default"
SCOPES = ("clinic", "mine")
_FMT = "%Y-%m-%dT%H:%M:%SZ"


def templates_dir() -> Path:
    """Private folder next to the DB; never under frontend/ or any static mount."""
    return dbmod.db_path().parent / "templates"


def original_path(template_id: int) -> Path:
    return templates_dir() / f"{template_id}_original.jpg"


def _confined(path) -> Path | None:
    """``path`` resolved, only when it lies inside this clinic's templates folder. A stored path is never trusted:
    another clinic's file, a symlink or ``..`` out of the folder, and non-path values are refused."""
    if not path:
        return None
    try:
        p = Path(path).resolve()
        return p if p.is_relative_to(templates_dir().resolve()) else None
    except (OSError, TypeError, ValueError):
        return None


def _unlink(*paths) -> None:
    for p in paths:
        safe = _confined(p)
        if safe is not None and safe != templates_dir().resolve() and (safe.is_file() or not safe.exists()):
            safe.unlink(missing_ok=True)


def view(row) -> dict:
    lay = json.loads(row["layout_json"])
    return {"id": row["id"], "status": row["status"],
            "layout": {k: v for k, v in lay.items() if k != "profile"}, "profile": lay.get("profile", {}),
            "scope": "clinic" if row["owner_user_id"] is None else "mine",
            "doctors": {"mode": row["doctors_mode"], "ids": doctors.stored_ids(row)},
            "warnings": doctors.literal_warnings(lay)}


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


def _draft(conn, template_id, user=None):
    row = tdb.get_template(conn, template_id)
    if row is None or not visible(row, user):        # a colleague's personal letterhead does not exist for me
        raise TemplateError(404, "template not found")
    if row["status"] != "draft":
        raise TemplateError(409, "only a draft can be changed")
    return row


def edit(conn, template_id: int, profile: dict, lines: list, actor=None, user=None) -> dict:
    row = _draft(conn, template_id, user)
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
        new = clean_text(details.get(k))      # pad text is model output: no control, bidi or newline characters
        out[k] = new or (existing.get(k) or "")
    return out


def _save_my_doctor_details(conn, user_id: int, layout_json: str) -> dict:
    """Merge the pad's three doctor fields into this user's own details (a blank pad value keeps theirs)."""
    pad = json.loads(layout_json).get("profile", {})
    merged = _merge_profile(details.my_details(conn, user_id), pad)
    mine = {k: merged[k] for k in details.DOCTOR_KEYS}
    details.save_my_details(conn, user_id, **mine)
    return mine


def _save_details(conn, layout_json: str, user_id=None, clinic: bool = True, fill_doctor: bool = True) -> dict:
    """Merge the draft's details into the Profile; return what was saved. Single mode (``user_id`` None): all six
    fields into ``clinic_profile``. Signed in: the pad's doctor name, qualifications and registration number go to
    the accepting user's own details (a login name is independent of the printed doctor details; a blank pad value
    keeps theirs), and, when ``clinic`` is set, its three clinic fields go to the shared clinic details. A personal
    letterhead passes ``clinic=False`` so shared details stay untouched. ``fill_doctor`` False (doctors mode ``all`` or
    ``selected``, where the doctors block prints each user's own details) skips the doctor-field write."""
    if user_id is None:
        row = dbmod.get_profile(conn)
        existing = {k: row[k] for k in FIELDS} if row is not None else {}
        merged = _merge_profile(existing, json.loads(layout_json).get("profile", {}))
        dbmod.save_profile(conn, **merged)
        return merged
    saved = _save_my_doctor_details(conn, user_id, layout_json) if fill_doctor else details.my_details(conn, user_id)
    if clinic:
        row = dbmod.get_profile(conn)
        existing = {k: row[k] for k in FIELDS} if row is not None else {}
        merged = _merge_profile(existing, json.loads(layout_json).get("profile", {}))
        details.save_clinic_details(conn, merged["clinic_name"], merged["address"], merged["phone"])
        saved.update({k: merged[k] for k in details.CLINIC_KEYS})
    return saved


def _owner(scope, user_id):
    """``owner_user_id`` for an accept or stop: None for the clinic, the signed-in user for ``mine``."""
    if scope not in SCOPES:
        raise TemplateError(400, "scope must be clinic or mine")
    if scope == "clinic":
        return None
    if user_id is None:
        raise TemplateError(400, "sign in to keep a letterhead for your own prescriptions")
    return user_id


def visible(row, user) -> bool:
    """Drafts and the clinic letterhead belong to everyone in the clinic; a doctor's own only to that doctor.
    ``user`` None means single-database mode (no one signs in, nothing is personal): everything is visible."""
    return row is not None and (user is None or can(user, "letterhead.manage", dict(row)))


def accept(conn, template_id: int, actor=None, scope="clinic", user_id=None, user=None) -> dict:
    """Draft -> active for the whole clinic (default) or for the signed-in doctor's prescriptions only."""
    row = _draft(conn, template_id, user)
    owner = _owner(scope, user_id)
    tdb.set_template_active(conn, template_id, owner_user_id=owner)
    # a clinic letterhead's details also become the clinic's; a personal one changes nothing shared
    _save_details(conn, row["layout_json"], user_id=user_id, clinic=owner is None,
                  fill_doctor=row["doctors_mode"] == "author")
    _unlink(original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_accept", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"], "scope": scope})
    if owner is not None:
        dbmod.log_audit(conn, actor=actor, action="letterhead_scope_change", entity="template",
                        entity_id=str(template_id), detail={"scope": "mine"})
    return view(tdb.get_template(conn, template_id))


def discard(conn, template_id: int, actor=None, user=None) -> None:
    row = _draft(conn, template_id, user)
    tdb.delete_template(conn, template_id)
    _unlink(row["logo_path"], original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_discard", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})


def use_details(conn, template_id: int, actor=None, user_id=None, user=None) -> dict:
    """Keep the built-in layout: save this draft's clinic details to the Profile, then discard the draft."""
    row = _draft(conn, template_id, user)
    saved = _save_details(conn, row["layout_json"], user_id=user_id, fill_doctor=row["doctors_mode"] == "author")
    tdb.delete_template(conn, template_id)
    _unlink(row["logo_path"], original_path(template_id))
    dbmod.log_audit(conn, actor=actor, action="template_use_details", entity="template",
                    entity_id=str(template_id), detail={"clinic": row["clinic"]})
    return {"profile": saved, "discarded": True}


def get_active(conn) -> dict | None:
    row = tdb.get_active_template(conn, CLINIC)
    return view(row) if row else None


def current(conn, user_id=None) -> dict:
    """Both letterhead states for the Profile section: the clinic's and the signed-in doctor's own."""
    clinic = tdb.get_active_template(conn, CLINIC)
    mine = tdb.get_active_template(conn, CLINIC, user_id) if user_id is not None else None
    return {"clinic": view(clinic) if clinic else None, "mine": view(mine) if mine else None,
            "personal": user_id is not None}


def active_row_for(conn, author_id=None):
    """Spec 9.1: the author's own active letterhead, else the clinic's, else None (the built-in layout)."""
    if author_id is not None:
        own = tdb.get_active_template(conn, CLINIC, author_id)
        if own is not None:
            return own
    return tdb.get_active_template(conn, CLINIC)


def active_layout_for_save(conn, author_id=None, row=None):
    """(Layout, logo_path) of the letterhead this author prints on, or (None, None) for the built-in layout.
    Pass ``row`` (from ``active_row_for``) to reuse one lookup for the layout and the doctors."""
    row = active_row_for(conn, author_id) if row is None else row
    if row is None:
        return None, None
    try:
        return validate_layout(json.loads(row["layout_json"])), row["logo_path"]
    except (LayoutError, ValueError):
        return None, None


def print_doctors(conn, author_id=None, row=None):
    """``meta["doctors"]`` for this author's print (None = the author). ``row`` as in ``active_layout_for_save``."""
    return doctors.for_print(conn, active_row_for(conn, author_id) if row is None else row)


def set_doctors(conn, template_id: int, mode, ids, user=None, actor=None) -> dict:
    """Choose which doctors a letterhead lists; works on a draft or an active letterhead (no re-upload)."""
    row = tdb.get_template(conn, template_id)
    if not visible(row, user):
        raise TemplateError(404, "template not found")
    if row["status"] == "archived":
        raise TemplateError(409, "this letterhead is no longer in use")
    mode, ids = doctors.check_choice(conn, mode, ids)
    tdb.set_template_doctors(conn, template_id, mode, ids)
    dbmod.log_audit(conn, actor=actor, action="template_doctors", entity="template",
                    entity_id=str(template_id), detail={"mode": mode, "ids": ids})
    return view(tdb.get_template(conn, template_id))


def logo_data_uri(path) -> str | None:
    """The stored logo crop as a data URI for the PDF builder; None when missing or outside this clinic's folder."""
    safe = _confined(path)
    if safe is None:
        return None
    try:
        return "data:image/jpeg;base64," + base64.b64encode(safe.read_bytes()).decode("ascii")
    except OSError:
        return None


def deactivate(conn, actor=None, scope="clinic", user_id=None) -> bool:
    """Stop using one scope's letterhead: ``clinic`` prints on the built-in layout again; ``mine`` returns this
    doctor to the clinic letterhead ("Use the clinic letterhead")."""
    owner = _owner(scope, user_id)
    row = tdb.get_active_template(conn, CLINIC, owner)
    if row is None:
        return False
    tdb.deactivate_templates(conn, CLINIC, owner)
    dbmod.log_audit(conn, actor=actor, action="template_deactivate", entity="template",
                    entity_id=str(row["id"]), detail={"clinic": CLINIC, "scope": scope})
    if owner is not None:
        dbmod.log_audit(conn, actor=actor, action="letterhead_scope_change", entity="template",
                        entity_id=str(row["id"]), detail={"scope": "clinic"})
    return True

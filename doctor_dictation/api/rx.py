"""POST /api/v1/rx/check-row: re-check ONE prescription row (the Spell it popover). Reads the doctor's own context only when the page sends it; no AI."""
import asyncio
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from doctor_dictation.api.formulary import use_clinic_layer
from doctor_dictation.api.spellctx import spell_context
from doctor_dictation.core.correction import strip_grounding_markers
from doctor_dictation.core.determinism import normalize_transcript
from doctor_dictation.core.rowcheck import ground_one, options, suggestions

router = APIRouter()
# Longest accepted text per field. The lookup is a difflib pass, so a huge string must not reach it.
ROW_LIMITS = {"form": 20, "name": 60, "strength": 60, "dose": 40, "timing": 60, "duration": 60, "instructions": 600}
MAX_TRANSCRIPT, MAX_AGE_SEX, MAX_NAME_WORDS = 20000, 40, 8
BLANK_ROW = "row needs a name or a strength"


class CheckRowRequest(BaseModel):
    row: Any = None            # validated by hand below so every failure is the same 400 {"error": ...}
    transcript: Any = ""
    age_sex: Any = ""
    context: Any = None        # Spell it load only: {"diagnosis": [...], "patient": {...}}; bad values are ignored
    document_id: Any = None    # the saved sheet; the server finds its patient itself


def _problem(req: CheckRowRequest):
    if not isinstance(req.row, dict):
        return "row must be an object"
    for field, limit in ROW_LIMITS.items():
        value = req.row.get(field, "")
        if value is not None and not isinstance(value, str):
            return f"row.{field} must be text"
        if value and len(value) > limit:
            return f"row.{field} is longer than {limit} characters"
    name = (req.row.get("name") or "").strip().strip(".")        # the same rule core/rowcheck.py applies
    if not name and not (req.row.get("strength") or "").strip():
        return BLANK_ROW
    if len(name.split()) > MAX_NAME_WORDS:
        return f"row.name has more than {MAX_NAME_WORDS} words"
    for label, value, limit in (("transcript", req.transcript, MAX_TRANSCRIPT), ("age_sex", req.age_sex, MAX_AGE_SEX)):
        if not isinstance(value, str) or len(value) > limit:
            return f"{label} must be text of at most {limit} characters"
    return None


def _ground(row: dict, raw: str, normalized: str, age_sex: str, prefer=frozenset(), groups=()) -> dict:
    # Known limitation: the row's form is used as given. An undictated form is "" and the page echoes "" back,
    # so only a form the doctor dictated is checked against the medicine here.
    grounded = ground_one(row, raw, normalized, age_sex)
    listed, total = options(grounded, prefer=prefer)
    return {"row": grounded, "suggestions": suggestions(grounded), "options": listed, "total": total,
            "context": list(groups)}


@router.post("/api/v1/rx/check-row", dependencies=[Depends(use_clinic_layer)])
async def check_row(request: Request, req: CheckRowRequest):
    """Ground one row exactly as /api/format does. A typed name is never trusted: it must still be in the transcript.

    With an empty transcript a known name comes back ``unverified-name`` (nobody said it); the doctor's own typing is
    confirmed in the page (its confirmed set), never by the server.
    """
    problem = _problem(req)
    if problem:
        return JSONResponse(status_code=400, content={"error": problem})
    raw = req.transcript.strip()
    normalized = await asyncio.to_thread(normalize_transcript, raw) if raw else ""   # same step as /api/format
    row = strip_grounding_markers({"rx": [req.row]})["rx"][0]            # a row sent back from the page keeps no stale marker
    prefer, groups = frozenset(), []
    if req.context is not None or req.document_id is not None:           # Search and Use this carry neither: no database
        prefer, groups = await asyncio.to_thread(spell_context, request, row.get("name") or "", req.context, req.document_id)
    try:
        return await asyncio.to_thread(_ground, row, raw, normalized, req.age_sex.strip(), prefer, groups)
    except ValueError:                                                   # belt and braces: a row grounding calls empty
        return JSONResponse(status_code=400, content={"error": BLANK_ROW})

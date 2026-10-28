"""The clinic's investigation list per request, POST /api/v1/investigations/lookup, and "Remember for this clinic"
on save (plan PQ-h)."""
import asyncio
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from doctor_dictation import db as dbmod
from doctor_dictation.api.formulary import use_clinic_layer
from doctor_dictation.core import investigations, overlay
from doctor_dictation.db import overlay as odb

router = APIRouter()
log = logging.getLogger(__name__)
KIND = "investigation"


def load_entries() -> list:
    """This clinic's effective ``"investigation"`` entries: the shipped catalogue with the request's ACTIVE overlay rows
    applied. No database read of its own: ``use_clinic_layer`` already read the overlay rows of BOTH lists in one thread
    hop (``formulary.load_overlay``), and a ``sqlite3.Error`` there gives the empty overlay, logged, so this is then the
    shipped catalogue."""
    return investigations.clinic_entries()


async def use_investigations(_layer: None = Depends(use_clinic_layer)) -> None:
    """Route dependency: make this clinic's investigation list the active one for the request.

    Depends on ``use_clinic_layer`` (FastAPI runs it once per request, before this), so the overlay is loaded first.
    Async for the same reason as ``use_clinic_layer``: the value is set in the request's own context.
    """
    investigations.activate(await asyncio.to_thread(load_entries))


class LookupRequest(BaseModel):
    text: str = Field(max_length=investigations.TEXT_CHARS)


@router.post("/api/v1/investigations/lookup", dependencies=[Depends(use_investigations)])
async def lookup(req: LookupRequest):
    """The catalogue name ``text`` matches in this clinic's list (exact only): verified, else new."""
    entry = investigations.lookup(req.text)
    canonical = entry.get("canonical") if isinstance(entry, dict) else ""
    return {"canonical": canonical if isinstance(canonical, str) else "", "status": "verified" if entry else "new"}


def _goes_live(shipped: list, active: list, row: dict, text: str) -> bool:
    """Whether ``row``, once active, makes ``text`` look up to the test it names on the clinic's list. Builds the effective
    list with ``row`` in place of its key's active row. Catches what ``overlay.conflicts`` lets through but the read path
    leaves inert: a name that stays on the shipped entry as its print form, a ``"safety": true`` entry's override."""
    expected = row["data"]["name"] if row["action"] == "add" else row["base_entry"]["canonical"]
    rows = [r for r in active if r.get("entry_key") != row["entry_key"]] + [row]
    hit = investigations.lookup_in(text, overlay.effective_entries(KIND, shipped, rows)[0], memo=False)
    return isinstance(hit, dict) and hit.get("canonical") == expected      # exact: a same-key twin would shadow it


def _held_back(conn, row: dict, data: dict) -> str:
    """Why ``row`` (validated ``data``) must not be counted though the read path would take it, else "".

    - an add whose name is, by this list's ``key``, another row's name (active or pending): "Vit. D Level" beside "Vit D
      Level" would be two overlay keys but one lookup name, and one would shadow the other;
    - an ACTIVE doctor-learned row on the key with other data: counting would restart it and take it off the list until a
      second document confirms (further aliases go through the clinic list screen). A pending row still restarts."""
    active = odb.list_rows(conn, KIND)
    rows = active + odb.list_rows(conn, KIND, pending=True)
    if row["action"] == "add":
        name = investigations.key(data["name"])
        twin = next((r for r in rows if r["entry_key"] != row["entry_key"]
                     and investigations.key(r["data"].get("name") or r["entry_key"]) == name), None)
        if twin is not None:
            return f"the clinic's list already has {twin['data'].get('name') or twin['entry_key']!r}"
    live = next((r for r in active if r["entry_key"] == row["entry_key"]), None)
    if live is not None and live["source"] == "doctor" and live["data"] != data:
        return "it would take the clinic's learned entry off the list; change it on the list screen"
    return ""


def _remember(conn, item: dict, row: dict, shipped: list, document_id: int, user_id) -> int:
    """Count one document for ``row``; 1 when a confirmation was recorded, else 0 (logged)."""
    text = item["text"]
    base_sha = (overlay.entry_sha(row["base_entry"]) if row["base_entry"] is not None
                else overlay.claimant_sha(shipped, row["data"]["name"]))   # the shipped entry an add overrides, or ""
    candidate = {"entry_key": row["entry_key"], "action": row["action"], "data": row["data"], "base_sha": base_sha}
    active = odb.list_rows(conn, KIND)
    why = overlay.conflicts(KIND, shipped, active, candidate)
    if why:
        log.info("clinic overlay: test %r not remembered: %s", text, why[0])
        return 0
    candidate["data"] = data = overlay.validate_data(KIND, row["action"], row["data"])
    if not _goes_live(shipped, active, {**candidate, "base_entry": row["base_entry"]}, text):
        log.info("clinic overlay: test %r not remembered: the list would still not find it", text)
        return 0
    held = _held_back(conn, row, data)
    if held:
        log.info("clinic overlay: test %r not remembered: %s", text, held)
        return 0
    count = odb.record_confirmation(conn, KIND, row["entry_key"], row["action"], data, base_sha, document_id, user_id)
    if count == 0:                              # a live admin row owns this key: nothing was counted
        log.info("clinic overlay: test %r not remembered: the clinic's own entry wins", text)
        return 0
    dbmod.log_audit(conn, action="investigation.remember", entity="clinic_overlay", entity_id=row["entry_key"],
                    detail={"entry_key": row["entry_key"], "action": row["action"], "count": count})
    return 1


def remember_from_save(conn, items, indexes, document_id: int, user_id) -> int:
    """Record one confirmation per ticked test of a saved document (plan PQ-h, "Remember for this clinic"); returns how
    many were recorded. Never ``upsert``: the row stays pending until ``formulary.THRESHOLD`` documents confirm the same
    data. ``items`` is the SAVED (regraded) list and ``indexes`` point into it; anything else (out of range, negative,
    not an int) is ignored. Only a ticked test counts, a shipped one included. ``record_confirmation`` COMMITS, so this
    runs after the document is saved. Never raises: a failure is logged and the save stands."""
    try:
        saved = items if isinstance(items, list) else []
        picks = sorted({i for i in (indexes if isinstance(indexes, list) else [])
                        if type(i) is int and 0 <= i < len(saved)})
        if not picks:
            return 0
        lex, shipped = investigations.entries(), investigations.shipped()
    except Exception:  # noqa: BLE001 - learning is a convenience, the prescription is already saved
        log.warning("clinic overlay: could not remember tests", exc_info=True)
        return 0
    done, seen = 0, set()
    for i in picks:
        try:
            row = investigations.remember_row(saved[i], lex, shipped)
            if row is None or row["entry_key"] in seen:
                continue
            seen.add(row["entry_key"])
            done += _remember(conn, saved[i], row, shipped, document_id, user_id)
        except Exception:  # noqa: BLE001 - one test failing never stops the others or the save
            log.warning("clinic overlay: could not remember test %d", i, exc_info=True)
    return done

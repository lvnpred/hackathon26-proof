"""Spell it context for POST /api/v1/rx/check-row (plan SH-B2, SH-B4): the doctor's own names for the sheet's
diagnosis and for the patient of a SAVED sheet. Patient identity comes only from the saved document, after the
authorship check; the client's patient fields never find a person. Logs carry a reason word or an exception type."""
import json
from contextlib import closing
from datetime import date

from fastapi import Request

from doctor_dictation import db as dbmod
from doctor_dictation.api import authorship, patientctx
from doctor_dictation.core import formulary, rowcheck, spellctx, spoken
from doctor_dictation.core.patientctx import match_patient
from doctor_dictation.db import formulary as formulary_db
from doctor_dictation.db import spoken as spoken_db
from doctor_dictation.scope import NoScope

NOTHING: tuple[frozenset, list] = (frozenset(), [])


def document_patient_ids(conn, request: Request, document_id: int, doctor: int) -> tuple[int, ...]:
    """Every patient row of the saved sheet's person (a save without an OP number adds a row each time); () when
    there is no such document or it is not this doctor's to edit."""
    doc = dbmod.get_document(conn, document_id)
    if doc is None or authorship.check(conn, request, "document.edit", document_id) is not None:
        return ()
    enc = dbmod.get_encounter(conn, doc["encounter_id"])
    patient = dbmod.get_patient(conn, enc["patient_id"]) if enc else None
    if patient is None:
        return ()
    ids = match_patient(patient["op_no"], patient["name"], patient["age_sex"], spoken_db.patient_candidates(conn, doctor))
    return tuple(ids) or (patient["id"],)


def _document_id(raw) -> int | None:
    return raw if isinstance(raw, int) and not isinstance(raw, bool) and raw >= 1 else None


def spell_context(request: Request, row_name: str, raw_context, raw_document_id) -> tuple[frozenset[str], list[dict]]:
    """(keys that break near-ties, labelled groups). Never raises except NoScope; a failure answers nothing."""
    doctor = patientctx.doctor_id()
    if doctor is None:
        return NOTHING
    try:
        context = None
        if isinstance(raw_context, dict):
            context, problem = spoken.parse_context(json.dumps(raw_context, ensure_ascii=False))
            if problem:
                print(f"check-row: context ignored ({problem})", flush=True)
        document_id = _document_id(raw_document_id)
        dkeys = spoken.diagnosis_keys(context.get("diagnosis") if context else None)
        if not dkeys and document_id is None:
            return NOTHING
        lines: dict[str, str] = {}
        for line in (context or {}).get("diagnosis", []):
            lines.setdefault(spoken.diagnosis_key(line), line)
        with closing(dbmod.get_conn()) as conn:
            ids = document_patient_ids(conn, request, document_id, doctor) if document_id is not None else ()
            patient_keys = spoken_db.patient_term_keys(conn, ids, doctor, exclude_document=document_id) if ids else set()
            linked = spoken_db.linked_ids_by_key(conn, doctor, dkeys)
            names = spoken_db.doctor_medicine_names(conn, doctor, date.today())
            removed = formulary_db.removed_keys(conn)
        blocked = lambda name: rowcheck._blocked(name) or formulary.key(name) in removed  # noqa: E731
        shown = spellctx.groups(names, linked, lines, patient_keys, spoken.key(row_name), blocked)
        return spellctx.prefer_keys([n for n in names if not blocked(n.name)], linked, patient_keys), shown
    except NoScope:
        raise
    except Exception as exc:  # noqa: BLE001 - context is optional
        print(f"check-row: context unavailable: {type(exc).__name__}", flush=True)
        return NOTHING

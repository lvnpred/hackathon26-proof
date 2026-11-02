"""Intake (spec §7.2, §7.5): one code path for a Doctor Dictation push, Sync and a new patient made here.

The store claims the intake key, the episode and its bed in one transaction, so a push and a Sync racing
for the same document make one patient. Only the caller that made the episode writes its first events.
Neither function takes a Request: the routes run settle() for each episode that changed.
"""

from __future__ import annotations

import threading

from app.journey import clock, states, ward_api
from app.journey.rx import from_document
from app.morning.discharge import visible_events

DD_SOURCE = "doctor-dictation"
CG_SOURCE = "count-guard"
SYNTHETIC = "(synthetic)"
RX_UPDATED = "Prescription updated in Doctor Dictation"
SAYS_HOME = "Doctor Dictation now says: send home"
DD_DOCTOR = "Doctor (Doctor Dictation)"  # the same fallback rx.from_document uses
DEFAULT_REASON = "Admitted in Doctor Dictation"
# One re-save at a time: reading the current prescription and superseding it must not interleave, or two
# re-saves would both supersede the same list. A re-save is rare, so one lock for the process is enough.
_RESAVE = threading.Lock()


class NotAdmitted(ValueError):
    """A send-home for a document that was never admitted here: nobody to tell."""


def ward_label(name: str, age_sex: str) -> str:
    """The ward-list name, written like the seed's: "M. Fernandes, 52 F (synthetic)"."""
    name, age_sex = " ".join(name.split()), " ".join(age_sex.split())
    if not age_sex or age_sex in name:
        return name
    if name.endswith(SYNTHETIC):
        return f"{name[: -len(SYNTHETIC)].rstrip().rstrip(',')}, {age_sex} {SYNTHETIC}"
    return f"{name}, {age_sex}"


def _details(document: dict) -> dict:
    structured = document.get("structured") or {}
    author = document.get("author") or {}
    return {
        "age_sex": str(structured.get("ageSex") or "").strip(),
        "op_no": str(structured.get("opNo") or "").strip(),
        "diagnosis": [str(d) for d in structured.get("diagnosis") or []],
        "dd_doctor": str(author.get("doctor_name") or "").strip(),
    }


def _result(episode_id: str, bed: str | None, *, created=False, updated=False, notice=None, at_ms=None) -> dict:
    return {"episode_id": episode_id, "bed": bed, "created": created, "updated": updated, "notice": notice,
            "at_ms": at_ms}


def take(store, payload: dict, *, now_ms: int) -> dict:
    """Make or update the patient for one Doctor Dictation document.

    `payload` is the push body (spec §7.1), already validated by the route. Returns
    {"episode_id", "bed", "created", "updated", "notice", "at_ms"}; at_ms is when the writes landed.
    """
    source, document_id = payload["source"], int(payload["document_id"])
    document = payload.get("document") or {}
    finalized_at = str(payload.get("finalized_at") or "")
    status = payload.get("status") or "admit"
    if status == "send_home" and store.intake_episode(source, document_id) is None:
        raise NotAdmitted("Doctor Dictation sent home a patient who was never admitted here.")
    details = _details(document)
    name = str((document.get("structured") or {}).get("patientName") or "").strip() or "Patient from Doctor Dictation"
    episode_id, created = store.claim_intake(source, document_id, finalized_at, ward_label(name, details["age_sex"]))
    bed = store.beds().get(episode_id)
    if created:
        ts = clock.stamp(store, episode_id, now_ms)
        ward_api.registered(store, episode_id, bed=bed, source=source, document_id=document_id, ts_ms=ts, **details)
        rx = from_document(document, source=source)
        if rx["rows"]:
            store.append(episode_id, "rx.ordered", rx, ts_ms=ts)
        reason = str(payload.get("admit_reason") or "").strip() or DEFAULT_REASON
        move = states.move_payload(store.events(episode_id), "admitting",
                                   {"by": details["dd_doctor"] or DD_DOCTOR, "reason": reason})
        store.append(episode_id, "patient.state", move, ts_ms=ts)
        return _result(episode_id, bed, created=True, at_ms=ts)
    if not _first_write_done(store.events(episode_id)):
        # Another caller made this patient and is still writing its first events. Changing nothing, and
        # leaving the stored finalized_at as it is, lets the next push or Sync supersede in order.
        return _result(episode_id, bed)
    with _RESAVE:
        if not store.update_intake(source, document_id, finalized_at):
            return _result(episode_id, bed)
        return _resave(store, episode_id, bed, document, source, status, now_ms)


def _first_write_done(events: list[dict]) -> bool:
    """True once the creator's first events are all written: the admitting move is the last of them."""
    return any(e["event_type"] == "patient.state" for e in events)


def _resave(store, episode_id: str, bed: str | None, document: dict, source: str, status: str, now_ms: int) -> dict:
    """A document saved again in Doctor Dictation. The state never changes here: the doctor in Count Guard decides."""
    events = store.events(episode_id)
    if states.current_state(events) == "home":
        return _result(episode_id, bed)
    ts = clock.stamp(store, episode_id, now_ms)
    if status == "send_home":
        notice = SAYS_HOME
    else:
        rx = from_document(document, source=source)
        old = [e for e in visible_events(events) if e["event_type"] == "rx.ordered"]
        store.append(episode_id, "rx.ordered", rx, ts_ms=ts, supersedes_id=old[-1]["id"] if old else None)
        notice = RX_UPDATED
    store.append(episode_id, "notice.dd", {"text": notice, "source": source}, ts_ms=ts)
    return _result(episode_id, bed, updated=True, notice=notice, at_ms=ts)


def new_patient(store, *, name: str, age_sex: str, reason: str, now_ms: int) -> dict:
    """A patient made in Count Guard (spec §7.5): in clinic, no prescription; the doctor admits them."""
    episode_id, _ = store.claim_intake(CG_SOURCE, None, "", ward_label(name, age_sex))
    bed = store.beds().get(episode_id)
    ts = clock.stamp(store, episode_id, now_ms)
    ward_api.registered(store, episode_id, bed=bed, source=CG_SOURCE, document_id=None, ts_ms=ts,
                        age_sex=" ".join(age_sex.split()), reason=reason.strip())
    return _result(episode_id, bed, created=True, at_ms=ts)


def chart_header(events: list[dict], bed: str | None, dd_base: str) -> dict:
    """What the chart shows beside the name: bed, age/sex, OP number, diagnosis, the DD doctor and the DD PDF."""
    rows = [e["payload"] for e in events if e["event_type"] == "patient.registered"]
    reg = rows[-1] if rows else {}
    document_id = reg.get("document_id")
    from_dd = reg.get("source") == DD_SOURCE and document_id is not None
    return {
        "bed": bed,
        "source": reg.get("source") or "",
        "age_sex": reg.get("age_sex") or "",
        "op_no": reg.get("op_no") or "",
        "diagnosis": list(reg.get("diagnosis") or []),
        "dd_doctor": reg.get("dd_doctor") or "",
        "dd_pdf": f"{dd_base.rstrip('/')}/api/v1/documents/{int(document_id)}/pdf" if from_dd else None,
    }

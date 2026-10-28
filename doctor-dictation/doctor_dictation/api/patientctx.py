"""Plan SH-H4: the patient context for speech hints. The dictated patient picks one stored person; the terms that
person got in their last visits with this doctor become tier-3 correction hints. Nothing here is logged or sent
to a speech engine except the term keys' own hint words."""
from doctor_dictation.core.patientctx import match_patient
from doctor_dictation.db import spoken as spoken_db
from doctor_dictation.scope import NoScope, current_scope

_FIELDS = ("name", "age_sex", "op_no")
_CAP = 200                                         # H3's cap on every context text


def doctor_id() -> int | None:
    """0 in single-database mode (no scope); the signed-in doctor's id; None for a scope without a doctor."""
    sc = current_scope()
    if sc is None:
        return 0
    return sc.user_id if sc.user_id else None


def clean_patient(raw) -> dict | None:
    """The patient's three text fields, each capped; None when ``raw`` is not a dict or every field is blank."""
    if not isinstance(raw, dict):
        return None
    out = {k: (raw[k][:_CAP] if isinstance(raw.get(k), str) else "") for k in _FIELDS}
    return out if any(v.strip() for v in out.values()) else None


def context_keys(conn, doctor: int | None, context) -> set[str]:
    """Spoken-term keys of the matched patient's last 3 visits with this doctor; set() when nothing matches
    or the lookup fails (hints are optional, so a failure only drops this tier)."""
    if doctor is None:
        return set()
    patient = clean_patient(context.get("patient") if isinstance(context, dict) else None)
    if patient is None:
        return set()
    try:
        candidates = spoken_db.patient_candidates(conn, doctor)
        ids = match_patient(patient["op_no"], patient["name"], patient["age_sex"], candidates)
        return spoken_db.patient_term_keys(conn, ids, doctor) if ids else set()
    except NoScope:
        raise                                       # a missing scope is an auth bug, not "no hints"
    except Exception as exc:  # noqa: BLE001 - hints are optional
        print(f"hints: patient context unavailable: {type(exc).__name__}", flush=True)
        return set()

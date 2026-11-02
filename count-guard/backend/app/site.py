"""The product map (GET /product): each feature, the care-app page it lives on, its code and its API."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.config import BANNER
from app.morning.guide import PATIENT_RULE

router = APIRouter()


def catalog() -> dict:
    return {
        "name": "Count Guard",
        "banner": BANNER,
        "summary": (
            "Count Guard follows one patient from admission through theatre to discharge. "
            "It records medicines from home, doses, observations, a swab count and confirmed theatre drugs, "
            "then drafts the discharge from that record. It does not give medical advice."
        ),
        "patient_rule": PATIENT_RULE,
        "audiences": [
            {
                "who": "Someone using the demo",
                "start": "/",
                "does": "Pick a role, work the queue, and open a patient's chart to act.",
            },
            {
                "who": "A developer",
                "start": "/help",
                "does": "Read this map, open the screen, then open the file named on the card.",
            },
        ],
        "features": [
            {
                "id": "ward",
                "title": "Ward list and the clock",
                "where": "My patients, My queue",
                "href": "/patients",
                "use": "See every patient, where they are and what is due; the demo dock moves the ward clock.",
                "code": "frontend/src/care/MyPatients.jsx",
                "api": "GET /journey/ward",
            },
            {
                "id": "intake",
                "title": "Admission from Doctor Dictation",
                "where": "My patients",
                "href": "/patients",
                "use": "A saved admission arrives from Doctor Dictation; Sync and New patient use the same path.",
                "code": "backend/app/journey/intake_api.py",
                "api": "POST /journey/intake",
            },
            {
                "id": "home-medicines",
                "title": "Medicines from home",
                "where": "Chart, doctor",
                "href": "/patients",
                "use": "Photograph or type the strips; a name on the demo list is grounded, and the photo stays on this machine without a key.",
                "code": "backend/app/journey/home_medicines.py",
                "api": "POST /journey/episodes/{id}/strips/photo",
            },
            {
                "id": "theatre",
                "title": "Theatre: drug given, vitals strip, context card",
                "where": "Chart, theatre",
                "href": "/queue",
                "use": "Say or type a drug line and confirm it; step the simulated strip; the fact card stays off unless turned on.",
                "code": "backend/app/journey/theatre_api.py",
                "api": "POST /journey/episodes/{id}/theatre/drug",
            },
            {
                "id": "count",
                "title": "Swab count and camera assist",
                "where": "Chart, theatre",
                "href": "/queue",
                "use": "A person saves the count; surgery cannot end until it adds up or a reason is given. The camera only advises.",
                "code": "backend/app/journey/count_api.py",
                "api": "POST /journey/episodes/{id}/count",
            },
            {
                "id": "nurse",
                "title": "Doses, observations and nudges",
                "where": "My queue",
                "href": "/queue",
                "use": "Log doses and observations. Answer each nudge; the answer is kept.",
                "code": "backend/app/journey/api.py",
                "api": "POST /journey/episodes/{id}/dose",
            },
            {
                "id": "discharge",
                "title": "Discharge draft, PDF and follow-up",
                "where": "Chart, doctor",
                "href": "/patients",
                "use": "Draft the discharge from the record, sign it, then download the PDF and the calendar file.",
                "code": "backend/app/journey/discharge_api.py",
                "api": "POST /journey/episodes/{id}/discharge/draft",
            },
            {
                "id": "patient",
                "title": "Today, my care and ask",
                "where": "Today",
                "href": "/today",
                "use": "See the schedule and reminders, check in, ask for help, and read the discharge card.",
                "code": "frontend/src/care/Today.jsx",
                "api": "POST /journey/episodes/{id}/checkin",
            },
            {
                "id": "audit",
                "title": "History and AI activity",
                "where": "AI activity",
                "href": "/ai",
                "use": "Every line as written, who wrote it, and what replaced it. Nothing is deleted.",
                "code": "backend/app/journey/stories.py",
                "api": "GET /journey/episodes/{id}/audit",
            },
            {
                "id": "guide",
                "title": "Help",
                "where": "Help",
                "href": "/help",
                "use": "What each part of the care app does. The same list the API returns at GET /product.",
                "code": "backend/app/site.py",
                "api": "GET /product",
            },
        ],
    }


@router.get("/product")
def product() -> dict:
    return catalog()


ADAPTERS = (  # (name, adapter file, settings prefix, note)
    ("sam-3.1", "sam", "sam", "Uploaded video or still image, and the theatre camera's live socket."),
    ("muse-voice-transcribe", "voice", "voice", "Turn-level timestamps. Word-level timestamps are not provided."),
    ("muse-spark-open", "spark_open", "spark_open", "Baseten chat completions. Tool calling is documented, not yet called from this machine."),
    ("muse-spark-1.3", "spark", "spark", "Second look only, and only when R5 fires."),
)


@router.get("/health")
def health(request: Request) -> dict:
    """The four models and whether a key is set (moved here from the archived api/routes.py)."""
    settings = request.app.state.settings
    adapters = {
        name: {
            "file": f"backend/app/adapters/{file}.py",
            "configured": getattr(settings, f"{key}_configured"),
            "model": getattr(settings, f"{key}_model"),
            "note": note,
        }
        for name, file, key, note in ADAPTERS
    }
    return {"ok": True, "banner": BANNER, "adapters": adapters}

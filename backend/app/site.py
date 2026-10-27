"""The product map. The guide page and the README both follow this list."""

from __future__ import annotations

from fastapi import APIRouter

from app.config import BANNER
from app.morning.guide import PATIENT_RULE

router = APIRouter()


def catalog() -> dict:
    return {
        "name": "Count Guard",
        "banner": BANNER,
        "summary": (
            "Count Guard keeps one morning for one patient. "
            "It records strips, a swab count, confirmed drugs, and a blood-pressure log, "
            "then folds those records into a discharge sheet. It does not give medical advice."
        ),
        "patient_rule": PATIENT_RULE,
        "audiences": [
            {
                "who": "Someone using the demo",
                "start": "/",
                "does": "Follow the six steps for one labelled patient, then start the next patient.",
            },
            {
                "who": "A developer",
                "start": "/guide",
                "does": "Read this map, open the screen, then open the file named on the card.",
            },
        ],
        "features": [
            {
                "id": "morning",
                "title": "One patient, one morning",
                "where": "Home",
                "href": "/",
                "use": "See which of the six steps is recorded, and start a new patient so the records do not mix.",
                "code": "frontend/src/screens/Home.jsx",
                "api": "GET /morning/episodes/{id}",
            },
            {
                "id": "strips",
                "title": "Medicine strips",
                "where": "Before the operation",
                "href": "/opd",
                "use": "Type each strip. A name on the 20-drug demo list is grounded. A photo stays on this machine when no model key is set.",
                "code": "backend/app/morning/lexicon.py",
                "api": "POST /morning/episodes/{id}/brownbag/text",
            },
            {
                "id": "theatre",
                "title": "Swab count and drug line",
                "where": "In the room",
                "href": "/ot",
                "use": "Say what was opened, replay the tray, confirm a drug, and step the blood-pressure trace.",
                "code": "backend/app/morning/count_rules.py",
                "api": "POST /morning/episodes/{id}/count/replay",
            },
            {
                "id": "sheet",
                "title": "Discharge sheet",
                "where": "After the room",
                "href": "/ward",
                "use": "Read the folded record, then download the PDF and the follow-up calendar.",
                "code": "backend/app/morning/discharge.py",
                "api": "POST /morning/episodes/{id}/discharge",
            },
            {
                "id": "camera",
                "title": "Camera count",
                "where": "A separate video check",
                "href": "/count",
                "use": "Track swabs in a clip. Six rules decide the alert. File the result onto the current patient from the close screen.",
                "code": "backend/app/core/rules.py",
                "api": "POST /cases/{id}/upload?scenario=demo",
            },
            {
                "id": "guide",
                "title": "This guide",
                "where": "For a developer or a new reader",
                "href": "/guide",
                "use": "The same list the API returns at GET /product. Change a feature here and the page follows.",
                "code": "backend/app/site.py",
                "api": "GET /product",
            },
        ],
    }


@router.get("/product")
def product() -> dict:
    return catalog()

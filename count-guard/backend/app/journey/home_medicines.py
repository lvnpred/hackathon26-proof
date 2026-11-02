"""The doctor's photo of medicines from home (spec 6.3). One action: it writes `brownbag.med_found` rows.

Each row keeps `generic` and `drug_class`, which the theatre context card reads. With the medicines switch off the
read is prepared and labelled so. It is chosen by the photo's bytes, never by the uploaded file name (spec 4): the
committed demo photo gives metoprolol and amlodipine, any other photo falls back to the older prepared fixtures.
A live call that fails is an error to retry (502), never a prepared read.
"""

from __future__ import annotations

import hashlib
import json

from fastapi import HTTPException

from app.config import Settings
from app.journey import live, switches
from app.journey.regions import pair_regions, strip_values, strips_from

# sha256 of eval/media/home-medicines/strips-metoprolol-amlodipine-synthetic.png (pinned by tests/test_home_medicines.py).
DEMO_SHA256 = "39f1c76301f38585b27e67b04137f59f23d9701cd490aeeb199a552d403102be"
DEMO_TEXT = json.dumps({"strips": [{"name": "Metoprolol", "strength": "25 mg"}, {"name": "Amlodipine", "strength": "5 mg"}]})


def read(settings: Settings, raw: bytes, filename: str, content_type: str) -> dict:
    """The photo read: {text, source, regions, calls, raw, handmade}. Raises 502 when a live call failed."""
    on = switches.is_live(settings, "medicines")
    if not on and hashlib.sha256(raw).hexdigest() == DEMO_SHA256:
        regions = pair_regions([], strip_values(strips_from(DEMO_TEXT)))
        return {"text": DEMO_TEXT, "source": "prepared", "regions": regions, "handmade": True, "raw": None,
                "calls": [live.call_of("spark", settings, "prepared", None)]}
    found = live.read_photo(settings, "strip", raw, filename, content_type, live_ok=on)
    if found["source"] == switches.UNAVAILABLE:
        raise HTTPException(status_code=502, detail=found["why"])
    return found


def _norm(strength: str) -> str:
    return "".join((strength or "").lower().split())


def matches(events: list[dict]) -> list[dict]:
    """One match per medicine from home, against the latest visible prescription: {id, kind, text}."""
    rx = next((e for e in reversed(events) if e["event_type"] == "rx.ordered"), None)
    rows = {row["key"]: row for row in rx["payload"]["rows"]} if rx else {}
    out = []
    for event in (e for e in events if e["event_type"] == "brownbag.med_found"):
        found = event["payload"]
        key = found.get("generic") or " ".join((found.get("name_as_read") or "").lower().split())
        row = rows.get(key)
        if rx is None:
            kind, text = "no_prescription", "No prescription yet."
        elif row is None:
            kind, text = "not_on_prescription", "Not on the prescription."
        elif found.get("strength") and row["strength"] and _norm(found["strength"]) != _norm(row["strength"]):
            kind, text = "strength_differs", f"Prescription says {row['strength']}."
        else:
            kind, text = "on_prescription", "On the prescription."
        out.append({"id": event["id"], "kind": kind, "text": text})
    return out


def with_match(events: list[dict]) -> list[dict]:
    """The medicines from home as the view lists them, each with its match to the prescription."""
    found = {m["id"]: m for m in matches(events)}
    return [{**e["payload"], "match": found[e["id"]]} for e in events if e["event_type"] == "brownbag.med_found"]

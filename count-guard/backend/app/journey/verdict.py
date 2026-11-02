"""Photo proof verdicts (spec §6.6, U9): Accepted, Not accepted, or Not checked, and whether an item is still open.

U9 reverses D9 for proof photos only: a photo that is not accepted, or that the model could not check, keeps its
item open until a retake is accepted or a person overrides it with a typed reason. Strip and monitor reads in
`proof.py` still flag and never block. An item with no photo is not open (rule (a)); it shows "No photo".

With PROOF_LIVE off the verdict is prepared and labelled so. It is chosen by the item and the photo's bytes,
never by the uploaded file name (§4): accepted, except the committed demo wrong photo, which is not accepted.
"""

from __future__ import annotations

import hashlib
import logging
import time

import httpx

from app.adapters.spark import SparkAdapter
from app.config import Settings
from app.journey import expected, switches
from app.journey.live import call_of

log = logging.getLogger(__name__)

# sha256 of eval/media/wrong-photo/wrong-photo-bed-rail-synthetic.png (pinned by tests/test_verdict.py).
WRONG_PHOTO_SHA256 = "3ef4a569957e10ade19d676c91542073e619bcfe2f5ea1dfeacffda1a67cad53"
NO_PHOTO = "No photo"
TASK_OPEN = "The proof photo is not accepted yet. Take it again, or override it with a reason."
NOT_OPEN = "This photo check is not open, so there is nothing to override."


def _prepared(raw: bytes, expect: str) -> dict:
    if hashlib.sha256(raw).hexdigest() == WRONG_PHOTO_SHA256:
        return {"verdict": "not_accepted", "why": f"The photo shows a bed rail, not {expect}."}
    return {"verdict": "accepted", "why": f"The photo shows {expect}."}


def check(settings: Settings, *, item: str, raw: bytes, content_type: str, expect: str | None = None) -> dict:
    """{verdict, why, source, calls} for one proof photo. `expect` defaults to the item's expected line.

    source is live, prepared or unavailable. A live call that fails, or a reply that does not parse, is
    not_checked with the fixed reason; it never falls back to a prepared verdict."""
    expect = expect or expected.expect_for(item)
    if not switches.is_live(settings, "proof"):
        return {**_prepared(raw, expect), "source": "prepared", "calls": [call_of("spark", settings, "prepared", None)]}
    start = time.monotonic()
    try:
        found = SparkAdapter(settings).check_photo(raw, content_type, expect)
    except (httpx.HTTPError, RuntimeError, ValueError) as exc:
        log.warning("Photo check for %s failed: %s", item, type(exc).__name__)
        ms = round((time.monotonic() - start) * 1000)
        return {"verdict": "not_checked", **switches.unavailable(switches.NOT_CHECKED),
                "calls": [call_of("spark", settings, switches.UNAVAILABLE, ms)]}
    ms = round((time.monotonic() - start) * 1000)
    return {"verdict": found["verdict"], "why": found["why"], "source": "live",
            "calls": [call_of("spark", settings, "muse-spark-1.3", ms)]}


def _last(events: list[dict], item: str) -> tuple[dict | None, dict | None]:
    """The latest check.photo of an item, and an override written after it (or None)."""
    photo, override = None, None
    for e in events:
        if e["event_type"] == "check.photo" and e["payload"].get("item") == item:
            photo, override = e, None
        elif e["event_type"] == "check.override" and e["payload"].get("item") == item and photo is not None:
            override = e
    return photo, override


def photo_state(events: list[dict], item: str) -> str:
    """accepted, not_accepted, not_checked, overridden or none (no photo yet)."""
    photo, override = _last(events, item)
    if photo is None:
        return "none"
    if override is not None:
        return "overridden"
    return photo["payload"]["verdict"]


def item_open(events: list[dict], item: str) -> bool:
    """Rule (a): open only when the latest photo is not accepted or not checked and no override came after it."""
    return photo_state(events, item) in ("not_accepted", "not_checked")


def view_text(state: str, why: str = "", reason: str = "") -> str:
    """The staff line for an item. "Prepared" is added by the page, beside the line."""
    if state == "none":
        return NO_PHOTO
    if state == "not_checked":
        return switches.NOT_CHECKED
    if state == "overridden":
        return f"Overridden — {reason}"
    return f"{'Accepted' if state == 'accepted' else 'Not accepted'} — {why}"


def _items(events: list[dict]) -> list[str]:
    """The items a chart lists: the fixed checks of each step the patient reached, then each task photographed."""
    reached = {e["payload"].get("to") for e in events if e["event_type"] == "patient.state"}
    out = [*(expected.ADMISSION if "admitting" in reached else ()), *(expected.THEATRE if "theatre" in reached else ()),
           *(expected.DISCHARGE if "discharging" in reached else ())]
    for e in events:
        item = e["payload"].get("item") if e["event_type"] == "check.photo" else None
        if item and item not in out:
            out.append(item)
    return out


def checks_view(events: list[dict]) -> list[dict]:
    """One row per photo check on the chart, with its state and the line the item shows."""
    rows = []
    titles = {e["id"]: e["payload"].get("title") for e in events if e["event_type"] == "task.created"}
    for item in _items(events):
        photo, override = _last(events, item)
        state = photo_state(events, item)
        p = photo["payload"] if photo else {}
        o = override["payload"] if override else {}
        rows.append({
            "item": item, "label": (titles.get(item[5:]) if item.startswith("task:") else None) or expected.label(item),
            "state": state, "open": state in ("not_accepted", "not_checked"),
            "verdict": p.get("verdict"), "why": p.get("why", ""), "source": p.get("source", ""), "calls": p.get("calls") or [],
            "photo_id": p.get("photo_id"), "reason": o.get("reason", ""), "overridden_by": o.get("by"),
            "text": view_text(state, p.get("why", ""), o.get("reason", "")),
            "photo_url": f"/journey/episodes/{photo['episode_id']}/photos/{p['photo_id']}" if photo else None,
        })
    return rows

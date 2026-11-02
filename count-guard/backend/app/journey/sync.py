"""Sync (spec §7.3): pull the admissions Doctor Dictation holds and make the patients Count Guard missed.

The push is the main path; this is the backup when a push was lost. Every row goes through intake.take,
so a row that is already here changes nothing. No Request here: the route settles each changed episode.
"""

from __future__ import annotations

import logging

import httpx

from app.config import sync_token
from app.journey import intake

log = logging.getLogger(__name__)
UNREACHABLE = "Doctor Dictation is not reachable"
TIMEOUT_S = 8.0


def pull(settings, store, *, since: str | None, now_ms: int, get=None) -> dict:
    """Returns {"new", "existing", "updated", "failed", "error", "changed"}; changed lists (episode_id, at_ms) to settle."""
    out = {"new": 0, "existing": 0, "updated": 0, "failed": 0, "error": None, "changed": []}
    headers = {"X-CG-Sync-Token": sync_token()} if sync_token() else {}
    params = {"since": since} if since else {}
    try:
        reply = (get or httpx.get)(f"{settings.dd_base.rstrip('/')}/api/v1/admissions", headers=headers, params=params,
                    timeout=TIMEOUT_S)
        reply.raise_for_status()
        rows = list(reply.json().get("admissions") or [])
    except (httpx.HTTPError, ValueError, AttributeError):
        out["error"] = UNREACHABLE
        return out
    for payload in rows:
        try:
            result = intake.take(store, payload, now_ms=now_ms)
        except intake.NotAdmitted:
            continue  # a send-home for a patient never admitted here: nobody to tell, not an error
        except Exception:  # noqa: BLE001 - one unreadable row must not stop the rest or skip their settle
            log.warning("Sync could not read one admission row", exc_info=True)
            out["failed"] += 1
            continue
        if result["created"]:
            out["new"] += 1
        elif result["updated"]:
            out["updated"] += 1
        else:
            out["existing"] += 1
        if result["created"] or result["updated"]:
            out["changed"].append((result["episode_id"], result["at_ms"]))
    return out

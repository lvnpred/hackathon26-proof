"""Draft discharge (spec §6.8, CG-23): the draft written from the timeline, its PDF and the follow-up .ics.

POST /discharge/draft writes `discharge.drafted` (ward only). Dictation (/dictate/discharge) amends that draft and
/discharge/sign signs the latest. The PDF and the .ics are made on request into the data dir, never the repo.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import Field

from app.journey import discharge_draft, states
from app.journey.dictation import open_drafts
from app.journey.api import At, _act, _require, _store
from app.morning.ics import follow_up_ics
from app.morning.pdf import write_discharge

discharge_router = APIRouter(prefix="/journey/episodes/{episode_id}")
NOT_ON_WARD = "The discharge is drafted only while the patient is on the ward. The patient is in {state}."
NOTHING_YET = "No discharge draft yet. Press Draft discharge first."


class DraftIn(At):
    by: str = Field(min_length=1, max_length=80)


def _pdf_url(episode_id: str) -> str:
    return f"/journey/episodes/{episode_id}/discharge.pdf"


def _ics_url(episode_id: str) -> str:
    return f"/journey/episodes/{episode_id}/follow-up.ics"


@discharge_router.post("/discharge/draft")
def draft(episode_id: str, body: DraftIn, request: Request) -> dict:
    episode = _require(request, episode_id)
    events = _store(request).events(episode_id)
    state = states.current_state(events)
    if state != "ward":
        raise HTTPException(status_code=409, detail=NOT_ON_WARD.format(state=state))
    built = discharge_draft.build(events)
    write = getattr(request.app.state, "discharge_write", None)  # tests stand a writer in here, as for the handover
    said = discharge_draft.wording(built, episode["label"], request.app.state.settings, write)
    payload = {"by": body.by, "from_timeline": True, "timeline": built, **said, "summary_source": said["source"],
               "pdf_url": _pdf_url(episode_id), "ics_url": _ics_url(episode_id)}
    # An open dictated draft is amended, not dropped: its sections stay under the timeline summary (as media_api does).
    open_draft = open_drafts(events)["discharge"]
    if open_draft and open_draft.get("sections"):
        payload.update(sections=open_draft["sections"], amends=open_draft["id"])
    return _act(request, episode_id, "discharge.drafted", payload, body.at_ms)


@discharge_router.get("/discharge.pdf")
def discharge_pdf(episode_id: str, request: Request) -> Response:
    episode = _require(request, episode_id)
    events = _store(request).events(episode_id)
    summary, source = discharge_draft.summary_of(events)
    if source is None:
        raise HTTPException(status_code=404, detail=NOTHING_YET)
    path = request.app.state.settings.report_dir / "journey" / f"{episode_id}-discharge.pdf"
    write_discharge(path, label=episode["label"], sheet=discharge_draft.sheet(events, summary, source))
    return Response(path.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": "inline; filename=discharge.pdf"})


@discharge_router.get("/follow-up.ics")
def follow_up(episode_id: str, request: Request) -> Response:
    episode = _require(request, episode_id)
    events = _store(request).events(episode_id)
    _, source = discharge_draft.summary_of(events)
    source = source or next((e for e in reversed(events) if e["event_type"] == "discharge.card"), None)  # a card alone
    if source is None:
        raise HTTPException(status_code=404, detail=NOTHING_YET)
    body = follow_up_ics(episode["label"], start=discharge_draft.ics_start(discharge_draft.follow_up_of(source)))
    return Response(body, media_type="text/calendar", headers={"Content-Disposition": "attachment; filename=follow-up.ics"})

"""Photo check routes (spec §6.6, U9): a proof photo for one check, and an override with a typed reason."""

from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import Field, field_validator

from app.journey import expected, tasks, verdict
from app.journey.api import At, _at, _require, _store, settle, view
from app.journey.media_api import read_upload_photo, write_photo
from app.journey.states import current_state

verdict_router = APIRouter(prefix="/journey/episodes/{episode_id}")


class OverrideIn(At):
    reason: str = Field(max_length=300)
    by: str = Field(min_length=1, max_length=80)

    @field_validator("reason", "by")
    @classmethod
    def _typed(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Type the reason for the override, and who overrides it.")
        return value.strip()


def _expect(events: list[dict], item: str) -> str:
    """The expected line for an item the patient's chart can take a photo for now: 404 unknown, 409 not now."""
    if item.startswith("task:"):
        task = next((t for t in tasks.task_list(events) if t["id"] == item[5:]), None)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if task["status"] not in ("open", "running"):
            raise HTTPException(status_code=409, detail=f"This task is {task['status']}; a proof photo goes with an open task.")
        return expected.expect_for(item, task["kind"])
    if not expected.fixed(item):
        raise HTTPException(status_code=404, detail="Unknown photo check")
    if current_state(events) != expected.STEP_STATE[item.partition(":")[0]]:
        raise HTTPException(status_code=409, detail=f"The photo of the {expected.label(item)} is taken at that step only.")
    return expected.expect_for(item)


@verdict_router.post("/checks/{item}/photo")
def check_photo(
    episode_id: str,
    item: str,
    request: Request,
    file: UploadFile = File(...),
    by: str = Form(..., min_length=1, max_length=80),
    at_ms: int | None = Form(None, ge=0),
) -> dict:
    _require(request, episode_id)
    store, settings = _store(request), request.app.state.settings
    expect = _expect(store.events(episode_id), item)
    raw, kind = read_upload_photo(file)
    ts = _at(store, episode_id, at_ms)
    photo = write_photo(settings, store, episode_id, raw, kind, {"purpose": "check", "item": item, "by": by}, ts)
    judged = verdict.check(settings, item=item, raw=raw, content_type=kind, expect=expect)
    store.append(episode_id, "check.photo", {"item": item, "photo_id": photo["id"], "by": by, **judged}, ts_ms=ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)


@verdict_router.post("/checks/{item}/override")
def override(episode_id: str, item: str, body: OverrideIn, request: Request) -> dict:
    _require(request, episode_id)
    store = _store(request)
    if not verdict.item_open(store.events(episode_id), item):
        raise HTTPException(status_code=409, detail=verdict.NOT_OPEN)
    ts = _at(store, episode_id, body.at_ms)
    store.append(episode_id, "check.override", {"item": item, "reason": body.reason, "by": body.by}, ts_ms=ts)
    settle(request, episode_id, ts)
    return view(request, episode_id)

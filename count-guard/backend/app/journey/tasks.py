"""Doctor orders become nurse tasks.

Pure readers (`orders_list`, `task_list`) fold the ledger into views. The writer helpers
(`sign_order`, `acknowledge_order`, `begin_task`, `complete_task`) append events and raise
`TaskError` on a refusal, so the routes and the seed share them and stay HTTP-free. The caller
runs `raise_nudges` after a write, using the ts the helper returns.
"""

from __future__ import annotations

from app.journey import proof
from app.journey.dictation import draft_refusal
from app.journey.rx import key_of
from app.journey.states import current_state
from app.morning.discharge import visible_events

HOUR_MS = 3_600_000
ORDER_STATES = ("clinic", "admitting", "ward")
CLOSED_STATES = ("discharging", "home", "clinic_done")  # tasks end with the stay
PROGRESS = ("task.began", "task.done")
OBS_FIELDS = ("sbp", "dbp", "hr", "spo2", "temp")


class TaskError(Exception):
    """A refused action. `status` is the HTTP code the route maps it to (404, 409 or 422)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _of(events: list[dict], kind: str) -> list[dict]:
    return [e for e in visible_events(events) if e["event_type"] == kind]


def orders_list(events: list[dict]) -> list[dict]:
    acked = {e["payload"]["order_id"]: e["payload"]["by"] for e in _of(events, "order.acknowledged")}
    return [
        {
            "id": e["id"],
            "by": e["payload"]["by"],
            "items": e["payload"]["items"],
            "at_ms": e["ts_ms"],
            "acknowledged_by": acked.get(e["id"]),
        }
        for e in _of(events, "order.signed")
    ]


def task_list(events: list[dict]) -> list[dict]:
    rows = visible_events(events)
    stay_over = current_state(events) in CLOSED_STATES
    out = []
    for created in (e for e in rows if e["event_type"] == "task.created"):
        p, tid = created["payload"], created["id"]
        # Only began and done are progress; a photo or its check carries task_id but changes nothing.
        mine = [e for e in rows if e["payload"].get("task_id") == tid and e["event_type"] in PROGRESS]
        done = [e for e in mine if e["event_type"] == "task.done"]
        began = [e for e in mine if e["event_type"] == "task.began"]
        running = bool(mine) and mine[-1]["event_type"] == "task.began"
        if stay_over:
            status, due = "closed", None
        elif running:
            status, due = "running", p["due_ms"] if not done else done[-1]["ts_ms"] + _gap(p)
        elif done and p["every_h"]:
            status, due = "open", done[-1]["ts_ms"] + _gap(p)
        elif done:
            status, due = "done", None
        else:
            status, due = "open", p["due_ms"]
        out.append(
            {
                "id": tid,
                "order_id": p["order_id"],
                "title": p["title"],
                "name": p.get("name") or "",
                "amount": p.get("amount") or "",
                "kind": p["kind"],
                "mode": p["mode"],
                "proof": p["proof"],
                "every_h": p["every_h"],
                "status": status,
                "due_ms": due,
                "done": [
                    {
                        "at_ms": e["ts_ms"],
                        "by": e["payload"]["by"],
                        "via": e["payload"]["via"],
                        "note": e["payload"]["note"],
                        "transcript": e["payload"].get("transcript", ""),
                        "proof_id": e["payload"].get("proof_id"),
                        "match": e["payload"].get("match"),
                        "why": e["payload"].get("why", ""),
                        "source": e["payload"].get("source", ""),
                    }
                    for e in done
                ],
                "began_ms": began[-1]["ts_ms"] if began else None,
                "video": _video_of(rows, tid),
            }
        )
    return out


def _video_of(rows: list[dict], task_id: str) -> dict | None:
    checks = [e for e in rows if e["event_type"] == "setup.checked" and e["payload"].get("task_id") == task_id]
    if not checks:
        return None
    latest = checks[-1]
    return {"id": latest["id"], "match": latest["payload"]["match"], "why": latest["payload"]["why"]}


def _gap(payload: dict) -> int:
    return int(payload["every_h"] * HOUR_MS) if payload["every_h"] else 0


def _merged_orders(previous: dict | None, items: list[dict], by: str) -> dict | None:
    doses = [i for i in items if i["kind"] == "dose" and i.get("every_h")]
    obs = [i for i in items if i["kind"] == "obs"]
    if not doses and not obs:
        return None
    old = previous or {}
    by_key = {d["key"]: d for d in old.get("doses", [])}
    for item in doses:
        name = item["name"] or item["text"]
        by_key[key_of(name)] = {"name": name, "amount": item["amount"], "every_h": item["every_h"], "key": key_of(name)}
    limits = dict(old.get("limits", {}))
    for item in obs:
        limits.update({k: v for k, v in (item.get("limits") or {}).items() if v is not None})
    every = next((i["every_h"] for i in reversed(obs) if i.get("every_h")), old.get("obs_every_h"))
    return {"doses": list(by_key.values()), "obs_every_h": every, "limits": limits, "by": by}


def sign_order(store, episode_id: str, items: list[dict], by: str, ts: int, draft_id: str | None = None) -> int:
    """Write `order.signed` and, for dose or obs items, the merged `ward.orders_set`. Returns ts.

    `draft_id` names the dictated draft being signed; it is stored so the draft closes.
    """
    events = store.events(episode_id)
    state = current_state(events)
    if state not in ORDER_STATES:
        raise TaskError(409, f"Orders are signed in clinic, admitting or ward. The patient is in {state}.")
    refusal = draft_refusal(events, "order", draft_id)
    if refusal:
        raise TaskError(*refusal)
    signed = {"items": items, "by": by, **({"draft_id": draft_id} if draft_id else {})}
    store.append(episode_id, "order.signed", signed, ts_ms=ts)
    previous = next(iter(reversed(_of(events, "ward.orders_set"))), None)
    merged = _merged_orders(previous["payload"] if previous else None, items, by)
    if merged:
        store.append(episode_id, "ward.orders_set", merged, ts_ms=ts)
    return ts


def acknowledge_order(store, episode_id: str, order_id: str, by: str, ts: int) -> int:
    """Write `order.acknowledged`, then one `task.created` per item, all due at ts. Returns ts."""
    order = store.get_event(order_id)
    if order is None or order["episode_id"] != episode_id or order["event_type"] != "order.signed":
        raise TaskError(404, "Order not found")
    if any(e["payload"]["order_id"] == order_id for e in _of(store.events(episode_id), "order.acknowledged")):
        raise TaskError(409, "This order is already acknowledged.")
    store.append(episode_id, "order.acknowledged", {"order_id": order_id, "by": by}, ts_ms=ts)
    for index, item in enumerate(order["payload"]["items"]):
        payload = {
            "order_id": order_id,
            "index": index,
            "title": item["text"],
            "kind": item["kind"],
            "mode": item["mode"],
            "proof": item["proof"],
            "every_h": item["every_h"],
            "due_ms": ts,
            "name": item["name"],
            "amount": item["amount"],
        }
        store.append(episode_id, "task.created", payload, ts_ms=ts)
    return ts


def _task(store, episode_id: str, task_id: str) -> tuple[dict, dict]:
    created = store.get_event(task_id)
    if created is None or created["episode_id"] != episode_id or created["event_type"] != "task.created":
        raise TaskError(404, "Task not found")
    view = next(t for t in task_list(store.events(episode_id)) if t["id"] == task_id)
    return created["payload"], view


def _refuse_if_closed(view: dict) -> None:
    if view["status"] == "closed":
        raise TaskError(409, "This task is closed because the patient's stay has ended.")


def begin_task(store, episode_id: str, task_id: str, by: str, ts: int) -> int:
    payload, view = _task(store, episode_id, task_id)
    _refuse_if_closed(view)
    if payload["mode"] != "start_end":
        raise TaskError(409, "This task is ticked, not begun.")
    if view["status"] == "running":
        raise TaskError(409, "This task is already running.")
    if view["status"] == "done":
        raise TaskError(409, "This task is already done.")
    store.append(episode_id, "task.began", {"task_id": task_id, "by": by}, ts_ms=ts)
    return ts


NOT_CHECKED = "Kept as proof; no check was made."
EARLIER_PHOTO = "This photo was taken before the last time this task was done. Add a new photo."


def _proof_match(store, episode_id: str, task: dict, task_id: str, proof_id: str, values: dict | None) -> dict:
    """{match, why, source} for this task's photo. A mismatch never refuses (D9).

    A monitor photo is compared again with the values confirmed now, not with what the form held at upload.
    """
    photo = store.get_event(proof_id)
    if photo is None or photo["episode_id"] != episode_id or photo["event_type"] != "photo.added":
        raise TaskError(404, "Photo not found")
    if photo["payload"].get("task_id") != task_id:
        raise TaskError(409, "This photo was checked against another task.")
    events = store.events(episode_id)
    seen_photo, checks = False, []
    for e in events:
        if e["id"] == proof_id:
            seen_photo = True
        elif e["event_type"] == "task.done" and e["payload"]["task_id"] == task_id and seen_photo:
            raise TaskError(409, EARLIER_PHOTO)
        elif e["event_type"] == "proof.checked" and e["payload"]["photo_id"] == proof_id:
            checks.append(e["payload"])
    if not checks:
        return {"match": "none", "why": NOT_CHECKED, "source": "none"}
    found = checks[-1]
    if task["kind"] == "obs" and values and "values_read" in found:
        again = proof.check_monitor(found["values_read"], values)
        return {"match": again["match"], "why": again["why"], "source": found.get("source", "none")}
    return {"match": found["match"], "why": found.get("why", ""), "source": found.get("source", "none")}


def complete_task(
    store,
    episode_id: str,
    task_id: str,
    by: str,
    ts: int,
    *,
    via: str = "tap",
    note: str = "",
    values: dict | None = None,
    transcript: str = "",
    proof_id: str | None = None,
) -> int:
    payload, view = _task(store, episode_id, task_id)
    _refuse_if_closed(view)
    if view["status"] == "done":
        raise TaskError(409, "This task is already done.")
    if payload["mode"] == "start_end" and view["status"] != "running":
        raise TaskError(409, "Begin the task before marking it done.")
    if payload["kind"] == "obs" and not values:
        raise TaskError(422, "Observation values are needed to finish this task.")
    done = {"task_id": task_id, "by": by, "via": via, "note": note, "transcript": transcript}
    if proof_id:
        done.update(proof_id=proof_id, **_proof_match(store, episode_id, payload, task_id, proof_id, values))
    if values:
        done["values"] = values
    store.append(episode_id, "task.done", done, ts_ms=ts)
    if payload["kind"] == "dose":
        name = payload["name"] or payload["title"]
        fact = {"key": key_of(name), "name": name, "amount": payload["amount"], "by": by, "source": "task"}
        store.append(episode_id, "dose.given", fact, ts_ms=ts)
    elif payload["kind"] == "obs":
        store.append(episode_id, "obs.recorded", {**values, "by": by}, ts_ms=ts)
    return ts

"""Nudges: a recorded fact set beside what a person ordered, limited or prescribed.

Every nudge names the intent event and the fact event it compares. The wording
restates both. It never says what to give, stop or change.
"""

from __future__ import annotations

from app.morning.discharge import visible_events

HOUR_MS = 3_600_000
GRACE_MS = 30 * 60_000
CORRECTABLE = {"count_open", "obs_past_limit"}  # nudges about a recorded fact that a correction replaces
LIMIT_TEXT = {
    "sbp_min": ("systolic BP", "below", "sbp"),
    "sbp_max": ("systolic BP", "above", "sbp"),
    "hr_max": ("heart rate", "above", "hr"),
    "spo2_min": ("SpO2", "below", "spo2"),
    "temp_max": ("temperature", "above", "temp"),
}


def hours(value: float) -> str:
    """An interval with its unit: 6.0 -> '6 h', 1.5 -> '1.5 h', 0.25 -> '15 min'. Below an hour reads in minutes."""
    if 0 < value < 1:
        return f"{round(value * 60):g} min"
    return f"{value:g} h"


def span(ms: int) -> str:
    minutes = max(0, int(ms // 60_000))
    hours, minutes = divmod(minutes, 60)
    if hours and minutes:
        return f"{hours} h {minutes} min"
    return f"{hours} h" if hours else f"{minutes} min"


def _nudge(key, kind, to, says, intent, fact, at_ms, says_staff=None):
    return {
        "key": key,
        "kind": kind,
        "to": to,
        "says": says,
        "says_staff": says_staff or says,
        "intent_id": intent["id"] if intent else None,
        "fact_id": fact["id"] if fact else None,
        "at_ms": at_ms,
    }


def _latest(events, kind):
    rows = [event for event in events if event["event_type"] == kind]
    return rows[-1] if rows else None


def _norm(strength: str) -> str:
    return "".join((strength or "").lower().split())


def strips_vs_rx(events: list[dict]) -> list[dict]:
    """A scanned strip whose strength differs from the prescription, or that is not on it."""
    rx = _latest(events, "rx.ordered")
    if rx is None:
        return []
    rows = {row["key"]: row for row in rx["payload"]["rows"]}
    out = []
    for strip in (e for e in events if e["event_type"] == "brownbag.med_found"):
        found = strip["payload"]
        name = found.get("generic") or found.get("name_as_read") or ""
        key = found.get("generic") or " ".join(name.lower().split())
        row = rows.get(key)
        read = f"{name} {found.get('strength') or ''}".strip()
        if row is None:
            says = f"The strip {read} is not on the prescription from {rx['payload']['by']}. Show it to your doctor."
            staff = f"Strip reads {read}; not on the prescription from {rx['payload']['by']}."
            out.append(_nudge(f"strip-off-rx:{strip['id']}", "strip_not_prescribed", "patient", says, rx, strip, strip["ts_ms"], staff))
        elif found.get("strength") and row["strength"] and _norm(found["strength"]) != _norm(row["strength"]):
            says = (
                f"This strip reads {read}. The prescription says {row['name']} {row['strength']}. "
                "Show both to your pharmacist or doctor."
            )
            staff = f"Strip reads {read}; prescription says {row['strength']}."
            out.append(_nudge(f"strip-strength:{strip['id']}", "strip_strength_differs", "patient", says, rx, strip, strip["ts_ms"], staff))
    return out


def _ward_clock(events: list[dict], at_ms: int) -> int:
    """Due-time checks run on the ward only: they stop when the discharge card is signed."""
    card = _latest(events, "discharge.card")
    return min(at_ms, card["ts_ms"]) if card else at_ms


def in_theatre(events: list[dict]) -> bool:
    """True while the latest patient.state event moved the patient into theatre. Ward tasks pause then."""
    last = _latest(events, "patient.state")
    return bool(last) and last["payload"]["to"] == "theatre"


def doses_vs_orders(events: list[dict], at_ms: int) -> list[dict]:
    """Overdue against the ordered interval, logged again too soon, or logged without an order."""
    orders = _latest(events, "ward.orders_set")
    if orders is None:
        return []
    at_ms = _ward_clock(events, at_ms)
    paused = in_theatre(events)  # due times are held in theatre and resume unchanged on return
    given = [e for e in events if e["event_type"] == "dose.given"]
    out = []
    ordered = {order["key"]: order for order in orders["payload"]["doses"]}
    for dose in given:
        if dose["payload"]["key"] not in ordered:
            says = f"{dose['payload']['name']} was logged by {dose['payload']['by']}. It is not on the ward orders."
            out.append(_nudge(f"dose-unordered:{dose['id']}", "dose_not_ordered", "nurse", says, orders, dose, dose["ts_ms"]))
    for key, order in ordered.items():
        every = order["every_h"] * HOUR_MS
        mine = [d for d in given if d["payload"]["key"] == key]
        for before, after in zip(mine, mine[1:]):
            gap = after["ts_ms"] - before["ts_ms"]
            if gap < every - GRACE_MS:
                says = (
                    f"{order['name']} was logged {span(gap)} after the previous dose. "
                    f"The order from {orders['payload']['by']} says every {hours(order['every_h'])}."
                )
                out.append(_nudge(f"dose-early:{after['id']}", "dose_logged_early", "nurse", says, orders, after, after["ts_ms"]))
        last = mine[-1] if mine else None
        since = last["ts_ms"] if last else orders["ts_ms"]
        if not paused and at_ms - since > every + GRACE_MS:
            what = f"The last dose was logged {span(at_ms - since)} ago." if last else f"No dose is logged in the {span(at_ms - since)} since the order."
            says = f"{order['name']} is ordered every {hours(order['every_h'])}. {what}"
            anchor = last["id"] if last else orders["id"]
            out.append(_nudge(f"dose-due:{key}:{anchor}", "dose_overdue", "nurse", says, orders, last, at_ms))
    return out


def obs_vs_limits(events: list[dict], at_ms: int) -> list[dict]:
    """A reading past a limit the doctor set, or an observation round that has not been logged."""
    orders = _latest(events, "ward.orders_set")
    if orders is None:
        return []
    limits = orders["payload"].get("limits") or {}
    out = []
    readings = [e for e in events if e["event_type"] == "obs.recorded"]
    for obs in readings:
        for name, limit in limits.items():
            label, side, field = LIMIT_TEXT[name]
            value = obs["payload"].get(field)
            if value is None or limit is None:
                continue
            crossed = value < limit if side == "below" else value > limit
            if crossed:
                says = f"{label[0].upper()}{label[1:]} {value} is {side} the limit of {limit} set by {orders['payload']['by']}."
                out.append(_nudge(f"obs:{obs['id']}:{name}", "obs_past_limit", "nurse", says, orders, obs, obs["ts_ms"]))
    every_h = orders["payload"].get("obs_every_h")
    at_ms = _ward_clock(events, at_ms)
    if every_h and readings and not in_theatre(events):  # the round starts with the first ward set, not in theatre
        last = readings[-1]
        if at_ms - last["ts_ms"] > every_h * HOUR_MS + GRACE_MS:
            says = f"Observations are ordered every {hours(every_h)}. The last set was logged {span(at_ms - last['ts_ms'])} ago."
            out.append(_nudge(f"obs-due:{last['id']}", "obs_overdue", "nurse", says, orders, last, at_ms))
    return out


def count_and_patient(events: list[dict]) -> list[dict]:
    """An open count at closing, a Need-help press, or a ticked sign from the doctor's discharge list."""
    out = []
    closing = _latest(events, "count.closing")
    if closing and (closing["payload"].get("unaccounted") or 0) > 0:
        opened = _latest(events, "count.pack_opened")
        p = closing["payload"]
        says = f"Closing count: {p.get('returned')} of {p.get('opened')} back, {p.get('unaccounted')} unaccounted."
        out.append(_nudge(f"count:{closing['id']}", "count_open", "nurse", says, opened, closing, closing["ts_ms"]))
    card = _latest(events, "discharge.card")
    for event in events:
        kind = event["event_type"]
        if kind == "help.requested":
            says = f"The patient pressed Need help: \"{event['payload']['says']}\""
            out.append(_nudge(f"help:{event['id']}", "help_requested", "nurse", says, card, event, event["ts_ms"]))
        elif kind == "checkin.recorded" and card is not None:
            listed = set(card["payload"]["warning_signs"])
            for sign in event["payload"].get("signs") or []:
                if sign in listed:
                    says = (
                        f"Day {event['payload']['day']} check-in ticked \"{sign}\". "
                        f"This sign is on the discharge list from {card['payload']['by']}."
                    )
                    out.append(_nudge(f"sign:{event['id']}:{sign}", "warning_sign_ticked", "nurse", says, card, event, event["ts_ms"]))
    return out


def evaluate(events: list[dict], at_ms: int) -> list[dict]:
    shown = visible_events(events)
    return (
        strips_vs_rx(shown)
        + doses_vs_orders(shown, at_ms)
        + obs_vs_limits(shown, at_ms)
        + count_and_patient(shown)
    )


def fresh(events: list[dict], at_ms: int) -> list[dict]:
    """Nudges not raised before. A key is raised once."""
    raised = {e["payload"]["key"] for e in events if e["event_type"] == "nudge.raised"}
    return [nudge for nudge in evaluate(events, at_ms) if nudge["key"] not in raised]


def open_nudges(events: list[dict]) -> list[dict]:
    """Raised nudges not yet answered. A count_open or obs_past_limit nudge closes when its fact is corrected.

    Overdue nudges (dose_overdue, obs_overdue) keep v1 behaviour: only an answer closes them.
    """
    seen = {e["payload"]["nudge_id"] for e in events if e["event_type"] == "nudge.seen"}
    struck = {e["supersedes_id"] for e in events if e.get("supersedes_id")}
    return [
        e for e in events
        if e["event_type"] == "nudge.raised" and e["id"] not in seen
        and not (e["payload"].get("kind") in CORRECTABLE and e["payload"].get("fact_id") in struck)
    ]

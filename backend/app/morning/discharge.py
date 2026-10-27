"""Fold the timeline into a discharge sheet. Decision events stay off it."""

from __future__ import annotations

DECISION_TYPES = {"vitals.card", "vitals.change", "brownbag.same_drug_twice"}


def visible_events(events: list[dict]) -> list[dict]:
    superseded = {event["supersedes_id"] for event in events if event.get("supersedes_id")}
    return [event for event in events if event["id"] not in superseded]


def fold(events: list[dict]) -> dict:
    shown = [
        event
        for event in visible_events(events)
        if event.get("tier") != "decision" and event["event_type"] not in DECISION_TYPES
    ]
    closings = [event for event in shown if event["event_type"] == "count.closing"]
    return {
        "opd": [event["payload"] for event in shown if event["event_type"] == "brownbag.med_found"],
        "drugs": [event["payload"] for event in shown if event["event_type"] == "druglog.given"],
        "count": closings[-1]["payload"] if closings else None,
        "readings": [event["payload"] for event in shown if event["event_type"] == "vitals.reading"],
        "narrative": (
            "Synthetic demo. This sheet lists what was recorded on the timeline. "
            "It does not state a treatment."
        ),
    }

"""Project the append-only event list into tracks, counts, and a ledger."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TrackView:
    track_id: str
    label: str
    zone: str
    status: str
    first_seen_ms: int
    last_seen_ms: int
    last_frame_id: str | None
    score: float | None
    low_confidence: bool
    bbox: list[float] | None


@dataclass
class AddView:
    item_type: str
    quantity: int
    media_ts_ms: int
    event_id: str
    transcript_id: str | None


@dataclass
class CountView:
    item_type: str | None
    quantity: int
    zone: str | None
    media_ts_ms: int
    event_id: str
    transcript_id: str | None


@dataclass
class Projection:
    tracks: dict[str, TrackView] = field(default_factory=dict)
    adds: list[AddView] = field(default_factory=list)
    counts: list[CountView] = field(default_factory=list)
    closing_ts: int | None = None
    phase: str | None = None

    def opened(self, item_type: str, at_ms: int | None = None) -> int:
        total = 0
        for add in self.adds:
            if add.item_type != item_type:
                continue
            if at_ms is not None and add.media_ts_ms > at_ms:
                continue
            total += add.quantity
        return total

    def item_types(self) -> list[str]:
        names = {track.label for track in self.tracks.values()}
        names.update(add.item_type for add in self.adds)
        return sorted(names)


def _payload(event: dict) -> dict:
    return event.get("payload") or {}


def project(events: list[dict], at_ms: int | None = None) -> Projection:
    """Fold events in append order. Events after at_ms are ignored."""
    view = Projection()
    for event in events:
        if at_ms is not None and event["media_ts_ms"] > at_ms:
            continue
        kind = event["event_type"]
        payload = _payload(event)
        if kind == "item_appeared":
            score = payload.get("score", event.get("confidence"))
            view.tracks[payload["track_id"]] = TrackView(
                track_id=payload["track_id"],
                label=payload["label"],
                zone=payload["zone"],
                status="active",
                first_seen_ms=event["media_ts_ms"],
                last_seen_ms=event["media_ts_ms"],
                last_frame_id=_frame_id(event),
                score=score,
                low_confidence=bool(payload.get("low_confidence")),
                bbox=payload.get("bbox"),
            )
        elif kind == "zone_changed":
            track = view.tracks.get(payload["track_id"])
            if track is None:
                continue
            track.zone = payload["to_zone"]
            track.last_seen_ms = event["media_ts_ms"]
            frame_id = _frame_id(event)
            if frame_id:
                track.last_frame_id = frame_id
            if payload.get("bbox"):
                track.bbox = payload["bbox"]
            if event.get("confidence") is not None:
                track.score = _min_score(track.score, event["confidence"])
        elif kind == "item_lost":
            track = view.tracks.get(payload["track_id"])
            if track is None:
                continue
            track.status = "lost"
            track.zone = payload.get("last_zone", track.zone)
            track.last_seen_ms = payload.get("last_seen_ms", track.last_seen_ms)
            if payload.get("last_frame_id"):
                track.last_frame_id = payload["last_frame_id"]
        elif kind == "spoken_count":
            action = payload.get("action")
            transcript_id = payload.get("transcript_id")
            if action == "add":
                view.adds.append(
                    AddView(
                        item_type=payload["item_type"],
                        quantity=int(payload["quantity"]),
                        media_ts_ms=event["media_ts_ms"],
                        event_id=event["id"],
                        transcript_id=transcript_id,
                    )
                )
            elif action == "count":
                view.counts.append(
                    CountView(
                        item_type=payload.get("item_type"),
                        quantity=int(payload["quantity"]),
                        zone=payload.get("zone"),
                        media_ts_ms=event["media_ts_ms"],
                        event_id=event["id"],
                        transcript_id=transcript_id,
                    )
                )
        elif kind == "checkpoint":
            phase = payload.get("phase")
            if phase in {"closing", "final"} and view.closing_ts is None:
                view.closing_ts = event["media_ts_ms"]
                view.phase = phase
            elif view.phase is None:
                view.phase = phase
        elif kind == "low_confidence":
            track = view.tracks.get(payload.get("track_id", ""))
            if track is not None:
                track.low_confidence = True
                if payload.get("score") is not None:
                    track.score = _min_score(track.score, payload["score"])
        elif kind == "identity_relink":
            track = view.tracks.get(payload.get("track_id", ""))
            if track is not None:
                track.low_confidence = True
    return view


def _frame_id(event: dict) -> str | None:
    for evidence_id in event.get("evidence") or []:
        if str(evidence_id).startswith("frame:"):
            return str(evidence_id).split(":", 1)[1]
    payload = _payload(event)
    return payload.get("frame_id")


def _min_score(current: float | None, new: float) -> float:
    if current is None:
        return new
    return min(current, new)


def tracks_at(events: list[dict], at_ms: int) -> dict[str, TrackView]:
    return project(events, at_ms=at_ms).tracks


def ledger_rows(events: list[dict], at_ms: int | None = None) -> list[dict]:
    """Counts per item type. After the closing checkpoint, field tracks are unaccounted."""
    if at_ms is None:
        closing = project(events).closing_ts
        at_ms = closing if closing is not None else _last_ts(events)
    view = project(events, at_ms=at_ms)
    closing = view.closing_ts is not None and (at_ms is None or at_ms >= view.closing_ts)
    rows = []
    for item_type in view.item_types():
        tray = field = bucket = unaccounted = 0
        for track in view.tracks.values():
            if track.label != item_type:
                continue
            if closing and track.zone == "field":
                unaccounted += 1
            elif track.zone == "tray":
                tray += 1
            elif track.zone == "field":
                field += 1
            elif track.zone == "bucket":
                bucket += 1
        rows.append(
            {
                "item_type": item_type,
                "opened": view.opened(item_type, at_ms),
                "tray": tray,
                "field": field,
                "bucket": bucket,
                "unaccounted": unaccounted,
            }
        )
    return rows


def _last_ts(events: list[dict]) -> int:
    if not events:
        return 0
    return max(event["media_ts_ms"] for event in events)


def open_discrepancies(events: list[dict]) -> list[dict]:
    resolved = {
        _payload(event)["discrepancy_id"]
        for event in events
        if event["event_type"] == "resolution"
    }
    rows = []
    for event in events:
        if event["event_type"] != "discrepancy":
            continue
        payload = dict(_payload(event))
        status = "resolved" if event["id"] in resolved else "open"
        payload["status"] = status
        rows.append(
            {
                "id": event["id"],
                "case_id": event["case_id"],
                "media_ts_ms": event["media_ts_ms"],
                **payload,
                "evidence": event.get("evidence") or payload.get("evidence") or [],
                "status": status,
            }
        )
    return rows

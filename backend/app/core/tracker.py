"""Turn per-frame detections into appear, move, lost, and re-link events."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.core.zones import bbox_center


@dataclass
class LiveTrack:
    track_id: str
    label: str
    zone: str
    status: str
    missed: int
    first_seen_ms: int
    last_seen_ms: int
    last_frame_id: str | None
    score: float | None
    low_confidence: bool
    bbox: list[float]
    seen_chunk: str | None = None


@dataclass
class Tracker:
    """In-memory cache. The event list remains the source of truth."""

    lost_after_frames: int = 4
    low_confidence: float = 0.45
    relink_distance: float = 0.15
    tracks: dict[str, LiveTrack] = field(default_factory=dict)
    _chunk_map: dict[tuple[str, str, str], str] = field(default_factory=dict)

    def feed(
        self,
        detections: list[dict],
        *,
        frame_id: str,
        media_ts_ms: int,
        chunk_id: str = "script",
        relink: bool = False,
        external_ids: bool = False,
    ) -> list[dict]:
        """Return event payloads. The engine stamps ids and evidence."""
        events: list[dict] = []
        seen: set[str] = set()
        for detection in detections:
            raw_id = str(detection["track_id"])
            label = detection["label"]
            zone = detection["zone"]
            bbox = list(detection["bbox"])
            score = detection.get("score")
            track_id = self._resolve_id(
                raw_id,
                label,
                bbox,
                chunk_id=chunk_id,
                relink=relink,
                external_ids=external_ids,
                events=events,
                media_ts_ms=media_ts_ms,
                frame_id=frame_id,
            )
            seen.add(track_id)
            if track_id not in self.tracks:
                self.tracks[track_id] = LiveTrack(
                    track_id=track_id,
                    label=label,
                    zone=zone,
                    status="active",
                    missed=0,
                    first_seen_ms=media_ts_ms,
                    last_seen_ms=media_ts_ms,
                    last_frame_id=frame_id,
                    score=score,
                    low_confidence=False,
                    bbox=bbox,
                    seen_chunk=chunk_id,
                )
                events.append(
                    {
                        "event_type": "item_appeared",
                        "media_ts_ms": media_ts_ms,
                        "confidence": score,
                        "evidence": [f"frame:{frame_id}"],
                        "payload": {
                            "track_id": track_id,
                            "label": label,
                            "zone": zone,
                            "bbox": bbox,
                            "mask_ref": detection.get("mask_ref"),
                            "score": score,
                            "frame_id": frame_id,
                        },
                    }
                )
                if score is not None and score < self.low_confidence:
                    self._flag_low(track_id, score, media_ts_ms, frame_id, events, "detection score")
                continue
            track = self.tracks[track_id]
            track.missed = 0
            track.status = "active"
            track.last_seen_ms = media_ts_ms
            track.last_frame_id = frame_id
            track.bbox = bbox
            track.seen_chunk = chunk_id
            if score is not None:
                track.score = score if track.score is None else min(track.score, score)
            if track.zone != zone:
                events.append(
                    {
                        "event_type": "zone_changed",
                        "media_ts_ms": media_ts_ms,
                        "confidence": score,
                        "evidence": [f"frame:{frame_id}"],
                        "payload": {
                            "track_id": track_id,
                            "from_zone": track.zone,
                            "to_zone": zone,
                            "bbox": bbox,
                            "frame_id": frame_id,
                        },
                    }
                )
                track.zone = zone
            if score is not None and score < self.low_confidence and not track.low_confidence:
                self._flag_low(track_id, score, media_ts_ms, frame_id, events, "detection score")
        for track_id, track in self.tracks.items():
            if track_id in seen or track.status == "lost":
                continue
            track.missed += 1
            if track.missed >= self.lost_after_frames:
                events.append(
                    {
                        "event_type": "item_lost",
                        "media_ts_ms": media_ts_ms,
                        "confidence": track.score,
                        "evidence": [f"frame:{track.last_frame_id}"] if track.last_frame_id else [],
                        "payload": {
                            "track_id": track_id,
                            "last_zone": track.zone,
                            "last_frame_id": track.last_frame_id,
                            "last_seen_ms": track.last_seen_ms,
                        },
                    }
                )
                track.status = "lost"
        return events

    def _resolve_id(
        self,
        raw_id: str,
        label: str,
        bbox: list[float],
        *,
        chunk_id: str,
        relink: bool,
        external_ids: bool,
        events: list[dict],
        media_ts_ms: int,
        frame_id: str,
    ) -> str:
        """Scripted clips keep the given id. SAM ids are only stable inside one call."""
        mapped = self._chunk_map.get((chunk_id, label, raw_id))
        if mapped:
            return mapped
        if not external_ids:
            self._chunk_map[(chunk_id, label, raw_id)] = raw_id
            return raw_id
        claimed = {track_id for (chunk, _label, _raw), track_id in self._chunk_map.items() if chunk == chunk_id}
        if relink:
            match = self._nearest(label, bbox, exclude=claimed)
            if match is not None:
                self._chunk_map[(chunk_id, label, raw_id)] = match
                self.tracks[match].low_confidence = True
                events.append(
                    {
                        "event_type": "identity_relink",
                        "media_ts_ms": media_ts_ms,
                        "confidence": self.low_confidence,
                        "evidence": [f"frame:{frame_id}"],
                        "payload": {
                            "track_id": match,
                            "observed_id": raw_id,
                            "label": label,
                            "reason": "stream re-link by label and position",
                        },
                    }
                )
                return match
        minted = self._mint(label)
        self._chunk_map[(chunk_id, label, raw_id)] = minted
        return minted

    def _mint(self, label: str) -> str:
        number = 1
        taken = set(self.tracks) | set(self._chunk_map.values())
        while f"{label}-{number}" in taken:
            number += 1
        return f"{label}-{number}"

    def _nearest(self, label: str, bbox: list[float], exclude: set[str]) -> str | None:
        x, y = bbox_center(bbox)
        best_id = None
        best_dist = self.relink_distance
        for track in self.tracks.values():
            if track.track_id in exclude or track.label != label or track.status == "lost":
                continue
            tx, ty = bbox_center(track.bbox)
            dist = ((tx - x) ** 2 + (ty - y) ** 2) ** 0.5
            if dist <= best_dist:
                best_dist = dist
                best_id = track.track_id
        return best_id

    def _flag_low(
        self,
        track_id: str,
        score: float,
        media_ts_ms: int,
        frame_id: str,
        events: list[dict],
        reason: str,
    ) -> None:
        track = self.tracks[track_id]
        track.low_confidence = True
        events.append(
            {
                "event_type": "low_confidence",
                "media_ts_ms": media_ts_ms,
                "confidence": score,
                "evidence": [f"frame:{frame_id}"],
                "payload": {
                    "track_id": track_id,
                    "score": score,
                    "reason": reason,
                },
            }
        )

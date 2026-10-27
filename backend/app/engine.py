"""One pipeline for scripted replay, upload, and the live socket."""

from __future__ import annotations

from pathlib import Path

from app.config import Settings
from app.core.frames import render_frame
from app.core.ledger import ledger_rows, open_discrepancies
from app.core.parser import parse_utterance
from app.core.rules import closing_gate, new_discrepancies
from app.core.tracker import Tracker
from app.core.zones import zone_for_bbox
from app.store import Store, new_id, now_iso


class Engine:
    def __init__(self, store: Store, settings: Settings):
        self.store = store
        self.settings = settings

    def create_case(self, label: str, item_types: list[str]) -> dict:
        return self.store.create_case(label, item_types)

    def set_zones(self, case_id: str, zones: list[dict]) -> dict[str, list]:
        self._require_case(case_id)
        self.store.save_zones(case_id, zones)
        return self.store.zones(case_id)

    def replay(self, case_id: str, scenario: dict) -> dict:
        self._require_case(case_id)
        zone_rows = [{"name": name, "polygon": polygon} for name, polygon in scenario["zones"].items()]
        self.store.save_zones(case_id, zone_rows)
        zones = self.store.zones(case_id)
        tracker = Tracker(
            lost_after_frames=self.settings.lost_after_frames,
            low_confidence=self.settings.low_confidence,
        )
        width = int(scenario.get("width", 640))
        height = int(scenario.get("height", 360))
        keyframes = []
        for step in scenario["steps"]:
            media_ts = int(step["media_ts_ms"])
            frame_id = None
            if "detections" in step:
                frame_id = self._ingest_detections(
                    case_id,
                    tracker,
                    zones,
                    step["detections"],
                    media_ts_ms=media_ts,
                    width=width,
                    height=height,
                    source="scripted-perception",
                )
            if step.get("say"):
                self.add_utterance(
                    case_id,
                    step["say"],
                    t0_ms=media_ts,
                    t1_ms=media_ts + 1500,
                    source="scripted-speech",
                )
            self.apply_rules(case_id, now_ms=media_ts, finalize=False)
            keyframes.append(self._keyframe(case_id, media_ts, frame_id))
        last_ts = scenario["steps"][-1]["media_ts_ms"] if scenario["steps"] else 0
        self.apply_rules(case_id, now_ms=last_ts, finalize=True)
        if keyframes:
            keyframes[-1] = self._keyframe(case_id, last_ts, keyframes[-1]["frame_id"])
        self._cache_tracks(case_id, tracker)
        return self.snapshot(case_id, keyframes=keyframes, perception="scripted")

    def add_utterance(
        self,
        case_id: str,
        text: str,
        *,
        t0_ms: int,
        t1_ms: int,
        source: str,
    ) -> list[dict]:
        parsed = parse_utterance(text)
        transcript_id = self.store.add_transcript(case_id, t0_ms, t1_ms, parsed["text"])
        drafts: list[dict] = []
        if parsed["phase"]:
            drafts.append(
                {
                    "event_type": "checkpoint",
                    "media_ts_ms": t0_ms,
                    "confidence": 1.0,
                    "evidence": [f"transcript:{transcript_id}"],
                    "payload": {"phase": parsed["phase"], "transcript_id": transcript_id},
                }
            )
        for kind in ("adds", "counts"):
            for item in parsed[kind]:
                drafts.append(
                    {
                        "event_type": "spoken_count",
                        "media_ts_ms": t0_ms,
                        "confidence": 1.0,
                        "evidence": [f"transcript:{transcript_id}"],
                        "payload": {**item, "transcript_id": transcript_id},
                    }
                )
        if parsed["needs_model"]:
            drafts.append(
                {
                    "event_type": "low_confidence",
                    "media_ts_ms": t0_ms,
                    "confidence": 0.2,
                    "evidence": [f"transcript:{transcript_id}"],
                    "payload": {
                        "track_id": "",
                        "score": 0.2,
                        "reason": "spoken line was not parsed",
                        "transcript_id": transcript_id,
                        "text": parsed["text"],
                    },
                }
            )
        return [self._append(case_id, draft, source) for draft in drafts]

    def apply_rules(self, case_id: str, *, now_ms: int, finalize: bool) -> list[dict]:
        events = self.store.events(case_id)
        drafts = new_discrepancies(
            events,
            now_ms=now_ms,
            finalize=finalize,
            low_confidence=self.settings.low_confidence,
            window_ms=self.settings.unannounced_window_ms,
        )
        written = []
        for draft in drafts:
            evidence = draft.get("evidence") or []
            payload = {key: value for key, value in draft.items() if key != "evidence"}
            written.append(
                self._append(
                    case_id,
                    {
                        "event_type": "discrepancy",
                        "media_ts_ms": draft["media_ts_ms"],
                        "confidence": 1.0,
                        "evidence": evidence,
                        "payload": payload,
                    },
                    source="rules",
                )
            )
        return written

    def resolve(self, discrepancy_id: str, reason: str, by: str) -> dict:
        found = None
        case_id = None
        for case_row in self._cases_touching(discrepancy_id):
            case_id = case_row
            for event in self.store.events(case_id):
                if event["id"] == discrepancy_id and event["event_type"] == "discrepancy":
                    found = event
                    break
            if found:
                break
        if found is None or case_id is None:
            raise KeyError(discrepancy_id)
        self._append(
            case_id,
            {
                "event_type": "resolution",
                "media_ts_ms": found["media_ts_ms"],
                "confidence": 1.0,
                "evidence": [discrepancy_id],
                "payload": {"discrepancy_id": discrepancy_id, "reason": reason, "by": by},
            },
            source="human",
        )
        return self.snapshot(case_id)

    def gate(self, case_id: str) -> dict:
        self.apply_rules(case_id, now_ms=self._last_ts(case_id), finalize=True)
        decision = closing_gate(self.store.events(case_id))
        self.store.set_status(case_id, "reconciled" if decision["ok"] else "blocked")
        decision["ledger"] = ledger_rows(self.store.events(case_id))
        return decision

    def snapshot(self, case_id: str, *, keyframes: list | None = None, perception: str | None = None) -> dict:
        events = self.store.events(case_id)
        case = self.store.get_case(case_id)
        return {
            "case": case,
            "zones": self.store.zones(case_id),
            "ledger": ledger_rows(events),
            "discrepancies": open_discrepancies(events),
            "transcript": self.store.transcripts(case_id),
            "frames": [
                {
                    "id": frame["id"],
                    "media_ts_ms": frame["media_ts_ms"],
                    "url": f"/frames/{frame['id']}",
                }
                for frame in self.store.frames(case_id)
            ],
            "model_calls": self.store.model_calls(case_id),
            "keyframes": keyframes or [],
            "perception": perception,
            "gate": closing_gate(events),
        }

    def _ingest_detections(
        self,
        case_id: str,
        tracker: Tracker,
        zones: dict[str, list],
        detections: list[dict],
        *,
        media_ts_ms: int,
        width: int,
        height: int,
        source: str,
        chunk_id: str = "script",
        relink: bool = False,
        external_ids: bool = False,
    ) -> str:
        located = []
        for detection in detections:
            zone = detection.get("zone") or zone_for_bbox(detection["bbox"], zones)
            located.append({**detection, "zone": zone})
        frame_id = new_id()
        png = render_frame(width, height, zones, located)
        path = self.settings.frame_dir / case_id / f"{frame_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(png)
        self.store.add_frame(frame_id, case_id, media_ts_ms, str(path), width, height)
        drafts = tracker.feed(
            located,
            frame_id=frame_id,
            media_ts_ms=media_ts_ms,
            chunk_id=chunk_id,
            relink=relink,
            external_ids=external_ids,
        )
        for draft in drafts:
            if draft["event_type"] == "low_confidence" and not draft["payload"].get("track_id"):
                continue
            self._append(case_id, draft, source)
        return frame_id

    def _append(self, case_id: str, draft: dict, source: str) -> dict:
        event = {
            "id": new_id(),
            "case_id": case_id,
            "media_ts_ms": int(draft["media_ts_ms"]),
            "wall_clock": now_iso(),
            "source": source,
            "confidence": draft.get("confidence"),
            "evidence": draft.get("evidence") or [],
            "event_type": draft["event_type"],
            "payload": draft.get("payload") or {},
        }
        return self.store.append_event(event)

    def _cache_tracks(self, case_id: str, tracker: Tracker) -> None:
        rows = []
        for track in tracker.tracks.values():
            rows.append(
                {
                    "track_id": track.track_id,
                    "label": track.label,
                    "zone": track.zone,
                    "status": track.status,
                    "first_seen_ms": track.first_seen_ms,
                    "last_seen_ms": track.last_seen_ms,
                    "last_frame_id": track.last_frame_id,
                    "score": track.score,
                    "low_confidence": track.low_confidence,
                    "bbox": track.bbox,
                }
            )
        self.store.save_tracks(case_id, rows)

    def _keyframe(self, case_id: str, media_ts_ms: int, frame_id: str | None) -> dict:
        events = self.store.events(case_id)
        return {
            "media_ts_ms": media_ts_ms,
            "frame_id": frame_id,
            "ledger": ledger_rows(events),
            "discrepancies": [row for row in open_discrepancies(events) if row["status"] == "open"],
        }

    def _last_ts(self, case_id: str) -> int:
        events = self.store.events(case_id)
        if not events:
            return 0
        return max(event["media_ts_ms"] for event in events)

    def _require_case(self, case_id: str) -> dict:
        case = self.store.get_case(case_id)
        if case is None:
            raise KeyError(case_id)
        return case

    def _cases_touching(self, discrepancy_id: str) -> list[str]:
        rows = self.store._conn.execute(
            "SELECT case_id FROM events WHERE id = ? AND event_type = 'discrepancy'",
            (discrepancy_id,),
        ).fetchall()
        return [row["case_id"] for row in rows]


def track_path(events: list[dict], track_id: str) -> list[dict]:
    points = []
    for event in events:
        payload = event.get("payload") or {}
        if payload.get("track_id") != track_id:
            continue
        if event["event_type"] not in {"item_appeared", "zone_changed", "item_lost"}:
            continue
        zone = payload.get("zone") or payload.get("to_zone") or payload.get("last_zone")
        points.append(
            {
                "media_ts_ms": event["media_ts_ms"],
                "event_type": event["event_type"],
                "zone": zone,
                "frame_id": payload.get("frame_id") or payload.get("last_frame_id"),
                "bbox": payload.get("bbox"),
            }
        )
    return points


def id_switch_count(events: list[dict]) -> int:
    return sum(1 for event in events if event["event_type"] == "identity_relink")

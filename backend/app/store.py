"""SQLite event ledger. The track table is a cache rebuilt from events."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.models import Event

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  status TEXT NOT NULL,
  item_types TEXT NOT NULL,
  created_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE TABLE IF NOT EXISTS zones (
  case_id TEXT NOT NULL,
  name TEXT NOT NULL,
  polygon TEXT NOT NULL,
  PRIMARY KEY (case_id, name)
);
CREATE TABLE IF NOT EXISTS frames (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  media_ts_ms INTEGER NOT NULL,
  path TEXT NOT NULL,
  width INTEGER NOT NULL,
  height INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS transcript_segments (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  t0_ms INTEGER NOT NULL,
  t1_ms INTEGER NOT NULL,
  text TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tracks (
  case_id TEXT NOT NULL,
  track_id TEXT NOT NULL,
  label TEXT NOT NULL,
  zone TEXT,
  status TEXT NOT NULL,
  first_seen_ms INTEGER,
  last_seen_ms INTEGER,
  last_frame_id TEXT,
  score REAL,
  low_confidence INTEGER NOT NULL DEFAULT 0,
  bbox TEXT,
  PRIMARY KEY (case_id, track_id)
);
CREATE TABLE IF NOT EXISTS events (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  media_ts_ms INTEGER NOT NULL,
  wall_clock TEXT NOT NULL,
  source TEXT NOT NULL,
  confidence REAL,
  evidence TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY,
  case_id TEXT NOT NULL,
  created_at TEXT NOT NULL,
  narrative TEXT NOT NULL,
  path TEXT NOT NULL,
  model TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS model_calls (
  id TEXT PRIMARY KEY,
  case_id TEXT,
  model TEXT NOT NULL,
  adapter TEXT NOT NULL,
  created_at TEXT NOT NULL,
  note TEXT NOT NULL
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid7())


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    def create_case(self, label: str, item_types: list[str]) -> dict:
        case_id = new_id()
        with self._lock:
            self._conn.execute(
                "INSERT INTO cases (id, label, status, item_types, created_at) VALUES (?, ?, ?, ?, ?)",
                (case_id, label, "open", json.dumps(item_types), now_iso()),
            )
            self._conn.commit()
        return self.get_case(case_id)

    def get_case(self, case_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM cases WHERE id = ?", (case_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["item_types"] = json.loads(data["item_types"])
        return data

    def set_status(self, case_id: str, status: str) -> None:
        closed = now_iso() if status == "reconciled" else None
        with self._lock:
            self._conn.execute(
                "UPDATE cases SET status = ?, closed_at = COALESCE(?, closed_at) WHERE id = ?",
                (status, closed, case_id),
            )
            self._conn.commit()

    def save_zones(self, case_id: str, zones: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM zones WHERE case_id = ?", (case_id,))
            for zone in zones:
                self._conn.execute(
                    "INSERT INTO zones (case_id, name, polygon) VALUES (?, ?, ?)",
                    (case_id, zone["name"], json.dumps(zone["polygon"])),
                )
            self._conn.commit()

    def zones(self, case_id: str) -> dict[str, list]:
        rows = self._conn.execute(
            "SELECT name, polygon FROM zones WHERE case_id = ? ORDER BY name", (case_id,)
        ).fetchall()
        return {row["name"]: json.loads(row["polygon"]) for row in rows}

    def add_frame(self, frame_id: str, case_id: str, media_ts_ms: int, path: str, width: int, height: int) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO frames (id, case_id, media_ts_ms, path, width, height) VALUES (?, ?, ?, ?, ?, ?)",
                (frame_id, case_id, media_ts_ms, path, width, height),
            )
            self._conn.commit()

    def get_frame(self, frame_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM frames WHERE id = ?", (frame_id,)).fetchone()
        return dict(row) if row else None

    def frames(self, case_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM frames WHERE case_id = ? ORDER BY media_ts_ms, id", (case_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def add_transcript(self, case_id: str, t0_ms: int, t1_ms: int, text: str) -> str:
        transcript_id = new_id()
        with self._lock:
            self._conn.execute(
                "INSERT INTO transcript_segments (id, case_id, t0_ms, t1_ms, text) VALUES (?, ?, ?, ?, ?)",
                (transcript_id, case_id, t0_ms, t1_ms, text),
            )
            self._conn.commit()
        return transcript_id

    def transcripts(self, case_id: str, t0_ms: int | None = None, t1_ms: int | None = None) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM transcript_segments WHERE case_id = ? ORDER BY t0_ms, id",
            (case_id,),
        ).fetchall()
        items = [dict(row) for row in rows]
        if t0_ms is None and t1_ms is None:
            return items
        start = 0 if t0_ms is None else t0_ms
        end = 10**12 if t1_ms is None else t1_ms
        return [item for item in items if item["t1_ms"] >= start and item["t0_ms"] <= end]

    def append_event(self, event: dict) -> dict:
        checked = Event.model_validate(event).model_dump()
        with self._lock:
            self._conn.execute(
                """INSERT INTO events
                   (id, case_id, media_ts_ms, wall_clock, source, confidence, evidence, event_type, payload)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    checked["id"],
                    checked["case_id"],
                    checked["media_ts_ms"],
                    checked["wall_clock"],
                    checked["source"],
                    checked["confidence"],
                    json.dumps(checked["evidence"]),
                    checked["event_type"],
                    json.dumps(checked["payload"]),
                ),
            )
            self._conn.commit()
        return checked

    def events(self, case_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM events WHERE case_id = ? ORDER BY rowid", (case_id,)
        ).fetchall()
        items = []
        for row in rows:
            item = dict(row)
            item["evidence"] = json.loads(item["evidence"])
            item["payload"] = json.loads(item["payload"])
            items.append(item)
        return items

    def save_tracks(self, case_id: str, tracks: list[dict]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM tracks WHERE case_id = ?", (case_id,))
            for track in tracks:
                self._conn.execute(
                    """INSERT INTO tracks
                       (case_id, track_id, label, zone, status, first_seen_ms, last_seen_ms,
                        last_frame_id, score, low_confidence, bbox)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        case_id,
                        track["track_id"],
                        track["label"],
                        track.get("zone"),
                        track.get("status", "active"),
                        track.get("first_seen_ms"),
                        track.get("last_seen_ms"),
                        track.get("last_frame_id"),
                        track.get("score"),
                        1 if track.get("low_confidence") else 0,
                        json.dumps(track.get("bbox")),
                    ),
                )
            self._conn.commit()

    def track(self, case_id: str, track_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM tracks WHERE case_id = ? AND track_id = ?",
            (case_id, track_id),
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["bbox"] = json.loads(data["bbox"]) if data["bbox"] else None
        data["low_confidence"] = bool(data["low_confidence"])
        return data

    def find_track(self, track_id: str) -> dict | None:
        rows = self._conn.execute("SELECT * FROM tracks WHERE track_id = ?", (track_id,)).fetchall()
        if len(rows) != 1:
            return None
        data = dict(rows[0])
        data["bbox"] = json.loads(data["bbox"]) if data["bbox"] else None
        data["low_confidence"] = bool(data["low_confidence"])
        return data

    def save_report(self, case_id: str, narrative: str, path: str, model: str) -> dict:
        report_id = new_id()
        created = now_iso()
        with self._lock:
            self._conn.execute("DELETE FROM reports WHERE case_id = ?", (case_id,))
            self._conn.execute(
                "INSERT INTO reports (id, case_id, created_at, narrative, path, model) VALUES (?, ?, ?, ?, ?, ?)",
                (report_id, case_id, created, narrative, path, model),
            )
            self._conn.commit()
        return self.get_report(case_id)

    def get_report(self, case_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM reports WHERE case_id = ? ORDER BY created_at DESC LIMIT 1",
            (case_id,),
        ).fetchone()
        return dict(row) if row else None

    def log_model_call(self, model: str, adapter: str, note: str, case_id: str | None = None) -> dict:
        call_id = new_id()
        created = now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO model_calls (id, case_id, model, adapter, created_at, note) VALUES (?, ?, ?, ?, ?, ?)",
                (call_id, case_id, model, adapter, created, note),
            )
            self._conn.commit()
        return {"id": call_id, "model": model, "adapter": adapter, "note": note, "created_at": created}

    def model_calls(self, case_id: str) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM model_calls WHERE case_id = ? ORDER BY created_at", (case_id,)
        ).fetchall()
        return [dict(row) for row in rows]

    def known_evidence_ids(self, case_id: str) -> set[str]:
        known: set[str] = set()
        for frame in self.frames(case_id):
            known.add(frame["id"])
            known.add(f"frame:{frame['id']}")
        for segment in self.transcripts(case_id):
            known.add(segment["id"])
            known.add(f"transcript:{segment['id']}")
        for event in self.events(case_id):
            known.add(event["id"])
            payload = event.get("payload") or {}
            if payload.get("track_id"):
                known.add(payload["track_id"])
                known.add(f"track:{payload['track_id']}")
        return known

"""Append-only morning timeline. A correction hides the event it replaces."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from app.store import new_id, now_iso

SCHEMA = """
CREATE TABLE IF NOT EXISTS episodes (
  id TEXT PRIMARY KEY,
  label TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS timeline (
  id TEXT PRIMARY KEY,
  episode_id TEXT NOT NULL,
  ts_ms INTEGER NOT NULL,
  wall_clock TEXT NOT NULL,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  supersedes_id TEXT,
  tier TEXT NOT NULL
);
"""


class MorningStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._sim: dict[str, dict] = {}

    def sim_state(self, episode_id: str) -> dict:
        return self._sim.setdefault(
            episode_id,
            {"cursor_ms": 0, "playing": False, "emitted": set(), "fired": {}},
        )

    def list_episodes(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, label, created_at FROM episodes ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]

    def create_episode(self, label: str) -> dict:
        episode_id = new_id()
        with self._lock:
            self._conn.execute(
                "INSERT INTO episodes (id, label, created_at) VALUES (?, ?, ?)",
                (episode_id, label, now_iso()),
            )
            self._conn.commit()
        return self.get_episode(episode_id)

    def get_episode(self, episode_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM episodes WHERE id = ?", (episode_id,)).fetchone()
        return dict(row) if row else None

    def append(
        self,
        episode_id: str,
        event_type: str,
        payload: dict,
        *,
        ts_ms: int,
        tier: str = "documentation",
        supersedes_id: str | None = None,
    ) -> dict:
        event = {
            "id": new_id(),
            "episode_id": episode_id,
            "ts_ms": int(ts_ms),
            "wall_clock": now_iso(),
            "event_type": event_type,
            "payload": payload,
            "supersedes_id": supersedes_id,
            "tier": tier,
        }
        with self._lock:
            self._conn.execute(
                """INSERT INTO timeline
                   (id, episode_id, ts_ms, wall_clock, event_type, payload, supersedes_id, tier)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    event["id"],
                    episode_id,
                    event["ts_ms"],
                    event["wall_clock"],
                    event_type,
                    json.dumps(payload),
                    supersedes_id,
                    tier,
                ),
            )
            self._conn.commit()
        return event

    def events(self, episode_id: str, after_id: str | None = None) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM timeline WHERE episode_id = ? ORDER BY rowid",
            (episode_id,),
        ).fetchall()
        items = []
        started = after_id is None
        for row in rows:
            if not started:
                if row["id"] == after_id:
                    started = True
                continue
            item = dict(row)
            item["payload"] = json.loads(item["payload"])
            items.append(item)
        return items

    def get_event(self, event_id: str) -> dict | None:
        row = self._conn.execute("SELECT * FROM timeline WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

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
CREATE TABLE IF NOT EXISTS episode_beds (
  episode_id TEXT PRIMARY KEY,
  bed TEXT UNIQUE
);
CREATE TABLE IF NOT EXISTS intake_keys (
  source TEXT NOT NULL,
  document_id INTEGER NOT NULL,
  episode_id TEXT NOT NULL,
  finalized_at TEXT NOT NULL,
  PRIMARY KEY (source, document_id)
);
CREATE TABLE IF NOT EXISTS clock (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  now_ms INTEGER
);
"""


def lowest_free_bed(taken: set[str]) -> str:
    """The lowest whole-number bed not in `taken`, as text. The one bed rule for the seed, intake and next_bed."""
    bed = 1
    while str(bed) in taken:
        bed += 1
    return str(bed)


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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
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
        with self._lock:
            row = self._conn.execute("SELECT * FROM timeline WHERE id = ?", (event_id,)).fetchone()
        if row is None:
            return None
        item = dict(row)
        item["payload"] = json.loads(item["payload"])
        return item

    # The ward list (spec §8): one bed per patient episode. The staff board never gets a bed.
    def beds(self) -> dict[str, str]:
        """{episode_id: bed} for every patient on the ward."""
        with self._lock:
            rows = self._conn.execute("SELECT episode_id, bed FROM episode_beds").fetchall()
        return {row["episode_id"]: row["bed"] for row in rows}

    def set_bed(self, episode_id: str, bed: str) -> None:
        """Give an episode its bed. A bed held by another episode raises sqlite3.IntegrityError."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO episode_beds (episode_id, bed) VALUES (?, ?) "
                "ON CONFLICT(episode_id) DO UPDATE SET bed = excluded.bed",
                (episode_id, bed),
            )
            self._conn.commit()

    def claim_intake(
        self, source: str, document_id: int | None, finalized_at: str, label: str
    ) -> tuple[str, bool]:
        """Claim an intake key and, when it is new, make the episode and give it a bed, all in one transaction.

        Returns (episode_id, created). A key already held returns the stored episode with created False. A document_id of None (a patient made in Count Guard) has nothing to repeat, so it
        always makes a new episode.
        """
        episode_id = new_id()
        with self._lock:
            try:
                if document_id is not None:
                    self._conn.execute(
                        "INSERT INTO intake_keys (source, document_id, episode_id, finalized_at) VALUES (?, ?, ?, ?)",
                        (source, int(document_id), episode_id, finalized_at),
                    )
                self._conn.execute(
                    "INSERT INTO episodes (id, label, created_at) VALUES (?, ?, ?)", (episode_id, label, now_iso())
                )
                taken = {row["bed"] for row in self._conn.execute("SELECT bed FROM episode_beds")}
                bed = lowest_free_bed(taken)
                self._conn.execute("INSERT INTO episode_beds (episode_id, bed) VALUES (?, ?)", (episode_id, bed))
                self._conn.commit()
                return episode_id, True
            except sqlite3.IntegrityError:
                self._conn.rollback()
                if document_id is None:
                    raise
                row = self._conn.execute(
                    "SELECT episode_id FROM intake_keys WHERE source = ? AND document_id = ?",
                    (source, int(document_id)),
                ).fetchone()
                if row is None:  # the key was not the clash
                    raise
                return row["episode_id"], False

    def intake_episode(self, source: str, document_id: int) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT episode_id FROM intake_keys WHERE source = ? AND document_id = ?", (source, int(document_id))
            ).fetchone()
        return row["episode_id"] if row else None

    def update_intake(self, source: str, document_id: int, finalized_at: str) -> bool:
        """Record a re-saved document's time. True when it is later than the stored one.

        Times are Doctor Dictation's ISO strings, which sort as text. An older save arriving late (a slow push
        after a Sync) changes nothing, so it can never put an earlier prescription back.
        """
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE intake_keys SET finalized_at = ? WHERE source = ? AND document_id = ? AND finalized_at < ?",
                (finalized_at, source, int(document_id), finalized_at),
            )
            self._conn.commit()
        return cursor.rowcount == 1

    def clear_intake_keys(self) -> None:
        """Forget every intake, so a document pushed again after a reset makes its patient again."""
        with self._lock:
            self._conn.execute("DELETE FROM intake_keys")
            self._conn.commit()

    def clear_beds(self) -> None:
        """Empty the ward list. The episodes and their events stay."""
        with self._lock:
            self._conn.execute("DELETE FROM episode_beds")
            self._conn.commit()

    # The demo clock: one row, unset until POST /journey/clock sets it.
    def get_clock(self) -> int | None:
        with self._lock:
            row = self._conn.execute("SELECT now_ms FROM clock WHERE id = 1").fetchone()
        return None if row is None else int(row["now_ms"])

    def set_clock(self, ms: int) -> int:
        with self._lock:
            self._conn.execute(
                "INSERT INTO clock (id, now_ms) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET now_ms = excluded.now_ms",
                (int(ms),),
            )
            self._conn.commit()
        return int(ms)

    def clear_clock(self) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM clock")
            self._conn.commit()

    def latest_ts(self, episode_id: str, *, skip: tuple[str, ...] = ()) -> int | None:
        """The latest ts_ms on an episode, leaving out the event types in `skip`; None when there are none."""
        marks = ",".join("?" * len(skip))
        where = f" AND event_type NOT IN ({marks})" if skip else ""
        with self._lock:
            row = self._conn.execute(
                f"SELECT MAX(ts_ms) AS ts FROM timeline WHERE episode_id = ?{where}", (episode_id, *skip)
            ).fetchone()
        return None if row["ts"] is None else int(row["ts"])

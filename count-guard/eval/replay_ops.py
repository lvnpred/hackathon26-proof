"""Replay recorded days through the ops agent and print proposal precision and undo rate.

Each --db is one recorded day (a morning.db). The replay drops everything the agent wrote, feeds the
person's events back in order and lets the agent run again, so the table shows what the rules would do
today on that day. No live model is called: write=None and no key.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.morning.store import MorningStore  # noqa: E402
from app.ops import run  # noqa: E402
from app.ops.policy import AI_BY  # noqa: E402

MIN_DAYS = 3
MIN_PRECISION = 0.9
MAX_UNDO_RATE = 0.05
_ZERO = {"proposed": 0, "agreed": 0, "l2": 0, "undone": 0}


def metrics(events: list[dict]) -> dict[str, dict]:
    """Per kind: proposals made and agreed, L2 actions done and undone, and the two rates."""
    kind_of = {e["id"]: e["payload"].get("kind", "") for e in events if e["event_type"] == "work.opened"}
    proposed = {e["payload"].get("work_id") for e in events if e["event_type"] == "work.proposed"}
    l2 = {e["payload"].get("work_id") for e in events
          if e["event_type"] == "work.done" and e["payload"].get("level") == "L2"}
    out: dict[str, dict] = {}

    def bump(work_id, field):
        kind = kind_of.get(work_id)
        if kind:
            out.setdefault(kind, dict(_ZERO))[field] += 1

    for work_id in proposed:
        bump(work_id, "proposed")
    for work_id in l2:
        bump(work_id, "l2")
    for e in events:
        p, kind = e["payload"], e["event_type"]
        wid = p.get("work_id")
        if kind == "work.done" and p.get("approved_by"):
            bump(wid, "agreed")
        elif kind == "work.dropped" and p.get("code") == "done_by_person" and wid in proposed:
            bump(wid, "agreed")
        elif kind == "work.undone" and wid in l2:
            bump(wid, "undone")
    for row in out.values():
        row["precision"] = row["agreed"] / row["proposed"] if row["proposed"] else None
        row["undo_rate"] = row["undone"] / row["l2"] if row["l2"] else None
    return out


def _agent_ids(events: list[dict]) -> set[str]:
    """Ids of everything the agent wrote: every `wrote` list, every revert target, every AI_BY event."""
    ids: set[str] = set()
    for e in events:
        p = e["payload"]
        if e["event_type"] == "work.done":
            ids.update(p.get("wrote") or [])
        elif e["event_type"] == "work.reverted":
            ids.add(p.get("event_id"))
        if p.get("by") == AI_BY:
            ids.add(e["id"])
    return ids


def _replay_episode(events: list[dict], label: str, settings, store: MorningStore) -> list[tuple[str, str]]:
    dropped = _agent_ids(events)
    episode = store.create_episode(label)["id"]
    new_id: dict[str, str] = {}
    for e in events:
        if e["id"] in dropped or e["event_type"].startswith(("work.", "ops.")):
            continue
        # A supersede link to a dropped event points at an id the replay never holds: the target is
        # gone, so the link is cleared and the event stands on its own.
        link = new_id.get(e["supersedes_id"]) if e["supersedes_id"] else None
        written = store.append(episode, e["event_type"], e["payload"], ts_ms=e["ts_ms"], tier=e["tier"],
                               supersedes_id=link)
        new_id[e["id"]] = written["id"]
        run.run(store, episode, e["ts_ms"], settings=settings, write=None)
    return [(r["payload"].get("kind", ""), r["payload"].get("created_by_rule", ""))
            for r in store.events(episode) if r["event_type"] == "work.opened"]


def replay(events: list[dict], settings, label: str = "Replay patient (synthetic)") -> list[tuple[str, str]]:
    """The (kind, rule) of every work item the agent opens when the person's events are replayed."""
    with tempfile.TemporaryDirectory() as tmp:
        return _replay_episode(events, label, settings, MorningStore(Path(tmp) / "replay.db"))


def eligible(days: list[dict[str, dict]]) -> dict[str, bool]:
    """A kind may go up a level only after 3 days that all hold the precision and undo-rate bars."""
    kinds = {k for day in days for k in day}
    result = {}
    for kind in sorted(kinds):
        ok = len(days) >= MIN_DAYS
        for day in days:
            row = day.get(kind) or {}
            precision, undo = row.get("precision"), row.get("undo_rate")
            ok = ok and (precision is None or precision >= MIN_PRECISION) and (undo is None or undo <= MAX_UNDO_RATE)
        result[kind] = ok
    return result


def _settings(tmp: Path) -> Settings:
    return Settings(
        data_dir=tmp, meta_api_key="", meta_base="https://api.meta.ai/v1", sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0", spark_model="muse-spark-1.3", baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1", spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45, unannounced_window_ms=30_000, lost_after_frames=4, sam_fps=2, ops_agent=True,
    )


def _recorded(events: list[dict]) -> list[tuple[str, str]]:
    return [(e["payload"].get("kind", ""), e["payload"].get("created_by_rule", ""))
            for e in events if e["event_type"] == "work.opened"]


def _fmt(value) -> str:
    return "-" if value is None else f"{value:.2f}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", action="append", required=True, help="a recorded day (morning.db); repeatable")
    args = parser.parse_args(argv)
    days: list[dict[str, dict]] = []
    same = total = 0
    with tempfile.TemporaryDirectory() as tmp:
        settings = _settings(Path(tmp))
        for i, path in enumerate(args.db):
            if not Path(path).is_file():
                parser.error(f"no such db: {path}")
            source = MorningStore(Path(path))
            day_events: list[dict] = []
            for ep in source.list_episodes():
                events = source.events(ep["id"])
                day_events.extend(events)
                got = Counter(_replay_episode(events, ep["label"], settings, MorningStore(Path(tmp) / f"r{i}.db")))
                want = Counter(_recorded(events))
                same += sum((got & want).values())
                total += sum(want.values())
            days.append(metrics(day_events))
    ok = eligible(days)
    print(f"{'kind':<22}{'proposed':>9}{'agreed':>8}{'precision':>10}{'l2':>5}{'undone':>8}{'undo_rate':>10}  eligible")
    for kind in sorted({k for d in days for k in d}):
        tot = Counter()
        for d in days:
            tot.update({f: d.get(kind, {}).get(f, 0) for f in _ZERO})
        prec = tot["agreed"] / tot["proposed"] if tot["proposed"] else None
        undo = tot["undone"] / tot["l2"] if tot["l2"] else None
        print(f"{kind:<22}{tot['proposed']:>9}{tot['agreed']:>8}{_fmt(prec):>10}{tot['l2']:>5}{tot['undone']:>8}"
              f"{_fmt(undo):>10}  {'yes' if ok[kind] else 'no'}")
    print(f"days: {len(days)}")
    print(f"eligible: {'yes' if ok and all(ok.values()) else 'no'}")
    print(f"same: {same}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

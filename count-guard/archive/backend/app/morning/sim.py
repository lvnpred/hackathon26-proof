"""Play, pause, and seek the vitals scenario. The clock is an argument."""

from __future__ import annotations

from app.morning.store import MorningStore
from app.morning.vitals import collect_facts, demo_readings, evaluate, template_card


def ensure(store: MorningStore, episode_id: str) -> dict:
    return store.sim_state(episode_id)


def apply(
    store: MorningStore,
    episode_id: str,
    *,
    action: str,
    t_ms: int | None = None,
    step_ms: int = 30_000,
    decision_tier: bool = False,
) -> dict:
    sim = store.sim_state(episode_id)
    if action == "start":
        sim["playing"] = True
    elif action == "pause":
        sim["playing"] = False
    elif action == "seek":
        sim["cursor_ms"] = max(0, int(t_ms or 0))
        _emit_until(store, episode_id, sim, decision_tier)
    elif action == "tick":
        if sim["playing"]:
            sim["cursor_ms"] += step_ms
            _emit_until(store, episode_id, sim, decision_tier)
    else:
        raise ValueError(action)
    return {
        "cursor_ms": sim["cursor_ms"],
        "playing": sim["playing"],
        "emitted": sorted(sim["emitted"]),
    }


def _emit_until(store: MorningStore, episode_id: str, sim: dict, decision_tier: bool) -> None:
    due = [row for row in demo_readings() if row.ts_ms <= sim["cursor_ms"] and row.ts_ms not in sim["emitted"]]
    for reading in due:
        store.append(
            episode_id,
            "vitals.reading",
            {"systolic": reading.systolic, "diastolic": reading.diastolic, "hr": reading.hr},
            ts_ms=reading.ts_ms,
        )
        sim["emitted"].add(reading.ts_ms)
        if not decision_tier:
            continue
        prefix = [row for row in demo_readings() if row.ts_ms <= reading.ts_ms]
        for fire in evaluate(prefix, last_fired=sim["fired"]):
            sim["fired"][fire["rule_id"]] = fire["ts_ms"]
            if fire["rule_id"] != "bp_drop_pct":
                continue
            facts = collect_facts(store.events(episode_id), reading.ts_ms)
            store.append(
                episode_id,
                "vitals.card",
                {
                    "text": template_card(fire, facts),
                    "wording": "template",
                    "facts": facts,
                    "rule_id": "bp_drop_pct",
                },
                ts_ms=reading.ts_ms,
                tier="decision",
            )

"""Site-wide agent state: the pause switch and level changes, kept as events on one site episode (R11)."""

from __future__ import annotations

from app.journey import seed
from app.ops.policy import EXECUTABLE_KINDS, LEVELS, OPS_LABEL, SETTABLE
from app.morning.discharge import visible_events


def _oldest(store, label: str) -> str | None:
    matches = [e for e in store.list_episodes() if e["label"] == label]
    return min(matches, key=lambda e: e["created_at"])["id"] if matches else None


def site_episode(store) -> str:
    """The episode holding ops.* events. Found by label (oldest), created on first use."""
    return _oldest(store, OPS_LABEL) or store.create_episode(OPS_LABEL)["id"]


def board_events(store) -> list[dict]:
    """The events of the newest staff board, or [] when there is none."""
    boards = [e for e in store.list_episodes() if e["label"] == seed.BOARD_LABEL]
    if not boards:
        return []
    return store.events(max(boards, key=lambda e: e["created_at"])["id"])


def _site_events(store) -> list[dict]:
    episode = _oldest(store, OPS_LABEL)
    return visible_events(store.events(episode)) if episode else []


def paused(store) -> tuple[bool, str | None, int | None]:
    """(is the agent paused, who last switched it, when). Never paused until someone pauses it."""
    last = None
    for event in _site_events(store):
        if event["event_type"] in ("ops.paused", "ops.resumed"):
            last = event
    if last is None:
        return False, None, None
    return last["event_type"] == "ops.paused", last["payload"].get("by"), last["ts_ms"]


def set_paused(store, paused: bool, by: str, at_ms: int) -> None:
    store.append(site_episode(store), "ops.paused" if paused else "ops.resumed", {"by": by}, ts_ms=at_ms)


def level_of(store, kind: str) -> str:
    """The level now in force for a kind: the latest change, else the table."""
    level = LEVELS[kind]
    for event in _site_events(store):
        if event["event_type"] == "ops.policy_changed" and event["payload"].get("kind") == kind:
            level = event["payload"]["to"]
    return level


def set_level(store, kind: str, level: str, by: str, at_ms: int) -> None:
    """Change a kind's level and audit it. Unknown kinds, levels outside L0-L3 and Never kinds raise."""
    if kind not in LEVELS:
        raise ValueError(f"Unknown kind: {kind}")
    if LEVELS[kind] == "Never":
        raise ValueError("The AI never does this, so its level cannot change.")
    if level not in SETTABLE:
        raise ValueError("A level is L0, L1, L2 or L3.")
    if level == "L1" and kind in EXECUTABLE_KINDS:
        raise ValueError("The AI does this itself, so it cannot be lowered to a proposal.")
    before = level_of(store, kind)
    store.append(site_episode(store), "ops.policy_changed",
                 {"kind": kind, "from": before, "to": level, "by": by}, ts_ms=at_ms)

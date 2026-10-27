"""Six fixed rules. A model never decides whether a count is right."""

from __future__ import annotations

from app.core.ledger import TrackView, ledger_rows, open_discrepancies, project, tracks_at

HARD_RULES = ("R1", "R2", "R3", "R4")
KIND = {
    "R1": "count_mismatch",
    "R2": "spoken_vs_camera",
    "R3": "unaccounted_item",
    "R4": "unannounced_add",
    "R5": "needs_human_look",
}


def desired_discrepancies(
    events: list[dict],
    *,
    now_ms: int,
    finalize: bool,
    low_confidence: float,
    window_ms: int,
) -> list[dict]:
    """Return the discrepancies the ledger supports at this moment."""
    view = project(events)
    found: list[dict] = []
    if view.closing_ts is not None:
        found.extend(_rule_opened_vs_returned(events, view.closing_ts))
        found.extend(_rule_unaccounted(events, view.closing_ts))
    found.extend(_rule_spoken_vs_camera(events))
    found.extend(
        _rule_unannounced(
            events,
            now_ms=now_ms,
            finalize=finalize,
            window_ms=window_ms,
        )
    )
    found.extend(_rule_low_confidence(events, low_confidence))
    return found


def new_discrepancies(
    events: list[dict],
    *,
    now_ms: int,
    finalize: bool,
    low_confidence: float,
    window_ms: int,
) -> list[dict]:
    """Drafts that are not already on the ledger, resolved or still open."""
    existing = {
        (event.get("payload") or {}).get("dedup_key")
        for event in events
        if event["event_type"] == "discrepancy"
    }
    drafts = []
    for draft in desired_discrepancies(
        events,
        now_ms=now_ms,
        finalize=finalize,
        low_confidence=low_confidence,
        window_ms=window_ms,
    ):
        if draft["dedup_key"] in existing:
            continue
        existing.add(draft["dedup_key"])
        drafts.append(draft)
    return drafts


def closing_gate(events: list[dict]) -> dict:
    """R6. R5 does not block. A human resolution with a reason does."""
    open_rows = [row for row in open_discrepancies(events) if row["status"] == "open"]
    blockers = [row for row in open_rows if row["rule_id"] in HARD_RULES]
    looks = [row for row in open_rows if row["rule_id"] == "R5"]
    return {
        "ok": not blockers,
        "status": "reconciled" if not blockers else "blocked",
        "blockers": blockers,
        "needs_human_look": looks,
    }


def _rule_opened_vs_returned(events: list[dict], closing_ts: int) -> list[dict]:
    rows = {row["item_type"]: row for row in ledger_rows(events, at_ms=closing_ts)}
    view = project(events, at_ms=closing_ts)
    drafts = []
    for item_type in view.item_types():
        opened = view.opened(item_type, closing_ts)
        if opened <= 0:
            continue
        row = rows.get(item_type) or {
            "bucket": 0,
            "tray": 0,
            "unaccounted": 0,
        }
        observed = row["bucket"] + row["tray"]
        if observed == opened:
            continue
        evidence = [
            f"transcript:{add.transcript_id}"
            for add in view.adds
            if add.item_type == item_type and add.transcript_id
        ]
        drafts.append(
            _draft(
                rule_id="R1",
                dedup_key=f"R1:{item_type}",
                item_type=item_type,
                expected=opened,
                observed=observed,
                media_ts_ms=closing_ts,
                detail=(
                    f"{item_type}: opened {opened}, in the bucket {row['bucket']}, "
                    f"on the tray {row['tray']}"
                ),
                figures={
                    "expected": opened,
                    "observed": observed,
                    "opened": opened,
                    "bucket": row["bucket"],
                    "tray": row["tray"],
                    "unaccounted": row["unaccounted"],
                },
                evidence=evidence,
            )
        )
    return drafts


def _rule_unaccounted(events: list[dict], closing_ts: int) -> list[dict]:
    drafts = []
    for track in tracks_at(events, closing_ts).values():
        if track.zone != "field":
            continue
        seen_ms = track.last_seen_ms or 0
        drafts.append(
            _draft(
                rule_id="R3",
                dedup_key=f"R3:{track.track_id}",
                item_type=track.label,
                track_id=track.track_id,
                expected=0,
                observed=1,
                media_ts_ms=closing_ts,
                last_frame_id=track.last_frame_id,
                last_zone=track.zone,
                last_media_ts_ms=track.last_seen_ms,
                detail=(
                    f"Unaccounted: 1 {track.label} ({track.track_id}). "
                    f"Last seen in {track.zone}."
                ),
                figures={
                    "expected": 0,
                    "observed": 1,
                    "unaccounted": 1,
                    "seen_min": seen_ms // 60_000,
                    "seen_sec": (seen_ms // 1000) % 60,
                },
                evidence=_frame_evidence(track),
            )
        )
    return drafts


def _rule_spoken_vs_camera(events: list[dict]) -> list[dict]:
    view = project(events)
    drafts = []
    for spoken in view.counts:
        if not spoken.zone:
            continue
        camera = _camera_count(events, spoken.media_ts_ms, spoken.zone, spoken.item_type)
        if camera == spoken.quantity:
            continue
        item_type = spoken.item_type or _only_label(events, spoken.media_ts_ms, spoken.zone)
        drafts.append(
            _draft(
                rule_id="R2",
                dedup_key=f"R2:{spoken.event_id}",
                item_type=item_type,
                expected=spoken.quantity,
                observed=camera,
                media_ts_ms=spoken.media_ts_ms,
                detail=(
                    f"Spoken count: {spoken.quantity}. "
                    f"Camera count in {spoken.zone}: {camera}."
                ),
                figures={"expected": spoken.quantity, "observed": camera, "spoken": spoken.quantity, "camera": camera},
                evidence=[f"transcript:{spoken.transcript_id}"] if spoken.transcript_id else [],
            )
        )
    return drafts


def _rule_unannounced(
    events: list[dict], *, now_ms: int, finalize: bool, window_ms: int
) -> list[dict]:
    adds = project(events).adds
    pools = [
        {"item": add.item_type, "ts": add.media_ts_ms, "left": add.quantity} for add in adds
    ]
    uncovered: dict[str, list[dict]] = {}
    appearances = [
        event
        for event in events
        if event["event_type"] == "item_appeared" and (event.get("payload") or {}).get("zone") == "tray"
    ]
    appearances.sort(key=lambda event: (event["media_ts_ms"], event["id"]))
    for event in appearances:
        payload = event["payload"]
        label = payload["label"]
        matched = False
        for pool in pools:
            if pool["item"] != label or pool["left"] <= 0:
                continue
            if abs(pool["ts"] - event["media_ts_ms"]) <= window_ms:
                pool["left"] -= 1
                matched = True
                break
        ready = finalize or now_ms >= event["media_ts_ms"] + window_ms
        if not matched and ready:
            uncovered.setdefault(label, []).append(event)
    drafts = []
    for item_type, group in uncovered.items():
        first = group[0]
        drafts.append(
            _draft(
                rule_id="R4",
                dedup_key=f"R4:{item_type}",
                item_type=item_type,
                expected=0,
                observed=len(group),
                media_ts_ms=first["media_ts_ms"],
                track_id=first["payload"]["track_id"],
                detail=(
                    f"Unannounced add: {len(group)} {item_type} appeared on the tray "
                    f"with no spoken add within {window_ms // 1000} sec."
                ),
                figures={"expected": 0, "observed": len(group)},
                evidence=list(first.get("evidence") or []),
            )
        )
    return drafts


def _rule_low_confidence(events: list[dict], threshold: float) -> list[dict]:
    view = project(events)
    drafts = []
    for track in view.tracks.values():
        low_score = track.score is not None and track.score < threshold
        if not (low_score or track.low_confidence):
            continue
        reason = "identity re-link" if track.low_confidence and not low_score else "detection score"
        if track.low_confidence and low_score:
            reason = "detection score and identity re-link"
        drafts.append(
            _draft(
                rule_id="R5",
                dedup_key=f"R5:{track.track_id}",
                item_type=track.label,
                track_id=track.track_id,
                expected=None,
                observed=None,
                media_ts_ms=track.last_seen_ms,
                last_frame_id=track.last_frame_id,
                detail=f"Needs a human look at {track.track_id}. Reason: {reason}.",
                figures={},
                evidence=_frame_evidence(track),
            )
        )
    return drafts


def _camera_count(events: list[dict], at_ms: int, zone: str, item_type: str | None) -> int:
    total = 0
    for track in tracks_at(events, at_ms).values():
        if track.zone != zone:
            continue
        if item_type and track.label != item_type:
            continue
        total += 1
    return total


def _only_label(events: list[dict], at_ms: int, zone: str) -> str | None:
    labels = {
        track.label
        for track in tracks_at(events, at_ms).values()
        if track.zone == zone
    }
    if len(labels) == 1:
        return next(iter(labels))
    if len(labels) > 1:
        return "mixed"
    return None


def _frame_evidence(track: TrackView) -> list[str]:
    if track.last_frame_id:
        return [f"frame:{track.last_frame_id}"]
    return []


def _draft(
    *,
    rule_id: str,
    dedup_key: str,
    item_type: str | None,
    expected: int | None,
    observed: int | None,
    media_ts_ms: int,
    detail: str,
    figures: dict,
    track_id: str | None = None,
    last_frame_id: str | None = None,
    last_zone: str | None = None,
    last_media_ts_ms: int | None = None,
    evidence: list[str] | None = None,
) -> dict:
    return {
        "rule_id": rule_id,
        "kind": KIND[rule_id],
        "dedup_key": dedup_key,
        "item_type": item_type,
        "track_id": track_id,
        "expected": expected,
        "observed": observed,
        "media_ts_ms": media_ts_ms,
        "detail": detail,
        "figures": figures,
        "last_frame_id": last_frame_id,
        "last_zone": last_zone,
        "last_media_ts_ms": last_media_ts_ms,
        "evidence": evidence or [],
        "blocks_closing": rule_id in HARD_RULES,
    }

"""Copy a camera count onto one patient's morning. Numbers come from the ledger."""

from __future__ import annotations


def camera_count_events(rows: list[dict], discrepancies: list[dict], case_id: str) -> list[dict]:
    opened = sum(int(row.get("opened") or 0) for row in rows)
    returned = sum(int(row.get("bucket") or 0) + int(row.get("tray") or 0) for row in rows)
    unaccounted = sum(int(row.get("unaccounted") or 0) for row in rows)
    missing = next(
        (
            row
            for row in discrepancies
            if row.get("rule_id") == "R3" and row.get("status") != "resolved"
        ),
        None,
    )
    parts = [
        (
            f"{row['item_type']}: opened {row['opened']}, "
            f"bucket {row['bucket']}, tray {row['tray']}, unaccounted {row['unaccounted']}"
        )
        for row in rows
    ]
    events = []
    for row in rows:
        if not row.get("opened"):
            continue
        events.append(
            {
                "event_type": "count.pack_opened",
                "payload": {
                    "item_type": row["item_type"],
                    "quantity": row["opened"],
                    "source": "camera",
                    "case_id": case_id,
                },
            }
        )
    events.append(
        {
            "event_type": "count.closing",
            "payload": {
                "source": "camera",
                "case_id": case_id,
                "opened": opened,
                "returned": returned,
                "unaccounted": unaccounted,
                "track_id": None if missing is None else missing.get("track_id"),
                "frame_id": None if missing is None else missing.get("last_frame_id"),
                "detail": "Camera count. " + "; ".join(parts),
                "items": rows,
            },
        }
    )
    return events

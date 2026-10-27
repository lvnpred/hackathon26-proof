"""Scripted perception for the five eval clips and the closing-count demo.

These are not SAM measurements. The tracker and the rules see the same
detections a video pass would emit. Ground truth is declared here, before
any result is computed.
"""

from __future__ import annotations

ZONES = {
    "tray": [[0.02, 0.05], [0.40, 0.05], [0.40, 0.95], [0.02, 0.95]],
    "field": [[0.42, 0.05], [0.70, 0.05], [0.70, 0.95], [0.42, 0.95]],
    "bucket": [[0.72, 0.05], [0.98, 0.05], [0.98, 0.95], [0.72, 0.95]],
}

WIDTH = 640
HEIGHT = 360


def _boxes(count: int, x0: float) -> list[list[float]]:
    """Five columns that stay inside a zone about 0.26 wide."""
    boxes = []
    for index in range(count):
        column = index % 5
        row = index // 5
        boxes.append([round(x0 + column * 0.045, 3), round(0.22 + row * 0.22, 3), 0.04, 0.04])
    return boxes


def _sponges(x0: float, present: range | list[int] | None = None, score: float = 0.93) -> list[dict]:
    ids = list(present) if present is not None else list(range(1, 11))
    boxes = _boxes(10, x0)
    return [
        {
            "track_id": f"sponge-{number}",
            "label": "lap sponge",
            "bbox": boxes[number - 1],
            "score": score,
        }
        for number in ids
    ]


def _placed(specs: list[tuple[str, str, list[float]]], score: float = 0.93) -> list[dict]:
    return [
        {"track_id": track_id, "label": label, "bbox": bbox, "score": score}
        for track_id, label, bbox in specs
    ]


def _scenario(name: str, steps: list[dict], expect: dict) -> dict:
    return {
        "name": name,
        "width": WIDTH,
        "height": HEIGHT,
        "zones": ZONES,
        "item_types": ["lap sponge", "gauze swab", "surgical forceps", "scissors", "needle holder"],
        "steps": steps,
        "expect": expect,
    }


def clip_clean() -> dict:
    steps = [
        {"media_ts_ms": 0, "say": "Adding 10 lap sponges"},
        {"media_ts_ms": 2000, "detections": _sponges(0.05)},
        {"media_ts_ms": 20000, "detections": _sponges(0.44)},
        {"media_ts_ms": 40000, "detections": _sponges(0.74)},
        {"media_ts_ms": 60000, "detections": _sponges(0.74), "say": "Closing count, ten."},
    ]
    return _scenario(
        "clip1",
        steps,
        {
            "headline": "No discrepancies",
            "rules": [],
            "ledger": {"lap sponge": {"opened": 10, "bucket": 10, "tray": 0, "unaccounted": 0}},
            "id_switches": 0,
            "gate": "reconciled",
        },
    )


def clip_missing_sponge() -> dict:
    nine = [n for n in range(1, 11) if n != 7]
    field_and_bucket = _sponges(0.74, nine) + _sponges(0.44, [7])
    bucket_nine = _sponges(0.74, nine)
    steps = [
        {"media_ts_ms": 0, "say": "Adding 10 lap sponges"},
        {"media_ts_ms": 2000, "detections": _sponges(0.05)},
        {"media_ts_ms": 20000, "detections": _sponges(0.44)},
        {"media_ts_ms": 40000, "detections": field_and_bucket},
        {"media_ts_ms": 50000, "detections": field_and_bucket},
        {"media_ts_ms": 52000, "detections": bucket_nine},
        {"media_ts_ms": 54000, "detections": bucket_nine},
        {"media_ts_ms": 56000, "detections": bucket_nine},
        {"media_ts_ms": 58000, "detections": bucket_nine},
        {"media_ts_ms": 60000, "detections": bucket_nine, "say": "Closing count, nine."},
    ]
    return _scenario(
        "clip2",
        steps,
        {
            "headline": "1 unaccounted_item",
            "rules": [("R1", "lap sponge"), ("R3", "lap sponge")],
            "ledger": {"lap sponge": {"opened": 10, "bucket": 9, "tray": 0, "unaccounted": 1}},
            "id_switches": 0,
            "gate": "blocked",
        },
    )


def clip_spoken_mismatch() -> dict:
    nine = list(range(1, 10))
    steps = [
        {"media_ts_ms": 0, "say": "Adding 10 lap sponges"},
        {"media_ts_ms": 2000, "detections": _sponges(0.05)},
        {"media_ts_ms": 20000, "detections": _sponges(0.44)},
        {
            "media_ts_ms": 40000,
            "detections": _sponges(0.74, nine) + _sponges(0.05, [10]),
        },
        {
            "media_ts_ms": 60000,
            "detections": _sponges(0.74, nine) + _sponges(0.05, [10]),
            "say": "Closing count, ten.",
        },
    ]
    return _scenario(
        "clip3",
        steps,
        {
            "headline": "1 spoken_vs_camera",
            "rules": [("R2", "lap sponge")],
            "ledger": {"lap sponge": {"opened": 10, "bucket": 9, "tray": 1, "unaccounted": 0}},
            "id_switches": 0,
            "gate": "blocked",
        },
    )


def clip_unannounced() -> dict:
    gauze = _placed(
        [
            (f"gauze-{index}", "gauze swab", [0.06 + (index - 1) * 0.06, 0.20, 0.05, 0.05])
            for index in range(1, 6)
        ]
    )
    steps = [
        {"media_ts_ms": 5000, "detections": gauze},
        {"media_ts_ms": 40000, "detections": gauze, "say": "Closing count"},
    ]
    return _scenario(
        "clip4",
        steps,
        {
            "headline": "1 unannounced_add",
            "rules": [("R4", "gauze swab")],
            "ledger": {"gauze swab": {"opened": 0, "bucket": 0, "tray": 5, "unaccounted": 0}},
            "id_switches": 0,
            "gate": "blocked",
        },
    )


def clip_swap() -> dict:
    left = [0.08, 0.30, 0.06, 0.06]
    right = [0.24, 0.30, 0.06, 0.06]
    pair = [
        ("forceps-1", "surgical forceps"),
        ("scissors-1", "scissors"),
    ]
    steps = [
        {"media_ts_ms": 0, "say": "Adding 1 surgical forceps"},
        {"media_ts_ms": 500, "say": "Adding 1 scissors"},
        {"media_ts_ms": 1000, "detections": _placed([(pair[0][0], pair[0][1], left), (pair[1][0], pair[1][1], right)])},
        {"media_ts_ms": 3000, "detections": _placed([(pair[0][0], pair[0][1], right), (pair[1][0], pair[1][1], left)])},
        {"media_ts_ms": 5000, "detections": _placed([(pair[0][0], pair[0][1], left), (pair[1][0], pair[1][1], right)])},
        {
            "media_ts_ms": 8000,
            "detections": _placed([(pair[0][0], pair[0][1], left), (pair[1][0], pair[1][1], right)]),
            "say": "Closing count, two on the tray.",
        },
    ]
    return _scenario(
        "clip5",
        steps,
        {
            "headline": "No discrepancies, no ID switches",
            "rules": [],
            "ledger": {
                "surgical forceps": {"opened": 1, "bucket": 0, "tray": 1, "unaccounted": 0},
                "scissors": {"opened": 1, "bucket": 0, "tray": 1, "unaccounted": 0},
            },
            "id_switches": 0,
            "gate": "reconciled",
        },
    )


def demo_missing() -> dict:
    """The 3-minute demo beat: spoken ten, nine in the bucket, one last seen in the field.

    Five gauze swabs land on the tray at 25 s with no spoken add (R4) and stay there.
    """
    scenario = clip_missing_sponge()
    scenario["name"] = "demo"
    gauze = _placed(
        [
            (f"gauze-{index}", "gauze swab", [0.06 + (index - 1) * 0.06, 0.75, 0.05, 0.05])
            for index in range(1, 6)
        ]
    )
    steps = scenario["steps"]
    later = next(index for index, step in enumerate(steps) if step["media_ts_ms"] > 25000)
    steps.insert(later, {"media_ts_ms": 25000, "detections": _sponges(0.44)})
    for step in steps:
        if step["media_ts_ms"] >= 25000:
            step["detections"] = step["detections"] + gauze
        if step.get("say", "").startswith("Closing"):
            step["say"] = "Closing count, ten."
    scenario["expect"] = {
        "headline": "Missing sponge at the closing count",
        "rules": [("R1", "lap sponge"), ("R2", "lap sponge"), ("R3", "lap sponge"), ("R4", "gauze swab")],
        "ledger": {
            "lap sponge": {"opened": 10, "bucket": 9, "tray": 0, "unaccounted": 1},
            "gauze swab": {"opened": 0, "bucket": 0, "tray": 5, "unaccounted": 0},
        },
        "id_switches": 0,
        "gate": "blocked",
    }
    return scenario


def worked_example() -> dict:
    """The spec table: 10 sponges opened, 9 returned, sponge 7 in the field. 4 forceps stay on the tray."""
    nine = [n for n in range(1, 11) if n != 7]
    forceps = _placed(
        [(f"forceps-{index}", "surgical forceps", [0.06 + (index - 1) * 0.06, 0.62, 0.05, 0.05]) for index in range(1, 5)]
    )
    steps = [
        {"media_ts_ms": 0, "say": "Adding 10 lap sponges"},
        {"media_ts_ms": 500, "say": "Adding 4 surgical forceps"},
        {"media_ts_ms": 2000, "detections": _sponges(0.05) + forceps},
        {"media_ts_ms": 20000, "detections": _sponges(0.44) + forceps},
        {"media_ts_ms": 40000, "detections": _sponges(0.74, nine) + _sponges(0.44, [7]) + forceps},
        {"media_ts_ms": 50000, "detections": _sponges(0.74, nine) + _sponges(0.44, [7]) + forceps},
        {"media_ts_ms": 52000, "detections": _sponges(0.74, nine) + forceps},
        {"media_ts_ms": 54000, "detections": _sponges(0.74, nine) + forceps},
        {"media_ts_ms": 56000, "detections": _sponges(0.74, nine) + forceps},
        {"media_ts_ms": 58000, "detections": _sponges(0.74, nine) + forceps},
        {"media_ts_ms": 60000, "detections": _sponges(0.74, nine) + forceps, "say": "Closing count"},
    ]
    return _scenario(
        "worked",
        steps,
        {
            "headline": "R1 and R3 for sponge 7. Forceps balance.",
            "rules": [("R1", "lap sponge"), ("R3", "lap sponge")],
            "ledger": {
                "lap sponge": {"opened": 10, "bucket": 9, "tray": 0, "unaccounted": 1},
                "surgical forceps": {"opened": 4, "bucket": 0, "tray": 4, "unaccounted": 0},
            },
            "id_switches": 0,
            "gate": "blocked",
        },
    )


SCENARIOS = {
    "clip1": clip_clean,
    "clip2": clip_missing_sponge,
    "clip3": clip_spoken_mismatch,
    "clip4": clip_unannounced,
    "clip5": clip_swap,
    "demo": demo_missing,
    "worked": worked_example,
}


def get_scenario(name: str) -> dict:
    try:
        return SCENARIOS[name]()
    except KeyError as exc:
        known = ", ".join(sorted(SCENARIOS))
        raise KeyError(f"Unknown scenario '{name}'. Known: {known}") from exc


def eval_clips() -> list[dict]:
    return [SCENARIOS[name]() for name in ("clip1", "clip2", "clip3", "clip4", "clip5")]

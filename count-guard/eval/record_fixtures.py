"""Re-record the prepared fixtures once with the real models (D2). The owner runs this, never a test.

    export MODEL_API_KEY   # your key, set in the environment, never in a file
    .venv/bin/python eval/record_fixtures.py --spend

It calls the same seam the app uses (`live.segment_clip`, `segment_photos`, `read_photo`) for each asset
below. A fixture is overwritten only when the live counts (or values read) equal the fixture's (R13).
Otherwise the live result goes to `prepared/<stem>.live.json`, which the app never loads, and the run
exits 2 so the owner can decide. Voice fixtures hold transcripts, not boxes, so they are not recorded.
"""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import get_settings  # noqa: E402
from app.journey import live  # noqa: E402
from app.journey.regions import READER_CONCEPTS  # noqa: E402
from app.spend import clip_seconds, sam_video_cost  # noqa: E402

PREPARED = live.PREPARED_DIR
EVAL = ROOT / "eval"
# (stem, path, kind): kind is clip, still, monitor or strip. A clip and its still share one fixture.
ASSETS = (
    ("tray-hernia", EVAL / "p3" / "tray-hernia.mp4", "clip"),
    ("tray-hernia", EVAL / "p3" / "tray-hernia.png", "still"),
    ("tray-hernia-full", EVAL / "p3" / "tray-hernia-full.mp4", "clip"),
    ("tray-hernia-full", EVAL / "p3" / "tray-hernia-full.png", "still"),
    ("saline-setup", EVAL / "p3" / "saline-setup.mp4", "clip"),
    ("swabs-closing", EVAL / "p3" / "swabs-closing.mp4", "clip"),  # Task 8 adds it; skipped until then
    ("monitor-88-54", EVAL / "p2" / "monitor-88-54.png", "monitor"),
    ("strip-paracetamol", EVAL / "p2" / "strip-paracetamol.png", "strip"),
    ("meds-kumar", EVAL / "p4" / "meds-kumar.png", "strip"),
    ("meds-iyer", EVAL / "p4" / "meds-iyer.png", "strip"),
)
NEW_CONCEPTS = {"swabs-closing": ["gauze swab"]}  # no fixture yet, so no concepts to read from one
PHOTO_KINDS = ("monitor", "strip")
LIVE_SOURCES = ("sam-3.1", "muse-spark-1.3")


def _old_values(old: dict, kind: str) -> list[dict]:
    """What the fixture reads: its regions, else the values parsed from its text."""
    regions = old.get("regions")
    if regions is not None:
        return [{"label": r["label"], "value": r["value"]} for r in regions]
    return live._values(kind, old.get("text"))


def _value_table(values: list[dict], kind: str) -> dict:
    """Monitor: the number per label. Strip: how many times each strip was read."""
    values = [v for v in values if v["value"] is not None]
    if kind == "monitor":
        return {v["label"]: v["value"] for v in values}
    return dict(Counter(v["value"] for v in values))


def _compare(old: dict, new: dict) -> list[str]:
    return [f"{k}: fixture {old.get(k, 0 if isinstance(new.get(k), int) else 'not read')}, "
            f"live {new.get(k, 0 if isinstance(old.get(k), int) else 'not read')}"
            for k in [*old, *(k for k in new if k not in old)] if old.get(k) != new.get(k)]


def differences(old: dict, live_result: dict, kind: str) -> list[str]:
    """One line per difference between the fixture and a live result; empty when they agree."""
    bad = [f"{c['model']} call did not run live ({c['source']})" for c in live_result.get("calls", [])
           if c.get("source") and c["source"] not in LIVE_SOURCES]
    if bad:
        return bad
    if kind in PHOTO_KINDS:
        if not old.get("regions") and not old.get("text"):
            return ["no fixture to compare with"]
        live_values = [{"label": r["label"], "value": r["value"]} for r in live_result.get("regions") or []]
        return _compare(_value_table(_old_values(old, kind), kind), _value_table(live_values, kind))
    if live_result.get("detections") is None:
        return ["no live result"]
    if not old.get("detections"):
        return ["no fixture to compare with"]
    counts = lambda d: {c: v["count"] for c, v in d.items()}
    return _compare(counts(old["detections"]), counts(live_result["detections"]))


def _total_ms(calls: list[dict]) -> int | None:
    times = [c["ms"] for c in calls if c.get("ms") is not None]
    return sum(times) if times else None


def candidate(old: dict, live_result: dict, kind: str) -> dict:
    """The new fixture (C6). Keeps what agrees from `old` (detections, text, transcript); drops `handmade`.

    A clip sets `frames`, `raw`, `ms` and `model_id`. Its still only adds `stills`, and fills those three
    when the clip has not (they describe the fixture once)."""
    new = {k: v for k, v in old.items() if k != "handmade"}
    calls = live_result.get("calls") or []
    evidence = {"raw": live_result.get("raw"), "ms": _total_ms(calls), "model_id": calls[0].get("model_id") if calls else None}
    if kind in PHOTO_KINDS:
        if not old.get("text") or differences(old, live_result, kind):
            new["text"] = live_result.get("text")
        new["regions"] = live_result.get("regions")
    else:
        if not old.get("detections") or differences(old, live_result, kind):
            new["detections"] = live_result["detections"]
        new["stills" if kind == "still" else "frames"] = live_result.get("frames")
    for key, value in evidence.items():
        if kind != "still" or key not in new:
            new[key] = value
    return {k: v for k, v in new.items() if v is not None}


def request_count(assets, concepts: dict) -> int:
    """Model requests: one SAM request per concept for a clip or a still, SAM plus Spark for a photo."""
    return sum(2 if kind in PHOTO_KINDS else len(concepts[stem]) for stem, _, kind in assets)


def _fixture(stem: str) -> dict:
    path = PREPARED / f"{stem}.json"
    return json.loads(path.read_text()) if path.is_file() else {}


def _concepts_of(stem: str) -> list[str]:
    return list(_fixture(stem).get("detections") or NEW_CONCEPTS.get(stem, []))


def _bill(assets, concepts: dict, fps: int) -> None:
    print("The bill for the clips (the `make cost` figures):")
    for stem, path, kind in assets:
        if kind != "clip" or not path.is_file():
            continue
        try:
            cost = sam_video_cost(clip_seconds(path), fps, len(concepts[stem]))
            print(f"  {path.name}: {cost['requests']} requests, {cost['billed_frames']} billed frames, ${cost['usd']:.4f}")
        except (SystemExit, OSError, ValueError) as exc:
            print(f"  {path.name}: cost unknown ({exc})")


def _run(settings, path: Path, kind: str, concepts: list[str]) -> dict:
    if kind == "clip":
        return live.segment_clip(settings, path, path.name, concepts, live_ok=True)
    if kind == "still":
        return live.segment_photos(settings, [path], concepts, path.name, live_ok=True)
    mime = live._IMAGE_TYPES.get(path.suffix, "image/jpeg")
    return live.read_photo(settings, kind, path.read_bytes(), path.name, mime, live_ok=True)


def _record(settings, stem: str, assets: list[tuple[Path, str]], regions_seen: Counter) -> list[str]:
    """Run one stem's assets, write the fixture or its .live.json, return the differences."""
    old = _fixture(stem)
    new, diffs, ran = dict(old), [], False
    for path, kind in assets:
        if not path.is_file():
            print(f"{stem}: skipped, {path} not found")
            continue
        try:
            result = _run(settings, path, kind, _concepts_of(stem))
        except live.NotHeard as exc:
            diffs.append(f"{path.name}: {exc.detail}")
            continue
        ran = True
        diffs += differences(old, result, kind)
        new = candidate(new, result, kind)
        if kind in PHOTO_KINDS:
            found = sum(1 for r in result.get("regions") or [] if r.get("bbox"))
            regions_seen[", ".join(READER_CONCEPTS[kind])] += found
            print(f"{stem}: SAM found {found} region(s) for {READER_CONCEPTS[kind]}")
    if not ran:
        return diffs
    target = PREPARED / (f"{stem}.live.json" if diffs else f"{stem}.json")
    target.write_text(json.dumps(new, indent=2) + "\n")
    print(f"{stem}: wrote {target.name}")
    for line in diffs:
        print(f"  {line}")
    return diffs


def main(argv: list[str]) -> int:
    if not os.environ.get("MODEL_API_KEY"):
        print("Set MODEL_API_KEY. This script calls the real models.")
        return 1
    settings = get_settings()
    concepts = {stem: _concepts_of(stem) for stem, _, _ in ASSETS}
    print(f"{len(ASSETS)} assets, about {request_count(ASSETS, concepts)} model requests in all.")
    _bill(ASSETS, concepts, settings.sam_fps)
    if "--spend" not in argv:
        print("Nothing was called. Add --spend to run it and spend credits.")
        return 1
    stems = list(dict.fromkeys(stem for stem, _, _ in ASSETS))
    regions_seen: Counter = Counter()
    differed = []
    for stem in stems:
        if _record(settings, stem, [(p, k) for s, p, k in ASSETS if s == stem], regions_seen):
            differed.append(stem)
    for concept, n in regions_seen.items():
        print(f"Regions found for SAM concept '{concept}': {n}")
    if differed:
        print(f"Differed, left alone (see <stem>.live.json): {', '.join(differed)}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

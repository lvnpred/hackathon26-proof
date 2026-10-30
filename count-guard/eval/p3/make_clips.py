"""Make the stand-in clips in eval/p3/ (git-ignored). Needs Pillow and ffmpeg.

These clips are D12 stand-ins until the owner films: labelled shapes, not real instruments.
Each item is drawn at the count in its prepared result (backend/app/journey/prepared/<stem>.json),
from the second its at_s says, for the rest of the 6 s clip at 2 fps.

Each stem also gets a still photo (<stem>.png) drawn with every item present, for the photo check.

`--write-fixtures` also writes each stem's per-frame boxes (`frames` for the clip, `stills` for the photo)
into its fixture, marked `"handmade": true`. `make demo-check` never runs it.

Run: .venv/bin/python eval/p3/make_clips.py [--write-fixtures]
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
PREPARED = HERE.parent.parent / "backend" / "app" / "journey" / "prepared"
STEMS = ("tray-hernia", "tray-hernia-full", "saline-setup", "swabs-closing")
SECONDS, FPS, SIZE = 6, 2, (640, 360)


PER_ROW, ROW_H = 6, 36  # items per row; a concept with more wraps to a new row
IGNORED = {"tray-hernia": ("needle holder", 2, (2.0, 2.5))}  # concept, item index, times: low-score boxes to show


def _rows(detections: dict):
    """(concept, cell, y) for each concept: 42 px apart, taller when its items wrap."""
    y = 40
    for concept, cell in detections.items():
        yield concept, cell, y
        y += 42 + ROW_H * max(0, (cell["count"] - 1) // PER_ROW)


def _box(y: int, k: int) -> tuple[int, int, int, int]:
    x, top = 220 + (k % PER_ROW) * 70, y + (k // PER_ROW) * ROW_H
    return x, top, x + 56, top + 30


def boxes_for(detections: dict, t: float) -> list[tuple[str, int, tuple[int, int, int, int]]]:
    """(concept, k, (x1, y1, x2, y2)) of every item in view at time t: the rectangles draw_frame draws."""
    return [
        (concept, k, _box(y, k))
        for concept, cell, y in _rows(detections)
        if cell["at_s"] is not None and t >= cell["at_s"]
        for k in range(cell["count"])
    ]


def draw_frame(detections: dict, t: float) -> Image.Image:
    image = Image.new("RGB", SIZE, (225, 232, 238))
    pen = ImageDraw.Draw(image)
    pen.rectangle((20, 20, SIZE[0] - 20, SIZE[1] - 20), outline=(90, 110, 130), width=3)
    for concept, cell, y in _rows(detections):
        if cell["at_s"] is not None and t >= cell["at_s"]:
            pen.text((34, y + 8), concept, fill=(20, 30, 40))
    for _, _, box in boxes_for(detections, t):
        pen.rounded_rectangle(box, radius=6, fill=(70, 120, 170), outline=(20, 50, 90))
    return image


def make(stem: str) -> Path:
    detections = json.loads((PREPARED / f"{stem}.json").read_text())["detections"]
    out = HERE / f"{stem}.mp4"
    with tempfile.TemporaryDirectory() as tmp:
        for n in range(SECONDS * FPS):
            draw_frame(detections, n / FPS).save(Path(tmp) / f"f{n:03d}.png")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-framerate", str(FPS), "-i", str(Path(tmp) / "f%03d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS), str(out)],
            check=True,
        )
    return out


def make_photo(stem: str) -> Path:
    """A still of the same scene with every item in view: the stand-in for a photo of the tray or set-up."""
    detections = json.loads((PREPARED / f"{stem}.json").read_text())["detections"]
    out = HERE / f"{stem}.png"
    draw_frame(detections, SECONDS).save(out)
    return out


def _object(concept: str, k: int, box: tuple, score: float = 0.9, oid: str | None = None) -> dict:
    x1, y1, x2, y2 = box
    bbox = [round(v, 4) for v in (x1 / SIZE[0], y1 / SIZE[1], (x2 - x1) / SIZE[0], (y2 - y1) / SIZE[1])]
    return {"id": oid or str(k + 1), "label": concept, "bbox": bbox, "score": score, "kept": score >= 0.45}


def _frame(detections: dict, t: float, index: int, stored_t: float | None, stem: str) -> dict:
    objects = [_object(c, k, box) for c, k, box in boxes_for(detections, t)]
    ignored = IGNORED.get(stem)
    if ignored and t in ignored[2] and stored_t is not None:
        concept, k, _ = ignored
        y = next(y for c, _, y in _rows(detections) if c == concept)
        objects.append(_object(concept, k, _box(y, k), score=0.32, oid="9"))
    return {"t": stored_t, "index": index, "objects": objects}


def write_fixtures() -> None:
    """Add `frames`, `stills` and `handmade` to each stem's fixture, from the boxes the stand-in clip draws."""
    for stem in STEMS:
        path = PREPARED / f"{stem}.json"
        data = json.loads(path.read_text())
        detections = data["detections"]
        data["frames"] = [_frame(detections, n / FPS, n, n / FPS, stem) for n in range(SECONDS * FPS)]
        data["stills"] = [_frame(detections, SECONDS, 0, None, stem)]
        data["handmade"] = True
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(path)


if __name__ == "__main__":
    if "--write-fixtures" in sys.argv[1:]:
        write_fixtures()
        sys.exit(0)
    for name in STEMS:
        print(make(name))
        print(make_photo(name))
    sys.exit(0)

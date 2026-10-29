"""Make the stand-in clips in eval/p3/ (git-ignored). Needs Pillow and ffmpeg.

These clips are D12 stand-ins until the owner films: labelled shapes, not real instruments.
Each item is drawn at the count in its prepared result (backend/app/journey/prepared/<stem>.json),
from the second its at_s says, for the rest of the 6 s clip at 2 fps.

Run: .venv/bin/python eval/p3/make_clips.py
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
STEMS = ("tray-hernia", "tray-hernia-full", "saline-setup")
SECONDS, FPS, SIZE = 6, 2, (640, 360)


def draw_frame(detections: dict, t: float) -> Image.Image:
    image = Image.new("RGB", SIZE, (225, 232, 238))
    pen = ImageDraw.Draw(image)
    pen.rectangle((20, 20, SIZE[0] - 20, SIZE[1] - 20), outline=(90, 110, 130), width=3)
    for row, (concept, cell) in enumerate(detections.items()):
        if cell["at_s"] is None or t < cell["at_s"]:
            continue
        y = 40 + row * 42
        pen.text((34, y + 8), concept, fill=(20, 30, 40))
        for k in range(cell["count"]):
            x = 220 + k * 70
            pen.rounded_rectangle((x, y, x + 56, y + 30), radius=6, fill=(70, 120, 170), outline=(20, 50, 90))
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


if __name__ == "__main__":
    for name in STEMS:
        print(make(name))
    sys.exit(0)

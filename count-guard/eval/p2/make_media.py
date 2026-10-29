"""Generate the P2 demo audio and photos. Needs macOS `say`, ffmpeg and Pillow.

Run: .venv/bin/python eval/p2/make_media.py
The output (*.wav, *.png) is git-ignored. The file names match backend/app/journey/prepared/*.json.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PREPARED = HERE.parents[1] / "backend" / "app" / "journey" / "prepared"


def speak(text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        aiff = Path(tmp) / "x.aiff"
        subprocess.run(["say", "-o", str(aiff), text], check=True)
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", str(aiff), "-ac", "1", "-ar", "16000", str(out)],
            check=True,
        )


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def strip_photo(out: Path) -> None:
    img = Image.new("RGB", (640, 400), (230, 230, 225))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 90, 580, 310), radius=18, fill=(245, 245, 245), outline=(120, 120, 130), width=4)
    for x in range(90, 560, 70):
        d.ellipse((x, 250, x + 44, 294), outline=(170, 170, 180), width=3)
    d.text((90, 120), "PARACETAMOL", font=_font(56), fill=(20, 40, 110))
    d.text((90, 190), "500 mg", font=_font(44), fill=(20, 40, 110))
    img.save(out)


def monitor_photo(out: Path) -> None:
    img = Image.new("RGB", (640, 400), (40, 40, 44))
    d = ImageDraw.Draw(img)
    d.rectangle((50, 40, 590, 360), fill=(10, 20, 15), outline=(90, 90, 95), width=6)
    for y, label, value in ((70, "SYS", "88"), (160, "DIA", "54"), (250, "PUL", "112")):
        d.text((90, y + 20), label, font=_font(40), fill=(120, 220, 140))
        d.text((300, y), value, font=_font(84), fill=(120, 255, 150))
    img.save(out)


def main() -> None:
    for path in sorted(PREPARED.glob("*.json")):
        data = json.loads(path.read_text())
        if "transcript" in data:
            speak(data["transcript"], HERE / f"{path.stem}.wav")
    strip_photo(HERE / "strip-paracetamol.png")
    monitor_photo(HERE / "monitor-88-54.png")


if __name__ == "__main__":
    main()

"""Stand-in photos for the P4 demo, until the owner photographs real strips (P2-R2). Needs Pillow.

Run: .venv/bin/python eval/p4/make_photos.py [--write-fixtures]
`--write-fixtures` adds the handmade `regions` (one box per card) to meds-kumar.json and meds-iyer.json, and writes strip-amlodipine.json.
Writes meds-kumar.png, meds-iyer.png (one drawn strip per prepared row), strip-amlodipine.png (one strip, for the clinic strip photo) wound-day3.png and wound-day0.png (the reference photo taken after theatre).
The output (*.png) is git-ignored. The medicine file names match backend/app/journey/prepared/*.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
PREPARED = HERE.parents[1] / "backend" / "app" / "journey" / "prepared"


def _font(size: int) -> ImageFont.ImageFont:
    for name in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def medicines_photo(strips: list[dict], out: Path) -> None:
    """Each strip is a card with its blisters, its name and its strength, stacked on a table colour."""
    height = 40 + 150 * len(strips)
    img = Image.new("RGB", (720, height), (214, 206, 190))
    d = ImageDraw.Draw(img)
    for index, strip in enumerate(strips):
        top = 30 + 150 * index
        d.rounded_rectangle((40, top, 680, top + 130), radius=14, fill=(245, 245, 245), outline=(120, 120, 130), width=3)
        for x in range(60, 660, 60):
            d.ellipse((x, top + 92, x + 36, top + 122), outline=(170, 170, 180), width=3)
        d.text((60, top + 10), strip["name"].upper(), font=_font(40), fill=(20, 40, 110))
        d.text((60, top + 56), strip["strength"], font=_font(30), fill=(20, 40, 110))
    img.save(out)


STRIP_AMLODIPINE = {"name": "Amlodipine", "strength": "10 mg"}
STRIP_SIZE = (720, 400)
STRIP_CARD = (40, 100, 680, 300)  # the card is the region: x 40..680, y 100..300 of a 720 x 400 photo


def strip_photo(strip: dict, out: Path) -> None:
    """One strip card, centred on the table colour, so its box is [0.0556, 0.25, 0.8889, 0.5] of the photo."""
    img = Image.new("RGB", STRIP_SIZE, (214, 206, 190))
    d = ImageDraw.Draw(img)
    left, top, right, bottom = STRIP_CARD
    d.rounded_rectangle(STRIP_CARD, radius=14, fill=(245, 245, 245), outline=(120, 120, 130), width=3)
    for x in range(left + 20, right - 20, 60):
        d.ellipse((x, bottom - 60, x + 36, bottom - 30), outline=(170, 170, 180), width=3)
    d.text((left + 20, top + 20), strip["name"].upper(), font=_font(48), fill=(20, 40, 110))
    d.text((left + 20, top + 85), strip["strength"], font=_font(36), fill=(20, 40, 110))
    img.save(out)


def wound_photo(out: Path) -> None:
    """A plain skin-tone panel with a drawn dressing line."""
    img = Image.new("RGB", (640, 400), (224, 172, 140))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((200, 150, 440, 250), radius=10, fill=(240, 240, 235), outline=(150, 150, 150), width=3)
    d.line((220, 200, 420, 200), fill=(190, 80, 80), width=5)
    img.save(out)


def wound_photo_day0(out: Path) -> None:
    """The same panel as wound_photo, with a fresh dressing: a clean blue line, so the two thumbnails differ."""
    img = Image.new("RGB", (640, 400), (224, 172, 140))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((200, 150, 440, 250), radius=10, fill=(250, 250, 250), outline=(150, 150, 150), width=3)
    d.line((220, 200, 420, 200), fill=(70, 110, 190), width=5)
    img.save(out)


def write_fixtures() -> None:
    """One region per card: (40, top, 680, top + 130) on a (720, 40 + 150 n) photo, labelled from the text strips."""
    for name in ("meds-kumar", "meds-iyer"):
        path = PREPARED / f"{name}.json"
        data = json.loads(path.read_text())
        strips = json.loads(data["text"])["strips"]
        width, height = 720, 40 + 150 * len(strips)
        data["regions"] = [
            {
                "bbox": [round(40 / width, 4), round((30 + 150 * n) / height, 4), round(640 / width, 4), round(130 / height, 4)],
                "label": f"{s['name']} {s['strength']}".strip(), "value": f"{s['name']} {s['strength']}".strip(), "row": n,
            }
            for n, s in enumerate(strips)
        ]
        data["handmade"] = True
        path.write_text(json.dumps(data, indent=2) + "\n")
        print(path)
    label = f"{STRIP_AMLODIPINE['name']} {STRIP_AMLODIPINE['strength']}"
    width, height = STRIP_SIZE
    left, top, right, bottom = STRIP_CARD
    path = PREPARED / "strip-amlodipine.json"
    path.write_text(json.dumps({
        "text": json.dumps({"strips": [STRIP_AMLODIPINE]}),
        "regions": [{"bbox": [round(left / width, 4), round(top / height, 4), round((right - left) / width, 4),
                              round((bottom - top) / height, 4)], "label": label, "value": label, "row": 0}],
        "handmade": True,
    }, indent=2) + "\n")
    print(path)


def main() -> None:
    if "--write-fixtures" in sys.argv[1:]:
        write_fixtures()
        return
    for name in ("meds-kumar", "meds-iyer"):
        text = json.loads((PREPARED / f"{name}.json").read_text())["text"]
        medicines_photo(json.loads(text)["strips"], HERE / f"{name}.png")
    strip_photo(STRIP_AMLODIPINE, HERE / "strip-amlodipine.png")
    wound_photo(HERE / "wound-day3.png")
    wound_photo_day0(HERE / "wound-day0.png")


if __name__ == "__main__":
    main()

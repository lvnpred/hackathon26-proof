"""Make the project-made sample media in eval/media/ (the files SOURCES.md marks "recorded for this project").

Synthetic forms use the made-up patient "M. Fernandes, 52 F (synthetic)". Needs Pillow, ffmpeg and macOS `say`.
Run: .venv/bin/python eval/make_media.py
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

MEDIA = Path(__file__).parent / "media"
PATIENT = "M. Fernandes, 52 F (synthetic)"
SAMPLE = "SAMPLE — synthetic"


def _font(size: int) -> ImageFont.ImageFont:
    for path in ("/System/Library/Fonts/Helvetica.ttc", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _out(kind: str, name: str) -> Path:
    (MEDIA / kind).mkdir(parents=True, exist_ok=True)
    return MEDIA / kind / name


def wristband() -> None:
    image = Image.new("RGB", (1200, 700), (196, 164, 140))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((60, 220, 1140, 480), radius=40, fill=(245, 248, 250), outline=(120, 130, 140), width=4)
    pen.text((100, 245), SAMPLE, fill=(190, 30, 30), font=_font(36))
    pen.text((100, 300), PATIENT, fill=(20, 20, 20), font=_font(56))
    pen.text((100, 385), "MRN SYN-000123   DOB 01 Jan 1974", fill=(20, 20, 20), font=_font(40))
    for i in range(32):  # a drawn bar code, not a real one
        pen.rectangle((830 + i * 9, 390, 830 + i * 9 + (3 if i % 3 else 6), 455), fill=(10, 10, 10))
    image.save(_out("wristband", "wristband-synthetic.png"))


def _form(kind: str, name: str, title: str, lines: list[str]) -> None:
    image = Image.new("RGB", (1000, 1300), (252, 252, 250))
    pen = ImageDraw.Draw(image)
    pen.rectangle((30, 30, 970, 1270), outline=(120, 120, 120), width=3)
    pen.text((70, 60), SAMPLE, fill=(190, 30, 30), font=_font(34))
    pen.text((70, 120), title, fill=(20, 40, 90), font=_font(52))
    pen.text((70, 200), f"Patient: {PATIENT}", fill=(20, 20, 20), font=_font(36))
    y = 290
    for line in lines:
        pen.text((70, y), line, fill=(30, 30, 30), font=_font(32))
        y += 56
    pen.line((70, 1120, 470, 1120), fill=(30, 30, 30), width=2)
    pen.text((70, 1130), "Signature (synthetic)", fill=(90, 90, 90), font=_font(26))
    pen.line((560, 1120, 930, 1120), fill=(30, 30, 30), width=2)
    pen.text((560, 1130), "Date", fill=(90, 90, 90), font=_font(26))
    image.save(_out(kind, name))


def forms() -> None:
    _form("consent", "consent-form.png", "Consent for surgery", [
        "Procedure: Right inguinal hernia repair (mesh)",
        "Anaesthesia: Spinal with sedation",
        "I understand the benefits and risks explained to me:",
        "  - bleeding, infection, recurrence, chronic pain",
        "  - swab and instrument counts are done before closing",
        "I agree to blood transfusion if needed:   [x] Yes   [ ] No",
        "Site marked by surgeon:                   [x] Yes   [ ] No",
    ])
    _form("discharge", "discharge-card.png", "Discharge card", [
        "Admitted: 02 Nov   Discharged: 03 Nov",
        "Procedure: Right inguinal hernia repair",
        "Medicines: paracetamol 500 mg, 1 tablet every 6 hours",
        "           amlodipine 5 mg, 1 tablet every morning",
        "Wound: keep dry for 48 hours, then normal washing",
        "Return if: fever, bleeding, spreading redness, severe pain",
        "Review: surgical clinic in 7 days",
    ])


def swab_clip() -> None:
    """10 s at 10 fps: six swabs on a tray; one is lifted out and carried out of the right edge from 5 s to 7 s."""
    size, fps, seconds = (640, 360), 10, 10
    home = [(120 + (k % 3) * 120, 120 + (k // 3) * 90) for k in range(6)]
    with tempfile.TemporaryDirectory() as tmp:
        for n in range(fps * seconds):
            t = n / fps
            image = Image.new("RGB", size, (60, 110, 100))
            pen = ImageDraw.Draw(image)
            pen.rounded_rectangle((60, 60, 460, 330), radius=14, fill=(190, 196, 202), outline=(110, 116, 122), width=4)
            pen.text((20, 12), f"{SAMPLE}: swab tray", fill=(255, 255, 255), font=_font(20))
            for k, (x, y) in enumerate(home):
                if k == 5 and t >= 5:
                    x += int(min(1.0, (t - 5) / 2) * 420)  # swab 6 slides off the right edge by 7 s
                    y -= int(min(1.0, (t - 5) / 2) * 60)
                if x > size[0]:
                    continue
                pen.rounded_rectangle((x, y, x + 90, y + 56), radius=8, fill=(250, 250, 250), outline=(150, 150, 150))
                pen.line((x + 70, y + 28, x + 105, y + 28), fill=(40, 90, 200), width=3)  # radio-opaque thread
            image.save(Path(tmp) / f"f{n:03d}.png")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-framerate", str(fps), "-i", str(Path(tmp) / "f%03d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps), str(_out("swab-count", "swab-leaving-field.mp4"))],
            check=True,
        )


def speech() -> None:
    phrases = {
        "drug-lignocaine.wav": "lignocaine two percent, five ml, local infiltration",
        "swabs-opening-twenty.wav": "opening twenty swabs",
    }
    for name, text in phrases.items():
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "s.aiff"
            subprocess.run(["say", "-o", str(aiff), text], check=True)
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(aiff), "-ar", "16000", "-ac", "1",
                            str(_out("drug-phrases", name))], check=True)


def _tag(pen: ImageDraw.ImageDraw, xy: tuple[int, int], color=(190, 30, 30), size: int = 30) -> None:
    pen.text(xy, SAMPLE, fill=color, font=_font(size))


def medicine_bag() -> None:
    image = Image.new("RGB", (1200, 900), (205, 215, 222))
    pen = ImageDraw.Draw(image)
    pen.polygon([(260, 120), (940, 120), (990, 860), (210, 860)], fill=(214, 182, 140), outline=(150, 120, 80))
    pen.polygon([(260, 120), (940, 120), (930, 190), (270, 190)], fill=(196, 164, 124))
    pen.rectangle((300, 260, 900, 780), fill=(250, 250, 248), outline=(90, 90, 90), width=3)
    _tag(pen, (320, 275))
    pen.text((320, 325), "CITY PHARMACY - take-home medicines", fill=(20, 40, 90), font=_font(26))
    pen.text((320, 375), f"Patient: {PATIENT}", fill=(20, 20, 20), font=_font(30))
    meds = ["Paracetamol 500 mg - 1 tablet every 6 hours", "Amlodipine 5 mg - 1 tablet every morning",
            "Metoprolol 25 mg - 1 tablet twice a day"]
    for i, line in enumerate(meds):
        pen.text((320, 460 + i * 80), line, fill=(20, 20, 20), font=_font(28))
    pen.text((320, 720), "Dispensed 03 Nov  |  Qty: 7 days", fill=(70, 70, 70), font=_font(26))
    image.save(_out("medicine-bag", "medicine-bag-synthetic.png"))


def saline_setup() -> None:
    image = Image.new("RGB", (900, 1300), (226, 232, 236))
    pen = ImageDraw.Draw(image)
    pen.line((450, 20, 450, 110), fill=(80, 80, 80), width=10)  # hook
    pen.rounded_rectangle((220, 110, 680, 720), radius=60, fill=(236, 246, 250), outline=(100, 130, 150), width=5)
    pen.rectangle((250, 250, 650, 520), fill=(255, 255, 255), outline=(60, 90, 140), width=3)
    pen.text((270, 262), "0.9% Sodium Chloride", fill=(20, 40, 110), font=_font(34))
    pen.text((270, 320), "Injection IP", fill=(20, 40, 110), font=_font(36))
    pen.text((270, 380), "1000 ml", fill=(20, 20, 20), font=_font(80))
    pen.text((270, 480), "For intravenous use", fill=(60, 60, 60), font=_font(26))
    _tag(pen, (250, 150), size=34)
    for y in range(560, 700, 40):  # level marks
        pen.line((600, y, 650, y), fill=(120, 120, 120), width=3)
    pen.line((450, 720, 450, 830), fill=(150, 160, 170), width=8)  # giving set tube
    pen.rounded_rectangle((405, 830, 495, 990), radius=20, fill=(240, 248, 252), outline=(90, 110, 130), width=4)  # drip chamber
    pen.ellipse((438, 880, 462, 915), fill=(120, 170, 220))  # a drop
    pen.text((505, 890), "drip chamber", fill=(60, 60, 60), font=_font(26))
    pen.line((450, 990, 450, 1250), fill=(150, 160, 170), width=8)
    pen.rectangle((430, 1060, 470, 1110), fill=(40, 90, 200))  # roller clamp
    pen.text((480, 1070), "roller clamp", fill=(60, 60, 60), font=_font(26))
    image.save(_out("saline-setup", "saline-setup-synthetic.png"))


def swab_tray() -> None:
    image = Image.new("RGB", (1200, 800), (60, 110, 100))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle((60, 120, 1140, 760), radius=30, fill=(192, 198, 204), outline=(110, 116, 122), width=6)
    _tag(pen, (70, 30), color=(255, 255, 255), size=34)
    pen.text((70, 75), "Pack: 20 swabs (4 rows of 5)", fill=(255, 255, 255), font=_font(34))
    for k in range(20):
        x, y = 120 + (k % 5) * 200, 170 + (k // 5) * 140
        pen.rounded_rectangle((x, y, x + 160, y + 90), radius=12, fill=(252, 252, 252), outline=(150, 150, 150), width=2)
        pen.line((x + 20, y + 25, x + 140, y + 25), fill=(225, 225, 225), width=2)
        pen.line((x + 20, y + 55, x + 140, y + 55), fill=(225, 225, 225), width=2)
        pen.line((x + 120, y + 45, x + 180, y + 45), fill=(40, 90, 200), width=4)  # tape tag
    image.save(_out("swab-tray", "swab-tray-synthetic.png"))


def home_strips() -> None:
    image = Image.new("RGB", (1200, 800), (30, 30, 34))
    pen = ImageDraw.Draw(image)
    _tag(pen, (30, 15), color=(255, 120, 120))
    for i, (name, color) in enumerate((("Metoprolol 25 mg", (236, 206, 150)), ("Amlodipine 5 mg", (205, 214, 222)))):
        x0 = 70 + i * 580
        pen.rounded_rectangle((x0, 80, x0 + 500, 740), radius=24, fill=(186, 190, 196), outline=(120, 124, 130), width=4)
        for k in range(10):
            cx, cy = x0 + 125 + (k % 2) * 250, 170 + (k // 2) * 80
            pen.ellipse((cx - 38, cy - 30, cx + 38, cy + 30), fill=color, outline=(110, 110, 110), width=3)
        pen.text((x0 + 30, 585), name, fill=(20, 20, 20), font=_font(46))
        pen.text((x0 + 30, 650), "10 tablets   Exp 08/2027", fill=(50, 50, 50), font=_font(28))
    image.save(_out("home-medicines", "strips-metoprolol-amlodipine-synthetic.png"))


def wrong_photo() -> None:
    image = Image.new("RGB", (1000, 1300), (224, 232, 238))
    pen = ImageDraw.Draw(image)
    pen.rectangle((0, 760, 1000, 1300), fill=(205, 220, 232))  # sheet
    for x in (140, 360, 580, 800):  # bed-rail bars
        pen.rounded_rectangle((x, 160, x + 40, 900), radius=18, fill=(150, 156, 162), outline=(100, 104, 110), width=2)
    for y in (200, 860):
        pen.rounded_rectangle((100, y, 900, y + 50), radius=22, fill=(165, 170, 176), outline=(100, 104, 110), width=2)
    pen.ellipse((300, 1000, 700, 1150), fill=(222, 190, 160))  # bare wrist area, no band
    _tag(pen, (30, 30))
    pen.text((30, 80), "bed rail and bare wrist, no wristband", fill=(60, 60, 60), font=_font(28))
    image.save(_out("wrong-photo", "wrong-photo-bed-rail-synthetic.png"))


def monitor() -> None:
    image = Image.new("RGB", (1200, 800), (8, 10, 12))
    pen = ImageDraw.Draw(image)
    _tag(pen, (20, 12), color=(255, 120, 120))
    pen.text((900, 14), "Adult  Bed 3", fill=(180, 180, 180), font=_font(26))
    rows = [("HR", "bpm", "72", (60, 230, 90), 70), ("SpO2", "%", "98", (90, 200, 255), 250),
            ("NIBP", "mmHg", "118/76", (255, 90, 90), 430), ("RR", "/min", "16", (255, 255, 255), 610)]
    for label, unit, value, color, y in rows:
        pen.text((40, y), f"{label} {unit}", fill=color, font=_font(34))
        pen.text((300, y - 20), value, fill=color, font=_font(120))
        trace = [(640 + i * 10, y + 70 - int(40 * (1 if i % 9 == 4 else 0.15 * (i % 3)))) for i in range(50)]
        pen.line(trace, fill=color, width=3)
    image.save(_out("monitor", "monitor-synthetic.png"))


def make_all() -> None:
    """Write every project-made file (deterministic: the same bytes on each run, on the same machine)."""
    wristband()
    forms()
    swab_clip()
    speech()
    medicine_bag()
    saline_setup()
    swab_tray()
    home_strips()
    wrong_photo()
    monitor()


if __name__ == "__main__":
    make_all()

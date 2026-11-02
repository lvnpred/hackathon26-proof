"""Re-download the openly licensed stand-in photos listed in eval/media/SOURCES.md (they are git-ignored).

Not run by `make demo-check` and not needed by any test: the demo uses the files eval/make_media.py draws.
Each downloaded file is resized to at most 1600 px on the long side and re-saved as JPEG under 550 KB,
the changes SOURCES.md records. Needs network access, curl and Pillow.

Run: .venv/bin/python eval/fetch_media.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

from PIL import Image

MEDIA = Path(__file__).parent / "media"
COMMONS = "https://commons.wikimedia.org/wiki/File:"
API = "https://commons.wikimedia.org/w/api.php"
AGENT = "count-guard-hackathon/1.0 (naren.lingala@covasant.com)"


def sources() -> list[tuple[str, str]]:
    """(path, Commons title) for each SOURCES.md row whose URL is a Commons file page."""
    found = []
    for line in (MEDIA / "SOURCES.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[2].startswith(COMMONS):
            found.append((cells[0], urllib.parse.unquote(cells[2][len(COMMONS):])))
    return found


def thumb_url(title: str) -> str:
    out = subprocess.run(
        ["curl", "-sG", API, "-A", AGENT, "--data-urlencode", f"titles=File:{title}", "--data-urlencode", "action=query",
         "--data-urlencode", "prop=imageinfo", "--data-urlencode", "iiprop=url", "--data-urlencode", "iiurlwidth=1600",
         "--data-urlencode", "format=json"], capture_output=True, text=True, check=True).stdout
    return list(json.loads(out)["query"]["pages"].values())[0]["imageinfo"][0]["thumburl"]


def shrink(path: Path) -> None:
    image = Image.open(path).convert("RGB")
    image.thumbnail((1600, 1600))
    quality = 85
    while True:
        image.save(path, "JPEG", quality=quality, optimize=True)
        if path.stat().st_size <= 550_000 or quality <= 40:
            return
        quality -= 7


def main() -> int:
    for rel, title in sources():
        target = MEDIA / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["curl", "-sL", "-A", AGENT, "-o", str(target), thumb_url(title)], check=True)
        shrink(target)
        print(target)
    return 0


if __name__ == "__main__":
    sys.exit(main())

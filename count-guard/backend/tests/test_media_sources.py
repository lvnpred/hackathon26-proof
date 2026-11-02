"""Every sample media file has a source row and stays within the size limits (spec §10, U14)."""

from pathlib import Path

import pytest
from PIL import Image

MEDIA = Path(__file__).resolve().parents[2] / "eval" / "media"
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
CLIP_SUFFIXES = {".mp4"}
RECORDED = "recorded for this project"


def _files() -> list[Path]:
    return sorted(p for p in MEDIA.rglob("*") if p.is_file() and p.name != "SOURCES.md" and not p.name.startswith("."))


def _rows() -> dict[str, list[str]]:
    rows = {}
    for line in (MEDIA / "SOURCES.md").read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] not in ("Path",) and not cells[0].startswith("-"):
            assert len(cells) >= 6, f"malformed row: {line}"
            rows[cells[0]] = cells
    return rows


def test_every_media_file_has_a_source_row():
    rows, files = _rows(), _files()
    assert files, "no media files found"
    for path in files:
        rel = path.relative_to(MEDIA).as_posix()
        assert rel in rows, f"{rel} has no row in SOURCES.md"
        _, shows, url, licence, author = rows[rel][:5]
        assert rows[rel][-1].split(":")[0] in ("demo", "stand-in"), f"{rel}: role must be demo or stand-in"
        assert shows and licence and author, f"{rel}: row needs what, licence and author"
        if RECORDED in (url, licence):
            assert url == licence == RECORDED, f"{rel}: both URL and licence must say '{RECORDED}'"
        else:
            assert url.startswith("https://"), f"{rel}: needs the file's page URL"
    for rel in rows:
        assert (MEDIA / rel).is_file(), f"SOURCES.md lists {rel} but the file is missing"


def test_media_files_are_within_size_limits():
    for path in _files():
        size = path.stat().st_size
        if path.suffix in IMAGE_SUFFIXES:
            assert size <= 600 * 1024, f"{path.name} is over 600 KB"
            with Image.open(path) as image:
                assert max(image.size) <= 1600, f"{path.name} is over 1600 px"
        elif path.suffix in CLIP_SUFFIXES:
            assert size <= 8 * 1024 * 1024, f"{path.name} is over 8 MB"


def test_clips_are_at_most_twenty_seconds():
    import shutil
    import subprocess

    if shutil.which("ffprobe") is None:
        pytest.skip("ffprobe not installed")
    for path in _files():
        if path.suffix in CLIP_SUFFIXES | {".wav"}:
            out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                                 capture_output=True, text=True, check=True).stdout
            assert float(out) <= 20, f"{path.name} is longer than 20 s"

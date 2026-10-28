"""Secrets and real media stay out of git. Checks what git tracks, not the disk."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MEDIA = {".png", ".jpg", ".jpeg", ".mp4", ".mov", ".wav", ".db", ".pdf"}
KEY_LINE = re.compile(r"(MODEL_API_KEY|BASETEN_API_KEY)=\S")


def _tracked_files(root: Path) -> list[str]:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False
    )
    if out.returncode != 0:
        pytest.skip("not run inside a git checkout")
    return [p for p in out.stdout.decode("utf-8", "replace").split("\0") if p]


def hygiene_problems(root: Path, paths: list[str]) -> list[str]:
    """Every tracked .env, media/db file, or line that sets an API key."""
    problems = []
    for rel in paths:
        name = Path(rel).name
        if name == ".env" or (name.startswith(".env.") and name != ".env.example"):
            problems.append(f"{rel}: env file is tracked")
        if Path(rel).suffix.lower() in MEDIA:
            problems.append(f"{rel}: media or database file is tracked")
        file = root / rel
        if not file.is_file():
            continue
        text = file.read_bytes().decode("utf-8", "ignore")
        for n, line in enumerate(text.splitlines(), 1):
            if KEY_LINE.search(line):
                problems.append(f"{rel}:{n}: API key has a value")
    return problems


def test_no_env_keys_or_media_are_tracked():
    assert hygiene_problems(REPO, _tracked_files(REPO)) == []
    ignored = (REPO / ".gitignore").read_text().splitlines()
    assert ".env" in ignored
    assert "*.db" in ignored


def test_hygiene_check_catches_a_forced_env_media_and_key(tmp_path):
    key = "MODEL" + "_API_KEY="
    (tmp_path / ".env").write_text(key + "sk-live\n")
    (tmp_path / ".env.example").write_text(key + "\n")
    (tmp_path / "clip.MP4").write_bytes(b"\0")
    (tmp_path / "notes.md").write_text("BASETEN" + "_API_KEY=abc\n")
    problems = hygiene_problems(tmp_path, [".env", ".env.example", "clip.MP4", "notes.md"])
    assert problems == [
        ".env: env file is tracked",
        ".env:1: API key has a value",
        "clip.MP4: media or database file is tracked",
        "notes.md:1: API key has a value",
    ]

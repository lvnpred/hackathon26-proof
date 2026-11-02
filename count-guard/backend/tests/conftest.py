"""Shared test helpers."""

from __future__ import annotations

import importlib.util
import re
import zlib
from pathlib import Path

import pytest

# A stream dictionary, then "stream" and its line ending. The data is read by its /Length, not
# up to "endstream": compressed bytes that end in 0x0D would otherwise lose that byte.
_STREAM = re.compile(rb"<<((?:(?!<<|stream).)*?)>>\s*stream\r?\n", re.S)
_LENGTH = re.compile(rb"/Length\s+(\d+)(?!\s+\d+\s+R)")
_FALLBACK_END = re.compile(rb"\r?\nendstream")
_LITERAL = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _unescape(literal: bytes) -> bytes:
    def swap(match: re.Match) -> bytes:
        token = match.group(1)
        if token[:1].isdigit():
            return bytes([int(token, 8) & 0xFF])
        return _ESCAPES.get(token, token)

    return re.sub(rb"\\([0-7]{1,3}|.)", swap, literal[1:-1], flags=re.S)


def pdf_text(raw: bytes) -> str:
    """Return the text drawn on every page of a PDF, one string per line.

    fpdf2 FlateDecode-compresses its content streams, so searching the raw
    bytes finds nothing. Inflate each stream and read its literal strings.
    """
    lines: list[str] = []
    for match in _STREAM.finditer(raw):
        start = match.end()
        length = _LENGTH.search(match.group(1))
        if length:
            data = raw[start : start + int(length.group(1))]
        else:  # an indirect /Length: fall back to the end marker
            end = _FALLBACK_END.search(raw, start)
            data = raw[start : end.start() if end else len(raw)]
        try:
            content = zlib.decompress(data)
        except zlib.error:
            content = data
        for literal in _LITERAL.findall(content):
            lines.append(_unescape(literal).decode("latin-1"))
    return "\n".join(lines)


@pytest.fixture(scope="session", autouse=True)
def project_made_media():
    """Write the project-made sample media (git-ignored) so tests that read them pass on a clean checkout."""
    path = Path(__file__).resolve().parents[2] / "eval" / "make_media.py"
    spec = importlib.util.spec_from_file_location("make_media", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.make_all()

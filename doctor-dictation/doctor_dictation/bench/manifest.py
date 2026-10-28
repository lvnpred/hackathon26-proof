"""Load and validate the benchmark manifest (a JSON list of clips)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


class ManifestError(ValueError):
    """str(e) names the offending entry."""


@dataclass(frozen=True)
class Clip:
    audio: Path
    reference: str
    seconds: float | None = None


def _clip(i: int, raw: object, base: Path) -> Clip:
    if not isinstance(raw, dict):
        raise ManifestError(f"entry {i}: expected an object, got {type(raw).__name__}")
    audio, ref, secs = raw.get("audio"), raw.get("reference"), raw.get("seconds")
    if not isinstance(audio, str) or not audio.strip():
        raise ManifestError(f"entry {i}: 'audio' must be a non-empty string path")
    where = f"entry {i} ({audio})"
    if not isinstance(ref, str) or not ref.strip():
        raise ManifestError(f"{where}: 'reference' must be non-empty text")
    path = Path(audio) if Path(audio).is_absolute() else base / audio
    if not path.is_file():
        raise ManifestError(f"{where}: audio file not found: {path}")
    if secs is not None and (isinstance(secs, bool) or not isinstance(secs, (int, float)) or secs <= 0):
        raise ManifestError(f"{where}: 'seconds' must be a positive number")
    return Clip(path, ref.strip(), None if secs is None else float(secs))


def load_manifest(path: str | Path) -> list[Clip]:
    """Relative audio paths resolve against the manifest's own folder."""
    manifest = Path(path)
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ManifestError(f"manifest not found: {manifest}") from None
    except (OSError, ValueError) as exc:
        raise ManifestError(f"manifest is not readable JSON: {manifest} ({exc})") from None
    if not isinstance(data, list) or not data:
        raise ManifestError("manifest must be a non-empty JSON list of clips")
    base = manifest.resolve().parent
    return [_clip(i, raw, base) for i, raw in enumerate(data)]

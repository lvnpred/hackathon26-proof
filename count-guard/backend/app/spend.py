"""What one real clip will cost on SAM 3.1, before any call. Does not spend credits.

Rates from https://dev.meta.ai/docs/pricing-rate-limits as quoted on 29 Oct 2026:
SAM 3.1 video is $0.20 per 1,000 frames, with a 50-frame minimum per request.
One request is one concept, so the frames are billed once per concept.
Muse Spark video token counts are not published; the baseline cost is printed as unknown.

    python -m app.spend clip.mp4 [concept ...]
"""

from __future__ import annotations

import math
import subprocess
import sys
from pathlib import Path

from app.config import SAM_CONCEPTS, get_settings

SAM_VIDEO_USD_PER_1000_FRAMES = 0.20
SAM_MIN_FRAMES_PER_REQUEST = 50


def sam_video_cost(duration_s: float, fps: int, concepts: int) -> dict:
    """Frames SAM 3.1 sees after the pipeline resamples to fps, and the billed dollars."""
    if duration_s <= 0 or fps <= 0 or concepts <= 0:
        raise ValueError("duration, fps and concept count must be positive")
    frames = math.ceil(duration_s * fps)
    billed = max(frames, SAM_MIN_FRAMES_PER_REQUEST) * concepts
    return {
        "frames": frames,
        "requests": concepts,
        "billed_frames": billed,
        "usd": round(billed * SAM_VIDEO_USD_PER_1000_FRAMES / 1000, 4),
    }


def clip_seconds(path: Path) -> float:
    try:
        completed = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(f"ffprobe timed out on {path}")
    if completed.returncode != 0 or not completed.stdout.strip():
        raise SystemExit(f"ffprobe could not read {path}")
    return float(completed.stdout.strip())


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    path = Path(argv[0])
    if not path.is_file():
        raise SystemExit(f"No clip at {path}")
    concepts = argv[1:] or list(SAM_CONCEPTS)
    settings = get_settings()
    seconds = clip_seconds(path)
    cost = sam_video_cost(seconds, settings.sam_fps, len(concepts))
    print("Count Guard spend check. No model call is made.")
    print(f"Clip: {path.name}, {seconds:.1f} s, resampled to {settings.sam_fps} fps = {cost['frames']} frames")
    print(f"SAM 3.1: {cost['requests']} requests ({', '.join(concepts)})")
    print(f"  Billed frames: {cost['billed_frames']} (50-frame minimum per request)")
    print(f"  Estimated: ${cost['usd']:.4f}")
    print("Muse Spark baseline: video token count is not published. Measure it on the first run.")
    print(f"Key configured: {settings.sam_configured}. Set a spend limit on the Meta billing page first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

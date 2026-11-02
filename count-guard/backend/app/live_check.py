"""make live-check (spec §11 A9): one real call per §6.7 model on the synthetic demo media, run by hand with a key.

    python -m app.live_check

Models: Muse Voice Transcribe (a drug phrase), Spark 1.3 text (card wording), Spark 1.3 vision (a proof photo),
SAM 3.1 (one concept on the swab tray photo). Each call's result goes to eval/live/<YYYY-MM-DD>/<model>.json, which
is git-ignored; only synthetic media is sent. The key is never printed or written. Refuses to run without a key.
"""
from __future__ import annotations

import base64
import json
import sys
import time
from datetime import date
from pathlib import Path

from app.adapters.sam import SamAdapter
from app.adapters.spark import SparkAdapter
from app.adapters.voice import VoiceAdapter
from app.config import get_settings
from app.spend import clip_seconds, sam_video_cost

EVAL = Path(__file__).resolve().parents[2] / "eval"
MODELS = ("voice", "spark-text", "spark-vision", "sam")
MEDIA = {
    "drug": "media/drug-phrases/drug-lignocaine.wav",
    "wristband": "media/wristband/wristband-synthetic.png",
    "tray": "media/swab-tray/swab-tray-synthetic.png",
}
CLIPS = ("media/swab-count/swab-leaving-field.mp4",)
ADAPTERS = {"voice": VoiceAdapter, "spark": SparkAdapter, "sam": SamAdapter}
WORDING_PROMPT = (
    "Synthetic data, research demo. Write one short plain sentence for a theatre nurse that states these numbers "
    "side by side, with no advice: synthetic patient M. Fernandes, BP 86/50, down 28% in 4 min, HR 76 not rising."
)
SAM_CONCEPT = "gauze swab"


class NoKey(RuntimeError):
    """No Meta key: live-check spends nothing and writes nothing."""


def out_dir_for(day: str) -> Path:
    return EVAL / "live" / day


def _png_url(raw: bytes) -> str:
    return f"data:image/png;base64,{base64.b64encode(raw).decode()}"


def _calls(settings, adapters: dict, root: Path) -> dict:
    """model -> a no-argument call returning what is saved as its artifact."""
    path = {name: root / rel for name, rel in MEDIA.items()}
    make = lambda name: adapters[name](settings)  # noqa: E731 - built per call, so a failed constructor is that row's failure
    return {
        "voice": lambda: {"segments": make("voice").transcribe(path["drug"], 0, "audio/wav")},
        "spark-text": lambda: {"text": make("spark").write(WORDING_PROMPT)},
        "spark-vision": lambda: make("spark").check_photo(path["wristband"].read_bytes(), "image/png", "a patient wristband"),
        "sam": lambda: {"concept": SAM_CONCEPT,
                        "records": make("sam").segment_images([_png_url(path["tray"].read_bytes())], [SAM_CONCEPT])},
    }


def run(settings, out_dir: Path, *, adapters: dict | None = None, root: Path = EVAL) -> list[dict]:
    """One call per model; a failure is recorded as its row (ok False), never raised. Rows: model, ok, seconds, artifact."""
    if not settings.meta_api_key:
        raise NoKey("No Meta key (MODEL_API_KEY or META_API_KEY). live-check made no call.")
    calls = _calls(settings, {**ADAPTERS, **(adapters or {})}, root)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for model in MODELS:
        start = time.monotonic()
        try:
            result, ok = calls[model](), True
        except Exception as exc:  # noqa: BLE001 - one model's failure is a row, the others still run
            result, ok = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}, False
        seconds = round(time.monotonic() - start, 2)
        artifact = f"{model}.json"
        (out_dir / artifact).write_text(json.dumps({"model": model, "ok": ok, "seconds": seconds, "result": result}, indent=2, default=str))
        rows.append({"model": model, "ok": ok, "seconds": seconds, "artifact": artifact})
    return rows


def cost_lines(clips: list[Path], fps: int) -> list[str]:
    """The SAM 3.1 video bill for each demo clip, as `make cost` prints it. No call."""
    lines = []
    for clip in clips:
        cost = sam_video_cost(clip_seconds(clip), fps, 1)
        lines.append(f"make cost CLIP={clip} -> {cost['frames']} frames per concept, about ${cost['usd']:.4f} per concept")
    return lines


def main(argv: list[str]) -> int:
    settings = get_settings()
    out = out_dir_for(date.today().isoformat())
    try:
        rows = run(settings, out)
    except NoKey as exc:
        print(exc)
        return 2
    print(f"live-check: artifacts in {out} (git-ignored, synthetic media only)")
    for row in rows:
        print(f"  {row['model']:<13} {'ok  ' if row['ok'] else 'FAIL'} {row['seconds']:>6.2f} s  {row['artifact']}")
    for line in cost_lines([EVAL / rel for rel in CLIPS], settings.sam_fps):
        print(line)
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

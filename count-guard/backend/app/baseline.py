"""Muse Spark alone: the baseline the count rules are measured against.

Muse Spark 1.3 watches the same clip with no SAM 3.1 tracks and no rules, and returns
a count per item. The answer is compared with eval/ground_truth/clipN.json. If Muse Spark
alone catches the planted sponge, the tracker has not earned its place; print that too.

Spends credits only with --spend. Without it, prints the plan and stops.

    python -m app.baseline clip.mp4 eval/ground_truth/clip2.json [--spend]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from app.adapters.sam import upload_video
from app.adapters.spark import SparkAdapter
from app.config import Settings, get_settings

COUNT_FIELDS = ("opened", "bucket", "tray", "unaccounted")


def baseline_prompt(item_types: list[str]) -> str:
    names = ", ".join(item_types)
    return (
        "This video shows a surgical count on a prop tray. Zones: tray, field, bucket. "
        f"For each of these item types: {names}, count how many were opened, how many ended "
        "in the bucket, how many are still on the tray, and how many are unaccounted for. "
        'Reply with JSON only: {"lap sponge": {"opened": 0, "bucket": 0, "tray": 0, "unaccounted": 0}}. '
        "Use whole numbers. Do not give medical advice."
    )


def parse_baseline(text: str) -> dict[str, dict[str, int]]:
    """Model text to {item: {field: int}}. Anything unreadable becomes an empty answer, not a guess."""
    match = re.search(r"\{.*\}", text or "", re.S)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    answer: dict[str, dict[str, int]] = {}
    for item, counts in payload.items() if isinstance(payload, dict) else []:
        if not isinstance(counts, dict):
            continue
        row = {}
        for field in COUNT_FIELDS:
            value = counts.get(field)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[field] = int(value)
        answer[str(item).strip().lower()] = row
    return answer


def score_baseline(answer: dict[str, dict[str, int]], truth: dict) -> dict:
    """Score Muse Spark's answer against one ground-truth clip.

    Returns {"caught": bool, "ledger_exact": bool, "false_alarm": bool}.
    truth["ledger"] holds the expected counts, e.g. {"lap sponge": {"opened": 10, "bucket": 9, ...}}.
    truth["rules"] lists the planted discrepancies; it is empty on a clean clip.
    """
    # TODO(you): decide what counts as Muse Spark "catching" the planted discrepancy.
    raise NotImplementedError("score_baseline: see the TODO above")


def run_baseline(settings: Settings, video: Path, truth: dict) -> dict:
    file_id = upload_video(settings, video)
    text = SparkAdapter(settings).watch(baseline_prompt(truth["item_types"]), file_id)
    answer = parse_baseline(text)
    return {"clip": truth["clip"], "raw": text, "answer": answer, "score": score_baseline(answer, truth)}


def main(argv: list[str]) -> int:
    spend = "--spend" in argv
    args = [arg for arg in argv if arg != "--spend"]
    if len(args) != 2:
        print(__doc__)
        return 2
    video, truth_path = Path(args[0]), Path(args[1])
    if not video.is_file() or not truth_path.is_file():
        raise SystemExit(f"Need a clip and a ground-truth file: {video}, {truth_path}")
    truth = json.loads(truth_path.read_text(encoding="utf-8"))
    settings = get_settings()
    print(f"Baseline: {settings.spark_model} alone on {video.name}, against {truth_path.name}.")
    print(f"Planted: {truth['rules'] or 'none'}")
    if not spend:
        print("Dry run. Add --spend to upload the clip and call Muse Spark.")
        return 0
    if not settings.spark_configured:
        raise SystemExit("MODEL_API_KEY is not set. Nothing was called.")
    result = run_baseline(settings, video, truth)
    print(f"Muse Spark answer: {json.dumps(result['answer'])}")
    print(f"Score: {json.dumps(result['score'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

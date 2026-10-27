"""Replay the five scripted clips and print the measured table.

This does not measure SAM 3.1. Perception is scripted on purpose until a
recorded tray clip exists. Misses are printed, not hidden.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.agent.reconciler import explain_case  # noqa: E402
from app.config import Settings  # noqa: E402
from app.engine import Engine, id_switch_count  # noqa: E402
from app.report.count_sheet import write_count_sheet  # noqa: E402
from app.scenarios import eval_clips  # noqa: E402
from app.store import Store  # noqa: E402


def settings(tmp: Path) -> Settings:
    return Settings(
        data_dir=tmp,
        meta_api_key="",
        meta_base="https://api.meta.ai/v1",
        sam_model="sam-3.1",
        voice_model="muse-voice-transcribe-1.0",
        spark_model="muse-spark-1.3",
        baseten_api_key="",
        spark_open_base="https://inference.baseten.co/v1",
        spark_open_model="meta-models/muse-spark-open-1026",
        low_confidence=0.45,
        unannounced_window_ms=30_000,
        lost_after_frames=4,
        sam_fps=2,
    )


def main() -> int:
    tmp = ROOT / "data" / "eval"
    if tmp.exists():
        for child in sorted(tmp.glob("**/*"), reverse=True):
            if child.is_file():
                child.unlink()
    app = Engine(Store(tmp / "eval.db"), settings(tmp))
    planted = {("R3", "lap sponge"), ("R2", "lap sponge"), ("R4", "gauze swab")}
    caught = set()
    rows = []
    report_ms = None
    for scenario in eval_clips():
        case = app.create_case(scenario["name"], scenario["item_types"])
        started = time.perf_counter()
        result = app.replay(case["id"], scenario)
        pipeline_ms = (time.perf_counter() - started) * 1000
        expected = set(map(tuple, scenario["expect"]["rules"]))
        observed = {
            (row["rule_id"], row["item_type"])
            for row in result["discrepancies"]
            if row["status"] == "open"
        }
        missed = expected - observed
        false = observed - expected
        caught |= observed & planted
        ledger_ok = True
        got = {row["item_type"]: row for row in result["ledger"]}
        for item_type, counts in scenario["expect"]["ledger"].items():
            for key, value in counts.items():
                if got.get(item_type, {}).get(key) != value:
                    ledger_ok = False
        if scenario["name"] == "clip1":
            report_started = time.perf_counter()
            decision = app.gate(case["id"])
            explained = explain_case(app.store, app.settings, case["id"])
            write_count_sheet(
                tmp / "clip1-count-sheet.pdf",
                case=app.store.get_case(case["id"]),
                ledger=decision["ledger"],
                discrepancies=result["discrepancies"],
                narrative=explained["narrative"],
                model=explained["model"],
                trace=explained["trace"],
            )
            report_ms = (time.perf_counter() - report_started) * 1000
        rows.append(
            {
                "clip": scenario["name"],
                "headline": scenario["expect"]["headline"],
                "observed": ", ".join(f"{rule}:{item}" for rule, item in sorted(observed)) or "none",
                "missed": ", ".join(f"{rule}:{item}" for rule, item in sorted(missed)) or "none",
                "false": len(false),
                "ledger": "yes" if ledger_ok else "NO",
                "switches": id_switch_count(app.store.events(case["id"])),
                "gate": result["gate"]["status"],
                "ms": round(pipeline_ms, 1),
            }
        )
    print("Scripted perception. SAM 3.1 was not called.")
    print()
    print("| Clip | Headline | Observed | Missed | False alarms | Ledger exact | ID switches | Gate | Pipeline ms |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for row in rows:
        print(
            f"| {row['clip']} | {row['headline']} | {row['observed']} | {row['missed']} | "
            f"{row['false']} | {row['ledger']} | {row['switches']} | {row['gate']} | {row['ms']} |"
        )
    print()
    print(f"Planted discrepancies caught: {len(caught)} of {len(planted)} ({', '.join(sorted(f'{a}:{b}' for a, b in caught)) or 'none'})")
    print(f"Clip 1 report ready in {report_ms:.1f} ms" if report_ms is not None else "Clip 1 report was not timed")
    failed = [row for row in rows if row["missed"] != "none" or row["ledger"] != "yes" or row["false"]]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
